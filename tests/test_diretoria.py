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
