"""SQLite do Vestiário: guarda a história que o save vai apagando."""
import sqlite3
from datetime import datetime
from pathlib import Path

from .leitor import Save

ESQUEMA = """
CREATE TABLE IF NOT EXISTS carreira(
  id INTEGER PRIMARY KEY, slot TEXT NOT NULL, nome TEXT NOT NULL, UNIQUE(slot, nome));
CREATE TABLE IF NOT EXISTS sincronizacao(
  id INTEGER PRIMARY KEY, carreira_id INTEGER NOT NULL REFERENCES carreira,
  em TEXT NOT NULL, data_jogo TEXT NOT NULL, clube_idx INTEGER NOT NULL, clube_nome TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS elenco(
  sincronizacao_id INTEGER NOT NULL REFERENCES sincronizacao, player_id INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS time(
  carreira_id INTEGER NOT NULL REFERENCES carreira, idx INTEGER NOT NULL, nome TEXT NOT NULL,
  PRIMARY KEY(carreira_id, idx));
CREATE TABLE IF NOT EXISTS jogador(player_id INTEGER PRIMARY KEY, nome TEXT NOT NULL);
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
    con.executescript(ESQUEMA)
    return con


def gravar_nomes(con: sqlite3.Connection, nomes: dict[int, str]) -> None:
    with con:
        con.executemany("INSERT INTO jogador VALUES(?, ?) ON CONFLICT DO UPDATE SET nome = excluded.nome",
                        nomes.items())


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
        cid = con.execute("INSERT INTO carreira(slot, nome) VALUES(?, ?) ON CONFLICT DO UPDATE "
                          "SET nome = excluded.nome RETURNING id", (slot, save.nome)).fetchone()[0]
        ultima = con.execute("SELECT max(data_jogo) FROM sincronizacao WHERE carreira_id = ?", (cid,)).fetchone()[0]
        mais_recente = ultima is None or save.data_jogo.isoformat() >= ultima
        sid = con.execute(
            "INSERT INTO sincronizacao(carreira_id, em, data_jogo, clube_idx, clube_nome) "
            "VALUES(?, ?, ?, ?, ?) RETURNING id",
            (cid, em.isoformat(timespec="seconds"), save.data_jogo.isoformat(), save.clube_idx, save.clube),
        ).fetchone()[0]
        con.executemany("INSERT INTO elenco VALUES(?, ?)", [(sid, p) for p in save.elenco])
        if mais_recente:
            con.executemany("INSERT INTO time VALUES(?, ?, ?) ON CONFLICT DO UPDATE SET nome = excluded.nome",
                            [(cid, i, n) for i, n in enumerate(save.times)])

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
        "SELECT c.id, c.slot, c.nome, s.clube_nome, s.data_jogo, s.em FROM carreira c "
        "JOIN sincronizacao s ON s.id = (SELECT id FROM sincronizacao WHERE carreira_id = c.id "
        "ORDER BY data_jogo DESC, id DESC LIMIT 1) ORDER BY s.em DESC, c.id")]


def carreira(con: sqlite3.Connection, cid: int) -> dict | None:
    s = _ultima(con, cid)
    if s is None:
        return None
    return {"id": cid, "clube_nome": s["clube_nome"], "clube_idx": s["clube_idx"], "data_jogo": s["data_jogo"]}


# ponytail: temporada = ano civil da partida (certo no Brasileirão, errado em ligas europeias);
# trocar quando o campo de competição for decodificado.
def temporadas(con: sqlite3.Connection, cid: int) -> list[int]:
    clube = _ultima(con, cid)["clube_idx"]
    return [int(r[0]) for r in con.execute(
        "SELECT DISTINCT substr(data, 1, 4) FROM partida "
        "WHERE carreira_id = ? AND ? IN (mandante_idx, visitante_idx) ORDER BY 1 DESC", (cid, clube))]


def partidas(con: sqlite3.Connection, cid: int, ano: int) -> list[dict]:
    clube = _ultima(con, cid)["clube_idx"]
    return [dict(r) for r in con.execute(
        "SELECT p.id, p.data, p.mandante_idx, tm.nome AS mandante, p.visitante_idx, tv.nome AS visitante,"
        " p.gols_mandante, p.gols_visitante, p.penaltis_mandante, p.penaltis_visitante, p.disputada "
        "FROM partida p "
        "LEFT JOIN time tm ON tm.carreira_id = p.carreira_id AND tm.idx = p.mandante_idx "
        "LEFT JOIN time tv ON tv.carreira_id = p.carreira_id AND tv.idx = p.visitante_idx "
        "WHERE p.carreira_id = ? AND ? IN (p.mandante_idx, p.visitante_idx) AND substr(p.data, 1, 4) = ? "
        "ORDER BY p.data", (cid, clube, str(ano)))]


def resumo(con: sqlite3.Connection, cid: int, ano: int) -> dict:
    clube = _ultima(con, cid)["clube_idx"]
    r = {"jogos": 0, "vitorias": 0, "empates": 0, "derrotas": 0, "gols_pro": 0, "gols_contra": 0}
    jogadas = [p for p in partidas(con, cid, ano) if p["disputada"]]
    for p in jogadas:
        pro, contra = ((p["gols_mandante"], p["gols_visitante"]) if p["mandante_idx"] == clube
                       else (p["gols_visitante"], p["gols_mandante"]))
        r["jogos"] += 1
        r["gols_pro"] += pro
        r["gols_contra"] += contra
        r["vitorias" if pro > contra else "derrotas" if pro < contra else "empates"] += 1
    r["ultimas"] = jogadas[-5:][::-1]
    return r


# ponytail: o clube é o da sincronização mais recente; se o usuário trocar de clube, a história do anterior some daqui.
_ESTATS = (
    "SELECT e.player_id, coalesce(j.nome, 'Jogador #' || e.player_id) AS nome, count(*) AS jogos,"
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
    atuais = {r[0]: r[1] for r in con.execute(
        "SELECT e.player_id, coalesce(j.nome, 'Jogador #' || e.player_id) FROM elenco e "
        "LEFT JOIN jogador j ON j.player_id = e.player_id WHERE e.sincronizacao_id = ?", (s["id"],))}
    for pid, nome in atuais.items():
        linhas.setdefault(pid, {"player_id": pid, "nome": nome, "jogos": 0, "gols": 0, "assistencias": 0})
    for pid, linha in linhas.items():
        linha["no_elenco"] = pid in atuais
    return sorted(linhas.values(), key=lambda l: (-l["jogos"], l["nome"]))


def lendas(con: sqlite3.Connection, cid: int, limite: int = 10) -> dict:
    s = _ultima(con, cid)
    todos = [dict(r) for r in con.execute(_ESTATS + "GROUP BY e.player_id", {"cid": cid, "clube": s["clube_idx"]})]

    def top(k):
        return sorted(todos, key=lambda l: (-l[k], l["nome"]))[:limite]

    return {"artilheiros": top("gols"), "garcons": top("assistencias"), "mais_jogos": top("jogos")}
