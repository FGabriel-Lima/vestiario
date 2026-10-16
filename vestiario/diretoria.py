"""Diretoria: o acordo anual (metas e regras de mercado), a fiscalização pelo save e a confiança.
Todo número sai do código daqui; a IA (reuniao) só dá a voz ao presidente e escolhe ofertas do cardápio.
Spec: docs/superpowers/specs/2026-10-16-diretoria-design.md"""
import json
import sqlite3
from datetime import date, datetime, timedelta

from . import banco, ia

INICIAL, PISO_DO_ANO, LIMITE_ULTIMATO = 60, 25, 15
FASES_COPA = ["fase inicial", "oitavas de final", "quartas de final", "semifinal", "final", "título"]
ORDEM_FASE = {"Oitavas de final": 1, "Quartas de final": 2, "Semifinal": 3, "Final": 4}


def _porte(posicao_valor: int) -> str:
    """Pela posição do clube no ranking de valor de mercado do elenco entre os times da liga."""
    return "grande" if posicao_valor <= 4 else "medio" if posicao_valor <= 12 else "pequeno"


def _divisao(nome: str | None) -> int:
    """Série A = 1, B = 2, C = 3, pelo nome da liga (o id 120 é a Série C no Transfer Patch e a liga chinesa no
    FL26, então o id não serve). Outra liga = 1."""
    if nome and nome.startswith("Brasileirão Série ") and nome[-1] in "ABC":
        return "ABC".index(nome[-1]) + 1
    return 1


def competicoes_do_ano(con: sqlite3.Connection, cid: int, ano: int, clube: int) -> tuple[dict | None, list[dict]]:
    """A liga de pontos corridos do clube no ano (a com mais jogos dele, contando os futuros do calendário) e as
    copas (edições com 2 ou mais jogos dele que não são de pontos corridos), montadas como na aba Campeonatos."""
    liga, jogos_na_liga, copas = None, 0, []
    for chave, e in banco._edicoes(con, cid).items():
        if not e["temporada"].startswith(str(ano)):
            continue
        todas = [p for t in e["partes"] for p in t]
        do_clube = [p for p in todas if clube in (p["mandante_idx"], p["visitante_idx"])]
        if not do_clube:
            continue
        if all(p["rodada"] < banco.MATA_MATA and not p["grupo"] for p in todas):
            if len(do_clube) > jogos_na_liga:
                fase = banco._montar(e, clube)["fases"][0]
                linhas = fase["grupos"][0]["linhas"]
                nossa = next((l for l in linhas if l["idx"] == clube), None)
                jogos_na_liga = len(do_clube)
                liga = {"chave": chave, "nome": e["nome"], "times": [l["idx"] for l in linhas],
                        "posicao": nossa["posicao"] if nossa else None, "rodadas_jogadas": fase["rodadas_jogadas"],
                        "rodadas_total": fase["rodadas_total"], "primeiro_jogo": min(p["data"] for p in do_clube),
                        "encerrada": all(p["disputada"] for p in do_clube)}
        elif len(do_clube) >= 2:
            copas.append({"chave": chave, "nome": e["nome"]})
    return liga, copas


def perfil(con: sqlite3.Connection, cid: int, ano: int | None = None) -> dict:
    """Como a diretoria enxerga o clube, só com dados do banco (spec, seção 1). Valores em R$."""
    s = banco._ultima(con, cid)
    clube = s["clube_idx"]
    ano = ano or int(s["data_jogo"][:4])
    liga, copas = competicoes_do_ano(con, cid, ano, clube)
    anterior, _ = competicoes_do_ano(con, cid, ano - 1, clube)
    faltou, posicao_valor = [], None
    if liga:
        soma = dict(con.execute("SELECT time_idx, sum(valor) FROM vinculo WHERE sincronizacao_id = ? AND valor > 0 "
                                "GROUP BY time_idx", (s["id"],)).fetchall())
        if soma.get(clube):
            posicao_valor = 1 + sum(soma.get(t, 0) > soma[clube] for t in liga["times"] if t != clube)
    if posicao_valor is None:
        faltou.append("valor de mercado dos elencos")
    divisao = _divisao(liga["nome"]) if liga else 1
    div_anterior = _divisao(anterior["nome"]) if anterior else None
    f = banco.financas(con, s)
    receitas = sum((f["receitas"] or {}).values())
    contratos = con.execute("SELECT player_id, salario_anual FROM contrato WHERE sincronizacao_id = ? AND emprestimo = 0 "
                            "ORDER BY salario_anual DESC, player_id", (s["id"],)).fetchall()
    anual = sum(c[1] for c in contratos)
    crise = False
    if not receitas:
        faltou.append("receitas")
    elif f["folha_semanal"]:
        crise = f["folha_semanal"] * 52 > 0.7 * receitas  # ressalva: as receitas do save não têm bilheteria
    if s["folga_salarial"] is not None and anual:
        crise = crise or s["folga_salarial"] < 0.05 * (s["folga_salarial"] + anual)
    ultimo = con.execute("SELECT balanco FROM acordo WHERE carreira_id = ? AND clube_idx = ? AND ano < ? "
                         "AND balanco IS NOT NULL ORDER BY ano DESC LIMIT 1", (cid, clube, ano)).fetchone()
    return {"ano": ano, "clube": s["clube_nome"], "liga": liga, "copas": copas, "divisao": divisao,
            "posicao_valor": posicao_valor, "porte": _porte(posicao_valor) if posicao_valor else "medio",
            "rebaixado": div_anterior is not None and divisao > div_anterior,
            "promovido": div_anterior is not None and divisao < div_anterior, "crise": crise,
            "orcamento": s["orcamento"] * banco.MOEDA if s["orcamento"] is not None else None,
            "folha_semanal": f["folha_semanal"], "receitas": receitas or None,
            "maiores_salarios": [c[0] for c in contratos[:5]],
            "momento": json.loads(ultimo[0])["momento"] if ultimo else "estreia", "faltou": faltou}
