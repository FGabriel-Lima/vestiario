"""Feed do Vestiário: posts no estilo Instagram de perfis reais (clube, TNT Sports, ge) e um de mercado.
Quem publica o quê sai do código, a partir dos fatos do banco; a IA só escreve as legendas."""
import json
import re
import sqlite3
import unicodedata
from datetime import date, datetime

from . import banco, ia
from .leitor import MOEDA

# @ oficiais conhecidos; os outros clubes saem do nome (sem acento e espaço)
ARROBAS = {"são paulo": "saopaulofc", "são paulo fc": "saopaulofc", "ceará sc": "cearasc", "mirassol fc": "mirassolfc",
           "mirassol": "mirassolfc"}
PERFIS = {
    "tntsportsbr": {"nome": "TNT Sports Brasil", "arroba": "tntsportsbr"},
    "geglobo": {"nome": "ge", "arroba": "geglobo"},
    # fictício de propósito: imita um jornalista específico, e a IA não fala em nome de uma pessoa real
    "mercadodabola": {"nome": "Mercado da Bola", "arroba": "mercadodabola"},
}


def arroba_do_clube(nome: str) -> str:
    if (a := ARROBAS.get(nome.casefold())) is not None:
        return a
    sem_acento = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", sem_acento.casefold())


def _time(p: dict, lado: str) -> dict:
    return {"idx": p[f"{lado}_idx"], "nome": p[lado], "escudo": p[f"{lado}_escudo"], "gols": p[f"gols_{lado}"]}


def posts_do_periodo(con: sqlite3.Connection, cid: int) -> list[dict]:
    """Posts do que aconteceu entre a sincronização anterior (outra data do jogo) e a mais recente, em ordem de data."""
    s = banco._ultima(con, cid)
    clube, ate = s["clube_idx"], s["data_jogo"]
    de = con.execute("SELECT max(data_jogo) FROM sincronizacao WHERE carreira_id = ? AND data_jogo < ?",
                     (cid, ate)).fetchone()[0]
    todas = banco.partidas(con, cid)
    posts = []
    post = lambda perfil, tipo, data, dados: posts.append({"perfil": perfil, "tipo": tipo, "data": data, "dados": dados})

    # o dia da sincronização anterior entra de novo: o save pode ter sido gravado nesse dia antes do jogo (aconteceu);
    # jogo que já virou post não se repete
    ja_postados = {(d["data"], d["mandante"]["idx"], d["visitante"]["idx"]) for d in (
        json.loads(r[0]) for r in con.execute("SELECT dados FROM post WHERE carreira_id = ? AND tipo = 'fim_de_jogo'", (cid,)))}
    jogados = [p for p in todas if p["disputada"] and (de is None or p["data"] >= de) and p["data"] <= ate
               and (p["data"], p["mandante_idx"], p["visitante_idx"]) not in ja_postados]
    for p in jogados[-5:] if de is None else jogados:
        pro, contra = banco._placar(p, clube)
        dados = {"competicao": p["competicao"], "data": p["data"], "mandante": _time(p, "mandante"),
                 "visitante": _time(p, "visitante"), "nosso_lado": "mandante" if p["mandante_idx"] == clube else "visitante",
                 "resultado": "vitória" if pro > contra else "derrota" if pro < contra else "empate",
                 "gols_do_clube": _gols_do_clube(con, p["id"], 0 if p["mandante_idx"] == clube else 1)}
        if melhor := con.execute("SELECT e.player_id, coalesce(j.nome, 'Jogador #' || e.player_id), e.nota FROM escalacao e "
                                 "LEFT JOIN jogador j ON j.player_id = e.player_id WHERE e.partida_id = ? AND e.nota IS NOT NULL "
                                 "ORDER BY e.nota DESC LIMIT 1", (p["id"],)).fetchone():
            dados["melhor_em_campo"] = {"player_id": melhor[0], "nome": melhor[1], "nota": melhor[2] / 10}
        if p["penaltis_mandante"] + p["penaltis_visitante"]:
            dados["penaltis"] = [p["penaltis_mandante"], p["penaltis_visitante"]]
        post("clube", "fim_de_jogo", p["data"], dados)
        if abs(pro - contra) >= 3:
            post("tntsportsbr", "goleada", p["data"], dados)

    da_temporada = lambda t: t.startswith(ate[:4]) or t.endswith("/" + ate[2:4])
    for e in banco.edicoes(con, cid):
        if e["do_clube"] and e["liga"] and da_temporada(e["temporada"]):
            fase = banco.edicao(con, cid, e["chave"])["fases"][0]
            linhas = fase["grupos"][0]["linhas"]
            nossa = next((l for l in linhas if l["idx"] == clube), None)
            if nossa and nossa["jogos"] and jogados:
                mostrar = linhas[:5] + ([nossa] if nossa["posicao"] > 5 else [])
                post("tntsportsbr", "classificacao", ate, {
                    "competicao": e["nome"], "rodadas_jogadas": fase["rodadas_jogadas"], "rodadas_total": fase["rodadas_total"],
                    "linhas": [{"posicao": l["posicao"], "nome": l["nome"], "escudo": l["escudo"], "pontos": l["pontos"],
                                "jogos": l["jogos"], "saldo": l["gols_pro"] - l["gols_contra"], "nosso": l["idx"] == clube}
                               for l in mostrar]})

    janela = next((j for j in banco.transferencias(con, cid)["janelas"] if j["ate"] == ate and j["de"] == de), None)
    jogador = lambda x: {"player_id": x["player_id"], "nome": x["nome"]}
    for chave, lado, tipo in (("chegaram", "veio_de", "chegada"), ("sairam", "foi_para", "saida")):
        for x in janela[chave] if janela else []:
            outro = {"nome": x["clube"]["nome"], "escudo": x["clube"]["escudo"]} if x["clube"] else None
            if x["valor"]:
                post("mercadodabola", "fechado", ate, {**jogador(x), "movimento": tipo, lado: outro, "valor": abs(x["valor"]),
                                                      "troca": x["tipo"] == 8})
            post("clube", tipo, ate, {**jogador(x), lado: outro, **({"fim_de_contrato": True} if x.get("fim_de_contrato") else {}),
                                      "jogos_pelo_clube": x["jogos"], "gols_pelo_clube": x["gols"]})

    for x in banco.movimentos_do_mundo(con, cid):
        post("mercadodabola", "mundo", ate, x)

    for x in banco.propostas(con, cid):
        if (de is None or x["primeira"] > de) and x["primeira"] <= ate:
            post("geglobo", "proposta", x["primeira"], {
                **jogador(x), "posicao": banco.POSICOES[x["posicao"]] if x["posicao"] is not None else None,
                "clube": {"nome": x["clube"]["nome"], "escudo": x["clube"]["escudo"]}, "valor": x["valor"],
                **({"valor_de_mercado": x["valor_mercado"]} if x["valor_mercado"] else {})})

    limite = date.fromisoformat(ate)
    limite = date(limite.year + (limite.month + 5) // 12, (limite.month + 5) % 12 + 1, 1).isoformat()
    nomes = {r[0]: r[1] for r in con.execute("SELECT e.player_id, coalesce(j.nome, 'Jogador #' || e.player_id) FROM elenco e "
                                             "LEFT JOIN jogador j USING(player_id) WHERE e.sincronizacao_id = ?", (s["id"],))}
    vencendo = sorted(({"player_id": pid, "nome": nomes[pid], "fim": c["fim"]}
                       for pid, c in banco._contratos(con, s["id"]).items()
                       if pid in nomes and not c["emprestimo"] and c["fim"] <= limite), key=lambda x: (x["fim"], x["nome"]))
    if vencendo:
        post("geglobo", "contratos", ate, {"jogadores": vencendo})

    for t in banco.titulos(con, cid):
        if (de is None or t["fim"] > de) and t["fim"] <= ate and clube in (t["campeao"]["idx"], t["vice"]["idx"]):
            post("clube", "titulo" if t["campeao"]["idx"] == clube else "vice", t["fim"],
                 {"competicao": t["nome"], "temporada": t["temporada"], "campeao": t["campeao"], "vice": t["vice"]})

    if proximo := next((p for p in todas if not p["disputada"] and p["data"] > ate), None):
        post("clube", "proximo_jogo", ate, {"competicao": proximo["competicao"], "data": proximo["data"],
                                            "mandante": _time(proximo, "mandante"), "visitante": _time(proximo, "visitante")})
    return sorted(posts, key=lambda p: p["data"])


def _gols_do_clube(con: sqlite3.Connection, pid: int, lado: int) -> list[str]:
    return [r[0] + (f" ({r[1]})" if r[1] > 1 else "") for r in con.execute(
        "SELECT coalesce(j.nome, 'Jogador #' || e.player_id), e.gols FROM escalacao e LEFT JOIN jogador j "
        "ON j.player_id = e.player_id WHERE e.partida_id = ? AND e.lado = ? AND e.gols > 0 ORDER BY e.gols DESC, 1",
        (pid, lado))]


SISTEMA = """Você escreve as legendas de posts de Instagram sobre um clube numa carreira de Master League do PES.
Cada post já tem o perfil que publica, o tipo e os fatos. Escreva uma legenda para cada post, na voz do perfil:
- "clube": o perfil oficial do próprio clube. Comemorativo na vitória, sóbrio na derrota, acolhedor com quem chega,
  grato com quem sai. Pode usar 1 ou 2 emojis (nunca bandeiras) e uma hashtag com o nome do clube.
- "tntsportsbr": canal de TV esportivo. Descontraído, com humor leve em goleada (sem ofender), direto nos números.
- "geglobo": portal de notícias. Tom jornalístico: "INFORMAÇÃO", "o ge apurou", proposta recebida, contrato vencendo.
- "mercadodabola": perfil de mercado. Curto, começa com "Tá fechado! ✅" quando a transferência está concluída.
  Nos posts "mundo" o valor pago é desconhecido: cite só o valor de mercado, nunca como preço da transferência.

Regras, sem exceção:
- Use SOMENTE os fatos de cada post. Não cite pessoas, clubes, números, lesões, declarações, bastidores, intenções
  ou histórico que não estejam nele. Não invente frases entre aspas nem o que alguém pensa, quer ou decide.
- Não diga o nome do treinador nem de ninguém da comissão ou da diretoria.
- Este mundo é o do jogo: não relacione com o futebol da vida real.
- 1 a 3 frases por legenda, em português do Brasil. Valores em reais como se fala no futebol ("R$ 3,6 milhões").
- Devolva o mesmo "id" de cada post."""

ESQUEMA = {"type": "OBJECT", "properties": {"posts": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
    "id": {"type": "INTEGER"}, "legenda": {"type": "STRING"}}, "required": ["id", "legenda"]}}}, "required": ["posts"]}


def _sem_imagem(dados):
    """Fatos para a IA: sem escudos e ids, que só servem para a arte do post."""
    if isinstance(dados, dict):
        return {k: _sem_imagem(v) for k, v in dados.items() if k not in ("escudo", "player_id", "idx")}
    if isinstance(dados, list):
        return [_sem_imagem(v) for v in dados]
    return dados


def legenda_padrao(post: dict) -> str:
    """Quando a IA não escreve a legenda de um post, uma frase simples com os fatos."""
    d, t = post["dados"], post["tipo"]
    if t in ("fim_de_jogo", "goleada"):
        return f"Fim de jogo: {d['mandante']['nome']} {d['mandante']['gols']} x {d['visitante']['gols']} {d['visitante']['nome']}."
    if t == "proximo_jogo":
        return f"Próximo jogo: {d['mandante']['nome']} x {d['visitante']['nome']}."
    if t == "classificacao":
        return f"Classificação do {d['competicao']} depois de {d['rodadas_jogadas']} rodadas."
    if t == "mundo":
        return f"{d['nome']} agora é do {d['para']['nome']}."
    if t in ("chegada", "saida", "fechado"):
        return f"{d['nome']}: {'chegou' if t == 'chegada' or d.get('movimento') == 'chegada' else 'saiu'}."
    if t == "proposta":
        return f"INFORMAÇÃO: {d['clube']['nome']} fez proposta por {d['nome']}."
    if t == "contratos":
        return "Contratos que vencem nos próximos meses: " + ", ".join(j["nome"] for j in d["jogadores"]) + "."
    return f"{d.get('competicao', '')} {d.get('temporada', '')}".strip()


def atualizar(con: sqlite3.Connection, cid: int) -> dict:
    """Publica os posts da data do jogo mais recente (uma vez só) e devolve o feed inteiro."""
    ate = banco._ultima(con, cid)["data_jogo"]
    if not con.execute("SELECT 1 FROM post WHERE carreira_id = ? AND edicao = ? LIMIT 1", (cid, ate)).fetchone():
        posts = posts_do_periodo(con, cid)
        legendas = {}
        if posts:
            r = ia.responder(SISTEMA, {"clube": banco._ultima(con, cid)["clube_nome"],
                                       "posts": [{"id": i, "perfil": p["perfil"], "tipo": p["tipo"], "data": p["data"],
                                                  "fatos": _sem_imagem(p["dados"])} for i, p in enumerate(posts)]}, ESQUEMA)
            legendas = {x["id"]: str(x.get("legenda", "")).strip() for x in r.get("posts", []) if isinstance(x, dict)}
        with con:
            # edição vazia também é gravada (uma linha sem post), para o botão não voltar a aparecer
            con.executemany("INSERT INTO post VALUES(?, ?, ?, ?, ?, ?, ?, ?)", [
                (cid, ate, i, p["perfil"], p["tipo"], p["data"], json.dumps(p["dados"], ensure_ascii=False),
                 legendas.get(i) or legenda_padrao(p)) for i, p in enumerate(posts)] or
                [(cid, ate, -1, "", "", ate, "{}", "")])
    return ler(con, cid)


def ler(con: sqlite3.Connection, cid: int) -> dict:
    s = banco._ultima(con, cid)
    t = con.execute("SELECT pes_id FROM time WHERE carreira_id = ? AND idx = ?", (cid, s["clube_idx"])).fetchone()
    posts = [{"edicao": r[0], "perfil": r[1], "tipo": r[2], "data": r[3], "dados": json.loads(r[4]), "legenda": r[5]}
             for r in con.execute("SELECT edicao, perfil, tipo, data, dados, legenda FROM post WHERE carreira_id = ? "
                                  "AND ordem >= 0 ORDER BY edicao DESC, data DESC, ordem DESC", (cid,))]
    publicado = con.execute("SELECT 1 FROM post WHERE carreira_id = ? AND edicao = ? LIMIT 1",
                            (cid, s["data_jogo"])).fetchone() is not None
    return {"atual": s["data_jogo"], "publicado": publicado, "posts": posts,
            "perfis": {"clube": {"nome": s["clube_nome"], "arroba": arroba_do_clube(s["clube_nome"]),
                                 "escudo": t[0] if t else None}, **PERFIS}}
