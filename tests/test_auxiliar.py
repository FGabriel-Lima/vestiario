from datetime import datetime

import pytest
from conftest import atuacao, fazer_save, partida

from vestiario import auxiliar, banco, ia
from vestiario.leitor import MOEDA

AGORA = datetime(2026, 10, 15, 10, 0)


@pytest.fixture
def con():
    c = banco.conectar(":memory:")
    banco.gravar_nomes(c, {10: "Zagueiro", 11: "Outro Zagueiro", 12: "Atacante"}, {10: 1, 11: 1, 12: 12})
    banco.gravar(c, "ML00000000", fazer_save("2026-03-01", [
        partida("2026-02-01", 0, 1, (2, 0), [atuacao(10, 0, 1), atuacao(12, 0, 1)]),
        partida("2026-02-08", 2, 0, (1, 1), [atuacao(12, 1, 1)]),
    ], elenco=(10, 11, 12), idades={10: 35, 11: 24}, valores={10: 8000},
        contratos={10: (16182, 10160, "2027-01-31")}, orcamento=87333, propostas=[(1, 10, 8320)]), AGORA)
    yield c
    c.close()


def test_fatos_da_proposta_so_com_dados_existentes(con):
    f = banco.fatos_da_proposta(con, 1, 10, 1, 8320)
    assert f["proposta"] == {"clube_interessado": "Clube B", "valor_oferecido": 8320 * MOEDA}
    j = f["jogador"]
    assert (j["nome"], j["idade"], j["posicao"], j["valor_de_mercado"]) == ("Zagueiro", 35, "ZC", 8000 * MOEDA)
    assert j["contrato"] == {"salario_semanal": 16182 // 52 * MOEDA, "multa_rescisoria": 10160 * MOEDA, "fim": "2027-01-31"}
    assert j["temporada"] == {"jogos": 1, "gols": 1, "assistencias": 0, "jogos_do_clube": 2, "minutos_jogados": 90,
                              "nota_media": 6.0}
    assert f["elenco_na_mesma_posicao"] == [{"nome": "Outro Zagueiro", "idade": 24}]
    assert f["clube"] == {"nome": "Clube A", "orcamento_de_transferencias": 87333 * MOEDA,
                          "folha_salarial_semanal": 16182 // 52 * MOEDA, "data_no_jogo": "2026-03-01"}
    assert "dados_que_nao_temos" not in f
    assert banco.fatos_da_proposta(con, 1, 10, 1, 999) is None  # proposta que não existe


def test_fatos_dizem_o_que_falta():
    c = banco.conectar(":memory:")
    banco.gravar(c, "ML00000000", fazer_save("2026-03-01", elenco=(10,), propostas=[(1, 10, 500)]), AGORA)
    assert banco.fatos_da_proposta(c, 1, 10, 1, 500)["dados_que_nao_temos"] == [
        "valor de mercado do jogador", "idade", "contrato"]


def test_parecer_fica_guardado(con, monkeypatch):
    chamadas = []

    def falso(sistema, fatos, esquema):
        chamadas.append(fatos)
        return {"parecer": "Oferta acima do valor por um zagueiro de 35 anos.", "recomendacao": "aceitar"}

    monkeypatch.setattr(ia, "responder", falso)
    p = auxiliar.parecer_da_proposta(con, 1, 10, 1, 8320)
    assert (p["recomendacao"], p["fatos"]["jogador"]["nome"]) == ("aceitar", "Zagueiro")
    assert auxiliar.parecer_da_proposta(con, 1, 10, 1, 8320)["parecer"] == p["parecer"]
    assert len(chamadas) == 1
    assert banco.propostas(con, 1)[0]["parecer"]["recomendacao"] == "aceitar"


def test_recomendacao_fora_da_lista_vira_erro(con, monkeypatch):
    monkeypatch.setattr(ia, "responder", lambda *a: {"parecer": "x", "recomendacao": "vender já"})
    with pytest.raises(ia.IAIndisponivel):
        auxiliar.parecer_da_proposta(con, 1, 10, 1, 8320)


def test_sem_chave(monkeypatch, tmp_path):
    monkeypatch.delenv("VESTIARIO_GEMINI_KEY", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    with pytest.raises(ia.IAIndisponivel, match="VESTIARIO_GEMINI_KEY"):
        ia.chave()


def test_demora_do_flash_cai_para_o_flash_lite(monkeypatch):
    import io
    import json as js
    usados = []

    def abrir(req, timeout):
        usados.append(req.full_url.split("/models/")[1].split(":")[0])
        if len(usados) == 1:
            raise TimeoutError("The read operation timed out")
        corpo = {"candidates": [{"content": {"parts": [{"text": js.dumps({"ok": True})}]}}]}
        return io.BytesIO(js.dumps(corpo).encode())

    from conftest import RESPONDER_REAL
    monkeypatch.setattr(ia, "responder", RESPONDER_REAL)
    monkeypatch.setenv("VESTIARIO_GEMINI_KEY", "teste")
    monkeypatch.setattr(ia.urllib.request, "urlopen", abrir)
    assert ia.responder("x", {}, {}) == {"ok": True}
    assert usados == list(ia.MODELOS)
