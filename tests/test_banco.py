from datetime import datetime

import pytest
from conftest import atuacao, fazer_save, partida

from vestiario import banco

AGORA = datetime(2026, 10, 14, 20, 0)


@pytest.fixture
def con():
    c = banco.conectar(":memory:")
    yield c
    c.close()


def contar(con, sql="SELECT count(*) FROM partida"):
    return con.execute(sql).fetchone()[0]


def test_sincronizar_duas_vezes_nao_duplica(con):
    save = fazer_save(partidas=[partida("2026-01-22", 0, 1, (2, 1), [atuacao(10, 0, 2)]),
                                partida("2026-04-01", 1, 0)])
    assert banco.gravar(con, "ML00000000", save, AGORA) == {"carreira_id": 1, "novas": 1, "atualizadas": 0}
    assert banco.gravar(con, "ML00000000", save, AGORA) == {"carreira_id": 1, "novas": 0, "atualizadas": 0}
    assert contar(con) == 2
    assert contar(con, "SELECT count(*) FROM escalacao") == 1
    assert contar(con, "SELECT count(*) FROM carreira") == 1


def test_partida_que_some_do_save_continua(con):
    banco.gravar(con, "ML00000000", fazer_save("2026-02-01", [partida("2025-05-01", 0, 1, (1, 0), [atuacao(10, 0, 1)])]), AGORA)
    banco.gravar(con, "ML00000000", fazer_save("2026-03-01", [partida("2026-02-10", 0, 2, (0, 0), [atuacao(10, 0)])]), AGORA)
    assert contar(con) == 2


def test_futura_vira_disputada(con):
    banco.gravar(con, "ML00000000", fazer_save("2026-02-01", [partida("2026-02-10", 0, 1)]), AGORA)
    r = banco.gravar(con, "ML00000000",
                     fazer_save("2026-03-01", [partida("2026-02-10", 0, 1, (3, 0), [atuacao(10, 0, 3)])]), AGORA)
    assert r["atualizadas"] == 1
    assert con.execute("SELECT gols_mandante, disputada FROM partida").fetchone()[:] == (3, 1)
    assert contar(con, "SELECT count(*) FROM escalacao") == 1


def test_save_antigo_nao_regride(con):
    banco.gravar(con, "ML00000000",
                 fazer_save("2026-03-01", [partida("2026-02-10", 0, 1, (3, 0), [atuacao(10, 0, 3)])]), AGORA)
    banco.gravar(con, "ML00000000", fazer_save("2026-02-01", [partida("2026-02-10", 0, 1),
                                                             partida("2026-02-20", 2, 0)]), AGORA)
    assert [tuple(r) for r in con.execute("SELECT gols_mandante, disputada FROM partida")] == [(3, 1)]


def test_futura_remarcada_some(con):
    banco.gravar(con, "ML00000000", fazer_save("2026-02-01", [partida("2026-02-10", 0, 1)]), AGORA)
    banco.gravar(con, "ML00000000", fazer_save("2026-02-05", [partida("2026-02-17", 0, 1)]), AGORA)
    assert [r[0] for r in con.execute("SELECT data FROM partida")] == ["2026-02-17"]


def test_nome_diferente_no_slot_e_outra_carreira(con):
    banco.gravar(con, "ML00000000", fazer_save(nome="Liga Master 01"), AGORA)
    banco.gravar(con, "ML00000000", fazer_save(nome="Liga Master 09"), AGORA)
    assert contar(con, "SELECT count(*) FROM carreira") == 2


def test_arquivo_visto(con):
    assert not banco.arquivo_visto(con, "x/ML00000000", 10, 1.5)
    banco.marcar_arquivo(con, "x/ML00000000", 10, 1.5)
    assert banco.arquivo_visto(con, "x/ML00000000", 10, 1.5)
    assert not banco.arquivo_visto(con, "x/ML00000000", 10, 2.0)


def test_save_antigo_com_jogo_que_o_banco_tem_como_futuro(con):
    banco.gravar(con, "ML00000000", fazer_save("2026-03-01", [partida("2026-03-05", 0, 1)]), AGORA)
    r = banco.gravar(con, "ML00000000",
                     fazer_save("2026-02-01", [partida("2026-03-05", 0, 1, (1, 0), [atuacao(10, 0, 1)])]), AGORA)
    assert r["atualizadas"] == 1
    assert [tuple(x) for x in con.execute("SELECT gols_mandante, disputada FROM partida")] == [(1, 1)]
    assert contar(con, "SELECT count(*) FROM escalacao") == 1


def test_consultas(con):
    banco.gravar_nomes(con, {10: "Artilheiro", 11: "Garçom", 12: "Reserva"})
    banco.gravar(con, "ML00000000", fazer_save("2026-03-01", [
        partida("2025-11-01", 1, 0, (0, 1), [atuacao(10, 1, 1), atuacao(99, 0)]),
        partida("2026-01-22", 0, 1, (2, 1), [atuacao(10, 0, 2), atuacao(11, 0, 0, 2), atuacao(50, 1, 1)]),
        partida("2026-02-01", 2, 0, (1, 1), [atuacao(11, 1, 1), atuacao(10, 1)]),
        partida("2026-02-08", 0, 2, (0, 2), [atuacao(10, 0)]),
        partida("2026-05-01", 0, 1),
    ]), AGORA)

    assert banco.carreiras(con)[0]["clube_nome"] == "Clube A"
    assert banco.temporadas(con, 1) == [2026, 2025]

    r = banco.resumo(con, 1, 2026)
    assert {k: r[k] for k in ("jogos", "vitorias", "empates", "derrotas", "gols_pro", "gols_contra")} == {
        "jogos": 3, "vitorias": 1, "empates": 1, "derrotas": 1, "gols_pro": 3, "gols_contra": 4}
    assert r["ultimas"][0]["data"] == "2026-02-08"

    assert len(banco.partidas(con, 1, 2026)) == 4

    el = {l["nome"]: (l["jogos"], l["gols"], l["assistencias"], l["no_elenco"]) for l in banco.elenco(con, 1, 2026)}
    assert el == {"Artilheiro": (3, 2, 0, True), "Garçom": (2, 1, 2, True), "Reserva": (0, 0, 0, True)}

    lendas = banco.lendas(con, 1)
    assert [(l["nome"], l["gols"]) for l in lendas["artilheiros"][:2]] == [("Artilheiro", 3), ("Garçom", 1)]
    assert lendas["garcons"][0]["nome"] == "Garçom"
    assert lendas["mais_jogos"][0]["jogos"] == 4
