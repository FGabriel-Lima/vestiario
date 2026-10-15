from datetime import datetime

import pytest
from conftest import atuacao, fazer_save, partida

from vestiario import banco, conversas, ia
from vestiario.leitor import MOEDA

AGORA = datetime(2026, 10, 15, 10, 0)


@pytest.fixture
def con():
    c = banco.conectar(":memory:")
    banco.gravar_nomes(c, {10: "Titular", 11: "Reserva", 12: "Veterano"}, {10: 12, 11: 12, 12: 0})
    banco.gravar(c, "ML00000000", fazer_save("2026-03-01", [
        partida("2026-02-01", 0, 1, (2, 0), [atuacao(10, 0, 2, 0, 90, 76), atuacao(11, 0, 0, 0, 10, None)]),
        partida("2026-02-08", 1, 0, (0, 0), [atuacao(10, 1, 0, 0, 90, 60)]),
        partida("2026-03-10", 0, 2),
    ], elenco=(10, 11, 12), idades={10: 25, 11: 19, 12: 36}, valores={10: 8000},
        contratos={10: (16182, 10160, "2028-01-31"), 12: (5200, 0, "2026-06-30")},
        orcamento=87333, propostas=[(1, 10, 9000)]), AGORA)
    yield c
    c.close()


def test_contatos_com_auxiliar_no_topo_e_sinais(con):
    cs = conversas.contatos(con, 1)
    assert cs[0]["contato"] == "auxiliar"
    por_nome = {c["nome"]: c for c in cs[1:]}
    assert [c["nome"] for c in cs[1:]] == ["Veterano", "Reserva", "Titular"]  # goleiro antes, depois por nome no setor
    assert por_nome["Titular"]["sinais"] == ["titular", "em boa fase", "proposta do Clube B"]
    assert por_nome["Reserva"]["sinais"] == ["joga pouco", "jovem"]
    assert por_nome["Veterano"]["sinais"] == ["joga pouco", "contrato vencendo", "veterano"]


def test_fatos_do_jogador(con):
    f = banco.fatos_do_jogador(con, 1, 10)
    assert f["jogador"]["temporada"] == {"jogos": 2, "gols": 2, "assistencias": 0, "jogos_do_clube": 2,
                                         "minutos_jogados": 180, "nota_media": 6.8}
    assert f["jogador"]["ultimos_jogos"][0] == {"data": "2026-02-08", "adversario": "Clube B", "minutos": 90,
                                                "nota": 6.0, "gols": 0, "assistencias": 0}
    assert f["propostas_abertas"] == [{"clube": "Clube B", "valor": 9000 * MOEDA}]
    assert f["proximo_jogo"] == {"data": "2026-03-10", "adversario": "Clube C", "em_casa": True}


def test_fatos_do_clube_para_o_auxiliar(con):
    f = banco.fatos_do_clube(con, 1)
    assert f["clube"]["orcamento_de_transferencias"] == 87333 * MOEDA
    assert [j["nome"] for j in f["elenco"]] == ["Veterano", "Reserva", "Titular"]
    assert f["propostas_abertas"] == [{"clube": "Clube B", "jogador": "Titular", "valor": 9000 * MOEDA}]
    assert f["contratos_vencendo"] == [{"nome": "Veterano", "fim": "2026-06-30"}]


def test_conversa_guardada_e_atalhos(con, monkeypatch):
    recebido = []

    def falso(sistema, fatos, esquema):
        recebido.append(fatos)
        return {"resposta": "Professor, tô bem."}

    monkeypatch.setattr(ia, "responder", falso)
    assert [a for a in conversas.conversa(con, 1, "10")["atalhos"]] == [
        "Como você está?", "Sobre os seus minutos", "Seu contrato", "A proposta do Clube B"]
    r = conversas.responder(con, 1, "10", "Como você está?")
    assert r["mensagens"][-2:] == [{"autor": "tecnico", "texto": "Como você está?", "data_jogo": "2026-03-01"},
                                   {"autor": "contato", "texto": "Professor, tô bem.", "data_jogo": "2026-03-01"}]
    conversas.responder(con, 1, "10", "E a proposta?")
    assert [m["texto"] for m in recebido[-1]["conversa_ate_agora"]] == ["Como você está?", "Professor, tô bem."]
    assert recebido[-1]["mensagem_do_treinador"] == "E a proposta?"
    assert conversas.contatos(con, 1)[3]["ultima"] == "Professor, tô bem."
    assert conversas.conversa(con, 1, "auxiliar")["atalhos"][0] == "Como está o elenco?"


def test_contato_que_nao_e_do_elenco(con):
    assert conversas.conversa(con, 1, "999") is None
    with pytest.raises(ValueError):
        conversas.responder(con, 1, "10", "   ")


def test_promessa_guardada_e_cobrada_com_os_jogos_depois_dela(con, monkeypatch):
    recebido = []

    def falso(sistema, fatos, esquema):
        recebido.append(fatos)
        return {"resposta": "Valeu, professor.", "promessa": "mais minutos nos próximos jogos" if len(recebido) == 1 else ""}

    monkeypatch.setattr(ia, "responder", falso)
    conversas.responder(con, 1, "11", "Você vai ter mais minutos.")
    assert "promessa feita" in next(c for c in conversas.contatos(con, 1) if c["nome"] == "Reserva")["sinais"]
    # o jogo de 10/03 vem depois da promessa (feita em 01/03): o Reserva jogou 20 minutos nele
    banco.gravar(con, "ML00000000", fazer_save("2026-03-20", [
        partida("2026-02-01", 0, 1, (2, 0), [atuacao(10, 0, 2, 0, 90, 76), atuacao(11, 0, 0, 0, 10, None)]),
        partida("2026-02-08", 1, 0, (0, 0), [atuacao(10, 1, 0, 0, 90, 60)]),
        partida("2026-03-10", 0, 2, (1, 0), [atuacao(10, 0, 1, 0, 90, 70), atuacao(11, 0, 0, 0, 20, 58)]),
    ], elenco=(10, 11, 12)), AGORA)
    conversas.responder(con, 1, "11", "E aí?")
    assert recebido[-1]["fatos"]["promessas_do_professor"] == [{
        "promessa": "mais minutos nos próximos jogos", "feita_em": "2026-03-01",
        "desde_entao": {"jogos_do_clube": 1, "jogos": 1, "minutos": 20, "nota_media": 5.8}}]
    assert len(banco.promessas(con, 1, 11)) == 1  # promessa vazia não é guardada
    assert "promessas_do_professor" not in banco.fatos_do_jogador(con, 1, 10)
