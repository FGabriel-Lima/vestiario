import shutil
import sqlite3
from datetime import datetime

import pytest
from conftest import SAVES, atuacao, fazer_save, partida
from fastapi.testclient import TestClient

from vestiario import api, banco, leitor


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "DB", tmp_path / "v.db")
    monkeypatch.setattr(api, "SAVES", tmp_path / "saves")
    monkeypatch.setattr(api, "PES", tmp_path / "pes")
    return TestClient(api.app)


def test_telas(cliente):
    con = banco.conectar(api.DB)
    banco.gravar(con, "ML00000000", fazer_save("2026-03-01", [
        partida("2026-01-22", 0, 1, (2, 1), [atuacao(10, 0, 2)])]), datetime(2026, 10, 14))
    con.close()
    assert cliente.get("/api/carreiras").json()[0]["id"] == 1
    assert cliente.get("/api/carreiras/1").json()["temporadas"] == [2026]
    assert cliente.get("/api/carreiras/1/resumo?ano=2026").json()["vitorias"] == 1
    assert cliente.get("/api/carreiras/1/elenco?ano=2026").json()[0]["gols"] == 2
    assert len(cliente.get("/api/carreiras/1/partidas?ano=2026").json()) == 1
    assert cliente.get("/api/carreiras/1/lendas").json()["artilheiros"][0]["gols"] == 2
    assert cliente.get("/api/carreiras/9").status_code == 404


def test_pasta_de_saves_inexistente(cliente):
    r = cliente.post("/api/sincronizar")
    assert r.status_code == 404 and "VESTIARIO_SAVES" in r.json()["detail"]


def test_save_corrompido_e_pulado(cliente):
    api.SAVES.mkdir()
    (api.SAVES / "ML00000000").write_bytes(b"lixo" * 1000)
    r = cliente.post("/api/sincronizar").json()
    assert r["arquivos"][0]["status"] == "erro"
    assert any("Player.bin" in a for a in r["avisos"])
    assert cliente.get("/api/carreiras").json() == []


def test_sincronizar_save_real(cliente):
    if not (SAVES / "ML00000002").exists():
        pytest.skip("copie um save de Master League para saves/ML00000002")
    api.SAVES.mkdir()
    shutil.copy2(SAVES / "ML00000002", api.SAVES / "ML00000002")
    r = cliente.post("/api/sincronizar").json()
    assert r["arquivos"][0]["status"] == "ok" and r["arquivos"][0]["novas"] > 0
    assert cliente.post("/api/sincronizar").json()["arquivos"][0]["status"] == "sem mudanças"


def test_erro_ao_gravar_pula_so_aquele_arquivo(cliente, monkeypatch):
    api.SAVES.mkdir()
    (api.SAVES / "ML00000000").write_bytes(b"Liga Master 01")
    (api.SAVES / "ML00000001").write_bytes(b"Liga Master 02")
    monkeypatch.setattr(leitor, "ler_save", lambda raw: fazer_save(nome=raw.decode()))
    original = banco.gravar

    def gravar(con, slot, save, em):
        if slot == "ML00000000":
            raise sqlite3.OperationalError("database is locked")
        return original(con, slot, save, em)

    monkeypatch.setattr(banco, "gravar", gravar)
    r = cliente.post("/api/sincronizar")
    assert r.status_code == 200
    status = {a["arquivo"]: (a["status"], a.get("mensagem", "")) for a in r.json()["arquivos"]}
    assert status["ML00000001"][0] == "ok"
    assert status["ML00000000"][0] == "erro" and "database is locked" in status["ML00000000"][1]
