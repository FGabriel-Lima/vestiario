"""API HTTP do Vestiário. Escuta em 127.0.0.1, ou também no Tailscale com --rede (veja __main__.py)."""
import ipaddress
import os
from contextlib import closing
from pathlib import Path

import segno
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from . import auxiliar, banco, conversas, feed, ia
from .sincronizar import sincronizar

_casa = Path.home()
SAVES = Path(os.environ.get("VESTIARIO_SAVES", _casa / "Documents/KONAMI/eFootball PES 2021 SEASON UPDATE/2026/save"))
PES = Path(os.environ.get("VESTIARIO_PES", r"D:\Transferpatch"))
DB = Path(os.environ.get("VESTIARIO_DB", Path(os.environ.get("LOCALAPPDATA", _casa)) / "Vestiario/vestiario.db"))
WEB = Path(__file__).resolve().parent.parent / "web" / "dist"

app = FastAPI(title="Vestiário")


TAILSCALE = ipaddress.ip_network("100.64.0.0/10")


def _ip_conhecido(texto: str) -> bool:
    """O próprio PC, um aparelho da conta Tailscale do usuário, os IPs de VESTIARIO_REDE_IPS (o PC e o celular
    quando o PC está no roteador do celular) ou a rede de VESTIARIO_REDE_PRIVADA (veja __main__.py). O resto do Wi-Fi não entra: numa rede compartilhada
    (o eduroam), qualquer um abriria o Vestiário e gastaria a chave do Gemini."""
    try:
        ip = ipaddress.ip_address(texto.strip("[]"))
    except ValueError:
        return False
    subrede = os.environ.get("VESTIARIO_REDE_PRIVADA")  # a rede de casa, marcada como Privada no Windows
    return (ip.is_loopback or ip in TAILSCALE or str(ip) in os.environ.get("VESTIARIO_REDE_IPS", "").split(",")
            or (subrede is not None and ip in ipaddress.ip_network(subrede)))


@app.middleware("http")
async def so_aparelhos_do_usuario(request, seguir):
    # Host por nome, só localhost: barra o DNS rebinding (uma página da internet chamando a API pelo navegador)
    host = request.headers.get("host", "").rsplit(":", 1)[0]
    cliente = request.client.host if request.client else ""
    if not ((host in ("localhost", "testserver") or _ip_conhecido(host)) and (cliente == "testclient" or _ip_conhecido(cliente))):
        return PlainTextResponse("Invalid host header", status_code=400)
    return await seguir(request)


@app.get("/api/rede")
def get_rede():
    """Endereço para abrir no celular, quando o servidor foi aberto com --rede, e o QR code dele (data URI)."""
    url = os.environ.get("VESTIARIO_REDE_URL")
    return {"url": url, "qr": url and segno.make(url, error="m").svg_data_uri(scale=4, border=2)}


def _con():
    return closing(banco.conectar(DB))


def _escudos() -> Path:
    return DB.parent / "escudos"


def _rostos() -> Path:
    return DB.parent / "rostos"


def _carreira(con, cid: int) -> dict:
    c = banco.carreira(con, cid)
    if c is None:
        raise HTTPException(404, "Carreira não encontrada")
    return c


@app.post("/api/sincronizar")
def post_sincronizar():
    with _con() as con:
        try:
            return sincronizar(con, SAVES, PES, _escudos(), _rostos())
        except FileNotFoundError as e:
            raise HTTPException(404, str(e))


@app.get("/api/escudos/{pes_id}")
def get_escudo(pes_id: int):
    arq = _escudos() / f"{pes_id}.png"
    if not arq.is_file():
        raise HTTPException(404, "Escudo não encontrado")
    return FileResponse(arq, media_type="image/png")


@app.get("/api/rostos/{player_id}")
def get_rosto(player_id: int):
    arq = _rostos() / f"{player_id}.png"
    if not arq.is_file():
        raise HTTPException(404, "Miniface não encontrada")
    return FileResponse(arq, media_type="image/png")


@app.get("/api/carreiras")
def get_carreiras():
    with _con() as con:
        return banco.carreiras(con)


@app.get("/api/carreiras/{cid}")
def get_carreira(cid: int):
    with _con() as con:
        return {**_carreira(con, cid), "temporadas": banco.temporadas(con, cid)}


@app.get("/api/carreiras/{cid}/resumo")
def get_resumo(cid: int, ano: int):
    with _con() as con:
        _carreira(con, cid)
        return banco.resumo(con, cid, ano)


@app.get("/api/carreiras/{cid}/elenco")
def get_elenco(cid: int, ano: int):
    with _con() as con:
        _carreira(con, cid)
        return banco.elenco(con, cid, ano)


@app.get("/api/carreiras/{cid}/partidas")
def get_partidas(cid: int, ano: int):
    with _con() as con:
        _carreira(con, cid)
        return banco.partidas(con, cid, ano)


@app.get("/api/carreiras/{cid}/partidas/{pid}")
def get_partida(cid: int, pid: int):
    with _con() as con:
        _carreira(con, cid)
        if (p := banco.partida(con, cid, pid)) is None:
            raise HTTPException(404, "Partida não encontrada")
        return p


@app.get("/api/carreiras/{cid}/confrontos")
def get_confrontos(cid: int):
    with _con() as con:
        _carreira(con, cid)
        return banco.confrontos(con, cid)


@app.get("/api/carreiras/{cid}/transferencias")
def get_transferencias(cid: int):
    with _con() as con:
        _carreira(con, cid)
        return banco.transferencias(con, cid)


@app.get("/api/carreiras/{cid}/mundo")
def get_mundo(cid: int, ano: int):
    with _con() as con:
        _carreira(con, cid)
        return banco.mundo(con, cid, ano)


@app.get("/api/carreiras/{cid}/campeonatos")
def get_campeonatos(cid: int):
    with _con() as con:
        _carreira(con, cid)
        return banco.edicoes(con, cid)


@app.get("/api/carreiras/{cid}/campeonato")
def get_campeonato(cid: int, chave: str):
    with _con() as con:
        _carreira(con, cid)
        if (e := banco.edicao(con, cid, chave)) is None:
            raise HTTPException(404, "Campeonato não encontrado")
        return e


@app.get("/api/carreiras/{cid}/titulos")
def get_titulos(cid: int):
    with _con() as con:
        _carreira(con, cid)
        return banco.titulos(con, cid)


class PedidoDeParecer(BaseModel):
    player_id: int
    clube_idx: int
    valor: int  # unidades do save (valor_bruto da proposta)


@app.post("/api/carreiras/{cid}/propostas/parecer")
def post_parecer(cid: int, pedido: PedidoDeParecer):
    with _con() as con:
        _carreira(con, cid)
        try:
            p = auxiliar.parecer_da_proposta(con, cid, pedido.player_id, pedido.clube_idx, pedido.valor)
        except ia.IAIndisponivel as e:
            raise HTTPException(503, str(e))
        if p is None:
            raise HTTPException(404, "Proposta não encontrada")
        return p


@app.get("/api/carreiras/{cid}/feed")
def get_feed(cid: int):
    """Posts publicados e se a data do jogo mais recente já foi publicada."""
    with _con() as con:
        _carreira(con, cid)
        return feed.ler(con, cid)


@app.post("/api/carreiras/{cid}/feed")
def post_feed(cid: int):
    with _con() as con:
        _carreira(con, cid)
        try:
            return feed.atualizar(con, cid)
        except ia.IAIndisponivel as e:
            raise HTTPException(503, str(e))


@app.get("/api/carreiras/{cid}/jogadores/{pid}")
def get_jogador(cid: int, pid: int):
    """Ficha do jogador: números, jogo a jogo, valor, contrato, propostas, promessas e o estado dele (sinais)."""
    with _con() as con:
        _carreira(con, cid)
        if (f := banco.ficha(con, cid, pid)) is None:
            raise HTTPException(404, "Jogador não passou pelo clube")
        f["sinais"] = next((c["sinais"] for c in conversas.contatos(con, cid) if c.get("player_id") == pid), [])
        return f


@app.get("/api/carreiras/{cid}/atencao")
def get_atencao(cid: int):
    with _con() as con:
        _carreira(con, cid)
        return conversas.atencao(con, cid)


@app.post("/api/carreiras/{cid}/coletiva")
def post_coletiva(cid: int):
    """Abre a coletiva do jogo mais recente: o repórter faz as perguntas."""
    with _con() as con:
        _carreira(con, cid)
        try:
            return feed.abrir_coletiva(con, cid)
        except LookupError as e:
            raise HTTPException(404, str(e))


class Respostas(BaseModel):
    respostas: list[str]


@app.post("/api/carreiras/{cid}/coletiva/respostas")
def post_respostas(cid: int, r: Respostas):
    with _con() as con:
        _carreira(con, cid)
        try:
            return feed.responder_coletiva(con, cid, r.respostas)
        except LookupError as e:
            raise HTTPException(404, str(e))
        except ValueError as e:
            raise HTTPException(400, str(e))


@app.get("/api/carreiras/{cid}/conversas")
def get_contatos(cid: int):
    with _con() as con:
        _carreira(con, cid)
        return conversas.contatos(con, cid)


@app.get("/api/carreiras/{cid}/conversas/{contato}")
def get_conversa(cid: int, contato: str):
    with _con() as con:
        _carreira(con, cid)
        if (c := conversas.conversa(con, cid, contato)) is None:
            raise HTTPException(404, "Contato não encontrado no elenco")
        return c


class Mensagem(BaseModel):
    texto: str


@app.post("/api/carreiras/{cid}/conversas/{contato}")
def post_conversa(cid: int, contato: str, m: Mensagem):
    with _con() as con:
        _carreira(con, cid)
        try:
            c = conversas.responder(con, cid, contato, m.texto)
        except ValueError as e:
            raise HTTPException(400, str(e))
        except ia.IAIndisponivel as e:
            raise HTTPException(503, str(e))
        if c is None:
            raise HTTPException(404, "Contato não encontrado no elenco")
        return c


@app.get("/api/carreiras/{cid}/lendas")
def get_lendas(cid: int):
    with _con() as con:
        _carreira(con, cid)
        return banco.lendas(con, cid)


if WEB.is_dir():
    app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
