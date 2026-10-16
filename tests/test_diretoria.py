from datetime import datetime

import pytest
from conftest import atuacao, fazer_save, partida

from vestiario import banco, diretoria, ia
from vestiario.leitor import MOEDA

AGORA = datetime(2026, 10, 16, 10, 0)
COMPS = {29: "Brasileirão Série A", 163: "Brasileirão Série B", 31: "Copa do Brasil"}


@pytest.fixture
def con():
    c = banco.conectar(":memory:")
    yield c
    c.close()


def jogo(dia, m, v, gols=(0, 0), rodada=0, comp=29, disputada=True):
    """Disputado = com escalação (é assim que o banco sabe que o jogo aconteceu)."""
    # gols diferentes de 0 x 0 também contam como disputada (Partida.disputada), então o jogo futuro zera o placar
    return partida(dia, m, v, gols if disputada else (0, 0), [atuacao(50, 0)] if disputada else [], comp=comp,
                   rodada=rodada)


def temporada(ano, ate_rodada, total=4, comp=29):
    """Liga de 3 times (A = 0, o clube do usuário; B = 1; C = 2), uma partida por rodada, no dia 10 de fevereiro em
    diante; o mandante ganha de 1 a 0. Disputadas as rodadas antes de `ate_rodada`."""
    pares = [(0, 1), (1, 2), (2, 0)]
    return [jogo(f"{ano}-{2 + r:02d}-10", *pares[r % 3], (1, 0), r, comp, disputada=r < ate_rodada)
            for r in range(total)]


def sincronizar(con, data, partidas, **kw):
    """Grava um save do Clube A. Valor de mercado dos elencos: A = 200, B = 500, C = 50 (A é o 2º)."""
    kw.setdefault("elenco", (10, 11, 12))
    kw.setdefault("outros", ((20, 21), (30,)))
    kw.setdefault("valores", {10: 100, 11: 100, 20: 500, 30: 50})
    kw.setdefault("competicoes", COMPS)
    banco.gravar(con, "ML00000000", fazer_save(data, list(partidas), **kw), AGORA)


def test_porte_pela_posicao_no_valor_do_elenco():
    assert [diretoria._porte(p) for p in (1, 4, 5, 12, 13, 20)] == [
        "grande", "grande", "medio", "medio", "pequeno", "pequeno"]


def test_divisao_pelo_nome_da_liga():
    assert [diretoria._divisao(n) for n in ("Brasileirão Série A", "Brasileirão Série B", "Premier League", None)] == [
        1, 2, 1, 1]


def test_perfil_do_clube(con):
    sincronizar(con, "2026-01-10", temporada(2026, 0), orcamento=10_000)
    p = diretoria.perfil(con, 1)
    assert (p["ano"], p["liga"]["nome"], p["divisao"], p["posicao_valor"], p["porte"]) == (
        2026, "Brasileirão Série A", 1, 2, "grande")
    assert (p["rebaixado"], p["promovido"], p["crise"], p["momento"]) == (False, False, False, "estreia")
    assert (p["liga"]["primeiro_jogo"], p["liga"]["encerrada"], p["liga"]["times"]) == ("2026-02-10", False, [0, 1, 2])
    assert p["orcamento"] == 10_000 * MOEDA and "receitas" in p["faltou"]


def test_rebaixado_pela_troca_de_divisao(con):
    sincronizar(con, "2026-01-10", temporada(2025, 4) + temporada(2026, 0, comp=163))
    p = diretoria.perfil(con, 1)
    assert (p["liga"]["nome"], p["divisao"], p["rebaixado"], p["promovido"]) == ("Brasileirão Série B", 2, True, False)


def test_crise_pela_folha_ou_pela_folga(con):
    # folha anual de 52.000 contra 70% de 1.000 de receita
    sincronizar(con, "2026-01-10", temporada(2026, 0), contratos={10: (52_000, 0, "2028-01-31")},
                receitas={"tv": 1000}, folga_salarial=100_000)
    assert diretoria.perfil(con, 1)["crise"] is True
    # receita folgada, mas a folga de 100 é menos de 5% do teto (100 + 52.000)
    sincronizar(con, "2026-01-11", temporada(2026, 0), contratos={10: (52_000, 0, "2028-01-31")},
                receitas={"tv": 10_000_000}, folga_salarial=100)
    p = diretoria.perfil(con, 1)
    assert p["crise"] is True and p["maiores_salarios"] == [10]


PERFIL = {"porte": "medio", "promovido": False, "rebaixado": False, "crise": False, "orcamento": 1_000_000,
          "folha_semanal": 50_000, "maiores_salarios": [10, 11, 12, 13, 14], "liga": {"times": list(range(20))},
          "copas": [{"nome": "Copa Libertadores", "chave": "L|2026"}, {"nome": "Copa do Brasil", "chave": "C|2026"}]}


def valores(itens):
    return {(i["tipo"], i.get("janela") or i.get("copa")): i["valor"] for i in itens}


def test_proposta_de_clube_medio():
    assert valores(diretoria.proposta(PERFIL)) == {
        ("meta_liga", None): 10, ("meta_copa", "Copa Libertadores"): 2, ("meta_copa", "Copa do Brasil"): 1,
        ("contratacoes", 1): 3, ("contratacoes", 2): 2, ("teto_contratacao", None): 40,
        ("vender_para_comprar", None): 50, ("livres", None): 1, ("emprestimos", None): 2}


def test_crise_sobrescreve_o_porte():
    v = valores(diretoria.proposta({**PERFIL, "crise": True}))
    assert (v[("meta_liga", None)], v[("contratacoes", 1)], v[("contratacoes", 2)], v[("vender_para_comprar", None)],
            v[("folha_maxima", None)], v[("vender_salarios", None)]) == (10, 1, 1, 100, 100, 1)


def test_rebaixado_quer_subir_e_vender_salarios():
    itens = diretoria.proposta({**PERFIL, "porte": "pequeno", "rebaixado": True})
    v = valores(itens)
    assert (v[("meta_liga", None)], v[("folha_maxima", None)], v[("vender_salarios", None)]) == (4, 80, 2)
    assert ("meta_copa", "Copa do Brasil") not in v  # clube pequeno não tem meta de copa
    assert diretoria.reais(next(i for i in itens if i["tipo"] == "folha_maxima")) == 40_000
    assert diretoria.reais(next(i for i in itens if i["tipo"] == "teto_contratacao")) == 250_000


def test_meta_da_liga_nao_passa_do_numero_de_times():
    assert valores(diretoria.proposta({**PERFIL, "liga": {"times": [0, 1, 2]}}))[("meta_liga", None)] == 3


def test_descricao_dos_itens():
    textos = [diretoria.descrever(i) for i in diretoria.proposta({**PERFIL, "crise": True})]
    assert "terminar a liga em 10º ou melhor" in textos
    assert "até 1 contratação na janela de janeiro" in textos
    assert "nenhuma compra acima de R$ 200 mil (20% do orçamento)" in textos
    assert "folha semanal de até R$ 50 mil" in textos
    assert "Copa Libertadores: chegar às quartas de final" in textos
    assert "vender 1 dos 5 maiores salários até 30/09" in textos
    assert diretoria._dinheiro(38_009_850) == "R$ 38 mi" and diretoria._dinheiro(1_250_000) == "R$ 1,2 mi"


def acordo_de_teste(itens, estado="assinado", ano=2026):
    return {"clube_idx": 0, "ano": ano, "estado": estado, "itens": itens}


def test_confianca_soma_presa_e_sem_repetir(con):
    sincronizar(con, "2026-01-10", temporada(2026, 0))
    assert diretoria.confianca(con, 1, 0) == 60
    for i in range(5):
        diretoria._evento(con, 1, 0, f"x{i}", "2026-01-10", "teste", -20)
    assert diretoria._evento(con, 1, 0, "x0", "2026-01-10", "teste", -20) is False
    assert diretoria.confianca(con, 1, 0) == 0
    diretoria._evento(con, 1, 0, "y", "2026-01-11", "teste", 10)
    assert diretoria.confianca(con, 1, 0) == 10  # presa em 0 antes de subir
    assert diretoria.historico(con, 1, 0)[0] == {"data_jogo": "2026-01-11", "motivo": "teste", "variacao": 10}


def mercado_movimentado(con):
    """13 comprado por 1.000, 14 sem negócio (agente livre), 15 emprestado; 11 vendido por 300."""
    sincronizar(con, "2026-01-10", temporada(2026, 0))
    sincronizar(con, "2026-02-01", temporada(2026, 0), elenco=(10, 12, 13, 14, 15),
                negocios=[(13, -1000, 1), (11, 300, 5)], contratos={15: (0, 0, "2026-12-31", True)})


def test_mercado_do_ano(con):
    mercado_movimentado(con)
    chegadas, saidas = diretoria.mercado(con, 1, 0, 2026)
    assert sorted((c["player_id"], c["janela"], c["valor"], c["emprestimo"]) for c in chegadas) == [
        (13, 1, -1000 * MOEDA, False), (14, 1, None, False), (15, 1, None, True)]
    assert [(s["player_id"], s["valor"]) for s in saidas] == [(11, 300 * MOEDA)]


def test_itens_quebrados_tiram_confianca_uma_vez(con):
    mercado_movimentado(con)
    itens = [diretoria._item("contratacoes", 2, janela=1), diretoria._item("teto_contratacao", 10, orcamento=1_000_000),
             diretoria._item("livres", 1), diretoria._item("emprestimos", 0), diretoria._item("vender_para_comprar", 50)]
    r = {i["tipo"]: i for i in diretoria.avaliar(con, 1, acordo_de_teste(itens), "2026-02-01")}
    assert (r["contratacoes"]["estado"], r["contratacoes"]["detalhe"]) == ("quebrado", {"usadas": 3})
    assert r["teto_contratacao"]["estado"] == "quebrado"  # 430 mil > 100 mil
    assert (r["livres"]["estado"], r["emprestimos"]["estado"]) == ("em_risco", "quebrado")
    assert r["vender_para_comprar"]["estado"] == "em_risco"  # 129 mil de vendas < 50% de 430 mil
    assert r["contratacoes"]["uso"] == "3 de 2 usadas"
    assert diretoria.confianca(con, 1, 0) == 60 - 15 - 10 - 15
    diretoria.avaliar(con, 1, acordo_de_teste(itens), "2026-02-01")
    assert diretoria.confianca(con, 1, 0) == 20  # a mesma quebra não conta duas vezes


def test_acordo_proposto_nao_gera_eventos(con):
    mercado_movimentado(con)
    r = diretoria.avaliar(con, 1, acordo_de_teste([diretoria._item("contratacoes", 1, janela=1)], estado="proposto"),
                          "2026-02-01")
    assert r[0]["estado"] == "quebrado" and diretoria.confianca(con, 1, 0) == 60


def test_folha_e_venda_de_salarios(con):
    sincronizar(con, "2026-01-10", temporada(2026, 0),
                contratos={10: (52_000, 0, "2028-01-31"), 11: (5_200, 0, "2028-01-31")})
    itens = [diretoria._item("folha_maxima", 90, folha=1100 * MOEDA),
             diretoria._item("vender_salarios", 1, jogadores=[10, 11])]
    r = {i["tipo"]: i for i in diretoria.avaliar(con, 1, acordo_de_teste(itens), "2026-01-10")}
    assert r["folha_maxima"]["estado"] == "quebrado"  # 1.100 × 430 por semana, acima de 90% disso
    assert r["vender_salarios"]["estado"] == "em_risco"
    r = {i["tipo"]: i for i in diretoria.avaliar(con, 1, acordo_de_teste(itens), "2026-10-01")}
    assert r["vender_salarios"]["estado"] == "quebrado"  # passou de 30/09 sem vender


def test_meta_da_liga_no_balanco(con):
    sincronizar(con, "2026-06-01", temporada(2026, 4))  # A: 1º com 6 pontos
    itens = [diretoria._item("meta_liga", 1)]
    r = diretoria.avaliar(con, 1, acordo_de_teste(itens), "2026-06-01", registrar=False, balanco=True)
    assert (r[0]["estado"], r[0]["detalhe"]["posicao"]) == ("cumprido", 1)


def test_reuniao_pendente_e_acordo_imposto_no_primeiro_jogo(con):
    sincronizar(con, "2026-01-10", temporada(2026, 0))
    diretoria.atualizar(con, 1)
    a = diretoria._acordo(con, 1, 0, 2026)
    assert a["estado"] == "proposto" and a["perfil"]["porte"] == "grande" and a["revisao_feita"] == 0
    assert [p["tipo"] for p in diretoria.pendencias(con, 1)] == ["reuniao"]
    sincronizar(con, "2026-02-15", temporada(2026, 1))  # o 1º jogo da liga foi em 10/02
    diretoria.atualizar(con, 1)
    a = diretoria._acordo(con, 1, 0, 2026)
    assert (a["estado"], a["assinado_data"]) == ("imposto", "2026-02-15")
    assert diretoria.confianca(con, 1, 0) == 55
    diretoria.atualizar(con, 1)
    assert diretoria.confianca(con, 1, 0) == 55  # imposto uma vez só


def test_balanco_no_fim_da_liga(con):
    sincronizar(con, "2026-06-30", temporada(2026, 4))  # liga toda disputada: A em 1º
    diretoria.atualizar(con, 1)
    a = diretoria._acordo(con, 1, 0, 2026)
    assert a["estado"] == "encerrado" and a["balanco"]["metas"] == {"meta_liga": "cumprido"}
    # sem imposição (o acordo nasceu depois do 1º jogo e ganha 30 dias); a meta de 3º foi cumprida: +15
    assert diretoria.confianca(con, 1, 0) == 60 + 15
    sincronizar(con, "2027-01-10", temporada(2026, 4) + temporada(2027, 0))
    diretoria.atualizar(con, 1)
    assert diretoria._acordo(con, 1, 0, 2027)["perfil"]["momento"] == "cumpriu"


def test_virada_do_ano_fecha_o_acordo_anterior(con):
    sincronizar(con, "2026-01-10", temporada(2026, 0))
    diretoria.atualizar(con, 1)
    sincronizar(con, "2027-01-05", temporada(2026, 2) + temporada(2027, 0))
    diretoria.atualizar(con, 1)
    assert diretoria._acordo(con, 1, 0, 2026)["estado"] == "encerrado"
    assert diretoria._acordo(con, 1, 0, 2027)["estado"] == "proposto"


def jogos_do_ultimato(resultados):
    """5 jogos A x B em março; `resultados` = placares dos que já foram disputados."""
    return [jogo(f"2026-03-0{i + 1}", 0, 1, resultados[i] if i < len(resultados) else (0, 0), rodada=i,
                 disputada=i < len(resultados)) for i in range(5)]


def ultimato_aberto(con):
    sincronizar(con, "2026-02-20", jogos_do_ultimato([]))
    diretoria.atualizar(con, 1)
    diretoria._evento(con, 1, 0, "teste", "2026-02-20", "teste", -50)
    diretoria.atualizar(con, 1)
    assert diretoria.pendencias(con, 1)[-1]["tipo"] == "ultimato"


def test_ultimato_cumprido_volta_a_30(con):
    ultimato_aberto(con)
    sincronizar(con, "2026-03-04", jogos_do_ultimato([(1, 0), (1, 0), (1, 1)]))  # 7 pontos
    diretoria.atualizar(con, 1)
    assert diretoria.confianca(con, 1, 0) == 30 and diretoria.demitido(con, 1, 0) is None


def test_ultimato_falhado_demite(con):
    ultimato_aberto(con)
    sincronizar(con, "2026-03-04", jogos_do_ultimato([(0, 1), (0, 1), (0, 1)]))  # 0 pontos, faltam 2 jogos
    diretoria.atualizar(con, 1)
    assert diretoria.demitido(con, 1, 0) == "2026-03-04"
    assert [p["tipo"] for p in diretoria.pendencias(con, 1)] == ["demissao"]


def test_cinco_derrotas_seguidas(con):
    sincronizar(con, "2026-01-01", jogos_do_ultimato([]))
    diretoria.atualizar(con, 1)
    sincronizar(con, "2026-03-06", jogos_do_ultimato([(0, 1)] * 5))
    diretoria.atualizar(con, 1)
    assert any(h["motivo"] == "5 derrotas seguidas" for h in diretoria.historico(con, 1, 0))


def acordo_proposto(con):
    sincronizar(con, "2026-01-10", temporada(2026, 0), orcamento=100_000, contratos={10: (52_000, 0, "2028-01-31")})
    diretoria.atualizar(con, 1)
    return diretoria._acordo(con, 1, 0, 2026)


def indice(acordo, tipo, janela=None):
    return next(n for n, i in enumerate(acordo["itens"]) if i["tipo"] == tipo and i.get("janela") == janela)


def test_cardapio_e_preco(con):
    a = acordo_proposto(con)  # grande: meta 3º (só 3 times), 4/3 contratações, preço 6 de confiança
    n = indice(a, "contratacoes", 1)
    ops = {o["id"]: o for o in diretoria.cardapio(a, 60)}
    assert (ops[f"{n}:confianca"]["novo"], ops[f"{n}:confianca"]["preco"]) == (5, {"confianca": -6})
    assert ops[f"{n}:endurecer"]["preco"] == {"confianca": 3}
    assert ops[f"{n}:meta"]["preco"] == {"meta_liga": 2}
    assert ops[f"{n}:venda"]["preco"] == {"vender_salarios": 1}
    assert ops[f"{n}:confianca"]["texto"] == (
        "até 5 contratações na janela de janeiro (em vez de até 4 contratações na janela de janeiro), "
        "custa 6 de confiança")


def test_aceitar_ate_o_fim_da_faixa_e_assinar(con):
    a = acordo_proposto(con)
    n = indice(a, "contratacoes", 1)
    diretoria.aceitar(con, 1, f"{n}:confianca")
    diretoria.aceitar(con, 1, f"{n}:confianca")
    with pytest.raises(ValueError):
        diretoria.aceitar(con, 1, f"{n}:confianca")  # 4 + 2 é o fim da faixa
    assert diretoria._acordo(con, 1, 0, 2026)["itens"][n]["valor"] == 6
    assert diretoria.confianca(con, 1, 0) == 48
    diretoria.assinar(con, 1)
    assert diretoria._acordo(con, 1, 0, 2026)["estado"] == "assinado"
    with pytest.raises(LookupError):
        diretoria.aceitar(con, 1, f"{n}:endurecer")


def test_concessao_em_troca_de_venda_cria_o_item(con):
    a = acordo_proposto(con)
    n = indice(a, "livres")
    diretoria.aceitar(con, 1, f"{n}:venda")
    itens = diretoria._acordo(con, 1, 0, 2026)["itens"]
    assert itens[n]["valor"] == 3
    assert next(i for i in itens if i["tipo"] == "vender_salarios")["jogadores"] == [10]
    assert diretoria.confianca(con, 1, 0) == 60  # quem paga é a venda, não a confiança


def test_revisao_aperta_com_confianca_baixa(con):
    sincronizar(con, "2026-01-10", temporada(2026, 0))
    diretoria.atualizar(con, 1)
    diretoria.assinar(con, 1)
    diretoria._evento(con, 1, 0, "teste", "2026-01-10", "teste", -25)  # 35
    sincronizar(con, "2026-07-05", temporada(2026, 2))
    diretoria.atualizar(con, 1)
    r = diretoria.revisao(con, 1)
    assert r["tipo"] == "endurecer" and len(r["opcoes"]) == 1
    assert "revisao" in [p["tipo"] for p in diretoria.pendencias(con, 1)]
    diretoria.responder_revisao(con, 1, None)
    assert diretoria.revisao(con, 1) is None and diretoria.confianca(con, 1, 0) == 30


def test_revisao_sem_mudanca_e_marcada_sozinha(con):
    sincronizar(con, "2026-01-10", temporada(2026, 0))
    diretoria.atualizar(con, 1)
    diretoria.assinar(con, 1)
    sincronizar(con, "2026-07-05", temporada(2026, 2))
    diretoria.atualizar(con, 1)
    assert diretoria.revisao(con, 1) is None  # confiança 60: nem afrouxa nem aperta


def test_aceitar_endurecer_rende_confianca(con):
    a = acordo_proposto(con)
    n = indice(a, "contratacoes", 1)
    diretoria.aceitar(con, 1, f"{n}:endurecer")
    assert diretoria._acordo(con, 1, 0, 2026)["itens"][n]["valor"] == 3
    assert diretoria.confianca(con, 1, 0) == 63


def test_aceitar_meta_afrouxa_item_e_aperta_a_meta(con):
    a = acordo_proposto(con)
    n, m = indice(a, "contratacoes", 1), indice(a, "meta_liga")
    diretoria.aceitar(con, 1, f"{n}:meta")
    itens = diretoria._acordo(con, 1, 0, 2026)["itens"]
    assert (itens[n]["valor"], itens[m]["valor"]) == (5, 2)
    assert diretoria.confianca(con, 1, 0) == 60


def test_revisao_afrouxa_com_confianca_alta(con):
    sincronizar(con, "2026-01-10", temporada(2026, 0))
    diretoria.atualizar(con, 1)
    diretoria.assinar(con, 1)
    diretoria._evento(con, 1, 0, "teste", "2026-01-10", "teste", 15)  # 75
    sincronizar(con, "2026-07-05", temporada(2026, 2))
    diretoria.atualizar(con, 1)
    r = diretoria.revisao(con, 1)
    assert r["tipo"] == "afrouxar" and r["opcoes"]
    o = r["opcoes"][0]
    diretoria.responder_revisao(con, 1, o["id"])
    assert diretoria._acordo(con, 1, 0, 2026)["itens"][o["item"]]["valor"] == o["novo"]
    assert diretoria.confianca(con, 1, 0) == 75
    assert diretoria.revisao(con, 1) is None


def test_revisao_com_opcao_invalida(con):
    sincronizar(con, "2026-01-10", temporada(2026, 0))
    diretoria.atualizar(con, 1)
    diretoria.assinar(con, 1)
    diretoria._evento(con, 1, 0, "teste", "2026-01-10", "teste", 15)
    sincronizar(con, "2026-07-05", temporada(2026, 2))
    diretoria.atualizar(con, 1)
    with pytest.raises(ValueError):
        diretoria.responder_revisao(con, 1, "rev:999")


def test_reuniao_so_oferece_o_que_esta_no_cardapio(con, monkeypatch):
    a = acordo_proposto(con)
    n = indice(a, "livres")
    recebido = []

    def falso(sistema, fatos, esquema):
        recebido.append(fatos)
        return {"resposta": "Professor, dá para liberar mais um livre.",
                "ofertas": [f"{n}:confianca", "inventada", f"{n}:confianca"]}

    monkeypatch.setattr(ia, "responder", falso)
    diretoria.reuniao(con, 1, "Preciso de mais um agente livre.")
    ms = diretoria.mensagens(con, 1, 0, 2026)
    assert [m["autor"] for m in ms] == ["tecnico", "presidente"]
    assert ms[1]["ofertas"] == [f"{n}:confianca"]  # a inventada sai, a repetida também
    assert any(c["id"] == f"{n}:confianca" for c in recebido[0]["cardapio"])
    assert recebido[0]["mensagem_do_tecnico"] == "Preciso de mais um agente livre."
    with pytest.raises(ValueError):
        diretoria.reuniao(con, 1, "   ")


def test_reuniao_sem_ia_nao_grava(con):
    acordo_proposto(con)
    with pytest.raises(ia.IAIndisponivel):
        diretoria.reuniao(con, 1, "Oi, presidente.")
    assert diretoria.mensagens(con, 1, 0, 2026) == []
