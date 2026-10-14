"""SQLite do Vestiário: guarda a história que o save vai apagando."""
import sqlite3
from datetime import datetime
from pathlib import Path

from .leitor import MOEDA, Save

ESQUEMA = """
CREATE TABLE IF NOT EXISTS carreira(
  id INTEGER PRIMARY KEY, slot TEXT NOT NULL, nome TEXT NOT NULL, UNIQUE(slot, nome));
CREATE TABLE IF NOT EXISTS sincronizacao(
  id INTEGER PRIMARY KEY, carreira_id INTEGER NOT NULL REFERENCES carreira,
  em TEXT NOT NULL, data_jogo TEXT NOT NULL, clube_idx INTEGER NOT NULL, clube_nome TEXT NOT NULL,
  orcamento INTEGER);
CREATE TABLE IF NOT EXISTS elenco(
  sincronizacao_id INTEGER NOT NULL REFERENCES sincronizacao, player_id INTEGER NOT NULL);
-- clube de cada jogador do mundo naquela sincronização (origem e destino das transferências)
CREATE TABLE IF NOT EXISTS vinculo(
  sincronizacao_id INTEGER NOT NULL REFERENCES sincronizacao, player_id INTEGER NOT NULL, time_idx INTEGER NOT NULL,
  PRIMARY KEY(sincronizacao_id, player_id));
-- livro de transferências do clube; o save zera o livro, o banco guarda cada negócio com a 1ª data do jogo em que apareceu
CREATE TABLE IF NOT EXISTS negocio(
  carreira_id INTEGER NOT NULL REFERENCES carreira, player_id INTEGER NOT NULL, tipo INTEGER NOT NULL,
  valor INTEGER NOT NULL, data_jogo TEXT NOT NULL, PRIMARY KEY(carreira_id, player_id, tipo, valor));
-- contratos do elenco do clube em cada sincronização (dinheiro em unidades do save, × MOEDA = R$)
CREATE TABLE IF NOT EXISTS contrato(
  sincronizacao_id INTEGER NOT NULL REFERENCES sincronizacao, player_id INTEGER NOT NULL,
  salario_anual INTEGER NOT NULL, multa INTEGER NOT NULL, fim TEXT NOT NULL, PRIMARY KEY(sincronizacao_id, player_id));
CREATE TABLE IF NOT EXISTS time(
  carreira_id INTEGER NOT NULL REFERENCES carreira, idx INTEGER NOT NULL, nome TEXT NOT NULL,
  pes_id INTEGER,
  PRIMARY KEY(carreira_id, idx));
CREATE TABLE IF NOT EXISTS cor_time(pes_id INTEGER PRIMARY KEY, cores TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS jogador(player_id INTEGER PRIMARY KEY, nome TEXT NOT NULL, posicao INTEGER);
CREATE TABLE IF NOT EXISTS partida(
  id INTEGER PRIMARY KEY, carreira_id INTEGER NOT NULL REFERENCES carreira, data TEXT NOT NULL,
  mandante_idx INTEGER NOT NULL, visitante_idx INTEGER NOT NULL,
  gols_mandante INTEGER NOT NULL, gols_visitante INTEGER NOT NULL,
  penaltis_mandante INTEGER NOT NULL, penaltis_visitante INTEGER NOT NULL,
  disputada INTEGER NOT NULL,
  UNIQUE(carreira_id, data, mandante_idx, visitante_idx));
CREATE TABLE IF NOT EXISTS escalacao(
  partida_id INTEGER NOT NULL REFERENCES partida ON DELETE CASCADE, player_id INTEGER NOT NULL,
  lado INTEGER NOT NULL, gols INTEGER NOT NULL, assistencias INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS escalacao_partida ON escalacao(partida_id);
CREATE TABLE IF NOT EXISTS arquivo(caminho TEXT PRIMARY KEY, tamanho INTEGER NOT NULL, mtime REAL NOT NULL);
"""


def conectar(caminho: Path | str) -> sqlite3.Connection:
    if str(caminho) != ":memory:":
        Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(caminho)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    tabelas = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    con.executescript(ESQUEMA)
    if tabelas and not {"vinculo", "negocio", "contrato"} <= tabelas:
        with con:  # banco anterior a origem e destino, valores ou contratos: relê os saves que ainda existem
            con.execute("DELETE FROM arquivo")
    if "posicao" not in {r[1] for r in con.execute("PRAGMA table_info(jogador)")}:
        con.execute("ALTER TABLE jogador ADD COLUMN posicao INTEGER")  # preenchida na próxima sincronização
    if "orcamento" not in {r[1] for r in con.execute("PRAGMA table_info(sincronizacao)")}:
        with con:  # banco anterior ao orçamento: relê os saves para preenchê-lo
            con.execute("ALTER TABLE sincronizacao ADD COLUMN orcamento INTEGER")
            con.execute("DELETE FROM arquivo")
    if "pes_id" not in {r[1] for r in con.execute("PRAGMA table_info(time)")}:
        with con:  # banco anterior aos escudos: ganha a coluna e relê todos os saves para preenchê-la
            con.execute("ALTER TABLE time ADD COLUMN pes_id INTEGER")
            con.execute("DELETE FROM arquivo")
    return con


def gravar_nomes(con: sqlite3.Connection, nomes: dict[int, str], posicoes: dict[int, int] | None = None) -> None:
    """Nomes e posições do Player.bin; sem posições, a que já estava gravada fica."""
    posicoes = posicoes or {}
    with con:
        con.executemany("INSERT INTO jogador VALUES(?, ?, ?) ON CONFLICT DO UPDATE "
                        "SET nome = excluded.nome, posicao = coalesce(excluded.posicao, posicao)",
                        ((pid, nome, posicoes.get(pid)) for pid, nome in nomes.items()))


def gravar_cores(con: sqlite3.Connection, cores: dict[int, list[str]]) -> None:
    with con:
        con.executemany("INSERT INTO cor_time VALUES(?, ?) ON CONFLICT DO UPDATE SET cores = excluded.cores",
                        ((tid, " ".join(c)) for tid, c in cores.items()))


def tem_cores(con: sqlite3.Connection) -> bool:
    return con.execute("SELECT 1 FROM cor_time LIMIT 1").fetchone() is not None


def arquivo_visto(con: sqlite3.Connection, caminho: str, tamanho: int, mtime: float) -> bool:
    return con.execute("SELECT 1 FROM arquivo WHERE caminho = ? AND tamanho = ? AND mtime = ?",
                       (caminho, tamanho, mtime)).fetchone() is not None


def marcar_arquivo(con: sqlite3.Connection, caminho: str, tamanho: int, mtime: float) -> None:
    with con:
        con.execute("INSERT INTO arquivo VALUES(?, ?, ?) ON CONFLICT DO UPDATE "
                    "SET tamanho = excluded.tamanho, mtime = excluded.mtime", (caminho, tamanho, mtime))


def gravar(con: sqlite3.Connection, slot: str, save: Save, em: datetime) -> dict:
    """Grava um save numa transação. Partida disputada nunca regride; jogos futuros vêm só do save mais recente."""
    with con:
        # ponytail: carreira = (slot, nome do save); uma ML nova no mesmo slot com o mesmo nome padrão se mistura com a antiga (a trava de times logo abaixo quase nunca pega isso, porque o patch é o mesmo). Achar um id de carreira no header.dat se virar problema.
        cid = con.execute("INSERT INTO carreira(slot, nome) VALUES(?, ?) ON CONFLICT DO UPDATE "
                          "SET nome = excluded.nome RETURNING id", (slot, save.nome)).fetchone()[0]
        guardados = {r[0]: r[1] for r in con.execute("SELECT idx, nome FROM time WHERE carreira_id = ?", (cid,))}
        diferente = next((i for i, n in enumerate(save.times) if guardados.get(i, n) != n), None)
        if diferente is not None:
            raise ValueError(f"tabela de times mudou no índice {diferente}: "
                             f"{guardados[diferente]!r} virou {save.times[diferente]!r}")
        ultima = con.execute("SELECT max(data_jogo) FROM sincronizacao WHERE carreira_id = ?", (cid,)).fetchone()[0]
        mais_recente = ultima is None or save.data_jogo.isoformat() >= ultima
        sid = con.execute(
            "INSERT INTO sincronizacao(carreira_id, em, data_jogo, clube_idx, clube_nome, orcamento) "
            "VALUES(?, ?, ?, ?, ?, ?) RETURNING id",
            (cid, em.isoformat(timespec="seconds"), save.data_jogo.isoformat(), save.clube_idx, save.clube,
             save.orcamento),
        ).fetchone()[0]
        con.executemany("INSERT INTO elenco VALUES(?, ?)", [(sid, p) for p in save.elenco])
        con.executemany("INSERT INTO contrato VALUES(?, ?, ?, ?, ?)",
                        [(sid, p, c.salario_anual, c.multa, c.fim.isoformat()) for p, c in save.contratos.items()])
        # só a sincronização mais recente de cada data do jogo guarda os vínculos (são ~18 mil por save)
        con.execute("DELETE FROM vinculo WHERE sincronizacao_id IN (SELECT id FROM sincronizacao "
                    "WHERE carreira_id = ? AND data_jogo = ? AND id <> ?)", (cid, save.data_jogo.isoformat(), sid))
        clube_de = {}
        for idx, pids in enumerate(save.elencos):
            for pid in pids:
                clube_de.setdefault(pid, idx)  # na tabela de times os clubes vêm antes das seleções
        con.executemany("INSERT INTO vinculo VALUES(?, ?, ?)", [(sid, p, i) for p, i in clube_de.items()])
        con.executemany("INSERT INTO negocio VALUES(?, ?, ?, ?, ?) ON CONFLICT DO UPDATE "
                        "SET data_jogo = min(data_jogo, excluded.data_jogo)",
                        [(cid, n.player_id, n.tipo, n.valor, save.data_jogo.isoformat()) for n in save.negocios])
        if mais_recente:
            con.executemany("INSERT INTO time VALUES(?, ?, ?, ?) ON CONFLICT DO UPDATE "
                            "SET nome = excluded.nome, pes_id = excluded.pes_id",
                            [(cid, i, n, save.ids[i] if save.ids else None) for i, n in enumerate(save.times)])

        existentes = {(r[0], r[1], r[2]): r[3] for r in con.execute(
            "SELECT data, mandante_idx, visitante_idx, disputada FROM partida WHERE carreira_id = ?", (cid,))}
        if mais_recente:
            con.execute("DELETE FROM partida WHERE carreira_id = ? AND disputada = 0", (cid,))

        novas = atualizadas = 0
        for p in save.partidas:
            chave = (p.data.isoformat(), p.mandante, p.visitante)
            antes = existentes.get(chave)
            if antes == 1 or (not p.disputada and not mais_recente):
                continue
            if p.disputada and antes == 0:
                atualizadas += 1
            elif p.disputada and antes is None:
                novas += 1
            pid = con.execute(
                "INSERT INTO partida(carreira_id, data, mandante_idx, visitante_idx, gols_mandante, gols_visitante,"
                " penaltis_mandante, penaltis_visitante, disputada) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(carreira_id, data, mandante_idx, visitante_idx) DO UPDATE SET"
                " gols_mandante = excluded.gols_mandante, gols_visitante = excluded.gols_visitante,"
                " penaltis_mandante = excluded.penaltis_mandante, penaltis_visitante = excluded.penaltis_visitante,"
                " disputada = excluded.disputada RETURNING id",
                (cid, *chave, *p.gols, *p.penaltis, int(p.disputada)),
            ).fetchone()[0]
            con.execute("DELETE FROM escalacao WHERE partida_id = ?", (pid,))
            con.executemany("INSERT INTO escalacao VALUES(?, ?, ?, ?, ?)",
                            [(pid, a.player_id, a.lado, a.gols, a.assistencias) for a in p.escalacao])
        return {"carreira_id": cid, "novas": novas, "atualizadas": atualizadas}


# --- consultas para as telas -------------------------------------------------

def _ultima(con: sqlite3.Connection, cid: int) -> sqlite3.Row | None:
    return con.execute("SELECT * FROM sincronizacao WHERE carreira_id = ? ORDER BY data_jogo DESC, id DESC LIMIT 1",
                       (cid,)).fetchone()


def carreiras(con: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in con.execute(
        "SELECT c.id, c.slot, c.nome, s.clube_nome, s.data_jogo, s.em, t.pes_id AS escudo FROM carreira c "
        "JOIN sincronizacao s ON s.id = (SELECT id FROM sincronizacao WHERE carreira_id = c.id "
        "ORDER BY data_jogo DESC, id DESC LIMIT 1) "
        "LEFT JOIN time t ON t.carreira_id = c.id AND t.idx = s.clube_idx ORDER BY s.em DESC, c.id")]


def carreira(con: sqlite3.Connection, cid: int) -> dict | None:
    s = _ultima(con, cid)
    if s is None:
        return None
    t = con.execute("SELECT t.pes_id, c.cores FROM time t LEFT JOIN cor_time c USING(pes_id) "
                    "WHERE t.carreira_id = ? AND t.idx = ?", (cid, s["clube_idx"])).fetchone()
    return {"id": cid, "clube_nome": s["clube_nome"], "clube_idx": s["clube_idx"], "data_jogo": s["data_jogo"],
            "escudo": t["pes_id"] if t else None, "cores": t["cores"].split() if t and t["cores"] else [],
            "orcamento": s["orcamento"] * MOEDA if s["orcamento"] is not None else None}


def escudos(con: sqlite3.Connection) -> set[int]:
    """Ids PES de todos os times conhecidos, para extrair os escudos."""
    return {r[0] for r in con.execute("SELECT DISTINCT pes_id FROM time WHERE pes_id IS NOT NULL")}


# ponytail: temporada = ano civil da partida (certo no Brasileirão, errado em ligas europeias);
# trocar quando o campo de competição for decodificado.
def temporadas(con: sqlite3.Connection, cid: int) -> list[int]:
    clube = _ultima(con, cid)["clube_idx"]
    return [int(r[0]) for r in con.execute(
        "SELECT DISTINCT substr(data, 1, 4) FROM partida "
        "WHERE carreira_id = ? AND ? IN (mandante_idx, visitante_idx) ORDER BY 1 DESC", (cid, clube))]


_PARTIDA = (
    "SELECT p.id, p.data, p.mandante_idx, tm.nome AS mandante, tm.pes_id AS mandante_escudo,"
    " p.visitante_idx, tv.nome AS visitante, tv.pes_id AS visitante_escudo,"
    " p.gols_mandante, p.gols_visitante, p.penaltis_mandante, p.penaltis_visitante, p.disputada "
    "FROM partida p "
    "LEFT JOIN time tm ON tm.carreira_id = p.carreira_id AND tm.idx = p.mandante_idx "
    "LEFT JOIN time tv ON tv.carreira_id = p.carreira_id AND tv.idx = p.visitante_idx "
)


def partidas(con: sqlite3.Connection, cid: int, ano: int | None = None) -> list[dict]:
    """Jogos do clube na temporada (ou de todas, sem ano), em ordem de data."""
    clube = _ultima(con, cid)["clube_idx"]
    sql = _PARTIDA + "WHERE p.carreira_id = :cid AND :clube IN (p.mandante_idx, p.visitante_idx) "
    if ano is not None:
        sql += "AND substr(p.data, 1, 4) = :ano "
    return [dict(r) for r in con.execute(sql + "ORDER BY p.data", {"cid": cid, "clube": clube, "ano": str(ano)})]


def partida(con: sqlite3.Connection, cid: int, pid: int) -> dict | None:
    """Súmula: o jogo com as duas escalações, na ordem em que o save as guarda."""
    p = con.execute(_PARTIDA + "WHERE p.carreira_id = ? AND p.id = ?", (cid, pid)).fetchone()
    if p is None:
        return None
    return {**dict(p), "escalacao": [dict(r) for r in con.execute(
        "SELECT e.player_id, coalesce(j.nome, 'Jogador #' || e.player_id) AS nome, e.lado, e.gols, e.assistencias "
        "FROM escalacao e LEFT JOIN jogador j ON j.player_id = e.player_id WHERE e.partida_id = ? ORDER BY e.rowid",
        (pid,))]}


def _placar(p: dict, clube: int) -> tuple[int, int]:
    """(gols pró, gols contra) do ponto de vista do clube."""
    if p["mandante_idx"] == clube:
        return p["gols_mandante"], p["gols_visitante"]
    return p["gols_visitante"], p["gols_mandante"]


def _campanha(jogadas: list[dict], clube: int) -> dict:
    """J/V/E/D e gols. Decisão nos pênaltis conta como empate."""
    r = {"jogos": 0, "vitorias": 0, "empates": 0, "derrotas": 0, "gols_pro": 0, "gols_contra": 0}
    for p in jogadas:
        pro, contra = _placar(p, clube)
        r["jogos"] += 1
        r["gols_pro"] += pro
        r["gols_contra"] += contra
        r["vitorias" if pro > contra else "derrotas" if pro < contra else "empates"] += 1
    return r


def resumo(con: sqlite3.Connection, cid: int, ano: int) -> dict:
    clube = _ultima(con, cid)["clube_idx"]
    jogadas = [p for p in partidas(con, cid, ano) if p["disputada"]]
    return {**_campanha(jogadas, clube), "ultimas": jogadas[-5:][::-1]}


def confrontos(con: sqlite3.Connection, cid: int) -> list[dict]:
    """Retrospecto contra cada adversário em toda a carreira, com os jogos do mais recente ao mais antigo."""
    clube = _ultima(con, cid)["clube_idx"]
    por_adversario = {}
    for p in partidas(con, cid):
        if p["disputada"]:
            lado = "visitante" if p["mandante_idx"] == clube else "mandante"
            por_adversario.setdefault(p[f"{lado}_idx"], (p[lado], p[f"{lado}_escudo"], []))[2].append(p)
    return sorted(({"idx": idx, "nome": nome, "escudo": escudo, **_campanha(ps, clube), "partidas": ps[::-1]}
                   for idx, (nome, escudo, ps) in por_adversario.items()), key=lambda a: (-a["jogos"], a["nome"]))


# ponytail: o clube é o da sincronização mais recente; se o usuário trocar de clube, a história do anterior some daqui.
_ESTATS = (
    "SELECT e.player_id, coalesce(j.nome, 'Jogador #' || e.player_id) AS nome, j.posicao, count(*) AS jogos,"
    " sum(e.gols) AS gols, sum(e.assistencias) AS assistencias "
    "FROM escalacao e JOIN partida p ON p.id = e.partida_id LEFT JOIN jogador j ON j.player_id = e.player_id "
    "WHERE p.carreira_id = :cid AND e.lado = CASE :clube WHEN p.mandante_idx THEN 0 WHEN p.visitante_idx THEN 1 END "
)


def elenco(con: sqlite3.Connection, cid: int, ano: int) -> list[dict]:
    """Estatísticas do clube no ano + quem está no elenco atual, mesmo sem jogos."""
    s = _ultima(con, cid)
    linhas = {r["player_id"]: dict(r) for r in con.execute(
        _ESTATS + "AND substr(p.data, 1, 4) = :ano GROUP BY e.player_id",
        {"cid": cid, "clube": s["clube_idx"], "ano": str(ano)})}
    atuais = {r[0]: (r[1], r[2]) for r in con.execute(
        "SELECT e.player_id, coalesce(j.nome, 'Jogador #' || e.player_id), j.posicao FROM elenco e "
        "LEFT JOIN jogador j ON j.player_id = e.player_id WHERE e.sincronizacao_id = ?", (s["id"],))}
    for pid, (nome, posicao) in atuais.items() if ano == int(s["data_jogo"][:4]) else ():
        linhas.setdefault(pid, {"player_id": pid, "nome": nome, "posicao": posicao, "jogos": 0, "gols": 0,
                                "assistencias": 0})
    contratos = _contratos(con, s["id"])
    for pid, linha in linhas.items():
        linha["no_elenco"] = pid in atuais
        linha["contrato"] = contratos.get(pid) if pid in atuais else None
    return sorted(linhas.values(), key=lambda l: (-l["jogos"], l["nome"]))


def _contratos(con: sqlite3.Connection, sid: int) -> dict[int, dict]:
    """Contratos daquela sincronização em R$; o salário semanal é o da tela do PES (anual // 52)."""
    return {r[0]: {"salario_semanal": r[1] // 52 * MOEDA, "multa": r[2] * MOEDA, "fim": r[3]} for r in con.execute(
        "SELECT player_id, salario_anual, multa, fim FROM contrato WHERE sincronizacao_id = ?", (sid,))}


def lendas(con: sqlite3.Connection, cid: int, limite: int = 10) -> dict:
    s = _ultima(con, cid)
    todos = [dict(r) for r in con.execute(_ESTATS + "GROUP BY e.player_id", {"cid": cid, "clube": s["clube_idx"]})]

    def top(k):
        return sorted(todos, key=lambda l: (-l[k], l["nome"]))[:limite]

    return {"artilheiros": top("gols"), "garcons": top("assistencias"), "mais_jogos": top("jogos"),
            "recordes": recordes(con, cid)}


def recordes(con: sqlite3.Connection, cid: int) -> dict:
    """Maior goleada, pior derrota, sequências e hat-tricks do clube em toda a carreira."""
    clube = _ultima(con, cid)["clube_idx"]
    jogadas = [p for p in partidas(con, cid) if p["disputada"]]

    def saldo(p):
        pro, contra = _placar(p, clube)
        return pro - contra

    def sequencia(vale):
        melhor, inicio = None, None
        for i, p in enumerate(jogadas):
            if not vale(p):
                inicio = None
                continue
            inicio = i if inicio is None else inicio
            if melhor is None or i - inicio + 1 > melhor["jogos"]:
                melhor = {"jogos": i - inicio + 1, "de": jogadas[inicio]["data"], "ate": p["data"]}
        return melhor

    # empate no saldo: vale a de mais gols (goleada) ou mais gols sofridos (derrota); depois, a mais antiga
    goleada = max(jogadas, key=lambda p: (saldo(p), _placar(p, clube)[0]), default=None)
    derrota = min(jogadas, key=lambda p: (saldo(p), -_placar(p, clube)[1]), default=None)
    por_id = {p["id"]: p for p in jogadas}
    hat_tricks = [{**dict(r), "partida": por_id[r["partida_id"]]} for r in con.execute(
        "SELECT e.player_id, coalesce(j.nome, 'Jogador #' || e.player_id) AS nome, e.gols, e.partida_id "
        "FROM escalacao e JOIN partida p ON p.id = e.partida_id LEFT JOIN jogador j ON j.player_id = e.player_id "
        "WHERE p.carreira_id = :cid AND e.gols >= 3 "
        "AND e.lado = CASE :clube WHEN p.mandante_idx THEN 0 WHEN p.visitante_idx THEN 1 END "
        "ORDER BY e.gols DESC, p.data DESC", {"cid": cid, "clube": clube}) if r["partida_id"] in por_id]
    return {"goleada": goleada if goleada and saldo(goleada) > 0 else None,
            "derrota": derrota if derrota and saldo(derrota) < 0 else None,
            "vitorias": sequencia(lambda p: saldo(p) > 0),
            "invencibilidade": sequencia(lambda p: saldo(p) >= 0),
            "hat_tricks": hat_tricks}


def transferencias(con: sqlite3.Connection, cid: int) -> dict:
    """Quem chegou e quem saiu entre duas datas do jogo sincronizadas, da janela mais recente à mais antiga.
    Cada jogador vem com os números dele pelo clube na carreira toda, com o clube de origem (no save anterior)
    ou de destino (no save novo) e com o valor do negócio em R$ (negativo = o clube pagou), se houve.
    clube = None é sem clube, se a origem ou o destino da janela for conhecido. Os negócios que o livro do save
    já trazia na primeira sincronização viram uma janela sem início (de = None)."""
    s = _ultima(con, cid)
    fotos = [(d, sid, {r[0] for r in con.execute("SELECT player_id FROM elenco WHERE sincronizacao_id = ?", (sid,))})
             for d, sid in con.execute("SELECT data_jogo, max(id) FROM sincronizacao WHERE carreira_id = ? "
                                       "AND clube_idx = ? GROUP BY data_jogo ORDER BY data_jogo",
                                       (cid, s["clube_idx"])).fetchall()]
    numeros = {r["player_id"]: dict(r) for r in con.execute(
        _ESTATS + "GROUP BY e.player_id", {"cid": cid, "clube": s["clube_idx"]})}
    negocios = con.execute("SELECT player_id, tipo, valor * ?, data_jogo FROM negocio WHERE carreira_id = ?",
                           (MOEDA, cid)).fetchall()

    def jogador(pid):
        if pid in numeros:
            return numeros[pid]
        nome = con.execute("SELECT nome FROM jogador WHERE player_id = ?", (pid,)).fetchone()
        return {"player_id": pid, "nome": nome[0] if nome else f"Jogador #{pid}", "jogos": 0, "gols": 0,
                "assistencias": 0}

    def clubes(sid, ids):
        """{player_id: clube} naquela sincronização; None se ela é anterior aos vínculos."""
        if con.execute("SELECT 1 FROM vinculo WHERE sincronizacao_id = ? LIMIT 1", (sid,)).fetchone() is None:
            return None
        return {r[0]: {"nome": r[1], "escudo": r[2]} for r in con.execute(
            "SELECT v.player_id, t.nome, t.pes_id FROM vinculo v JOIN time t ON t.carreira_id = ? AND t.idx = v.time_idx "
            f"WHERE v.sincronizacao_id = ? AND v.player_id IN ({','.join('?' * len(ids))})", (cid, sid, *ids))}

    def janela(de, ate, chegaram, sairam, origem, destino, s_antes=None):
        valores = {pid: (tipo, valor) for pid, tipo, valor, d in negocios if (de is None or d > de) and d <= ate}
        # saiu com o contrato do save anterior já vencido na data nova: fim de contrato, não venda
        vencidos = {p for p, c in (_contratos(con, s_antes) if s_antes else {}).items() if c["fim"] <= ate}

        def lista(ids, clube):
            return sorted(({**jogador(i), "clube": (clube or {}).get(i), "valor": valores.get(i, (None, None))[1],
                            "tipo": valores.get(i, (None, None))[0], "fim_de_contrato": i in vencidos} for i in ids),
                          key=lambda j: (-abs(j["valor"] or 0), -j["jogos"], j["nome"]))

        return {"de": de, "ate": ate, "origem_conhecida": origem is not None, "destino_conhecido": destino is not None,
                "gastos": -sum(v for _, v in valores.values() if v < 0),
                "receitas": sum(v for _, v in valores.values() if v > 0),
                "chegaram": lista(chegaram, origem), "sairam": lista(sairam, destino)}

    janelas = []
    if fotos:
        ate, sid, _ = fotos[0]
        antigos = {pid: valor for pid, _, valor, d in negocios if d <= ate}
        if antigos:
            sairam = {pid for pid, valor in antigos.items() if valor > 0}
            janelas.append(janela(None, ate, set(antigos) - sairam, sairam, None, clubes(sid, sairam)))
    for (de, s_antes, antes), (ate, s_depois, depois) in zip(fotos, fotos[1:]):
        if antes != depois:
            chegaram, sairam = depois - antes, antes - depois
            janelas.append(janela(de, ate, chegaram, sairam, clubes(s_antes, chegaram), clubes(s_depois, sairam), s_antes))
    return {"primeira": fotos[0][0] if fotos else None, "janelas": janelas[::-1]}


# ponytail: temporada = ano civil e todas as competições somadas; separar quando o campo de competição sair.
def mundo(con: sqlite3.Connection, cid: int, ano: int, limite: int = 20) -> dict:
    """Artilharia e garçons de todas as partidas do mundo no ano. O time é o do último jogo do jogador."""
    args = {"cid": cid, "ano": str(ano)}
    todos = [dict(r) for r in con.execute(
        # com um único max() no SELECT, o SQLite tira time_idx da linha da partida mais recente
        "SELECT s.*, t.nome AS time, t.pes_id AS escudo FROM ("
        " SELECT e.player_id, coalesce(j.nome, 'Jogador #' || e.player_id) AS nome, count(*) AS jogos,"
        " sum(e.gols) AS gols, sum(e.assistencias) AS assistencias, max(p.data) AS ultima,"
        " CASE e.lado WHEN 0 THEN p.mandante_idx ELSE p.visitante_idx END AS time_idx"
        " FROM escalacao e JOIN partida p ON p.id = e.partida_id LEFT JOIN jogador j ON j.player_id = e.player_id"
        " WHERE p.carreira_id = :cid AND substr(p.data, 1, 4) = :ano GROUP BY e.player_id) s "
        "LEFT JOIN time t ON t.carreira_id = :cid AND t.idx = s.time_idx", args)]

    def top(k, desempate):
        return sorted((l for l in todos if l[k] > 0), key=lambda l: (-l[k], -l[desempate], l["nome"]))[:limite]

    jogos = con.execute("SELECT count(*) FROM partida WHERE carreira_id = :cid AND disputada = 1 "
                        "AND substr(data, 1, 4) = :ano", args).fetchone()[0]
    return {"partidas": jogos, "artilheiros": top("gols", "assistencias"), "garcons": top("assistencias", "gols")}


def rostos(con: sqlite3.Connection) -> set[int]:
    """Quem passou pelo clube de alguma carreira (elenco ou escalação) e os líderes da artilharia do mundo,
    para extrair as minifaces."""
    ids = {r[0] for r in con.execute("SELECT DISTINCT player_id FROM elenco")}
    for (cid,) in con.execute("SELECT id FROM carreira").fetchall():
        if s := _ultima(con, cid):
            ids |= {r[0] for r in con.execute(_ESTATS + "GROUP BY e.player_id", {"cid": cid, "clube": s["clube_idx"]})}
            for ano in temporadas(con, cid):
                m = mundo(con, cid, ano)
                ids |= {l["player_id"] for l in m["artilheiros"] + m["garcons"]}
    return ids
