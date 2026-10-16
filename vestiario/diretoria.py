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


def _evento(con: sqlite3.Connection, cid: int, clube: int, chave: str, data_jogo: str, motivo: str,
            variacao: int) -> bool:
    """Grava um evento de confiança uma vez só (a chave não se repete). Devolve se gravou."""
    return con.execute("INSERT OR IGNORE INTO confianca VALUES(?, ?, ?, ?, ?, ?)",
                       (cid, clube, chave, data_jogo, motivo, variacao)).rowcount == 1


def confianca(con: sqlite3.Connection, cid: int, clube: int) -> int:
    """Soma dos eventos a partir de 60, presa entre 0 e 100 a cada passo."""
    v = INICIAL
    for (d,) in con.execute("SELECT variacao FROM confianca WHERE carreira_id = ? AND clube_idx = ? ORDER BY rowid",
                            (cid, clube)):
        v = min(100, max(0, v + d))
    return v


def historico(con: sqlite3.Connection, cid: int, clube: int) -> list[dict]:
    return [{"data_jogo": r[0], "motivo": r[1], "variacao": r[2]} for r in con.execute(
        "SELECT data_jogo, motivo, variacao FROM confianca WHERE carreira_id = ? AND clube_idx = ? ORDER BY rowid DESC",
        (cid, clube))]


def _janela_de(data: str) -> int:
    return 1 if data[5:7] <= "06" else 2


def mercado(con: sqlite3.Connection, cid: int, clube: int, ano: int) -> tuple[list[dict], list[dict]]:
    """Chegadas e saídas do ano, pela aba Transferências. A janela (1 = janeiro a junho, 2 = julho a dezembro) é a da
    sincronização em que o negócio apareceu; o valor é em R$ (negativo = o clube pagou; None = sem negócio no livro);
    empréstimo = a chegada teve contrato de empréstimo em alguma sincronização do ano."""
    emprestados = {r[0] for r in con.execute(
        "SELECT DISTINCT c.player_id FROM contrato c JOIN sincronizacao s ON s.id = c.sincronizacao_id WHERE "
        "s.carreira_id = ? AND s.clube_idx = ? AND c.emprestimo = 1 AND substr(s.data_jogo, 1, 4) = ?",
        (cid, clube, str(ano)))}
    chegadas, saidas = [], []
    for j in banco.transferencias(con, cid)["janelas"]:
        if j["ate"][:4] != str(ano):
            continue
        janela = _janela_de(j["ate"])
        chegadas += [{"player_id": x["player_id"], "nome": x["nome"], "janela": janela, "valor": x["valor"],
                      "emprestimo": x["player_id"] in emprestados} for x in j["chegaram"]]
        saidas += [{"player_id": x["player_id"], "nome": x["nome"], "janela": janela, "valor": x["valor"]}
                   for x in j["sairam"]]
    return chegadas, saidas


def fase_na_copa(con: sqlite3.Connection, cid: int, clube: int, chave: str) -> tuple[int, bool]:
    """(fase mais longe que o clube alcançou, foi eliminado?) numa edição de copa. 0 = fase inicial (grupos ou fases
    antes das oitavas), 1 = oitavas, 2 = quartas, 3 = semifinal, 4 = final, 5 = título."""
    e = banco.edicao(con, cid, chave)
    if e is None:
        return 0, False
    if e["campeao"] and e["campeao"]["idx"] == clube:
        return 5, False
    alcancada, eliminado = 0, False
    for col in e["chaveamento"]:
        for c in col["confrontos"]:
            nosso = next((t for t in c["times"] if t["idx"] == clube), None)
            if nosso:
                alcancada = max(alcancada, ORDEM_FASE.get(col["titulo"], 0))
                eliminado = eliminado or (any(t["vencedor"] for t in c["times"]) and not nosso["vencedor"])
    for f in e["fases"]:
        for g in f.get("grupos", []):
            eliminado = eliminado or any(l["idx"] == clube and l.get("avancou") is False for l in g["linhas"])
    return alcancada, eliminado


def _uso(item: dict) -> str:
    """O andamento do item em poucas palavras, para a tela e para a IA."""
    d, t, v = item["detalhe"], item["tipo"], item["valor"]
    if t == "meta_liga" and d.get("posicao"):
        return f"{d['posicao']}º agora ({d['rodadas_jogadas']} de {d['rodadas_total']} rodadas)"
    if t == "meta_copa":
        return f"até agora: {d['fase']}"
    if t == "contratacoes":
        return f"{d['usadas']} de {v} usadas"
    if t in ("livres", "emprestimos"):
        return f"{d['usados']} de {v} usados"
    if t == "teto_contratacao":
        return f"maior compra: {_dinheiro(d['maior'])}" if d["maior"] else "nenhuma compra"
    if t == "vender_para_comprar":
        return f"vendas {_dinheiro(d['vendas'])} · compras {_dinheiro(d['gastos'])}"
    if t == "folha_maxima":
        return f"folha agora: {_dinheiro(d['folha'])}" if d["folha"] else ""
    if t == "vender_salarios":
        return f"{d['vendidos']} de {v} vendidos"
    return ""


def avaliar(con: sqlite3.Connection, cid: int, acordo: dict, hoje: str, registrar: bool = True,
            balanco: bool = False) -> list[dict]:
    """O estado de cada item do acordo, com o detalhe dos números (spec, seção 2). Com registrar, grava os eventos
    de quebra e de meta em risco (só com o acordo assinado ou imposto). Com balanco, as metas e o vender_para_comprar
    ganham o resultado final do ano."""
    clube, ano = acordo["clube_idx"], acordo["ano"]
    vale = registrar and acordo["estado"] in ("assinado", "imposto")
    chegadas, saidas = mercado(con, cid, clube, ano)
    liga, _ = competicoes_do_ano(con, cid, ano, clube)
    s = banco._ultima(con, cid)
    elenco = {r[0] for r in con.execute("SELECT player_id FROM elenco WHERE sincronizacao_id = ?", (s["id"],))}
    folha = banco.financas(con, s)["folha_semanal"]
    compras = [-c["valor"] for c in chegadas if c["valor"] and c["valor"] < 0]
    gastos, vendas = sum(compras), sum(x["valor"] for x in saidas if x["valor"] and x["valor"] > 0)

    def quebra(chave, motivo, variacao):
        if vale:
            _evento(con, cid, clube, f"quebra:{chave}", hoje, motivo, variacao)

    resultado = []
    for item in acordo["itens"]:
        t, v = item["tipo"], item["valor"]
        estado, detalhe = "em_dia", {}
        if t == "meta_liga":
            pos = liga["posicao"] if liga else None
            detalhe = {"posicao": pos, "rodadas_jogadas": liga["rodadas_jogadas"] if liga else 0,
                       "rodadas_total": liga["rodadas_total"] if liga else 0}
            if balanco:
                estado = "cumprido" if pos is not None and pos <= v else "nao_cumprido"
            elif pos is not None and liga["rodadas_jogadas"] * 3 >= liga["rodadas_total"] and pos > v + 3:
                estado = "em_risco"
                if vale:
                    _evento(con, cid, clube, f"risco:meta_liga:{hoje[:7]}", hoje,
                            f"Meta da liga em risco ({pos}º, meta de {v}º)", -5)
        elif t == "meta_copa":
            alcancada, eliminado = fase_na_copa(con, cid, clube, item["chave"])
            detalhe = {"fase": FASES_COPA[alcancada]}
            if alcancada >= v:
                estado = "cumprido"
            elif eliminado:
                estado = "nao_cumprido"
        elif t == "contratacoes":
            usadas = sum(c["janela"] == item["janela"] for c in chegadas)
            detalhe = {"usadas": usadas}
            if usadas > v:
                estado = "quebrado"
                quebra(f"contratacoes:{ano}:{item['janela']}",
                       f"Contratações além do limite na janela {JANELA[item['janela']]} ({usadas} de {v})", -15)
            elif usadas and usadas >= v - 1:
                estado = "em_risco"
        elif t == "teto_contratacao":
            teto = reais(item)
            detalhe = {"maior": max(compras, default=0), "teto": teto}
            acima = [c for c in chegadas if c["valor"] and -c["valor"] > teto]
            if acima:
                estado = "quebrado"
                for janela in sorted({c["janela"] for c in acima}):
                    nomes = ", ".join(c["nome"] for c in acima if c["janela"] == janela)
                    quebra(f"teto_contratacao:{ano}:{janela}", f"Compra acima do teto de {_dinheiro(teto)} ({nomes})", -10)
        elif t == "vender_para_comprar":
            detalhe = {"gastos": gastos, "vendas": vendas}
            if gastos and vendas * 100 < v * gastos:
                estado = "quebrado" if balanco else "em_risco"
                if balanco:
                    quebra(f"vender_para_comprar:{ano}", f"As vendas pagaram menos de {v}% das compras", -15)
            elif balanco:
                estado = "cumprido"
        elif t in ("livres", "emprestimos"):
            n = sum(c["emprestimo"] if t == "emprestimos" else (c["valor"] is None and not c["emprestimo"])
                    for c in chegadas)
            detalhe = {"usados": n}
            if n > v:
                estado = "quebrado"
                rotulo = "Empréstimos de entrada" if t == "emprestimos" else "Agentes livres"
                quebra(f"{t}:{ano}", f"{rotulo} além do limite ({n} de {v})", -15)
            elif n and n == v:
                estado = "em_risco"
        elif t == "folha_maxima":
            teto = reais(item)
            detalhe = {"folha": folha, "teto": teto}
            if folha and folha > teto:
                estado = "quebrado"
                quebra(f"folha_maxima:{ano}:{_janela_de(hoje)}",
                       f"Folha semanal de {_dinheiro(folha)}, acima de {_dinheiro(teto)}", -10)
            elif folha and folha > 0.95 * teto:
                estado = "em_risco"
        elif t == "vender_salarios":
            vendidos = [p for p in item["jogadores"] if p not in elenco]
            detalhe = {"vendidos": len(vendidos)}
            if len(vendidos) >= v:
                estado = "cumprido"
            elif balanco or hoje > f"{ano}-09-30":
                estado = "quebrado"
                quebra(f"vender_salarios:{ano}", f"Não vendeu {v} dos 5 maiores salários até 30/09", -15)
            else:
                estado = "em_risco"
        feito = {**item, "estado": estado, "detalhe": detalhe, "descricao": descrever(item)}
        feito["uso"] = _uso(feito)
        resultado.append(feito)
    return resultado


TITULOS_GRANDES = {"Brasileirão Série A", "Copa Libertadores", "Copa do Brasil"}


def _data(iso: str) -> str:
    return "/".join(reversed(iso[:10].split("-")))


def _acordo(con: sqlite3.Connection, cid: int, clube: int, ano: int) -> dict | None:
    r = con.execute("SELECT * FROM acordo WHERE carreira_id = ? AND clube_idx = ? AND ano = ?",
                    (cid, clube, ano)).fetchone()
    if r is None:
        return None
    return {**dict(r), "itens": json.loads(r["itens"]), "perfil": json.loads(r["perfil"]),
            "balanco": json.loads(r["balanco"]) if r["balanco"] else None}


def _salvar_itens(con: sqlite3.Connection, acordo: dict) -> None:
    con.execute("UPDATE acordo SET itens = ? WHERE carreira_id = ? AND clube_idx = ? AND ano = ?",
                (json.dumps(acordo["itens"], ensure_ascii=False), acordo["carreira_id"], acordo["clube_idx"],
                 acordo["ano"]))


def demitido(con: sqlite3.Connection, cid: int, clube: int) -> str | None:
    """A data do jogo da demissão, se houve."""
    r = con.execute("SELECT data_jogo FROM confianca WHERE carreira_id = ? AND clube_idx = ? AND chave LIKE 'demissao:%'",
                    (cid, clube)).fetchone()
    return r[0] if r else None


def _ultimato_ativo(con: sqlite3.Connection, cid: int, clube: int) -> sqlite3.Row | None:
    return con.execute("SELECT nascido_em, jogos FROM ultimato WHERE carreira_id = ? AND clube_idx = ? "
                       "AND estado = 'ativo'", (cid, clube)).fetchone()


def _criar_acordo(con: sqlite3.Connection, cid: int, clube: int, ano: int, hoje: str) -> None:
    p = perfil(con, cid, ano)
    atual = confianca(con, cid, clube)
    if atual < PISO_DO_ANO and not _ultimato_ativo(con, cid, clube):
        _evento(con, cid, clube, f"piso:{ano}", hoje, "Ano novo: a diretoria dá um voto de confiança", PISO_DO_ANO - atual)
    # a primeira sincronização do ano já depois de 01/07 pula a revisão do meio do ano
    con.execute("INSERT INTO acordo(carreira_id, clube_idx, ano, estado, itens, perfil, data_jogo, revisao_feita) "
                "VALUES(?, ?, ?, 'proposto', ?, ?, ?, ?)",
                (cid, clube, ano, json.dumps(proposta(p), ensure_ascii=False), json.dumps(p, ensure_ascii=False), hoje,
                 int(hoje >= f"{ano}-07-01")))


def _vence_a_reuniao(acordo: dict, hoje: str) -> bool:
    """A reunião vence no 1º jogo da liga (sem liga, em 01/04). Acordo aberto com a liga já começada ganha 30 dias."""
    prazo = acordo["perfil"]["liga"]["primeiro_jogo"] if acordo["perfil"]["liga"] else f"{acordo['ano']}-04-01"
    if acordo["data_jogo"] >= prazo:
        prazo = (date.fromisoformat(acordo["data_jogo"]) + timedelta(days=30)).isoformat()
    return hoje >= prazo


def _balanco(con: sqlite3.Connection, cid: int, acordo: dict, hoje: str) -> None:
    """Fecha o ano: confere as metas e o vender_para_comprar, lança os eventos e guarda o resultado."""
    clube, ano = acordo["clube_idx"], acordo["ano"]
    metas = {}
    for i in avaliar(con, cid, acordo, hoje, registrar=True, balanco=True):
        if i["tipo"] == "meta_liga" and i["detalhe"]["posicao"] is not None:
            pos, v = i["detalhe"]["posicao"], i["valor"]
            if i["estado"] == "cumprido":
                d, motivo = 15, f"Meta da liga cumprida ({pos}º, meta de {v}º)"
            else:
                d, motivo = -30 if pos > v + 4 else -20, f"Meta da liga não cumprida ({pos}º, meta de {v}º)"
            _evento(con, cid, clube, f"balanco:meta_liga:{ano}", hoje, motivo, d)
            metas["meta_liga"] = i["estado"]
        elif i["tipo"] == "meta_copa" and i["estado"] in ("cumprido", "nao_cumprido"):
            ok = i["estado"] == "cumprido"
            _evento(con, cid, clube, f"balanco:meta_copa:{ano}:{i['copa']}", hoje,
                    f"{i['copa']}: meta {'cumprida' if ok else 'não cumprida'} ({i['detalhe']['fase']})", 8 if ok else -8)
            metas[i["copa"]] = i["estado"]
    campeao = any(t["campeao"]["idx"] == clube and t["temporada"].startswith(str(ano)) for t in banco.titulos(con, cid))
    momento = "campeao" if campeao else "nao_cumpriu" if any(e != "cumprido" for e in metas.values()) else "cumpriu"
    con.execute("UPDATE acordo SET estado = 'encerrado', balanco = ? WHERE carreira_id = ? AND clube_idx = ? AND ano = ?",
                (json.dumps({"metas": metas, "momento": momento, "data_jogo": hoje}, ensure_ascii=False), cid, clube, ano))


def _titulos(con: sqlite3.Connection, cid: int, clube: int, inicio: str) -> None:
    """Título conquistado desde o primeiro acordo (os de antes não mexem na confiança)."""
    for t in banco.titulos(con, cid):
        if t["campeao"]["idx"] == clube and t["fim"] >= inicio:
            _evento(con, cid, clube, f"titulo:{t['chave']}", t["fim"], f"Título: {t['nome']} {t['temporada']}",
                    20 if t["nome"] in TITULOS_GRANDES else 10)


def _derrotas(con: sqlite3.Connection, cid: int, clube: int, inicio: str) -> None:
    seguidas = []
    for p in banco.partidas(con, cid):
        if not p["disputada"] or p["data"] < inicio:
            continue
        pro, contra = banco._placar(p, clube)
        seguidas = seguidas + [p["data"]] if pro < contra else []
        if len(seguidas) == 5:
            _evento(con, cid, clube, f"derrotas:{seguidas[0]}", p["data"], "5 derrotas seguidas", -5)


def situacao_do_ultimato(todas: list[dict], jogos: list[list], clube: int) -> dict:
    """Pontos nos jogos do ultimato já disputados e quantos faltam."""
    # ponytail: jogo remarcado muda a data e não é achado (o ultimato fica esperando); casar por adversário se acontecer
    chaves = {tuple(j) for j in jogos}
    disputados = [p for p in todas if p["disputada"] and (p["data"], p["mandante_idx"], p["visitante_idx"]) in chaves]
    pontos = sum(3 if a > b else 1 if a == b else 0 for a, b in (banco._placar(p, clube) for p in disputados))
    return {"pontos": pontos, "faltam": len(chaves) - len(disputados), "jogos": jogos}


def _ultimato(con: sqlite3.Connection, cid: int, clube: int, hoje: str) -> None:
    todas = banco.partidas(con, cid)
    ativo = _ultimato_ativo(con, cid, clube)
    if ativo:
        r = situacao_do_ultimato(todas, json.loads(ativo["jogos"]), clube)
        if r["pontos"] >= 7:
            novo = "cumprido"
            _evento(con, cid, clube, f"ultimato:cumprido:{ativo['nascido_em']}", hoje,
                    f"Ultimato cumprido ({r['pontos']} pontos)", 30 - confianca(con, cid, clube))
        elif r["pontos"] + 3 * r["faltam"] < 7:
            novo = "falhou"
            _evento(con, cid, clube, f"demissao:{ativo['nascido_em']}", hoje,
                    f"Demitido: ultimato não cumprido ({r['pontos']} pontos)", 0)
        else:
            return
        con.execute("UPDATE ultimato SET estado = ? WHERE carreira_id = ? AND clube_idx = ? AND nascido_em = ?",
                    (novo, cid, clube, ativo["nascido_em"]))
    elif confianca(con, cid, clube) < LIMITE_ULTIMATO:
        futuros = [p for p in todas if not p["disputada"] and p["data"] > hoje][:5]
        if len(futuros) == 5:
            con.execute("INSERT OR IGNORE INTO ultimato VALUES(?, ?, ?, ?, 'ativo')", (cid, clube, hoje, json.dumps(
                [[p["data"], p["mandante_idx"], p["visitante_idx"]] for p in futuros])))
            _evento(con, cid, clube, f"ultimato:inicio:{hoje}", hoje,
                    "Ultimato: pelo menos 7 pontos nos próximos 5 jogos", 0)


def atualizar(con: sqlite3.Connection, cid: int) -> None:
    """Roda a cada sincronização, sem IA: fecha os anos anteriores, abre ou impõe o acordo do ano, fiscaliza, conta
    títulos e derrotas e cuida do ultimato."""
    s = banco._ultima(con, cid)
    clube, hoje = s["clube_idx"], s["data_jogo"]
    ano = int(hoje[:4])
    with con:
        for (a,) in con.execute("SELECT ano FROM acordo WHERE carreira_id = ? AND clube_idx = ? AND ano < ? "
                                "AND estado <> 'encerrado'", (cid, clube, ano)).fetchall():
            _balanco(con, cid, _acordo(con, cid, clube, a), hoje)
        if demitido(con, cid, clube):
            return
        acordo = _acordo(con, cid, clube, ano)
        if acordo is None:
            _criar_acordo(con, cid, clube, ano, hoje)
            acordo = _acordo(con, cid, clube, ano)
        if acordo["estado"] == "proposto" and _vence_a_reuniao(acordo, hoje):
            con.execute("UPDATE acordo SET estado = 'imposto', assinado_data = ? WHERE carreira_id = ? AND clube_idx = ? "
                        "AND ano = ?", (hoje, cid, clube, ano))
            _evento(con, cid, clube, f"faltou:{ano}", hoje, "Acordo imposto: o técnico faltou à reunião", -5)
            acordo = _acordo(con, cid, clube, ano)
        if acordo["estado"] != "encerrado":
            avaliar(con, cid, acordo, hoje)
            liga, _ = competicoes_do_ano(con, cid, ano, clube)
            if liga and liga["encerrada"]:
                _balanco(con, cid, acordo, hoje)
        inicio = con.execute("SELECT min(data_jogo) FROM acordo WHERE carreira_id = ? AND clube_idx = ?",
                             (cid, clube)).fetchone()[0]
        _titulos(con, cid, clube, inicio)
        _derrotas(con, cid, clube, inicio)
        _ultimato(con, cid, clube, hoje)


def pendencias(con: sqlite3.Connection, cid: int) -> list[dict]:
    """O que a diretoria espera do técnico agora."""
    s = banco._ultima(con, cid)
    clube, ano = s["clube_idx"], int(s["data_jogo"][:4])
    if d := demitido(con, cid, clube):
        return [{"tipo": "demissao",
                 "texto": f"Você foi demitido em {_data(d)}. Por honra, aceite a proposta de outro clube no PES."}]
    lista = []
    acordo = _acordo(con, cid, clube, ano)
    if acordo and acordo["estado"] == "proposto":
        lista.append({"tipo": "reuniao", "texto": f"A diretoria marcou a reunião do acordo de {ano}."})
    if ativo := _ultimato_ativo(con, cid, clube):
        r = situacao_do_ultimato(banco.partidas(con, cid), json.loads(ativo["jogos"]), clube)
        lista.append({"tipo": "ultimato",
                      "texto": f"Ultimato: {r['pontos']} de 7 pontos, faltam {_plural(r['faltam'], 'jogo', 'jogos')}."})
    return lista
