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



def test_jogo_no_dia_da_sincronizacao_anterior_entra_uma_vez(monkeypatch):
    c = banco.conectar(":memory:")
    monkeypatch.setattr(ia, "responder", lambda *a: {"posts": []})
    jogo = lambda gols, esc: partida("2026-01-22", 0, 1, gols, esc, comp=29, rodada=0)
    # save gravado no dia do jogo, antes da partida
    banco.gravar(c, "ML00000000", fazer_save("2026-01-22", [jogo((0, 0), [])], competicoes=COMPETICOES), AGORA)
    feed.atualizar(c, 1)
    banco.gravar(c, "ML00000000", fazer_save("2026-01-27", [jogo((0, 1), [atuacao(50, 1, 1)])], competicoes=COMPETICOES), AGORA)
    assert [p["tipo"] for p in feed.atualizar(c, 1)["posts"]].count("fim_de_jogo") == 1
    banco.gravar(c, "ML00000000", fazer_save("2026-02-01", [jogo((0, 1), [atuacao(50, 1, 1)])], competicoes=COMPETICOES), AGORA)
    assert [p["tipo"] for p in feed.atualizar(c, 1)["posts"]].count("fim_de_jogo") == 1  # não repete


def test_coletiva_do_ultimo_jogo_vira_post_do_ge(con, monkeypatch):
    monkeypatch.setattr(ia, "responder", lambda *a: {"posts": []})
    assert feed.atualizar(con, 1)["coletiva"] == {"jogo": feed.ler(con, 1)["posts"][-1]["dados"], "perguntas": None}
    # sem IA, as perguntas saem do código
    monkeypatch.setattr(ia, "responder", lambda *a: (_ for _ in ()).throw(ia.IAIndisponivel("fora")))
    perguntas = feed.abrir_coletiva(con, 1)["coletiva"]["perguntas"]
    assert perguntas[0] == "Como você avalia o resultado contra o Clube C?"
    assert feed.abrir_coletiva(con, 1)["coletiva"]["perguntas"] == perguntas  # guardadas: não pergunta de novo
    with pytest.raises(ValueError):
        feed.responder_coletiva(con, 1, ["", "", ""])
    # citação que não está nas respostas é trocada pela legenda do código
    monkeypatch.setattr(ia, "responder", lambda *a: {"legenda": 'O técnico disse: "fomos campeões".'})
    f = feed.responder_coletiva(con, 1, ["Vencemos com autoridade.", "", "Agora é o Clube A."])
    assert f["coletiva"] is None
    i = next(i for i, p in enumerate(f["posts"]) if p["tipo"] == "coletiva")
    post = f["posts"][i]
    assert post["perfil"] == "geglobo" and f["posts"][i + 1]["tipo"] == "fim_de_jogo"  # logo acima do jogo
    assert post["dados"]["entrevista"] == [{"pergunta": perguntas[0], "resposta": "Vencemos com autoridade."},
                                           {"pergunta": perguntas[2], "resposta": "Agora é o Clube A."}]
    assert post["legenda"] == '"Vencemos com autoridade.", disse o técnico do Clube A depois do jogo.'


def test_posts_da_diretoria(con):
    from vestiario import diretoria
    diretoria._evento(con, 1, 0, "quebra:contratacoes:2026:1", "2026-02-03", "Contratações além do limite", -15)
    diretoria._evento(con, 1, 0, "demissao:2026-01-30", "2026-02-03", "Demitido: ultimato não cumprido", 0)
    con.execute("INSERT INTO acordo(carreira_id, clube_idx, ano, estado, itens, perfil, data_jogo, assinado_data) "
                "VALUES(1, 0, 2026, 'assinado', ?, '{}', '2026-01-25', '2026-01-25')",
                ('[{"tipo": "livres", "valor": 1, "base": 1}]',))
    posts = feed.posts_do_periodo(con, 1)
    tipos = [(p["perfil"], p["tipo"]) for p in posts]
    for esperado in [("geglobo", "diretoria_insatisfeita"), ("clube", "demissao"), ("geglobo", "demissao"),
                     ("clube", "acordo")]:
        assert esperado in tipos
    acordo = next(p for p in posts if p["tipo"] == "acordo")
    assert acordo["dados"] == {"ano": 2026, "imposto": False, "exigencias": ["até 1 agente livre no ano"]}
    assert feed.legenda_padrao(next(p for p in posts if p["tipo"] == "demissao")) == "Demitido: ultimato não cumprido."
