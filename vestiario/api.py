"""API HTTP do Vestiário. Só escuta em 127.0.0.1 (veja __main__.py)."""
import os
from contextlib import closing
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import banco
from .sincronizar import sincronizar

_casa = Path.home()
SAVES = Path(os.environ.get("VESTIARIO_SAVES", _casa / "Documents/KONAMI/eFootball PES 2021 SEASON UPDATE/2026/save"))
PES = Path(os.environ.get("VESTIARIO_PES", r"D:\Transferpatch"))
DB = Path(os.environ.get("VESTIARIO_DB", Path(os.environ.get("LOCALAPPDATA", _casa)) / "Vestiario/vestiario.db"))
WEB = Path(__file__).resolve().parent.parent / "web" / "dist"

app = FastAPI(title="Vestiário")
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])  # testserver = TestClient


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


@app.get("/api/carreiras/{cid}/lendas")
def get_lendas(cid: int):
    with _con() as con:
        _carreira(con, cid)
        return banco.lendas(con, cid)


if WEB.is_dir():
    app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
