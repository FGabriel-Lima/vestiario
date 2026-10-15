from datetime import datetime

import pytest
from conftest import atuacao, fazer_save, partida

from vestiario import banco, ia, jornal
from vestiario.leitor import MOEDA

AGORA = datetime(2026, 10, 15, 10, 0)
COMPETICOES = {29: "Brasileirão Série A"}


@pytest.fixture
def con():
    c = banco.conectar(":memory:")
    banco.gravar_nomes(c, {10: "Artilheiro", 11: "Reserva", 12: "Contratado", 50: "Rival"})
    liga = lambda dia, m, v, gols, esc, r: partida(dia, m, v, gols, esc, comp=29, rodada=r)
    # primeira sincronização: um jogo disputado
    banco.gravar(c, "ML00000000", fazer_save("2026-01-25", [
        liga("2026-01-22", 0, 1, (2, 0), [atuacao(10, 0, 2)], 0),
        liga("2026-02-01", 2, 0, (0, 0), [], 1), liga("2026-02-08", 1, 0, (0, 0), [], 2)],
        elenco=(10, 11), competicoes=COMPETICOES), AGORA)
    # segunda: mais um jogo, uma contratação e uma proposta
    banco.gravar(c, "ML00000000", fazer_save("2026-02-03", [
        liga("2026-01-22", 0, 1, (2, 0), [atuacao(10, 0, 2)], 0),
        liga("2026-02-01", 2, 0, (1, 3), [atuacao(10, 1, 1, 0), atuacao(12, 1, 2), atuacao(50, 0, 1)], 1),
        liga("2026-02-08", 1, 0, (0, 0), [], 2)],
        elenco=(10, 11, 12), competicoes=COMPETICOES, contratos={11: (5200, 0, "2026-06-30")},
        negocios=[(12, -1000, 1)], propostas=[(1, 10, 9000)]), AGORA)
    yield c
    c.close()


def test_fatos_da_edicao_so_trazem_o_periodo(con):
    f = banco.fatos_da_edicao(con, 1)
    assert (f["edicao"]["de"], f["edicao"]["ate"]) == ("2026-01-25", "2026-02-03")
    (jogo,) = f["resultados"]  # só o jogo de 01/02; o de 22/01 já foi noticiado na edição anterior
    assert (jogo["placar"], jogo["resultado"], jogo["competicao"]) == ("Clube C 1 x 3 Clube A", "vitória", "Brasileirão Série A")
    assert jogo["gols_do_clube"] == ["Contratado (2)", "Artilheiro"]
    assert f["classificacao"] == [{"competicao": "Brasileirão Série A", "posicao": 1, "pontos": 6, "jogos": 2,
                                   "rodadas_jogadas": 2, "rodadas_total": 3, "lider": "Clube A"}]
    assert f["chegaram"] == [{"nome": "Contratado", "veio_de": None, "valor": 1000 * MOEDA}]
    assert f["propostas"] == [{"clube_interessado": "Clube B", "jogador": "Artilheiro", "valor": 9000 * MOEDA}]
    assert f["contratos_vencendo"] == [{"nome": "Reserva", "fim": "2026-06-30"}]
    assert f["proximos_jogos"] == [{"data": "2026-02-08", "jogo": "Clube B x Clube A", "competicao": "Brasileirão Série A"}]
    assert f["artilheiros_do_clube"][0] == {"nome": "Artilheiro", "gols": 3}
    assert "sairam" not in f  # vazio fica de fora


def test_edicao_fica_guardada(con, monkeypatch):
    chamadas = []

    def falso(sistema, fatos, esquema):
        chamadas.append(fatos)
        return {"manchete": "Clube A vira e lidera", "linha_fina": "Contratado faz dois",
                "materias": [{"titulo": "Virada", "texto": "O Clube A venceu."}]}

    monkeypatch.setattr(ia, "responder", falso)
    e = jornal.rodar_edicao(con, 1)
    assert (e["data_jogo"], e["conteudo"]["manchete"]) == ("2026-02-03", "Clube A vira e lidera")
    assert jornal.rodar_edicao(con, 1)["conteudo"] == e["conteudo"]
    assert len(chamadas) == 1
    assert [x["data_jogo"] for x in banco.edicoes_do_jornal(con, 1)] == ["2026-02-03"]


def test_edicao_sem_materias_vira_erro(con, monkeypatch):
    monkeypatch.setattr(ia, "responder", lambda *a: {"manchete": "x", "linha_fina": "y", "materias": []})
    with pytest.raises(ia.IAIndisponivel):
        jornal.rodar_edicao(con, 1)
