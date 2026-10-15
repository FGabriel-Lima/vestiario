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


def test_idade_no_elenco(con):
    banco.gravar_nomes(con, {10: "Veterano", 11: "Sem idade"})
    banco.gravar(con, "ML00000000", fazer_save("2026-03-01", elenco=(10, 11), idades={10: 35, 99: 20}), AGORA)
    assert {l["nome"]: l["idade"] for l in banco.elenco(con, 1, 2026)} == {"Veterano": 35, "Sem idade": None}


def test_banco_sem_idade_ganha_a_coluna_e_rele_os_saves(tmp_path):
    caminho = tmp_path / "v.db"
    banco.conectar(caminho).close()
    antigo = sqlite3.connect(caminho)
    antigo.executescript("ALTER TABLE elenco DROP COLUMN idade; INSERT INTO arquivo VALUES('x/ML00000000', 1, 1.0);")
    antigo.close()
    con = banco.conectar(caminho)
    assert contar(con, "SELECT count(*) FROM arquivo") == 0
    con.close()


COMPETICOES = {29: "Brasileirão Série A", 31: "Copa do Brasil", 9: "Copa Libertadores", 10: "Copa Libertadores"}


def test_campeonatos(con):
    liga = lambda dia, m, v, gols, r: partida(dia, m, v, gols, [atuacao(10, 0)] if gols != (0, 0) or m == 0 else [],
                                             comp=29, rodada=r)
    banco.gravar(con, "ML00000000", fazer_save("2026-06-01", [
        # liga de 2025: B campeão
        liga("2025-04-01", 1, 0, (2, 0), 0), liga("2025-04-08", 2, 1, (0, 1), 1), liga("2025-04-15", 0, 2, (1, 1), 2),
        # liga de 2026 (a rodada volta a 0 depois de uma pausa longa); a rodada 2 ainda não foi jogada
        liga("2026-04-05", 0, 1, (3, 1), 0), liga("2026-04-12", 1, 2, (2, 2), 1), liga("2026-04-19", 2, 0, (0, 0), 2),
        # copa: semifinal (2 confrontos) e final
        partida("2026-05-01", 0, 1, (1, 0), [atuacao(10, 0)], comp=31, rodada=52),
        partida("2026-05-02", 2, 1, (0, 2), [], comp=31, rodada=52),
        partida("2026-05-20", 0, 1, (0, 0), [atuacao(10, 0)], (4, 3), comp=31, rodada=53),
        # libertadores: fase de grupos (id 9) e mata-mata (id 10) juntam numa edição só
        partida("2026-03-01", 0, 1, (2, 0), [atuacao(10, 0)], comp=9, grupo=1, rodada=0),
        partida("2026-03-01", 2, 1, (1, 0), [], comp=9, grupo=2, rodada=0),
        partida("2026-07-01", 0, 2, (1, 0), [atuacao(10, 0)], comp=10, rodada=53),
    ], competicoes=COMPETICOES), AGORA)

    eds = banco.edicoes(con, 1)
    assert [(e["nome"], e["temporada"]) for e in eds] == [
        ("Brasileirão Série A", "2026"), ("Copa do Brasil", "2026"), ("Copa Libertadores", "2026"),
        ("Brasileirão Série A", "2025")]

    liga26 = banco.edicao(con, 1, eds[0]["chave"])
    (fase,) = liga26["fases"]
    assert (fase["tipo"], fase["rodadas_jogadas"], fase["rodadas_total"]) == ("tabela", 2, 3)
    linhas = [(l["nome"], l["jogos"], l["pontos"], l["gols_pro"] - l["gols_contra"]) for l in fase["grupos"][0]["linhas"]]
    assert linhas == [("Clube A", 1, 3, 2), ("Clube C", 1, 1, 0), ("Clube B", 2, 1, -2)]

    liga25 = banco.edicao(con, 1, eds[3]["chave"])
    assert liga25["fases"][0]["grupos"][0]["linhas"][0]["nome"] == "Clube B"

    copa = banco.edicao(con, 1, eds[1]["chave"])
    assert [(f["titulo"], f["tipo"], len(f["partidas"])) for f in copa["fases"]] == [("Semifinal", "jogos", 2),
                                                                                     ("Final", "jogos", 1)]
    assert len(copa["partidas_clube"]) == 2

    lib = banco.edicao(con, 1, eds[2]["chave"])
    assert [(f["titulo"], f["tipo"]) for f in lib["fases"]] == [("Fase de grupos", "tabela"), ("Final", "jogos")]
    assert [g["titulo"] for g in lib["fases"][0]["grupos"]] == ["Grupo A", "Grupo B"]
    assert banco.partidas(con, 1, 2026)[0]["competicao"] == "Copa Libertadores"


def test_supercopa_de_cada_ano_e_uma_edicao(con):
    banco.gravar(con, "ML00000000", fazer_save("2026-03-01", [
        partida("2025-01-20", 1, 2, (1, 0), [atuacao(50, 0, 1)], comp=7, rodada=53),
        partida("2026-01-20", 2, 1, (2, 0), [atuacao(60, 0, 2)], comp=7, rodada=53),
    ], competicoes={7: "Supercopa"}), AGORA)
    assert [(e["nome"], e["temporada"]) for e in banco.edicoes(con, 1)] == [("Supercopa", "2026"), ("Supercopa", "2025")]


def test_partida_que_ja_estava_no_banco_ganha_a_competicao(con):
    banco.gravar(con, "ML00000000", fazer_save("2026-03-01", [partida("2026-02-01", 0, 1, (1, 0), [atuacao(10, 0)])]), AGORA)
    banco.gravar(con, "ML00000000", fazer_save("2026-03-01", [
        partida("2026-02-01", 0, 1, (1, 0), [atuacao(10, 0)], comp=29, rodada=0)], competicoes=COMPETICOES), AGORA)
    assert banco.partidas(con, 1, 2026)[0]["competicao"] == "Brasileirão Série A"


def test_jogo_avulso_sai_da_fase_de_grupos():
    jogo = lambda m, v: {"mandante_idx": m, "visitante_idx": v}
    grupo = [jogo(1, 2), jogo(3, 4), jogo(1, 3), jogo(2, 4), jogo(8, 9)]  # 8 x 9: marcado no grupo, mas só joga ali
    assert banco._sem_avulsos(grupo) == grupo[:4]


def jogo_de_copa(pid, data, m, v, gm, gv, pm=0, pv=0, disputada=1):
    nomes = "ABCDEFGH"
    return {"id": pid, "data": data, "mandante_idx": m, "visitante_idx": v, "mandante": f"Time {nomes[m]}",
            "visitante": f"Time {nomes[v]}", "mandante_escudo": None, "visitante_escudo": None, "gols_mandante": gm,
            "gols_visitante": gv, "penaltis_mandante": pm, "penaltis_visitante": pv, "disputada": disputada}


def test_chaveamento():
    fases = [
        {"titulo": "Semifinal", "tipo": "jogos", "partidas": [
            jogo_de_copa(1, "2026-05-01", 0, 1, 1, 0), jogo_de_copa(2, "2026-05-08", 1, 0, 2, 1),  # 2 x 2 no agregado
            jogo_de_copa(3, "2026-05-01", 2, 3, 0, 3), jogo_de_copa(4, "2026-05-08", 3, 2, 1, 1),
        ]},
        {"titulo": "Final", "tipo": "jogos", "partidas": [{**jogo_de_copa(5, "2026-05-20", 3, 0, 0, 0, 3, 4), "rodada": 53}]},
    ]
    semis, final = banco._chaveamento(fases)
    # a ordem da chave segue a final: o semifinalista que é mandante na final (D) vem primeiro
    assert [[t["nome"] for t in c["times"]] for c in semis["confrontos"]] == [["Time C", "Time D"], ["Time A", "Time B"]]
    assert [(t["gols"], t["vencedor"]) for t in semis["confrontos"][1]["times"]] == [(2, True), (2, False)]  # passou A
    assert [j["id"] for j in semis["confrontos"][1]["jogos"]] == [1, 2]
    assert (semis["encaixa"], final["encaixa"]) == (True, False)
    assert [(t["nome"], t["penaltis"], t["vencedor"]) for t in final["confrontos"][0]["times"]] == [
        ("Time D", 3, False), ("Time A", 4, True)]


def test_chaveamento_sem_jogos_disputados():
    (fase,) = banco._chaveamento([{"titulo": "Final", "tipo": "jogos",
                                   "partidas": [jogo_de_copa(1, "2026-12-01", 0, 1, 0, 0, disputada=0)]}])
    assert [(t["gols"], t["vencedor"]) for t in fase["confrontos"][0]["times"]] == [(None, False), (None, False)]


def test_chave_reconstruida_pelos_times_quando_a_rodada_do_save_vem_trocada():
    # 4 quartas, 2 semis, final; o save gravou a quarta C x D com a rodada da semifinal (52)
    j = lambda pid, data, m, v, gm, gv, r: {**jogo_de_copa(pid, data, m, v, gm, gv), "rodada": r}
    fases = [
        {"titulo": "Quartas de final", "tipo": "jogos", "partidas": [
            j(1, "2026-03-01", 0, 1, 1, 0, 51), j(3, "2026-03-01", 4, 5, 2, 0, 51), j(4, "2026-03-01", 6, 7, 0, 1, 51)]},
        {"titulo": "Semifinal", "tipo": "jogos", "partidas": [
            j(2, "2026-03-01", 2, 3, 0, 3, 52), j(5, "2026-04-01", 0, 3, 1, 1, 52), j(6, "2026-04-01", 4, 7, 2, 1, 52)]},
        {"titulo": "Final", "tipo": "jogos", "partidas": [j(7, "2026-05-01", 4, 0, 1, 0, 53)]},
    ]
    q, s, f = banco._chaveamento(fases)
    assert [c["titulo"] for c in (q, s, f)] == ["Quartas de final", "Semifinal", "Final"]
    assert all(c["encaixa"] for c in (q, s))
    nomes = lambda col: [[t["nome"] for t in c["times"]] if c else None for c in col["confrontos"]]
    assert nomes(f) == [["Time E", "Time A"]]
    assert nomes(s) == [["Time E", "Time H"], ["Time A", "Time D"]]
    assert nomes(q) == [["Time E", "Time F"], ["Time G", "Time H"], ["Time A", "Time B"], ["Time C", "Time D"]]


def test_jogo_unico_sozinho_numa_copa_de_ida_e_volta_sai_da_chave():
    # Monterrey x PSG gravado com o id do mata-mata da Champions, dois meses antes das oitavas
    fases = [{"titulo": "Oitavas de final", "tipo": "jogos", "partidas": [
        jogo_de_copa(1, "2025-12-19", 6, 0, 0, 2),
        jogo_de_copa(2, "2026-02-24", 0, 1, 1, 0), jogo_de_copa(3, "2026-03-17", 1, 0, 0, 0),
        jogo_de_copa(4, "2026-02-24", 2, 3, 2, 2), jogo_de_copa(5, "2026-03-17", 3, 2, 1, 0)]}]
    (oitavas,) = banco._chaveamento(fases)
    assert [[t["nome"] for t in c["times"]] for c in oitavas["confrontos"]] == [["Time A", "Time B"], ["Time C", "Time D"]]


def test_copa_de_jogo_unico_mantem_a_primeira_fase_com_um_confronto():
    fases = [{"titulo": "1ª fase", "tipo": "jogos", "partidas": [jogo_de_copa(1, "2025-03-14", 0, 1, 4, 0)]},
             {"titulo": "Oitavas de final", "tipo": "jogos", "partidas": [
                 jogo_de_copa(2, "2025-05-16", 0, 2, 0, 1), jogo_de_copa(3, "2025-05-16", 3, 4, 1, 0)]}]
    assert [len(c["confrontos"]) for c in banco._chaveamento(fases)] == [1, 2]


def test_classificacao_usa_confronto_direto_e_divide_a_posicao():
    # como no Brasileirão 2026 do save: Mirassol, São Paulo e Cuiabá com 3 pontos e 2-3; o Mirassol venceu o
    # São Paulo; São Paulo e Cuiabá não se enfrentaram e dividem a posição (a tela do PES mostra 11, 12, 12)
    jogos = [jogo_de_copa(1, "2026-01-20", 0, 1, 2, 0),   # M 2 x 0 S
             jogo_de_copa(2, "2026-01-27", 3, 0, 3, 0),   # X 3 x 0 M
             jogo_de_copa(3, "2026-01-20", 1, 4, 2, 1),   # S 2 x 1 I
             jogo_de_copa(4, "2026-01-20", 2, 5, 2, 0),   # C 2 x 0 Y
             jogo_de_copa(5, "2026-01-27", 6, 2, 3, 0)]   # Z 3 x 0 C
    linhas = banco._classificacao(jogos)
    assert [(l["nome"], l["posicao"]) for l in linhas] == [
        ("Time D", 1), ("Time G", 1), ("Time A", 3), ("Time B", 4), ("Time C", 4), ("Time E", 6), ("Time F", 7)]



def test_empate_triplo_sem_confronto_entre_dois_deles_nao_divide_com_quem_tem_mais_pontos_diretos():
    # A, B e C terminam iguais (3 pontos, 1-1); A venceu C; B não jogou contra nenhum dos dois
    jogos = [jogo_de_copa(1, "2026-01-20", 0, 2, 1, 0),   # A 1 x 0 C
             jogo_de_copa(2, "2026-01-27", 3, 0, 1, 0),   # D 1 x 0 A
             jogo_de_copa(3, "2026-01-20", 1, 4, 1, 0),   # B 1 x 0 E
             jogo_de_copa(4, "2026-01-27", 5, 1, 1, 0),   # F 1 x 0 B
             jogo_de_copa(5, "2026-01-27", 2, 6, 1, 0)]   # C 1 x 0 G
    pos = {l["nome"]: l["posicao"] for l in banco._classificacao(jogos)}
    assert (pos["Time A"], pos["Time B"], pos["Time C"]) == (3, 4, 4)  # D e F dividem o 1º; A à frente; B e C dividem
