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


# Proposta base por porte e o que cada situação muda (spec, seção 2). meta_liga = posição; meta_copa = se o porte
# tem meta de copa; contratacoes = (janela de janeiro, janela do meio); teto_contratacao = % do orçamento;
# vender_para_comprar = %; folha_maxima = % da folha atual; vender_salarios = quantos dos 5 maiores salários.
# None = o item não entra.
BASE = {
    "grande": {"meta_liga": 4, "meta_copa": True, "contratacoes": (4, 3), "teto_contratacao": 50,
               "vender_para_comprar": None, "livres": 2, "emprestimos": 2, "folha_maxima": None, "vender_salarios": None},
    "medio": {"meta_liga": 10, "meta_copa": True, "contratacoes": (3, 2), "teto_contratacao": 40,
              "vender_para_comprar": 50, "livres": 1, "emprestimos": 2, "folha_maxima": None, "vender_salarios": None},
    "pequeno": {"meta_liga": 16, "meta_copa": False, "contratacoes": (2, 2), "teto_contratacao": 30,
                "vender_para_comprar": 75, "livres": 1, "emprestimos": 1, "folha_maxima": None, "vender_salarios": None},
}
SITUACOES = [  # nesta ordem; um valor da situação substitui o do porte; chave ausente = o porte fica
    ("promovido", {"meta_liga": 16, "contratacoes": (5, 3), "teto_contratacao": 40, "livres": 2, "emprestimos": 3}),
    ("rebaixado", {"meta_liga": 4, "contratacoes": (2, 1), "teto_contratacao": 25, "vender_para_comprar": 100,
                   "livres": 1, "emprestimos": 1, "folha_maxima": 80, "vender_salarios": 2}),
    ("crise", {"contratacoes": (1, 1), "teto_contratacao": 20, "vender_para_comprar": 100, "livres": 1,
               "emprestimos": 1, "folha_maxima": 100, "vender_salarios": 1}),
]
FAIXA = {"meta_liga": (2, 1), "meta_copa": (1, 1), "contratacoes": (2, 1), "teto_contratacao": (20, 10),
         "vender_para_comprar": (25, 25), "livres": (1, 1), "emprestimos": (1, 1), "folha_maxima": (10, 5),
         "vender_salarios": (1, 1)}  # (amplitude em volta do valor base, passo)
AFROUXA = {"meta_liga": 1, "meta_copa": -1, "contratacoes": 1, "teto_contratacao": 1, "vender_para_comprar": -1,
           "livres": 1, "emprestimos": 1, "folha_maxima": 1, "vender_salarios": -1}  # sentido de afrouxar
LIMITES = {"meta_liga": (1, 20), "meta_copa": (0, 5), "contratacoes": (0, 10), "teto_contratacao": (0, 100),
           "vender_para_comprar": (0, 100), "livres": (0, 10), "emprestimos": (0, 10), "folha_maxima": (50, 150),
           "vender_salarios": (0, 5)}
JANELA = {1: "de janeiro", 2: "do meio do ano"}


def _item(tipo: str, valor: int, **extra) -> dict:
    return {"tipo": tipo, "valor": valor, "base": valor, **extra}


def proposta(p: dict) -> list[dict]:
    """Os itens do acordo para o perfil (spec, seção 2)."""
    v = dict(BASE[p["porte"]])
    for marca, muda in SITUACOES:
        if p[marca]:
            v.update(muda)
    itens = []
    if p["liga"] and v["meta_liga"] is not None:
        itens.append(_item("meta_liga", min(v["meta_liga"], len(p["liga"]["times"]))))
    if v["meta_copa"]:
        for c in p["copas"]:
            itens.append(_item("meta_copa", 2 if c["nome"] == "Copa Libertadores" else 1, copa=c["nome"],
                               chave=c["chave"]))
    for janela, n in enumerate(v["contratacoes"], start=1):
        itens.append(_item("contratacoes", n, janela=janela))
    if p["orcamento"] is not None:
        itens.append(_item("teto_contratacao", v["teto_contratacao"], orcamento=p["orcamento"]))
    if v["vender_para_comprar"] is not None:
        itens.append(_item("vender_para_comprar", v["vender_para_comprar"]))
    itens.append(_item("livres", v["livres"]))
    itens.append(_item("emprestimos", v["emprestimos"]))
    if v["folha_maxima"] is not None and p["folha_semanal"]:
        itens.append(_item("folha_maxima", v["folha_maxima"], folha=p["folha_semanal"]))
    if v["vender_salarios"] and p["maiores_salarios"]:
        itens.append(_item("vender_salarios", v["vender_salarios"], jogadores=p["maiores_salarios"]))
    return itens


def reais(item: dict) -> int | None:
    """O valor em R$ dos itens em porcentagem: o teto por contratação e a folha máxima."""
    if item["tipo"] == "teto_contratacao":
        return round(item["orcamento"] * item["valor"] / 100)
    if item["tipo"] == "folha_maxima":
        return round(item["folha"] * item["valor"] / 100)
    return None


def _dinheiro(v: int) -> str:
    if abs(v) >= 1_000_000:
        return f"R$ {v / 1_000_000:.1f} mi".replace(".0 mi", " mi").replace(".", ",")
    return f"R$ {round(v / 1000)} mil"


def _plural(n: int, um: str, varios: str) -> str:
    return f"{n} {um if n == 1 else varios}"


def descrever(item: dict, valor: int | None = None) -> str:
    """A exigência em uma frase (com outro valor, para descrever uma mudança)."""
    v = item["valor"] if valor is None else valor
    t, x = item["tipo"], {**item, "valor": v}
    if t == "meta_liga":
        return f"terminar a liga em {v}º ou melhor"
    if t == "meta_copa":
        fase = FASES_COPA[v]
        artigo = "o" if v == 5 else "a" if v in (3, 4) else "as"
        return f"{item['copa']}: chegar {'ao' if artigo == 'o' else 'à' if artigo == 'a' else 'às'} {fase}"
    if t == "contratacoes":
        return f"até {_plural(v, 'contratação', 'contratações')} na janela {JANELA[item['janela']]}"
    if t == "teto_contratacao":
        return f"nenhuma compra acima de {_dinheiro(reais(x))} ({v}% do orçamento)"
    if t == "vender_para_comprar":
        return f"vendas pagando pelo menos {v}% do gasto com compras no ano"
    if t == "livres":
        return f"até {_plural(v, 'agente livre', 'agentes livres')} no ano"
    if t == "emprestimos":
        return f"até {_plural(v, 'empréstimo', 'empréstimos')} de entrada no ano"
    if t == "folha_maxima":
        return f"folha semanal de até {_dinheiro(reais(x))}"
    return f"vender {v} dos 5 maiores salários até 30/09"
