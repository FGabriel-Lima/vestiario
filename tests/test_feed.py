from datetime import datetime

import pytest
from conftest import atuacao, fazer_save, partida

from vestiario import banco, feed, ia
from vestiario.leitor import MOEDA

AGORA = datetime(2026, 10, 15, 10, 0)
COMPETICOES = {29: "Brasileirão Série A"}


@pytest.fixture
def con():
    c = banco.conectar(":memory:")
    banco.gravar_nomes(c, {10: "Artilheiro", 11: "Reserva", 12: "Contratado", 50: "Rival"}, {10: 12, 11: 1, 12: 8})
    liga = lambda dia, m, v, gols, esc, r: partida(dia, m, v, gols, esc, comp=29, rodada=r)
    banco.gravar(c, "ML00000000", fazer_save("2026-01-25", [
        liga("2026-01-22", 0, 1, (2, 0), [atuacao(10, 0, 2)], 0),
        liga("2026-02-01", 2, 0, (0, 0), [], 1), liga("2026-02-08", 1, 0, (0, 0), [], 2)],
        elenco=(10, 11), competicoes=COMPETICOES), AGORA)
    banco.gravar(c, "ML00000000", fazer_save("2026-02-03", [
        liga("2026-01-22", 0, 1, (2, 0), [atuacao(10, 0, 2)], 0),
        liga("2026-02-01", 2, 0, (1, 4), [atuacao(10, 1, 2), atuacao(12, 1, 2), atuacao(50, 0, 1)], 1),
        liga("2026-02-08", 1, 0, (0, 0), [], 2)],
        elenco=(10, 11, 12), competicoes=COMPETICOES, contratos={11: (5200, 0, "2026-06-30")},
        negocios=[(12, -1000, 1)], propostas=[(1, 10, 9000)]), AGORA)
    yield c
    c.close()


def test_posts_do_periodo(con):
    posts = feed.posts_do_periodo(con, 1)
    tipos = [(p["perfil"], p["tipo"]) for p in posts]
    assert tipos == [("clube", "fim_de_jogo"), ("tntsportsbr", "goleada"), ("tntsportsbr", "classificacao"),
                     ("mercadodabola", "fechado"), ("clube", "chegada"), ("geglobo", "proposta"),
                     ("geglobo", "contratos"), ("clube", "proximo_jogo")]
    jogo = posts[0]["dados"]
    assert (jogo["mandante"]["gols"], jogo["visitante"]["gols"], jogo["gols_do_clube"]) == (1, 4, ["Artilheiro (2)", "Contratado (2)"])
    assert posts[3]["dados"]["valor"] == 1000 * MOEDA
    assert posts[5]["dados"]["clube"]["nome"] == "Clube B" and posts[5]["dados"]["valor"] == 9000 * MOEDA
    assert posts[6]["dados"]["jogadores"] == [{"player_id": 11, "nome": "Reserva", "fim": "2026-06-30"}]
    assert posts[7]["dados"]["visitante"]["nome"] == "Clube A"
    assert all(p["data"] <= "2026-02-08" for p in posts)


def test_feed_fica_guardado_e_legenda_que_falta_usa_a_padrao(con, monkeypatch):
    chamadas = []

    def falso(sistema, fatos, esquema):
        chamadas.append(fatos)
        return {"posts": [{"id": 0, "legenda": "FIM DE JOGO! Virada tricolor."}]}

    monkeypatch.setattr(ia, "responder", falso)
    f = feed.atualizar(con, 1)
    assert f["posts"][-1]["tipo"] == "fim_de_jogo"  # o feed mostra o mais recente primeiro
    assert f["posts"][-1]["legenda"] == "FIM DE JOGO! Virada tricolor."
    assert all(p["legenda"] for p in f["posts"])  # as que a IA não mandou ficam com a legenda padrão
    assert feed.atualizar(con, 1)["posts"] == f["posts"]
    assert len(chamadas) == 1
    assert feed.ler(con, 1)["publicado"] is True
    assert feed.ler(con, 1)["perfis"]["clube"]["arroba"] == "clubea"


def test_perfil_oficial_do_clube():
    assert feed.arroba_do_clube("São Paulo") == "saopaulofc"
    assert feed.arroba_do_clube("Ceará SC") == "cearasc"
    assert feed.arroba_do_clube("Atlético Mineiro") == "atleticomineiro"
