import sqlite3
from datetime import datetime

import pytest
from conftest import atuacao, fazer_save, partida

from vestiario import banco
from vestiario.leitor import MOEDA

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


def test_tabela_de_times_diferente_recusa_o_save(con):
    banco.gravar(con, "ML00000000", fazer_save("2026-03-01"), AGORA)
    outro = fazer_save("2026-04-01")
    outro.times = ["Clube A", "Clube X", "Clube C"]
    with pytest.raises(ValueError, match="índice 1"):
        banco.gravar(con, "ML00000000", outro, AGORA)
    assert contar(con, "SELECT count(*) FROM sincronizacao") == 1


def test_elenco_de_temporada_passada_nao_inclui_contratados_depois(con):
    banco.gravar_nomes(con, {10: "Veterano", 12: "Novato"})
    banco.gravar(con, "ML00000000", fazer_save("2026-03-01", [
        partida("2025-06-01", 0, 1, (1, 0), [atuacao(10, 0, 1)])], elenco=(10, 12)), AGORA)
    assert [l["nome"] for l in banco.elenco(con, 1, 2025)] == ["Veterano"]
    assert {l["nome"] for l in banco.elenco(con, 1, 2026)} == {"Novato", "Veterano"}


def test_escudos_dos_times(con):
    save = fazer_save("2026-03-01", [partida("2026-01-22", 0, 1, (2, 1), [atuacao(10, 0, 2)])])
    save.ids = [1255, 137, 9]
    banco.gravar(con, "ML00000000", save, AGORA)
    assert banco.carreiras(con)[0]["escudo"] == 1255
    assert banco.carreira(con, 1)["escudo"] == 1255
    p = banco.partidas(con, 1, 2026)[0]
    assert (p["mandante_escudo"], p["visitante_escudo"]) == (1255, 137)
    assert banco.escudos(con) == {1255, 137, 9}


def test_banco_antigo_ganha_coluna_de_escudo_e_relê_os_saves(tmp_path):
    caminho = tmp_path / "v.db"
    antigo = sqlite3.connect(caminho)
    antigo.executescript("CREATE TABLE time(carreira_id INTEGER NOT NULL, idx INTEGER NOT NULL, nome TEXT NOT NULL,"
                         " PRIMARY KEY(carreira_id, idx));"
                         "CREATE TABLE arquivo(caminho TEXT PRIMARY KEY, tamanho INTEGER NOT NULL, mtime REAL NOT NULL);"
                         "INSERT INTO arquivo VALUES('x/ML00000000', 1, 1.0);")
    antigo.commit()
    antigo.close()
    con = banco.conectar(caminho)
    assert "pes_id" in {r[1] for r in con.execute("PRAGMA table_info(time)")}
    assert contar(con, "SELECT count(*) FROM arquivo") == 0
    con.close()


def test_rostos_sao_de_quem_passou_pelo_clube(con):
    banco.gravar(con, "ML00000000", fazer_save("2026-03-01", [
        partida("2026-01-22", 0, 1, (2, 1), [atuacao(10, 0), atuacao(99, 0), atuacao(50, 1)])], elenco=(10, 12)), AGORA)
    assert banco.rostos(con) == {10, 12, 99}  # 99 jogou e saiu; 50 é do adversário


def test_telas_da_parte_1(con):
    banco.gravar_nomes(con, {10: "Artilheiro", 11: "Garçom", 12: "Reserva", 13: "Novato", 50: "Rival"})
    banco.gravar(con, "ML00000000", fazer_save("2026-01-01", [], elenco=(10, 11, 12)), AGORA)
    banco.gravar(con, "ML00000000", fazer_save("2026-03-01", [
        partida("2026-01-22", 0, 1, (4, 0), [atuacao(10, 0, 3), atuacao(11, 0, 1, 2), atuacao(50, 1)]),
        partida("2026-02-01", 2, 0, (1, 1), [atuacao(10, 1, 1), atuacao(60, 0, 1)]),
        partida("2026-02-08", 0, 1, (0, 2), [atuacao(10, 0), atuacao(50, 1, 2)]),
        partida("2026-02-15", 1, 2, (5, 0), [atuacao(50, 0, 5)]),  # jogo entre outros times
        partida("2026-05-01", 0, 2),
    ], elenco=(10, 11, 13)), AGORA)

    s = banco.partida(con, 1, 1)
    assert (s["mandante"], s["visitante"]) == ("Clube A", "Clube B")
    assert [(e["nome"], e["lado"], e["gols"]) for e in s["escalacao"]] == [
        ("Artilheiro", 0, 3), ("Garçom", 0, 1), ("Rival", 1, 0)]
    assert banco.partida(con, 1, 99) is None

    c = {a["nome"]: (a["jogos"], a["vitorias"], a["empates"], a["derrotas"], len(a["partidas"]))
         for a in banco.confrontos(con, 1)}
    assert c == {"Clube B": (2, 1, 0, 1, 2), "Clube C": (1, 0, 1, 0, 1)}

    r = banco.recordes(con, 1)
    assert r["goleada"]["data"] == "2026-01-22" and r["derrota"]["data"] == "2026-02-08"
    assert r["vitorias"] == {"jogos": 1, "de": "2026-01-22", "ate": "2026-01-22"}
    assert r["invencibilidade"] == {"jogos": 2, "de": "2026-01-22", "ate": "2026-02-01"}
    assert [(h["nome"], h["gols"], h["partida"]["data"]) for h in r["hat_tricks"]] == [("Artilheiro", 3, "2026-01-22")]

    t = banco.transferencias(con, 1)
    assert t["primeira"] == "2026-01-01"
    assert [(j["de"], j["ate"]) for j in t["janelas"]] == [("2026-01-01", "2026-03-01")]
    assert [(p["nome"], p["jogos"]) for p in t["janelas"][0]["chegaram"]] == [("Novato", 0)]
    assert [(p["nome"], p["jogos"]) for p in t["janelas"][0]["sairam"]] == [("Reserva", 0)]

    m = banco.mundo(con, 1, 2026)
    assert m["partidas"] == 4
    assert [(l["nome"], l["gols"], l["time"]) for l in m["artilheiros"]] == [
        ("Rival", 7, "Clube B"), ("Artilheiro", 4, "Clube A"), ("Garçom", 1, "Clube A"), ("Jogador #60", 1, "Clube C")]
    assert [l["nome"] for l in m["garcons"]] == ["Garçom"]
    assert {50, 10} <= banco.rostos(con)


def test_transferencias_com_clube_de_origem_e_destino(con):
    banco.gravar_nomes(con, {12: "Vendido", 13: "Contratado", 14: "Dispensado"})
    # 13 está no Clube B e no C: vale o de índice mais baixo (os clubes vêm antes das seleções)
    banco.gravar(con, "ML00000000", fazer_save("2026-01-01", elenco=(10, 12, 14), outros=((13,), (13,))), AGORA)
    banco.gravar(con, "ML00000000", fazer_save("2026-01-01", elenco=(10, 12, 14), outros=((13,), (13,))), AGORA)
    banco.gravar(con, "ML00000000", fazer_save("2026-03-01", elenco=(10, 13), outros=((), (12,))), AGORA)
    assert contar(con, "SELECT count(DISTINCT sincronizacao_id) FROM vinculo") == 2  # uma por data do jogo
    j = banco.transferencias(con, 1)["janelas"][0]
    assert (j["origem_conhecida"], j["destino_conhecido"]) == (True, True)
    assert [(p["nome"], p["clube"]["nome"]) for p in j["chegaram"]] == [("Contratado", "Clube B")]
    assert {p["nome"]: p["clube"] and p["clube"]["nome"] for p in j["sairam"]} == {"Vendido": "Clube C",
                                                                                   "Dispensado": None}


def test_transferencias_de_snapshot_sem_vinculo(con):
    banco.gravar(con, "ML00000000", fazer_save("2026-01-01", elenco=(10, 12)), AGORA)
    con.execute("DELETE FROM vinculo")  # sincronização feita antes desta versão
    banco.gravar(con, "ML00000000", fazer_save("2026-03-01", elenco=(10, 13), outros=((12,), ())), AGORA)
    j = banco.transferencias(con, 1)["janelas"][0]
    assert (j["origem_conhecida"], j["destino_conhecido"]) == (False, True)
    assert j["chegaram"][0]["clube"] is None and j["sairam"][0]["clube"]["nome"] == "Clube B"


def test_banco_sem_vinculo_rele_os_saves(tmp_path):
    caminho = tmp_path / "v.db"
    banco.conectar(caminho).close()
    antigo = sqlite3.connect(caminho)
    antigo.executescript("DROP TABLE vinculo; INSERT INTO arquivo VALUES('x/ML00000000', 1, 1.0);")
    antigo.close()
    con = banco.conectar(caminho)
    assert contar(con, "SELECT count(*) FROM arquivo") == 0
    con.close()


def test_valores_das_transferencias(con):
    banco.gravar_nomes(con, {12: "Vendido", 13: "Contratado", 20: "Antigo"})
    # o livro do save já traz uma venda de antes da primeira sincronização
    banco.gravar(con, "ML00000000", fazer_save("2026-01-01", elenco=(10, 12), negocios=[(20, 1000, 5)],
                                               outros=((20,), ())), AGORA)
    banco.gravar(con, "ML00000000", fazer_save("2026-03-01", elenco=(10, 13), outros=((), (12,)),
                                               negocios=[(20, 1000, 5), (13, -500, 8), (12, 300, 5)]), AGORA)
    banco.gravar(con, "ML00000000", fazer_save("2026-03-01", elenco=(10, 13), outros=((), (12,)),
                                               negocios=[(20, 1000, 5), (13, -500, 8), (12, 300, 5)]), AGORA)
    assert contar(con, "SELECT count(*) FROM negocio") == 3
    recente, primeira = banco.transferencias(con, 1)["janelas"]
    assert (recente["gastos"], recente["receitas"]) == (500 * MOEDA, 300 * MOEDA)
    assert [(p["nome"], p["valor"], p["tipo"]) for p in recente["chegaram"]] == [("Contratado", -500 * MOEDA, 8)]
    assert [(p["nome"], p["valor"]) for p in recente["sairam"]] == [("Vendido", 300 * MOEDA)]
    assert (primeira["de"], primeira["ate"], primeira["chegaram"]) == (None, "2026-01-01", [])
    assert [(p["nome"], p["valor"], p["clube"]["nome"]) for p in primeira["sairam"]] == [("Antigo", 1000 * MOEDA, "Clube B")]


def test_contratos_no_elenco_e_fim_de_contrato_nas_transferencias(con):
    banco.gravar_nomes(con, {10: "Titular", 12: "Vencido", 13: "Vendido"})
    banco.gravar(con, "ML00000000", fazer_save("2026-01-01", elenco=(10, 12, 13), contratos={
        10: (17967, 60458, "2027-01-31"), 12: (5200, 0, "2026-01-31"), 13: (5200, 100, "2029-01-31")}), AGORA)
    banco.gravar(con, "ML00000000", fazer_save("2026-03-01", [partida("2026-02-01", 0, 1, (1, 0), [atuacao(10, 0, 1)])],
                                               elenco=(10,), contratos={10: (17967, 60458, "2027-01-31")}), AGORA)
    titular = banco.elenco(con, 1, 2026)[0]
    assert titular["contrato"] == {"salario_semanal": 345 * MOEDA, "multa": 60458 * MOEDA, "fim": "2027-01-31"}
    sairam = {p["nome"]: p["fim_de_contrato"] for p in banco.transferencias(con, 1)["janelas"][0]["sairam"]}
    assert sairam == {"Vencido": True, "Vendido": False}


def test_posicao_e_orcamento(con):
    banco.gravar_nomes(con, {10: "Goleiro", 11: "Atacante"}, {10: 0, 11: 12})
    banco.gravar(con, "ML00000000", fazer_save("2026-03-01", elenco=(10, 11), orcamento=1031606), AGORA)
    assert {l["nome"]: l["posicao"] for l in banco.elenco(con, 1, 2026)} == {"Goleiro": 0, "Atacante": 12}
    assert banco.carreira(con, 1)["orcamento"] == 1031606 * MOEDA
    banco.gravar_nomes(con, {10: "Goleiro"})  # sem posições (patch antigo): a posição gravada fica
    assert banco.elenco(con, 1, 2026)[0]["posicao"] in (0, 12)


def test_banco_sem_orcamento_ganha_as_colunas_e_rele_os_saves(tmp_path):
    caminho = tmp_path / "v.db"
    banco.conectar(caminho).close()
    antigo = sqlite3.connect(caminho)
    antigo.executescript("ALTER TABLE sincronizacao DROP COLUMN orcamento; ALTER TABLE jogador DROP COLUMN posicao;"
                         "INSERT INTO arquivo VALUES('x/ML00000000', 1, 1.0);")
    antigo.close()
    con = banco.conectar(caminho)
    assert contar(con, "SELECT count(*) FROM arquivo") == 0
    assert "posicao" in {r[1] for r in con.execute("PRAGMA table_info(jogador)")}
    con.close()
