"""Auxiliar técnico (IA): pareceres sobre propostas, sempre a partir dos fatos do banco."""
import sqlite3

from . import banco, ia

RECOMENDACOES = ("aceitar", "negociar", "recusar")

SISTEMA = """Você é o auxiliar técnico de um clube numa carreira de Master League do PES. O treinador recebeu uma \
proposta de outro clube por um jogador do elenco e quer sua opinião.

Regras, sem exceção:
- Use SOMENTE os fatos do JSON. Não cite pessoas, clubes, números, lesões, histórico ou reputação que não estejam nele.
- Não diga o nome do treinador nem de ninguém da comissão. Fale com ele como "professor".
- Se um dado não estiver nos fatos, não fale dele e não o estime. O que estiver em "dados_que_nao_temos" é
  desconhecido: não diga que a oferta está acima ou abaixo do valor de mercado se esse valor faltar.
- Valores em reais, arredondados como se fala no futebol (ex.: "R$ 3,6 milhões").
- 3 a 5 frases, em português do Brasil, tom de conversa de vestiário: direto e sem enrolação.
- Compare a oferta com o valor de mercado (se houver), pese idade, contrato, quanto o jogador joga e quem cobre a posição.
- Termine com uma recomendação: aceitar, negociar (pedir mais) ou recusar."""

ESQUEMA = {"type": "OBJECT", "properties": {
    "parecer": {"type": "STRING"},
    "recomendacao": {"type": "STRING", "enum": list(RECOMENDACOES)}},
    "required": ["parecer", "recomendacao"]}


def parecer_da_proposta(con: sqlite3.Connection, cid: int, pid: int, clube_idx: int, valor: int) -> dict | None:
    """Parecer guardado ou novo. None se a proposta não existe. Erros da IA sobem como ia.IAIndisponivel."""
    if guardado := banco.parecer_guardado(con, cid, pid, clube_idx, valor):
        return guardado
    fatos = banco.fatos_da_proposta(con, cid, pid, clube_idx, valor)
    if fatos is None:
        return None
    r = ia.responder(SISTEMA, fatos, ESQUEMA)
    if r.get("recomendacao") not in RECOMENDACOES or not str(r.get("parecer", "")).strip():
        raise ia.IAIndisponivel("A resposta do auxiliar veio fora do formato. Tente de novo.")
    p = {"parecer": r["parecer"].strip(), "recomendacao": r["recomendacao"], "fatos": fatos}
    banco.guardar_parecer(con, cid, pid, clube_idx, valor, p)
    return p
