import sqlite3
from datetime import datetime

import pytest
from conftest import atuacao, fazer_save, partida

from vestiario import banco

AGORA = datetime(2026, 10, 17, 10, 0)


@pytest.fixture
def con():
    c = banco.conectar(":memory:")
    yield c
    c.close()


def no_clube(con, data, clube_idx, partidas=()):
    """Save da 'Liga Master 01' no slot ML00000000 com o técnico no clube de índice clube_idx."""
    banco.gravar(con, "ML00000000", fazer_save(data, list(partidas), clube_idx=clube_idx), AGORA)


def test_outro_clube_abre_uma_passagem_nova(con):
    no_clube(con, "2026-03-01", 0)
    no_clube(con, "2027-01-10", 1)
    assert [tuple(r) for r in con.execute("SELECT id, slot, nome, clube_idx FROM carreira ORDER BY id")] == [
        (1, "ML00000000", "Liga Master 01", 0), (2, "ML00000000", "Liga Master 01", 1)]
    ps = banco._passagens_curtas(con, 1)
    assert [(p["id"], p["clube_nome"], p["inicio"], p["fim"], p["atual"], p["motivo_saida"]) for p in ps] == [
        (1, "Clube A", "2026-03-01", "2026-03-01", False, "trocou de clube"),
        (2, "Clube B", "2027-01-10", "2027-01-10", True, None)]
    assert banco._passagens_curtas(con, 2) == ps  # a mesma lista vista de qualquer passagem
    assert banco.carreira(con, 1)["encerrada"] == {"data": "2026-03-01", "motivo": "trocou de clube"}
    assert banco.carreira(con, 2)["encerrada"] is None
    assert banco.carreira(con, 2)["passagens"] == [{"id": 1, "clube_nome": "Clube A", "atual": False},
                                                   {"id": 2, "clube_nome": "Clube B", "atual": True}]


def test_demissao_vira_o_motivo_da_saida(con):
    no_clube(con, "2026-03-01", 0)
    con.execute("INSERT INTO confianca VALUES(1, 0, 'demissao:2026-02-20', '2026-03-01', 'Demitido', 0)")
    no_clube(con, "2027-01-10", 1)
    assert banco.carreira(con, 1)["encerrada"]["motivo"] == "demitido"


def test_volta_ao_clube_antigo_retoma_a_passagem(con):
    no_clube(con, "2026-03-01", 0)
    no_clube(con, "2027-01-10", 1)
    no_clube(con, "2028-01-10", 0)
    assert con.execute("SELECT count(*) FROM carreira").fetchone()[0] == 2
    assert banco.carreira(con, 1)["encerrada"] is None and banco.carreira(con, 2)["encerrada"]["motivo"] == "trocou de clube"


def test_lista_de_carreiras_mostra_so_a_passagem_atual(con):
    no_clube(con, "2026-03-01", 0)
    no_clube(con, "2027-01-10", 1)
    banco.gravar(con, "ML00000001", fazer_save("2026-05-01", nome="Liga Master 02"), AGORA)
    lista = banco.carreiras(con)
    assert sorted((c["id"], c["clube_nome"]) for c in lista) == [(2, "Clube B"), (3, "Clube A")]
    c2 = next(c for c in lista if c["id"] == 2)
    assert c2["outras_passagens"] == [{"id": 1, "clube_nome": "Clube A", "inicio": "2026-03-01", "fim": "2026-03-01"}]
    assert next(c for c in lista if c["id"] == 3)["outras_passagens"] == []


def test_banco_sem_clube_na_carreira_ganha_a_coluna_e_mantem_os_ids(tmp_path):
    arq = tmp_path / "v.db"
    c = banco.conectar(arq)
    banco.gravar(c, "ML00000000", fazer_save("2026-03-01", clube_idx=2), AGORA)
    c.close()
    antigo = sqlite3.connect(arq)  # volta a tabela carreira ao formato antigo, sem o clube
    antigo.executescript("PRAGMA foreign_keys = OFF; CREATE TABLE velha(id INTEGER PRIMARY KEY, slot TEXT NOT NULL, "
                         "nome TEXT NOT NULL, UNIQUE(slot, nome)); INSERT INTO velha SELECT id, slot, nome FROM carreira; "
                         "DROP TABLE carreira; ALTER TABLE velha RENAME TO carreira;")
    antigo.close()
    c = banco.conectar(arq)
    assert [tuple(r) for r in c.execute("SELECT id, slot, nome, clube_idx FROM carreira")] == [
        (1, "ML00000000", "Liga Master 01", 2)]
    assert banco.carreira(c, 1)["clube_nome"] == "Clube C"
    assert c.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    c.close()


def test_campanha_de_cada_passagem_pelo_periodo(con):
    # A (idx 0) até 2026-03-01: ganhou de B em 02/01 e perdeu para C em 20/02; depois treina B (idx 1) e ganha de C
    jogos_a = [partida("2026-01-02", 0, 1, (2, 0), [atuacao(10, 0)]), partida("2026-02-20", 2, 0, (1, 0), [atuacao(10, 1)])]
    no_clube(con, "2026-03-01", 0, jogos_a)
    jogos_b = jogos_a + [partida("2026-04-05", 1, 2, (3, 1), [atuacao(20, 0)])]
    no_clube(con, "2026-05-01", 1, jogos_b)
    r = banco.passagens(con, 2)
    a, b = r["passagens"]
    assert (a["clube_nome"], a["jogos"], a["vitorias"], a["derrotas"], a["aproveitamento"]) == ("Clube A", 2, 1, 1, 50)
    # o jogo de B em 02/01 (contra A) é de antes da passagem dele: não conta
    assert (b["clube_nome"], b["jogos"], b["vitorias"], b["aproveitamento"]) == ("Clube B", 1, 1, 100)
    assert r["total"] == {"clubes": 2, "jogos": 3, "vitorias": 2, "empates": 0, "derrotas": 1, "aproveitamento": 67,
                          "titulos": 0}
