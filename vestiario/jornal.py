"""Jornal do Vestiário (IA): uma edição por sincronização, redigida só com os fatos novos do banco."""
import sqlite3

from . import banco, ia

SISTEMA = """Você é a redação da Gazeta do Vestiário, um jornal esportivo que cobre um clube numa carreira de Master \
League do PES. Escreva a edição a partir dos fatos do JSON.

Regras, sem exceção:
- Use SOMENTE os fatos do JSON. Não cite pessoas, clubes, números, lesões, declarações, bastidores ou histórico que
  não estejam nele. Não invente frases entre aspas.
- Não diga o nome do treinador nem de ninguém da comissão ou da diretoria, e não descreva o que o clube, a diretoria,
  o treinador ou os jogadores pensam, analisam, querem ou decidem: só o que aconteceu (placar, proposta, contratação).
- Este mundo é o do jogo: não relacione com o futebol da vida real.
- Se uma seção não estiver nos fatos, não escreva sobre ela.
- Português do Brasil, tom de jornal esportivo popular: manchete forte e curta (até 8 palavras), linha fina com o
  contexto, e de 2 a 5 matérias curtas (2 a 4 frases cada), da mais importante para a menos.
- Valores em reais, arredondados como se fala no futebol (ex.: "R$ 3,6 milhões"). Datas como "1º de fevereiro"."""

ESQUEMA = {"type": "OBJECT", "properties": {
    "manchete": {"type": "STRING"},
    "linha_fina": {"type": "STRING"},
    "materias": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
        "titulo": {"type": "STRING"}, "texto": {"type": "STRING"}}, "required": ["titulo", "texto"]}}},
    "required": ["manchete", "linha_fina", "materias"]}


def rodar_edicao(con: sqlite3.Connection, cid: int) -> dict:
    """Edição da data do jogo mais recente: a guardada ou uma nova. Erros da IA sobem como ia.IAIndisponivel."""
    fatos = banco.fatos_da_edicao(con, cid)
    ate = fatos["edicao"]["ate"]
    if guardada := next((e for e in banco.edicoes_do_jornal(con, cid) if e["data_jogo"] == ate), None):
        return guardada
    r = ia.responder(SISTEMA, fatos, ESQUEMA)
    materias = [m for m in r.get("materias", []) if str(m.get("titulo", "")).strip() and str(m.get("texto", "")).strip()]
    if not str(r.get("manchete", "")).strip() or not materias:
        raise ia.IAIndisponivel("A edição veio sem matérias. Tente de novo.")
    conteudo = {"manchete": r["manchete"].strip(), "linha_fina": str(r.get("linha_fina", "")).strip(),
                "materias": [{"titulo": m["titulo"].strip(), "texto": m["texto"].strip()} for m in materias[:5]]}
    banco.guardar_edicao(con, cid, fatos, conteudo)
    return {"data_jogo": ate, "de": fatos["edicao"]["de"], "conteudo": conteudo}
