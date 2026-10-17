"""Feed do Vestiário: posts no estilo Instagram de perfis reais (clube, TNT Sports, ge) e um de mercado.
Quem publica o quê sai do código, a partir dos fatos do banco; a IA só escreve as legendas."""
import json
import re
import sqlite3
import unicodedata
from datetime import date, datetime

from . import banco, diretoria, ia
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

    # primeira edição de uma passagem que veio depois de outra: o clube anuncia o técnico e o ge dá a notícia
    if de is None:
        anteriores = [p for p in banco._passagens_curtas(con, cid) if p["id"] != cid and p["fim"] <= ate]
        if anteriores:
            ant = max(anteriores, key=lambda p: p["fim"])
            dados = {"clube_anterior": ant["clube_nome"], "motivo_saida": ant["motivo_saida"], "data": ate}
            post("clube", "novo_tecnico", ate, dados)
            post("geglobo", "novo_tecnico", ate, dict(dados))
            de = ate  # jogos, títulos, propostas e negócios de antes da chegada foram de outro técnico

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

    # diretoria: os eventos de confiança do período (gravados na data da sincronização em que aconteceram) e o acordo
    # assinado ou imposto, uma vez por ano
    eventos = con.execute("SELECT chave, data_jogo, motivo, variacao FROM confianca WHERE carreira_id = ? AND "
                          "clube_idx = ? AND data_jogo <= ? AND (? IS NULL OR data_jogo > ?) ORDER BY rowid",
                          (cid, clube, ate, de, de)).fetchall()
    for chave, data, motivo, variacao in eventos:
        if chave.startswith("quebra:"):
            post("geglobo", "diretoria_insatisfeita", data, {"motivo": motivo})
        elif chave.startswith("ultimato:inicio"):
            post("geglobo", "ultimato", data, {"motivo": motivo})
        elif chave.startswith("demissao:"):
            post("clube", "demissao", data, {"motivo": motivo})
            post("geglobo", "demissao", data, {"motivo": motivo})
        elif chave.startswith("balanco:meta_liga"):
            post("geglobo", "balanco", data, {"motivo": motivo, "variacao": variacao})
    anunciados = {json.loads(r[0]).get("ano") for r in con.execute(
        "SELECT dados FROM post WHERE carreira_id = ? AND tipo = 'acordo'", (cid,))}
    for ano, estado, itens, assinado in con.execute(
            "SELECT ano, estado, itens, assinado_data FROM acordo WHERE carreira_id = ? AND clube_idx = ? AND "
            "assinado_data IS NOT NULL AND assinado_data <= ? AND (? IS NULL OR assinado_data >= ?)",
            (cid, clube, ate, de, de)).fetchall():
        if ano not in anunciados:
            post("clube", "acordo", assinado, {"ano": ano, "imposto": estado == "imposto",
                                               "exigencias": [diretoria.descrever(i) for i in json.loads(itens)]})

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
- Posts da diretoria ("acordo", "diretoria_insatisfeita", "ultimato", "demissao", "balanco"): a relação do técnico
  com a diretoria, só com o "motivo" e as "exigencias" dos fatos. O perfil oficial anuncia o acordo da temporada e a
  saída do técnico com sobriedade; o ge noticia a insatisfação, o ultimato, a demissão e o balanço.
- Posts "novo_tecnico": a chegada do técnico ao clube. O perfil oficial dá as boas-vindas; o ge noticia citando o
  "clube_anterior" e o "motivo_saida" ("demitido" ou "trocou de clube") dos fatos.

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
    if t == "novo_tecnico":
        return f"Novo técnico no comando, vindo do {d['clube_anterior']}."
    if t == "acordo":
        return f"Diretoria e comissão técnica alinhadas para {d['ano']}."
    if t in ("diretoria_insatisfeita", "ultimato", "demissao", "balanco"):
        return f"{d['motivo']}."
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


SISTEMA_COLETIVA = """Você é repórter do ge numa entrevista coletiva com o treinador de um clube, logo depois de um \
jogo numa carreira de Master League do PES. Faça 3 perguntas curtas e diretas sobre o jogo, como um repórter de
verdade: o resultado, quem decidiu ou foi bem (ou mal) e o que vem pela frente. Use SOMENTE os fatos do JSON: não
invente lances, lesões, polêmicas, declarações nem histórico. Não diga o nome do treinador. Português do Brasil."""

ESQUEMA_COLETIVA = {"type": "OBJECT", "properties": {"perguntas": {"type": "ARRAY", "items": {"type": "STRING"}}},
                    "required": ["perguntas"]}

SISTEMA_MATERIA = """Você escreve a legenda de um post do ge no Instagram sobre a entrevista coletiva do treinador de \
um clube depois de um jogo numa carreira de Master League do PES. Tom jornalístico, de 1 a 3 frases. Cite entre aspas
um ou dois trechos das respostas, copiados palavra por palavra. Use só os fatos do JSON. Não diga o nome do treinador:
chame-o de "o técnico do" clube. Português do Brasil."""

ESQUEMA_MATERIA = {"type": "OBJECT", "properties": {"legenda": {"type": "STRING"}}, "required": ["legenda"]}


def coletiva(con: sqlite3.Connection, cid: int) -> dict | None:
    """A coletiva do jogo mais recente do clube no feed (None se não há jogo ou se ela já foi dada). As perguntas
    ficam None até o treinador entrar na sala de imprensa."""
    r = con.execute("SELECT dados FROM post WHERE carreira_id = ? AND tipo = 'fim_de_jogo' ORDER BY data DESC LIMIT 1",
                    (cid,)).fetchone()
    if r is None:
        return None
    jogo = json.loads(r[0])
    c = con.execute("SELECT perguntas, respostas FROM coletiva WHERE carreira_id = ? AND data = ?",
                    (cid, jogo["data"])).fetchone()
    if c and c[1] is not None:
        return None
    return {"jogo": jogo, "perguntas": json.loads(c[0]) if c else None}


def _perguntas_padrao(jogo: dict) -> list[str]:
    adversario = jogo["visitante" if jogo["nosso_lado"] == "mandante" else "mandante"]["nome"]
    p = [f"Como você avalia o resultado contra o {adversario}?"]
    if m := jogo.get("melhor_em_campo"):
        p.append(f"{m['nome']} foi o melhor em campo. O que achou da atuação?")
    p.append("O que o time precisa melhorar para o próximo jogo?")
    return p


def abrir_coletiva(con: sqlite3.Connection, cid: int) -> dict:
    """Gera (uma vez) as perguntas do repórter. Sem IA, as perguntas saem do código."""
    c = coletiva(con, cid)
    if c is None:
        raise LookupError("Não há jogo para a coletiva")
    if c["perguntas"] is None:
        try:
            r = ia.responder(SISTEMA_COLETIVA, {"clube": banco._ultima(con, cid)["clube_nome"],
                                                "jogo": _sem_imagem(c["jogo"])}, ESQUEMA_COLETIVA)
            perguntas = [str(p).strip() for p in r.get("perguntas", []) if str(p).strip()][:3]
        except ia.IAIndisponivel:
            perguntas = []
        with con:
            con.execute("INSERT INTO coletiva VALUES(?, ?, ?, NULL, NULL, ?)", (
                cid, c["jogo"]["data"], json.dumps(perguntas or _perguntas_padrao(c["jogo"]), ensure_ascii=False),
                datetime.now().isoformat(timespec="seconds")))
    return ler(con, cid)


def responder_coletiva(con: sqlite3.Connection, cid: int, respostas: list[str]) -> dict:
    """Guarda as respostas (pergunta sem resposta fica de fora do post) e a legenda do ge, que só pode citar entre
    aspas o que o treinador disse; se citar outra coisa, a legenda sai do código."""
    c = coletiva(con, cid)
    if c is None or c["perguntas"] is None:
        raise LookupError("Não há coletiva aberta")
    respostas = [str(r).strip() for r in respostas]
    if len(respostas) != len(c["perguntas"]) or not any(respostas):
        raise ValueError("Responda a pelo menos uma pergunta")
    entrevista = [{"pergunta": p, "resposta": r} for p, r in zip(c["perguntas"], respostas) if r]
    clube = banco._ultima(con, cid)["clube_nome"]
    try:
        legenda = str(ia.responder(SISTEMA_MATERIA, {"clube": clube, "jogo": _sem_imagem(c["jogo"]),
                                                     "entrevista": entrevista}, ESQUEMA_MATERIA).get("legenda", "")).strip()
    except ia.IAIndisponivel:
        legenda = ""
    falas = " ".join(r.casefold() for r in respostas)
    if not legenda or any(q.strip(" .,!?…").casefold() not in falas for q in re.findall(r'[“"]([^”"]+)[”"]', legenda)):
        legenda = f'"{entrevista[0]["resposta"]}", disse o técnico do {clube} depois do jogo.'
    with con:
        con.execute("UPDATE coletiva SET respostas = ?, legenda = ? WHERE carreira_id = ? AND data = ?",
                    (json.dumps(respostas, ensure_ascii=False), legenda, cid, c["jogo"]["data"]))
    return ler(con, cid)


def ler(con: sqlite3.Connection, cid: int) -> dict:
    s = banco._ultima(con, cid)
    t = con.execute("SELECT pes_id FROM time WHERE carreira_id = ? AND idx = ?", (cid, s["clube_idx"])).fetchone()
    dadas = {r[0]: (json.loads(r[1]), json.loads(r[2]), r[3]) for r in con.execute(
        "SELECT data, perguntas, respostas, legenda FROM coletiva WHERE carreira_id = ? AND respostas IS NOT NULL", (cid,))}
    posts = []
    for r in con.execute("SELECT edicao, perfil, tipo, data, dados, legenda FROM post WHERE carreira_id = ? "
                         "AND ordem >= 0 ORDER BY edicao DESC, data DESC, ordem DESC", (cid,)):
        p = {"edicao": r[0], "perfil": r[1], "tipo": r[2], "data": r[3], "dados": json.loads(r[4]), "legenda": r[5]}
        if p["tipo"] == "fim_de_jogo" and (c := dadas.get(p["data"])):  # a coletiva sai logo depois do jogo
            perguntas, respostas, legenda = c
            posts.append({**p, "perfil": "geglobo", "tipo": "coletiva", "legenda": legenda, "dados": {
                **p["dados"], "entrevista": [{"pergunta": q, "resposta": a} for q, a in zip(perguntas, respostas) if a]}})
        posts.append(p)
    publicado = con.execute("SELECT 1 FROM post WHERE carreira_id = ? AND edicao = ? LIMIT 1",
                            (cid, s["data_jogo"])).fetchone() is not None
    return {"atual": s["data_jogo"], "publicado": publicado, "posts": posts, "coletiva": coletiva(con, cid),
            "perfis": {"clube": {"nome": s["clube_nome"], "arroba": arroba_do_clube(s["clube_nome"]),
                                 "escudo": t[0] if t else None}, **PERFIS}}
