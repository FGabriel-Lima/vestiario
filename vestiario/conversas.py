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

""" + REGRAS

SISTEMA_AUXILIAR = """Você é o auxiliar técnico do clube numa carreira de Master League do PES, conversando com o \
treinador por mensagem. Analise o elenco e o momento do clube com franqueza, como um auxiliar de confiança: quem
joga pouco, quem está em boa ou má fase, contratos vencendo, propostas abertas, próximos jogos e orçamento.
Sugira caminhos, mas a decisão é do treinador.

""" + REGRAS

ESQUEMA = {"type": "OBJECT", "properties": {"resposta": {"type": "STRING"}}, "required": ["resposta"]}
ESQUEMA_JOGADOR = {"type": "OBJECT", "properties": {"resposta": {"type": "STRING"}, "promessa": {"type": "STRING"}},
                   "required": ["resposta"]}


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
    lista = [{"contato": "auxiliar", "nome": "Auxiliar técnico", "sinais": [], "ultima": ultima.get("auxiliar")}]
    for l in banco.elenco_para_conversa(con, cid):
        c = str(l["player_id"])
        lista.append({"contato": c, "player_id": l["player_id"], "nome": l["nome"], "posicao": l["posicao"],
                      "idade": l["idade"], "ultima": ultima.get(c),
                      "sinais": sinais(l, jogos, s["data_jogo"], abertas) + ["promessa feita"] * (l["player_id"] in prometidos)})
    return lista


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
        con.executemany("INSERT INTO mensagem VALUES(?, ?, ?, ?, ?, ?, ?)",
                        [(cid, contato, ordem, "tecnico", texto, data_jogo, agora),
                         (cid, contato, ordem + 1, "contato", resposta, data_jogo, agora)])
        if not auxiliar and (promessa := str(r.get("promessa") or "").strip()):
            con.execute("INSERT INTO promessa SELECT ?, ?, coalesce(max(ordem), -1) + 1, ?, ?, ? FROM promessa "
                        "WHERE carreira_id = ? AND player_id = ?", (cid, int(contato), promessa, data_jogo, agora,
                                                                     cid, int(contato)))
    return conversa(con, cid, contato)
