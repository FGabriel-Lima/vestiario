"""SQLite do Vestiário: guarda a história que o save vai apagando."""
import sqlite3
from collections import Counter
from datetime import date, datetime
from itertools import groupby
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
  sincronizacao_id INTEGER NOT NULL REFERENCES sincronizacao, player_id INTEGER NOT NULL, idade INTEGER);
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
  salario_anual INTEGER NOT NULL, multa INTEGER NOT NULL, fim TEXT NOT NULL, emprestimo INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY(sincronizacao_id, player_id));
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
  disputada INTEGER NOT NULL, competicao INTEGER, grupo INTEGER NOT NULL DEFAULT 0, rodada INTEGER NOT NULL DEFAULT 0,
  UNIQUE(carreira_id, data, mandante_idx, visitante_idx));
CREATE TABLE IF NOT EXISTS competicao(
  carreira_id INTEGER NOT NULL REFERENCES carreira, id INTEGER NOT NULL, nome TEXT NOT NULL, PRIMARY KEY(carreira_id, id));
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
    if "emprestimo" not in {r[1] for r in con.execute("PRAGMA table_info(contrato)")}:
        with con:  # banco anterior aos empréstimos: relê os saves para marcar quem veio emprestado
            con.execute("ALTER TABLE contrato ADD COLUMN emprestimo INTEGER NOT NULL DEFAULT 0")
            con.execute("DELETE FROM arquivo")
    if "competicao" not in {r[1] for r in con.execute("PRAGMA table_info(partida)")}:
        with con:  # banco anterior às competições: relê os saves para preencher as partidas que ainda estão neles
            con.execute("ALTER TABLE partida ADD COLUMN competicao INTEGER")
            con.execute("ALTER TABLE partida ADD COLUMN grupo INTEGER NOT NULL DEFAULT 0")
            con.execute("ALTER TABLE partida ADD COLUMN rodada INTEGER NOT NULL DEFAULT 0")
            con.execute("DELETE FROM arquivo")
    if "idade" not in {r[1] for r in con.execute("PRAGMA table_info(elenco)")}:
        with con:  # banco anterior às idades da ML: relê os saves para preenchê-las
            con.execute("ALTER TABLE elenco ADD COLUMN idade INTEGER")
            con.execute("DELETE FROM arquivo")
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
        con.executemany("INSERT INTO elenco VALUES(?, ?, ?)", [(sid, p, save.idades.get(p)) for p in save.elenco])
        con.executemany("INSERT INTO contrato VALUES(?, ?, ?, ?, ?, ?)",
                        [(sid, p, c.salario_anual, c.multa, c.fim.isoformat(), int(c.emprestimo))
                         for p, c in save.contratos.items()])
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

        con.executemany("INSERT INTO competicao VALUES(?, ?, ?) ON CONFLICT DO UPDATE SET nome = excluded.nome",
                        [(cid, i, n) for i, n in save.competicoes.items()])
        novas = atualizadas = 0
        for p in save.partidas:
            chave = (p.data.isoformat(), p.mandante, p.visitante)
            antes = existentes.get(chave)
            if antes == 1:  # disputada nunca regride; só ganha a competição se foi gravada antes de existir o campo
                con.execute("UPDATE partida SET competicao = ?, grupo = ?, rodada = ? WHERE carreira_id = ? AND data = ?"
                            " AND mandante_idx = ? AND visitante_idx = ? AND competicao IS NULL",
                            (p.competicao, p.grupo, p.rodada, cid, *chave))
                continue
            if not p.disputada and not mais_recente:
                continue
            if p.disputada and antes == 0:
                atualizadas += 1
            elif p.disputada and antes is None:
                novas += 1
            pid = con.execute(
                "INSERT INTO partida(carreira_id, data, mandante_idx, visitante_idx, gols_mandante, gols_visitante,"
                " penaltis_mandante, penaltis_visitante, disputada, competicao, grupo, rodada)"
                " VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(carreira_id, data, mandante_idx, visitante_idx) DO UPDATE SET"
                " gols_mandante = excluded.gols_mandante, gols_visitante = excluded.gols_visitante,"
                " penaltis_mandante = excluded.penaltis_mandante, penaltis_visitante = excluded.penaltis_visitante,"
                " disputada = excluded.disputada, competicao = excluded.competicao, grupo = excluded.grupo,"
                " rodada = excluded.rodada RETURNING id",
                (cid, *chave, *p.gols, *p.penaltis, int(p.disputada), p.competicao, p.grupo, p.rodada),
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
    " p.gols_mandante, p.gols_visitante, p.penaltis_mandante, p.penaltis_visitante, p.disputada,"
    " cp.nome AS competicao, p.competicao AS competicao_id, p.grupo, p.rodada "
    "FROM partida p "
    "LEFT JOIN time tm ON tm.carreira_id = p.carreira_id AND tm.idx = p.mandante_idx "
    "LEFT JOIN time tv ON tv.carreira_id = p.carreira_id AND tv.idx = p.visitante_idx "
    "LEFT JOIN competicao cp ON cp.carreira_id = p.carreira_id AND cp.id = p.competicao "
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
    atuais = {r[0]: (r[1], r[2], r[3]) for r in con.execute(
        "SELECT e.player_id, coalesce(j.nome, 'Jogador #' || e.player_id), j.posicao, e.idade FROM elenco e "
        "LEFT JOIN jogador j ON j.player_id = e.player_id WHERE e.sincronizacao_id = ?", (s["id"],))}
    for pid, (nome, posicao, _) in atuais.items() if ano == int(s["data_jogo"][:4]) else ():
        linhas.setdefault(pid, {"player_id": pid, "nome": nome, "posicao": posicao, "jogos": 0, "gols": 0,
                                "assistencias": 0})
    contratos = _contratos(con, s["id"])
    for pid, linha in linhas.items():
        linha["no_elenco"] = pid in atuais
        linha["contrato"] = contratos.get(pid) if pid in atuais else None
        linha["idade"] = atuais[pid][2] if pid in atuais else None
    return sorted(linhas.values(), key=lambda l: (-l["jogos"], l["nome"]))


def _contratos(con: sqlite3.Connection, sid: int) -> dict[int, dict]:
    """Contratos daquela sincronização em R$; o salário semanal é o da tela do PES (anual // 52)."""
    return {r[0]: {"salario_semanal": r[1] // 52 * MOEDA, "multa": r[2] * MOEDA, "fim": r[3], "emprestimo": bool(r[4])}
            for r in con.execute("SELECT player_id, salario_anual, multa, fim, emprestimo FROM contrato "
                                 "WHERE sincronizacao_id = ?", (sid,))}


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


# --- campeonatos ---------------------------------------------------------------

MATA_MATA = 46        # rodadas a partir daqui são fases eliminatórias (53 = final)
# edição nova: rodada que volta para trás depois de 45 dias sem jogo, ou qualquer pausa de mais de 120 dias
# (fase preliminar e supercopa usam sempre a mesma rodada)
PAUSA_ENTRE_EDICOES, PAUSA_LONGA = 45, 120
PAUSA_ENTRE_FASES = 120  # dias entre o fim de uma fase e o começo da seguinte (outro id com o mesmo nome)
# conferido em Copa do Brasil, Libertadores e AFC Champions League; as outras rodadas viram "Nª fase"
FASES = {53: "Final", 52: "Semifinal", 51: "Quartas de final"}


def _edicoes(con: sqlite3.Connection, cid: int) -> dict[str, dict]:
    """Junta as partidas de cada competição em edições. O id da competição se repete a cada temporada, então, dentro
    de um id, uma edição nova começa depois de uma pausa (veja PAUSA_LONGA). Ids diferentes com o mesmo nome são
    fases da mesma competição (Champions: 2 preliminar, 3 grupos, 4 mata-mata; Libertadores: 8, 9, 10) e se
    encadeiam numa edição enquanto o id sobe e a pausa entre elas é de até PAUSA_ENTRE_FASES dias."""
    por_id = {}
    for p in con.execute(_PARTIDA + "WHERE p.carreira_id = ? AND p.competicao IS NOT NULL ORDER BY p.data", (cid,)):
        por_id.setdefault(p["competicao_id"], []).append(dict(p))
    _devolve_avulsos(por_id)
    por_nome = {}
    for ps in por_id.values():
        trechos = [[ps[0]]]
        for anterior, p in zip(ps, ps[1:]):
            pausa = (date.fromisoformat(p["data"]) - date.fromisoformat(anterior["data"])).days
            if pausa > PAUSA_LONGA or (pausa > PAUSA_ENTRE_EDICOES and p["rodada"] < max(x["rodada"] for x in trechos[-1])):
                trechos.append([])
            trechos[-1].append(p)
        for t in trechos:
            por_nome.setdefault(t[0]["competicao"] or f"Competição {t[0]['competicao_id']}", []).append(t)
    edicoes = {}
    for nome, trechos in por_nome.items():
        cadeias = []
        for t in sorted(trechos, key=lambda t: t[0]["data"]):
            ultimo = cadeias[-1][-1] if cadeias else None
            if ultimo and t[0]["competicao_id"] > ultimo[0]["competicao_id"] and                     (date.fromisoformat(t[0]["data"]) - date.fromisoformat(ultimo[-1]["data"])).days <= PAUSA_ENTRE_FASES:
                cadeias[-1].append(t)
            else:
                cadeias.append([t])
        for partes in cadeias:
            inicio, fim = partes[0][0]["data"][:4], max(t[-1]["data"] for t in partes)[:4]
            temporada = inicio if inicio == fim else f"{inicio}/{fim[2:]}"
            e = edicoes.setdefault(f"{nome}|{temporada}", {"nome": nome, "temporada": temporada, "partes": []})
            e["partes"].extend(partes)
    return edicoes


def _devolve_avulsos(por_id: dict[int, list[dict]]) -> None:
    """O save às vezes grava um jogo com o id de outra competição: a final do Mundial 2025 (Monterrey 0 x 2 PSG)
    veio com o id do mata-mata da Champions. Num mata-mata de ida e volta, um jogo único sozinho na sua data volta
    para a competição cujo último jogo (uma final, rodada 53) foi até 7 dias antes com um dos mesmos times, e vira
    a final dela. Sem competição assim, ele fica onde está (e o chaveamento o deixa de fora)."""
    dia = lambda p: date.fromisoformat(p["data"])
    par = lambda p: frozenset((p["mandante_idx"], p["visitante_idx"]))
    for comp, ps in list(por_id.items()):
        mata = [p for p in ps if p["rodada"] >= MATA_MATA]
        if not any(a is not b and par(a) == par(b) and abs((dia(a) - dia(b)).days) <= 30 for a in mata for b in mata):
            continue
        for m in mata:
            if m["rodada"] >= 53 or any(o is not m and (abs((dia(o) - dia(m)).days) <= MESMA_FASE or
                                                        (par(o) == par(m) and abs((dia(o) - dia(m)).days) <= 60))
                                        for o in mata):
                continue
            for outro, qs in por_id.items():
                antes = [q for q in qs if 0 < (dia(m) - dia(q)).days <= 7]
                ultimo = max(antes, key=dia) if antes and outro != comp else None
                if ultimo and ultimo["rodada"] == 53 and par(ultimo) & par(m):
                    ps.remove(m)
                    qs.append({**m, "competicao_id": outro, "competicao": ultimo["competicao"], "rodada": 53})
                    qs.sort(key=lambda q: q["data"])
                    break


def _fases(partes: list[list[dict]]) -> list[dict]:
    fases, numero = [], 0
    for parte in sorted(partes, key=lambda t: t[0]["data"]):
        if any(p["rodada"] >= MATA_MATA for p in parte):
            rodadas = sorted({p["rodada"] for p in parte})
            for i, rodada in enumerate(rodadas):
                jogos = [p for p in parte if p["rodada"] == rodada]
                if any(p["grupo"] for p in jogos):  # a preliminar da Libertadores vem dividida em chaves, na rodada 53
                    titulo = "Fase preliminar"
                elif rodada in FASES:
                    titulo = FASES[rodada]
                elif i + 1 < len(rodadas) and rodadas[i + 1] == 51:
                    titulo = "Oitavas de final"
                else:
                    numero += 1
                    titulo = f"{numero}ª fase"
                fases.append({"titulo": titulo, "tipo": "jogos", "partidas": jogos})
        else:
            grupos = [{"titulo": f"Grupo {chr(64 + g)}" if g else None,
                       "linhas": _classificacao(_sem_avulsos([p for p in parte if p["grupo"] == g]))}
                      for g in sorted({p["grupo"] for p in parte})]
            # jogo remarcado deixa a numeração de rodada do PES fora de ordem; conta pelos jogos de quem mais jogou
            jogadas = max((l["jogos"] for g in grupos for l in g["linhas"]), default=0)
            total = len({p["rodada"] for p in parte})  # com os jogos futuros no banco, é o total da temporada
            incompleta = False
            if not grupos[0]["titulo"] and all(p["disputada"] for p in parte):
                # liga encerrada no banco: se os jogos não fecham um turno nem um ida e volta, faltam rodadas que saíram
                # do save antes de ele ser sincronizado (o Brasileirão 2025 do São Paulo tem só as 23 primeiras)
                n = len(grupos[0]["linhas"])
                turno = n - 1 if n % 2 == 0 else n
                if jogadas not in (n - 1, 2 * (n - 1)):
                    total = next((t for t in (turno, 2 * turno) if t > jogadas), total)
                    incompleta = jogadas < total
            fases.append({"titulo": "Fase de grupos" if grupos[0]["titulo"] else "Classificação", "tipo": "tabela",
                          "rodadas_jogadas": jogadas, "rodadas_total": total, "grupos": grupos,
                          "incompleta": incompleta})
    return fases


def _sem_avulsos(partidas: list[dict]) -> list[dict]:
    """O save às vezes marca um jogo de outros times com a competição (Buriram x Al Hussein no grupo A da
    Libertadores 2025). Time de verdade joga várias vezes; jogo em que nenhum dos dois tem outro jogo ali sai."""
    vezes = Counter(t for p in partidas for t in (p["mandante_idx"], p["visitante_idx"]))
    tipico = sorted(vezes.values())[len(vezes) // 2] if vezes else 0
    # também sai o time com menos de 1/4 dos jogos de um time típico (a Inter de Milão com 1 jogo na Premier League)
    avulso = lambda t: vezes[t] * 4 < tipico
    return [p for p in partidas if (vezes[p["mandante_idx"]] > 1 or vezes[p["visitante_idx"]] > 1)
            and not avulso(p["mandante_idx"]) and not avulso(p["visitante_idx"])] or partidas


def _classificacao(partidas: list[dict]) -> list[dict]:
    """Classificação com posição (dividida em empate total). Os times entram pelos jogos marcados, mesmo sem ter jogado."""
    linhas = {}
    for p in partidas:
        for lado in ("mandante", "visitante"):
            linhas.setdefault(p[f"{lado}_idx"], {"idx": p[f"{lado}_idx"], "nome": p[lado], "escudo": p[f"{lado}_escudo"],
                                                 "jogos": 0, "vitorias": 0, "empates": 0, "derrotas": 0,
                                                 "gols_pro": 0, "gols_contra": 0, "pontos": 0})
    for p in partidas:
        if p["disputada"]:
            for idx in (p["mandante_idx"], p["visitante_idx"]):
                r = _campanha([p], idx)
                linha = linhas[idx]
                for k in ("jogos", "vitorias", "empates", "derrotas", "gols_pro", "gols_contra"):
                    linha[k] += r[k]
                linha["pontos"] += 3 * r["vitorias"] + r["empates"]
    # critério da tela do PES (conferido no Brasileirão 2026): pontos, vitórias, saldo, gols pró e, entre os que
    # continuam empatados, pontos nos jogos entre eles; quem empata em tudo divide a posição e o PES lista pelo id
    # do time no jogo (o do escudo)
    chave = lambda l: (-l["pontos"], -l["vitorias"], l["gols_contra"] - l["gols_pro"], -l["gols_pro"])
    ordem = sorted(linhas.values(), key=lambda l: (chave(l), l["escudo"] if l["escudo"] is not None else 1 << 30,
                                                   l["nome"] or ""))
    resultado = []
    for _, grupo in groupby(ordem, key=chave):
        grupo = list(grupo)
        empatados = {l["idx"] for l in grupo}
        diretos = [p for p in partidas if p["disputada"] and {p["mandante_idx"], p["visitante_idx"]} <= empatados]
        pontos = {idx: sum(3 * r["vitorias"] + r["empates"] for r in (_campanha([p], idx) for p in diretos
                                                                       if idx in (p["mandante_idx"], p["visitante_idx"])))
                  for idx in empatados}
        resultado += [(l, pontos[l["idx"]]) for l in sorted(grupo, key=lambda l: -pontos[l["idx"]])]
    for i, (l, diretos) in enumerate(resultado):
        anterior, diretos_ant = resultado[i - 1] if i else (None, None)
        divide = anterior and chave(anterior) == chave(l) and diretos == diretos_ant and             _pontos_diretos(partidas, anterior, l) == (0, 0)
        l["posicao"] = anterior["posicao"] if divide else i + 1
    return [l for l, _ in resultado]


def _pontos_diretos(partidas: list[dict], a: dict, b: dict) -> tuple[int, int]:
    """Saldo de pontos entre dois times nos jogos entre eles: (0, 0) é empate ou nunca se enfrentaram."""
    jogos = [p for p in partidas if p["disputada"] and {p["mandante_idx"], p["visitante_idx"]} == {a["idx"], b["idx"]}]
    pa = sum(3 * r["vitorias"] + r["empates"] for r in (_campanha([p], a["idx"]) for p in jogos))
    pb = sum(3 * r["vitorias"] + r["empates"] for r in (_campanha([p], b["idx"]) for p in jogos))
    return (0, 0) if pa == pb else (pa, pb)


def _confronto(pernas: list[dict]) -> dict:
    """Ida e volta do mesmo par de times: agregado e pênaltis do último jogo."""
    primeiro, ultimo = pernas[0], pernas[-1]
    jogados = [p for p in pernas if p["disputada"]]
    times = []
    for lado in ("mandante", "visitante"):
        idx = primeiro[f"{lado}_idx"]
        pen = None
        if ultimo["disputada"] and ultimo["penaltis_mandante"] + ultimo["penaltis_visitante"]:
            pen = ultimo["penaltis_mandante"] if ultimo["mandante_idx"] == idx else ultimo["penaltis_visitante"]
        times.append({"idx": idx, "nome": primeiro[lado], "escudo": primeiro[f"{lado}_escudo"],
                      "gols": sum(_placar(p, idx)[0] for p in jogados) if jogados else None,
                      "penaltis": pen, "vencedor": False})
    return {"times": times, "encerrado": len(jogados) == len(pernas),
            "jogos": [{"id": p["id"], "data": p["data"], "disputada": p["disputada"],
                       "placar": f"{p['gols_mandante']}-{p['gols_visitante']}"} for p in pernas]}


MESMA_FASE = 2  # dias: jogos de ida a até 2 dias um do outro são da mesma fase (o Mundial tem fases a 3 dias)


def _chaveamento(fases: list[dict]) -> list[dict]:
    """Colunas do mata-mata em ordem de chave. O PES às vezes grava um jogo com a rodada da fase seguinte (a volta,
    ou o jogo único de uma fase), então a rodada gravada não basta: o confronto é montado pelo par de times, a fase
    sai da data do jogo de ida (os jogos de uma fase acontecem juntos) e o nome vem do confronto com a menor rodada
    da fase (o deslocamento é sempre para cima). Quem passou é quem aparece na fase seguinte (na última, quem fez
    mais gols no agregado e depois nos pênaltis). A ordem vem de trás para frente, a partir da última fase."""
    pares, titulo_do_jogo = {}, {}
    for f in fases:
        for p in f["partidas"]:
            pares.setdefault(frozenset((p["mandante_idx"], p["visitante_idx"])), []).append(p)
            titulo_do_jogo[p["id"]] = f["titulo"]
    confrontos = []
    for pernas in pares.values():
        pernas.sort(key=lambda p: p["data"])
        primeiro = min(pernas, key=lambda p: (p.get("rodada") or 0, p["data"]))
        confrontos.append((pernas[0]["data"], (primeiro.get("rodada") or 0, titulo_do_jogo[primeiro["id"]]),
                           _confronto(pernas)))
    confrontos.sort(key=lambda c: c[0])
    grupos = []
    for inicio, rodada, c in confrontos:
        if grupos and (date.fromisoformat(inicio) - date.fromisoformat(grupos[-1][-1][0])).days <= MESMA_FASE:
            grupos[-1].append((inicio, rodada, c))
        else:
            grupos.append([(inicio, rodada, c)])
    # o save às vezes grava um jogo de outra competição com o id da copa (Monterrey x PSG, do Mundial, no mata-mata
    # da Champions 2025/26; América de Cali x Millonarios na Copa do Brasil 2026): numa copa de ida e volta, um jogo
    # único sozinho na sua data sai, a não ser que seja a final (rodada 53; o deslocamento do PES nunca puxa para baixo)
    if any(len(c["jogos"]) > 1 for _, _, c in confrontos):
        grupos = [g for g in grupos if not (len(g) == 1 and len(g[0][2]["jogos"]) == 1 and g[0][1][0] < 53)]
    colunas = [{"titulo": min(r for _, r, _ in g)[1], "confrontos": [c for _, _, c in g]} for g in grupos]
    for i, col in enumerate(colunas[:-1]):  # duas "finais" (uma devolvida por _devolve_avulsos): só a última é final
        if col["titulo"] == "Final":
            col["titulo"] = f"{i + 1}ª fase"
    for i in range(len(colunas) - 2, -1, -1):
        ordem = [t["idx"] for c in colunas[i + 1]["confrontos"] for t in c["times"]]
        posicao = lambda c: min((ordem.index(t["idx"]) for t in c["times"] if t["idx"] in ordem), default=len(ordem))
        colunas[i]["confrontos"].sort(key=posicao)

    times = lambda c: {t["idx"] for t in c["times"]}
    for i, col in enumerate(colunas):
        seguinte = colunas[i + 1]["confrontos"] if i + 1 < len(colunas) else []
        seguintes = set().union(*map(times, seguinte)) if seguinte else None
        for c in col["confrontos"]:
            a, b = c["times"]
            if seguintes is not None and (a["idx"] in seguintes) != (b["idx"] in seguintes):
                (a if a["idx"] in seguintes else b)["vencedor"] = True
            elif seguintes is None and c["encerrado"] and (a["gols"], a["penaltis"] or 0) != (b["gols"], b["penaltis"] or 0):
                (a if (a["gols"], a["penaltis"] or 0) > (b["gols"], b["penaltis"] or 0) else b)["vencedor"] = True
        # as linhas ligam o par (2k, 2k+1) ao confronto k da fase seguinte só quando os times batem de verdade
        col["encaixa"] = bool(seguinte) and len(col["confrontos"]) == 2 * len(seguinte) and all(
            times(prox) <= times(col["confrontos"][2 * k]) | times(col["confrontos"][2 * k + 1])
            for k, prox in enumerate(seguinte))
    return colunas


def edicoes(con: sqlite3.Connection, cid: int) -> list[dict]:
    """Edições de todas as competições guardadas: as do clube primeiro, a temporada mais recente antes, ligas de
    pontos corridos antes das copas."""
    clube = _ultima(con, cid)["clube_idx"]
    lista = []
    for chave, e in _edicoes(con, cid).items():
        todas = [p for t in e["partes"] for p in t]
        lista.append({"chave": chave, "nome": e["nome"], "temporada": e["temporada"],
                      "do_clube": any(clube in (p["mandante_idx"], p["visitante_idx"]) for p in todas),
                      "liga": all(p["rodada"] < MATA_MATA and not p["grupo"] for p in todas)})
    return sorted(lista, key=lambda e: (not e["do_clube"], -int(e["temporada"][:4]), not e["liga"],
                                        e["nome"].casefold()))


def edicao(con: sqlite3.Connection, cid: int, chave: str) -> dict | None:
    e = _edicoes(con, cid).get(chave)
    return _montar(e, _ultima(con, cid)["clube_idx"]) if e else None


def _montar(e: dict, clube: int) -> dict:
    todas = sorted((p for t in e["partes"] for p in t), key=lambda p: p["data"])
    fases = _fases(e["partes"])
    # a fase preliminar vem em chaves paralelas e não entra na chave do mata-mata
    mata_mata = [f for f in fases if f["tipo"] == "jogos" and f["titulo"] != "Fase preliminar"]
    chave = _chaveamento(mata_mata)
    return {"nome": e["nome"], "temporada": e["temporada"], "fases": fases, "chaveamento": chave,
            **_campeao(fases, chave, todas),
            "partidas_clube": [p for p in todas if clube in (p["mandante_idx"], p["visitante_idx"])]}


def _campeao(fases: list[dict], chave: list[dict], todas: list[dict]) -> dict:
    """Campeão e vice só com a competição decidida no save: o vencedor da final (com mata-mata) ou o líder isolado
    de uma liga de pontos corridos completa no banco. Senão, os dois ficam None."""
    time = lambda t: {"idx": t["idx"], "nome": t["nome"], "escudo": t["escudo"]}
    if chave:
        final = chave[-1]
        if final["titulo"] == "Final" and len(final["confrontos"]) == 1:
            ganhou = [t for t in final["confrontos"][0]["times"] if t["vencedor"]]
            if ganhou:
                perdeu = next(t for t in final["confrontos"][0]["times"] if not t["vencedor"])
                return {"campeao": time(ganhou[0]), "vice": time(perdeu)}
    elif len(fases) == 1 and fases[0]["tipo"] == "tabela" and len(fases[0]["grupos"]) == 1 and             all(p["disputada"] for p in todas):
        linhas = fases[0]["grupos"][0]["linhas"]
        # o save apaga as partidas mais antigas: só é campeão quem completou um turno (ou ida e volta) inteiro
        n = len(linhas)
        completa = n > 1 and len({l["jogos"] for l in linhas}) == 1 and linhas[0]["jogos"] in (n - 1, 2 * (n - 1))
        if completa and linhas[1]["posicao"] > 1:
            return {"campeao": time(linhas[0]), "vice": time(linhas[1])}
    return {"campeao": None, "vice": None}


def titulos(con: sqlite3.Connection, cid: int) -> list[dict]:
    """Edições já decididas no save, da mais recente para a mais antiga, com campeão e vice."""
    clube = _ultima(con, cid)["clube_idx"]
    lista = []
    for chave, e in _edicoes(con, cid).items():
        m = _montar(e, clube)
        if m["campeao"]:
            fim = max(p["data"] for t in e["partes"] for p in t)
            lista.append({"chave": chave, "nome": m["nome"], "temporada": m["temporada"], "fim": fim,
                          "campeao": m["campeao"], "vice": m["vice"]})
    return sorted(lista, key=lambda t: (t["fim"], t["nome"]), reverse=True)
