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
                " penaltis_mandante, penaltis_visitante, disputada) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id",
                (cid, *chave, *p.gols, *p.penaltis, int(p.disputada)),
            ).fetchone()[0]
            con.executemany("INSERT INTO escalacao VALUES(?, ?, ?, ?, ?)",
                            [(pid, a.player_id, a.lado, a.gols, a.assistencias) for a in p.escalacao])
        return {"carreira_id": cid, "novas": novas, "atualizadas": atualizadas}
