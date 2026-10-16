"""Conversas (IA) com o auxiliar técnico e os jogadores do elenco, sempre a partir dos fatos do banco."""
import sqlite3
from datetime import date, datetime

from . import banco, ia

HISTORICO = 12  # mensagens anteriores que a IA recebe

REGRAS = """Regras, sem exceção:
- Use SOMENTE os fatos do JSON para números, jogos, contratos, valores e acontecimentos. Não invente lesões,
  declarações de outras pessoas, bastidores, treinos, vida pessoal ou histórico que não estejam nos fatos.
- Se o treinador perguntar algo que os fatos não dizem, diga que não sabe ou mude de assunto com naturalidade.
- O que estiver em "dados_que_nao_temos" é desconhecido: não fale como se soubesse.
- Não diga o nome do treinador; chame-o de "professor".
- Este mundo é o do jogo: não relacione com o futebol da vida real.
- Responda em português do Brasil, de 1 a 4 frases, como numa conversa de WhatsApp. Valores em reais como se fala no
  futebol ("R$ 3,6 milhões"). Notas do PES de 0 a 10."""

SISTEMA_JOGADOR = """Você é um jogador de futebol do elenco de um clube numa carreira de Master League do PES, conversando \
com o seu treinador por mensagem. Fale em primeira pessoa, como o jogador dos fatos. Você pode ter opinião,
sentimento, ambição e preocupação; o seu estado vem de "como_voce_esta" (por exemplo, quem joga pouco cobra espaço,
quem tem contrato vencendo puxa o assunto da renovação, quem tem proposta sabe dela).

Promessas: se a mensagem do treinador prometer algo concreto a você (mais minutos, vaga de titular, renovação,
aumento, não ser vendido), resuma a promessa em "promessa", em poucas palavras ("mais minutos nos próximos jogos");
se não prometer nada, deixe "promessa" vazio. Em "promessas_do_professor" estão as que ele já fez, com o que
aconteceu nos jogos depois ("desde_entao"): reconheça a que está sendo cumprida e cobre, com esses números, a que não
está. Sem jogos do clube desde a promessa, ainda é cedo para cobrar.
Em "propostas_que_acabaram" estão propostas por você que se encerraram sem você sair, com o que você queria na
época ("sua_vontade"): lembre disso quando o assunto vier (quem queria sair pode guardar mágoa).

""" + REGRAS

SISTEMA_AUXILIAR = """Você é o auxiliar técnico do clube numa carreira de Master League do PES, conversando com o \
treinador por mensagem. Analise o elenco e o momento do clube com franqueza, como um auxiliar de confiança: quem
joga pouco, quem está em boa ou má fase, contratos vencendo, propostas abertas, próximos jogos e orçamento.
Sugira caminhos, mas a decisão é do treinador.

""" + REGRAS

ESQUEMA = {"type": "OBJECT", "properties": {"resposta": {"type": "STRING"}}, "required": ["resposta"]}
ESQUEMA_JOGADOR = {"type": "OBJECT", "properties": {"resposta": {"type": "STRING"}, "promessa": {"type": "STRING"}},
                   "required": ["resposta"]}


VONTADES = ("ficar", "sair", "dividido")
SISTEMA_REACAO = """Você é um jogador de futebol do elenco de um clube numa carreira de Master League do PES e manda \
mensagem ao seu treinador por conta própria, sem ele ter perguntado. Fale em primeira pessoa, como o jogador dos fatos.

Se houver "propostas_novas": acabou de chegar proposta de outro clube por você. Diga o que acha e se quer ficar ou
sair, pesando o seu momento ("como_voce_esta", minutos, fase, contrato, idade), o tamanho do clube que fez a proposta
("valor_do_elenco" dele comparado ao "valor_do_nosso_elenco") e as promessas do professor. Com "oferta_anterior", o
clube melhorou a oferta. Em "vontade", ponha "ficar", "sair" ou "dividido", coerente com a mensagem.
Se houver "propostas_encerradas_agora": a proposta acabou e você continua no clube (o professor recusou ou ela
expirou). Reaja de acordo com "sua_vontade" na época: frustrado se queria sair, aliviado se queria ficar.
Se houver "despedida": você foi vendido e está deixando o clube. Despeça-se do professor.

""" + REGRAS
ESQUEMA_REACAO = {"type": "OBJECT", "properties": {"mensagem": {"type": "STRING"},
                                                   "vontade": {"type": "STRING", "enum": list(VONTADES)}},
                  "required": ["mensagem"]}


def _seis_meses(ate: str) -> str:
    d = date.fromisoformat(ate)
    return date(d.year + (d.month + 5) // 12, (d.month + 5) % 12 + 1, 1).isoformat()


def sinais(linha: dict, jogos_do_clube: int, ate: str, propostas: list[dict]) -> list[str]:
    """O estado do jogador, decidido pelo código: minutos, fase, contrato, propostas e idade, nessa ordem."""
    s = []
    if jogos_do_clube:
        parte = linha["minutos"] / (90 * jogos_do_clube)
        if parte < 0.3:
            s.append("joga pouco")
        elif parte >= 0.8:
            s.append("titular")
    if linha["nota"] is not None and linha["notas"] >= 2:
        if linha["nota"] >= 6.8:
            s.append("em boa fase")
        elif linha["nota"] <= 5.5:
            s.append("fase ruim")
    if c := linha["contrato"]:
        if c["emprestimo"]:
            s.append("emprestado")
        elif c["fim"] <= _seis_meses(ate):
            s.append("contrato vencendo")
    s += [f"proposta do {p['clube']['nome']}" for p in propostas if p["player_id"] == linha["player_id"]]
    if linha["idade"] is not None and linha["idade"] >= 32:
        s.append("veterano")
    elif linha["idade"] is not None and linha["idade"] <= 21:
        s.append("jovem")
    return s


def _contexto(con: sqlite3.Connection, cid: int):
    s = banco._ultima(con, cid)
    jogos = len([p for p in banco.partidas(con, cid, int(s["data_jogo"][:4])) if p["disputada"]])
    abertas = [p for p in banco.propostas(con, cid) if p["situacao"] == "aberta"]
    return s, jogos, abertas


def _mensagens(con: sqlite3.Connection, cid: int, contato: str) -> list[dict]:
    return [{"autor": r[0], "texto": r[1], "data_jogo": r[2]} for r in con.execute(
        "SELECT autor, texto, data_jogo FROM mensagem WHERE carreira_id = ? AND contato = ? ORDER BY ordem", (cid, contato))]


def contatos(con: sqlite3.Connection, cid: int) -> list[dict]:
    """Agenda: o auxiliar fixado no topo e o elenco por setor, com a última mensagem e os sinais."""
    s, jogos, abertas = _contexto(con, cid)
    ultima = {r[0]: r[1] for r in con.execute(
        "SELECT contato, texto FROM mensagem m WHERE carreira_id = ? AND ordem = (SELECT max(ordem) FROM mensagem "
        "WHERE carreira_id = m.carreira_id AND contato = m.contato)", (cid,))}
    prometidos = {r[0] for r in con.execute("SELECT player_id FROM promessa WHERE carreira_id = ?", (cid,))}
    nao_lidas = {r[0]: r[1] for r in con.execute(
        "SELECT contato, count(*) FROM mensagem WHERE carreira_id = ? AND lida = 0 GROUP BY contato", (cid,))}
    lista = [{"contato": "auxiliar", "nome": "Auxiliar técnico", "sinais": [], "ultima": ultima.get("auxiliar"),
              "nao_lidas": nao_lidas.get("auxiliar", 0)}]
    for l in banco.elenco_para_conversa(con, cid):
        c = str(l["player_id"])
        lista.append({"contato": c, "player_id": l["player_id"], "nome": l["nome"], "posicao": l["posicao"],
                      "idade": l["idade"], "ultima": ultima.get(c), "nao_lidas": nao_lidas.get(c, 0),
                      "sinais": sinais(l, jogos, s["data_jogo"], abertas) + ["promessa feita"] * (l["player_id"] in prometidos)})
    return lista


def atencao(con: sqlite3.Connection, cid: int) -> dict:
    """O que pede uma decisão do treinador agora, decidido pelo código: propostas abertas, contratos e empréstimos que
    acabam em até 6 meses, promessas feitas (com o que veio depois) e os jogadores mais valiosos jogando pouco."""
    s, jogos, abertas = _contexto(con, cid)
    elenco = banco.elenco_para_conversa(con, cid)
    valor = {r[0]: r[1] for r in con.execute("SELECT player_id, valor FROM elenco WHERE sincronizacao_id = ?", (s["id"],))}
    limite = _seis_meses(s["data_jogo"])
    prometidos = {r[0] for r in con.execute("SELECT DISTINCT player_id FROM promessa WHERE carreira_id = ?", (cid,))}
    return {
        "propostas": [{k: p[k] for k in ("player_id", "nome", "clube", "valor", "valor_mercado", "vontade")} for p in abertas],
        "contratos": sorted(({"player_id": l["player_id"], "nome": l["nome"], "fim": c["fim"], "emprestimo": c["emprestimo"]}
                             for l in elenco if (c := l["contrato"]) and c["fim"] <= limite), key=lambda x: (x["fim"], x["nome"])),
        "promessas": [{"player_id": l["player_id"], "nome": l["nome"], **p} for l in elenco if l["player_id"] in prometidos
                      for p in banco.promessas(con, cid, l["player_id"], limite=1)],
        "sem_espaco": [{"player_id": l["player_id"], "nome": l["nome"], "jogos": l["jogos"], "minutos": l["minutos"],
                        "jogos_do_clube": jogos, "valor": (valor.get(l["player_id"]) or 0) * banco.MOEDA or None}
                       for l in sorted((l for l in elenco if "joga pouco" in sinais(l, jogos, s["data_jogo"], abertas)),
                                       key=lambda l: (-(valor.get(l["player_id"]) or 0), l["nome"]))][:3],
    }


def _atalhos(contato: str, fatos: dict) -> list[str]:
    if contato == "auxiliar":
        a = ["Como está o elenco?", "Quem está jogando pouco?"]
        if fatos.get("contratos_vencendo"):
            a.append("Quem devo renovar?")
        if fatos.get("propostas_abertas"):
            a.append("E as propostas que chegaram?")
        if fatos.get("proximos_jogos"):
            a.append("Como encarar o próximo jogo?")
        return a
    j = fatos["jogador"]
    a = ["Como você está?"]
    if j["temporada"]["jogos_do_clube"]:
        a.append("Sobre os seus minutos")
    if c := j.get("contrato"):
        a.append("Seu empréstimo" if "emprestado_ate" in c else "Seu contrato")
    a += [f"A proposta do {p['clube']}" for p in fatos.get("propostas_abertas", [])]
    return a


def _fatos(con: sqlite3.Connection, cid: int, contato: str) -> dict | None:
    if contato == "auxiliar":
        return banco.fatos_do_clube(con, cid)
    if not contato.isdigit():
        return None
    fatos = banco.fatos_do_jogador(con, cid, int(contato))
    if fatos is not None:
        s, jogos, abertas = _contexto(con, cid)
        linha = next(l for l in banco.elenco_para_conversa(con, cid) if l["player_id"] == int(contato))
        fatos["como_voce_esta"] = sinais(linha, jogos, s["data_jogo"], abertas)
    return fatos


def conversa(con: sqlite3.Connection, cid: int, contato: str) -> dict | None:
    fatos = _fatos(con, cid, contato)
    if fatos is None:
        return None
    with con:  # abrir a conversa é ler o que o contato mandou por conta própria
        con.execute("UPDATE mensagem SET lida = 1 WHERE carreira_id = ? AND contato = ? AND lida = 0", (cid, contato))
    return {"contato": contato, "mensagens": _mensagens(con, cid, contato), "atalhos": _atalhos(contato, fatos),
            "fatos": fatos}


def responder(con: sqlite3.Connection, cid: int, contato: str, texto: str) -> dict | None:
    """Grava a mensagem do treinador, pede a resposta à IA e grava a resposta. Erros da IA sobem como
    ia.IAIndisponivel, e aí nada é gravado."""
    texto = texto.strip()
    if not texto:
        raise ValueError("Mensagem vazia")
    fatos = _fatos(con, cid, contato)
    if fatos is None:
        return None
    anteriores = _mensagens(con, cid, contato)[-HISTORICO:]
    auxiliar = contato == "auxiliar"
    r = ia.responder(SISTEMA_AUXILIAR if auxiliar else SISTEMA_JOGADOR,
                     {"fatos": fatos, "conversa_ate_agora": [{"autor": m["autor"], "texto": m["texto"]} for m in anteriores],
                      "mensagem_do_treinador": texto}, ESQUEMA if auxiliar else ESQUEMA_JOGADOR)
    resposta = str(r.get("resposta", "")).strip()
    if not resposta:
        raise ia.IAIndisponivel("A resposta veio vazia. Tente de novo.")
    data_jogo = banco._ultima(con, cid)["data_jogo"]
    agora = datetime.now().isoformat(timespec="seconds")
    with con:
        ordem = con.execute("SELECT coalesce(max(ordem), -1) + 1 FROM mensagem WHERE carreira_id = ? AND contato = ?",
                            (cid, contato)).fetchone()[0]
        con.executemany("INSERT INTO mensagem(carreira_id, contato, ordem, autor, texto, data_jogo, em) VALUES(?, ?, ?, ?, ?, ?, ?)",
                        [(cid, contato, ordem, "tecnico", texto, data_jogo, agora),
                         (cid, contato, ordem + 1, "contato", resposta, data_jogo, agora)])
        if not auxiliar and (promessa := str(r.get("promessa") or "").strip()):
            con.execute("INSERT INTO promessa SELECT ?, ?, coalesce(max(ordem), -1) + 1, ?, ?, ? FROM promessa "
                        "WHERE carreira_id = ? AND player_id = ?", (cid, int(contato), promessa, data_jogo, agora,
                                                                     cid, int(contato)))
    return conversa(con, cid, contato)


def _sem_nulos(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None}


def _valor_do_elenco(con: sqlite3.Connection, sid: int, idx: int) -> int | None:
    v = con.execute("SELECT sum(valor) FROM vinculo WHERE sincronizacao_id = ? AND time_idx = ?", (sid, idx)).fetchone()[0]
    return v * banco.MOEDA if v else None


def _ouvir(con: sqlite3.Connection, cid: int, pid: int, fatos: dict) -> tuple[str, str]:
    """A mensagem que o jogador manda por conta própria e a vontade dele (dividido se a IA não disser)."""
    anteriores = _mensagens(con, cid, str(pid))[-HISTORICO:]
    r = ia.responder(SISTEMA_REACAO, {"fatos": fatos, "conversa_ate_agora": [
        {"autor": m["autor"], "texto": m["texto"]} for m in anteriores]}, ESQUEMA_REACAO)
    texto = str(r.get("mensagem", "")).strip()
    if not texto:
        raise ia.IAIndisponivel("A mensagem do jogador veio vazia. Tente de novo.")
    return texto, r.get("vontade") if r.get("vontade") in VONTADES else "dividido"


def _gravar_fala(con: sqlite3.Connection, cid: int, pid: int, texto: str, data_jogo: str) -> None:
    con.execute("INSERT INTO mensagem SELECT ?, ?, coalesce(max(ordem), -1) + 1, 'contato', ?, ?, ?, 0 FROM mensagem "
                "WHERE carreira_id = ? AND contato = ?", (cid, str(pid), texto, data_jogo,
                                                          datetime.now().isoformat(timespec="seconds"), cid, str(pid)))


def reagir_propostas(con: sqlite3.Connection, cid: int, pid: int | None = None) -> int:
    """O jogador manda mensagem por conta própria quando chega proposta por ele (com a vontade: ficar, sair ou
    dividido) e quando ela acaba (frustração, alívio ou despedida). Só reage ao fim quem reagiu à chegada; a
    proposta que acabou sem reação fica calada, e a que o mesmo clube melhorou vira a reação à oferta nova.
    pid limita a um jogador. Devolve quantas mensagens mandou. Um erro da IA sobe como ia.IAIndisponivel, e o que já
    foi mandado fica gravado."""
    s = banco._ultima(con, cid)
    todas = [p for p in banco.propostas(con, cid) if pid is None or p["player_id"] == pid]
    k = lambda p: (p["player_id"], p["clube"]["idx"], p["valor_bruto"])
    estado = {(r[0], r[1], r[2]): (r[3], r[4]) for r in con.execute(
        "SELECT player_id, clube_idx, valor, vontade, desfecho_avisado FROM vontade WHERE carreira_id = ?", (cid,))}
    abertas = {(p["player_id"], p["clube"]["idx"]) for p in todas if p["situacao"] == "aberta"}
    acabadas = [p for p in todas if p["situacao"] != "aberta"]
    pendentes = [p for p in acabadas if k(p) in estado and estado[k(p)][0] and not estado[k(p)][1]]
    melhoradas = [p for p in pendentes if (p["player_id"], p["clube"]["idx"]) in abertas]
    anterior = {(p["player_id"], p["clube"]["idx"]): p["valor"] for p in melhoradas}
    with con:
        con.executemany("INSERT INTO vontade(carreira_id, player_id, clube_idx, valor, desfecho_avisado) "
                        "VALUES(?, ?, ?, ?, 1)", [(cid, *k(p)) for p in acabadas if k(p) not in estado])
        con.executemany("UPDATE vontade SET desfecho_avisado = 1 WHERE carreira_id = ? AND player_id = ? "
                        "AND clube_idx = ? AND valor = ?", [(cid, *k(p)) for p in melhoradas])
    novas, fins = {}, {}
    for p in todas:
        if p["situacao"] == "aberta" and k(p) not in estado:
            novas.setdefault(p["player_id"], []).append(p)
    for p in pendentes:
        if p not in melhoradas:
            fins.setdefault(p["player_id"], []).append(p)

    enviadas = 0
    for jogador, ps in novas.items():
        fatos = _fatos(con, cid, str(jogador))
        fatos.update(_sem_nulos({"valor_do_nosso_elenco": _valor_do_elenco(con, s["id"], s["clube_idx"])}))
        fatos["propostas_novas"] = [_sem_nulos({
            "clube": p["clube"]["nome"], "valor": p["valor"],
            "valor_do_elenco": _valor_do_elenco(con, s["id"], p["clube"]["idx"]),
            "oferta_anterior": anterior.get((jogador, p["clube"]["idx"]))}) for p in ps]
        texto, vontade = _ouvir(con, cid, jogador, fatos)
        with con:
            _gravar_fala(con, cid, jogador, texto, s["data_jogo"])
            con.executemany("INSERT INTO vontade(carreira_id, player_id, clube_idx, valor, vontade, fala) "
                            "VALUES(?, ?, ?, ?, ?, ?)", [(cid, *k(p), vontade, texto) for p in ps])
        enviadas += 1
    for jogador, ps in fins.items():
        if ps[0]["situacao"] == "saiu":  # quem saiu do elenco sai de todas as propostas de uma vez
            novo = con.execute("SELECT t.nome FROM vinculo v JOIN time t ON t.carreira_id = ? AND t.idx = v.time_idx "
                               "WHERE v.sincronizacao_id = ? AND v.player_id = ?", (cid, s["id"], jogador)).fetchone()
            fatos = {"jogador": banco._jogador(con, cid, s, jogador)[0],
                     "despedida": _sem_nulos({"clube_novo": novo[0] if novo else None})}
        else:
            fatos = _fatos(con, cid, str(jogador))
            fatos["propostas_encerradas_agora"] = [{"clube": p["clube"]["nome"], "valor": p["valor"],
                                                    "sua_vontade": p["vontade"]} for p in ps]
        texto, _ = _ouvir(con, cid, jogador, fatos)
        with con:
            _gravar_fala(con, cid, jogador, texto, s["data_jogo"])
            con.executemany("UPDATE vontade SET fala = ?, desfecho_avisado = 1 WHERE carreira_id = ? AND player_id = ? "
                            "AND clube_idx = ? AND valor = ?", [(texto, cid, *k(p)) for p in ps])
        enviadas += 1
    return enviadas
