import io
import shutil
import sqlite3
from datetime import datetime

import pytest
from conftest import SAVES, atuacao, fazer_save, partida
from fastapi.testclient import TestClient
from PIL import Image

from vestiario import api, banco, ia, leitor


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
    assert cliente.get("/api/carreiras/1/lendas").json()["recordes"]["goleada"]["id"] == 1
    assert cliente.get("/api/carreiras/1/partidas/1").json()["escalacao"][0]["gols"] == 2
    assert cliente.get("/api/carreiras/1/partidas/9").status_code == 404
    assert cliente.get("/api/carreiras/1/confrontos").json()[0]["vitorias"] == 1
    assert cliente.get("/api/carreiras/1/transferencias").json()["janelas"] == []
    assert cliente.get("/api/carreiras/1/mundo?ano=2026").json()["artilheiros"][0]["gols"] == 2
    assert cliente.get("/api/carreiras/9").status_code == 404
    assert cliente.get("/api/carreiras/1/campeonatos").json() == []
    assert cliente.get("/api/carreiras/1/titulos").json() == []
    assert cliente.get("/api/carreiras/1/campeonato", params={"chave": "Nada|2026"}).status_code == 404


def test_parecer_da_proposta(cliente, monkeypatch):
    con = banco.conectar(api.DB)
    banco.gravar(con, "ML00000000", fazer_save("2026-03-01", elenco=(10,), propostas=[(1, 10, 8320)]), datetime(2026, 10, 15))
    con.close()
    monkeypatch.setattr(ia, "responder", lambda *a: {"parecer": "Recusa, professor.", "recomendacao": "recusar"})
    url = "/api/carreiras/1/propostas/parecer"
    assert cliente.post(url, json={"player_id": 10, "clube_idx": 1, "valor": 8320}).json()["recomendacao"] == "recusar"
    assert cliente.post(url, json={"player_id": 10, "clube_idx": 1, "valor": 1}).status_code == 404

    def sem_rede(*a):
        raise ia.IAIndisponivel("Sem conexão com o Gemini.")

    monkeypatch.setattr(ia, "responder", sem_rede)
    banco.conectar(api.DB).execute("DELETE FROM parecer").connection.commit()
    r = cliente.post(url, json={"player_id": 10, "clube_idx": 1, "valor": 8320})
    assert r.status_code == 503 and "Gemini" in r.json()["detail"]


def test_feed(cliente, monkeypatch):
    con = banco.conectar(api.DB)
    banco.gravar(con, "ML00000000", fazer_save("2026-03-01", [partida("2026-02-01", 0, 1, (2, 0), [atuacao(10, 0, 2)])]),
                 datetime(2026, 10, 15))
    con.close()
    f = cliente.get("/api/carreiras/1/feed").json()
    assert (f["publicado"], f["posts"]) == (False, [])
    monkeypatch.setattr(ia, "responder", lambda *a: {"posts": [{"id": 0, "legenda": "Vitória!"}]})
    f = cliente.post("/api/carreiras/1/feed").json()
    assert (f["publicado"], f["posts"][0]["legenda"]) == (True, "Vitória!")


def test_conversas(cliente, monkeypatch):
    con = banco.conectar(api.DB)
    banco.gravar(con, "ML00000000", fazer_save("2026-03-01", elenco=(10,)), datetime(2026, 10, 15))
    con.close()
    assert [c["contato"] for c in cliente.get("/api/carreiras/1/conversas").json()] == ["auxiliar", "10"]
    monkeypatch.setattr(ia, "responder", lambda *a: {"resposta": "Tô pronto, professor."})
    r = cliente.post("/api/carreiras/1/conversas/10", json={"texto": "Tudo certo?"}).json()
    assert r["mensagens"][-1]["texto"] == "Tô pronto, professor."
    assert cliente.post("/api/carreiras/1/conversas/10", json={"texto": " "}).status_code == 400
    assert cliente.get("/api/carreiras/1/conversas/999").status_code == 404


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


def test_host_estranho_e_recusado(cliente):
    assert cliente.get("/api/carreiras", headers={"host": "evil.example"}).status_code == 400
    assert cliente.get("/api/carreiras", headers={"host": "8.8.8.8:8765"}).status_code == 400


def test_so_o_pc_e_o_celular_no_tailscale_entram(cliente, monkeypatch):
    assert cliente.get("/api/carreiras", headers={"host": "100.101.102.103:8765"}).status_code == 200
    assert cliente.get("/api/carreiras", headers={"host": "192.168.0.12:8765"}).status_code == 400  # Wi-Fi compartilhado
    assert [api._ip_conhecido(ip) for ip in ("127.0.0.1", "::1", "100.88.1.2", "10.0.0.7", "192.168.0.12")] == [
        True, True, True, False, False]
    monkeypatch.setenv("VESTIARIO_REDE_IPS", "10.148.134.11,10.148.134.225")  # PC e celular no roteador do celular
    assert [api._ip_conhecido(ip) for ip in ("10.148.134.225", "10.148.134.11", "10.148.134.7")] == [True, True, False]
    monkeypatch.setenv("VESTIARIO_REDE_PRIVADA", "192.168.0.0/24")  # rede marcada como Privada no Windows
    assert [api._ip_conhecido(ip) for ip in ("192.168.0.23", "192.168.1.23")] == [True, False]
    assert cliente.get("/api/rede").json() == {"url": None, "qr": None}
    monkeypatch.setenv("VESTIARIO_REDE_URL", "http://100.101.102.103:8765")
    rede = cliente.get("/api/rede").json()
    assert rede["url"] == "http://100.101.102.103:8765" and rede["qr"].startswith("data:image/svg+xml")


def test_escudo(cliente):
    pasta = api.DB.parent / "escudos"
    pasta.mkdir(parents=True)
    (pasta / "1255.png").write_bytes(b"\x89PNG fake")
    r = cliente.get("/api/escudos/1255")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png" and r.content == b"\x89PNG fake"
    assert cliente.get("/api/escudos/1256").status_code == 404


def test_sincronizar_extrai_so_os_escudos_que_existem(cliente, monkeypatch):
    flag = api.PES / "SiderAddons" / "livecpk" / "root" / "common/render/symbol/flag"
    flag.mkdir(parents=True)
    (flag / "e_000007_r.png").write_bytes(b"png 7")
    (api.PES / "SiderAddons" / "sider.ini").write_text(r'cpk.root = ".\livecpk\root"' + "\n", encoding="utf8")
    api.SAVES.mkdir()
    (api.SAVES / "ML00000000").write_bytes(b"Liga Master 01")

    def ler_save(raw):
        save = fazer_save(nome=raw.decode())
        save.ids = [7, 8, 9]
        return save

    monkeypatch.setattr(leitor, "ler_save", ler_save)
    cliente.post("/api/sincronizar")
    assert sorted(p.name for p in (api.DB.parent / "escudos").iterdir()) == ["7.png"]
    assert cliente.get("/api/escudos/7").content == b"png 7"


def test_carreira_traz_as_cores_do_clube(cliente):
    con = banco.conectar(api.DB)
    save = fazer_save("2026-03-01", [])
    save.ids = [2454] + [None] * (len(save.times) - 1)
    banco.gravar(con, "ML00000000", save, datetime(2026, 10, 14))
    assert cliente.get("/api/carreiras/1").json()["cores"] == []
    banco.gravar_cores(con, {2454: ["#191c19", "#ffffff"]})
    con.close()
    assert cliente.get("/api/carreiras/1").json()["cores"] == ["#191c19", "#ffffff"]


def test_sincronizar_extrai_minifaces_do_elenco(cliente, monkeypatch):
    rostos = api.PES / "SiderAddons" / "livecpk" / "root" / "common/render/symbol/player"
    rostos.mkdir(parents=True)
    Image.new("RGBA", (256, 256), "red").save(rostos / "10.dds")
    (api.PES / "SiderAddons" / "sider.ini").write_text(r'cpk.root = ".\livecpk\root"' + "\n", encoding="utf8")
    api.SAVES.mkdir()
    (api.SAVES / "ML00000000").write_bytes(b"x")
    monkeypatch.setattr(leitor, "ler_save", lambda raw: fazer_save(elenco=(10, 11)))
    cliente.post("/api/sincronizar")
    r = cliente.get("/api/rostos/10")
    assert r.status_code == 200 and Image.open(io.BytesIO(r.content)).size == (128, 128)
    assert cliente.get("/api/rostos/11").status_code == 404



def test_sincronizar_publica_o_feed(cliente, monkeypatch):
    monkeypatch.setattr(leitor, "ler_save", lambda raw: fazer_save("2026-03-01", [
        partida("2026-02-01", 0, 1, (2, 0), [atuacao(10, 0, 2)])]))
    (api.SAVES).mkdir()
    (api.SAVES / "ML00000000").write_bytes(b"x")
    monkeypatch.setattr(ia, "responder", lambda *a: {"posts": [{"id": 0, "legenda": "Vitória!"}]})
    assert not any("Feed" in a for a in cliente.post("/api/sincronizar").json()["avisos"])
    assert cliente.get("/api/carreiras/1/feed").json()["publicado"] is True


def test_sincronizar_sem_ia_avisa_e_nao_publica(cliente, monkeypatch):
    monkeypatch.setattr(leitor, "ler_save", lambda raw: fazer_save("2026-03-01", [
        partida("2026-02-01", 0, 1, (2, 0), [atuacao(10, 0, 2)])]))
    (api.SAVES).mkdir()
    (api.SAVES / "ML00000000").write_bytes(b"x")
    avisos = cliente.post("/api/sincronizar").json()["avisos"]
    assert any("Feed de" in a and "aba Feed" in a for a in avisos)
    assert cliente.get("/api/carreiras/1/feed").json()["publicado"] is False


def test_coletiva(cliente, monkeypatch):
    monkeypatch.setattr(leitor, "ler_save", lambda raw: fazer_save("2026-03-01", [
        partida("2026-02-01", 0, 1, (2, 0), [atuacao(10, 0, 2)])]))
    (api.SAVES).mkdir()
    (api.SAVES / "ML00000000").write_bytes(b"x")
    cliente.post("/api/sincronizar")
    assert cliente.post("/api/carreiras/1/coletiva").status_code == 404  # feed ainda não publicado: sem jogo
    monkeypatch.setattr(ia, "responder", lambda *a: {"posts": []})
    cliente.post("/api/carreiras/1/feed")
    monkeypatch.setattr(ia, "responder", lambda *a: {"perguntas": ["E o jogo?"]})
    assert cliente.post("/api/carreiras/1/coletiva").json()["coletiva"]["perguntas"] == ["E o jogo?"]
    assert cliente.post("/api/carreiras/1/coletiva/respostas", json={"respostas": []}).status_code == 400
    monkeypatch.setattr(ia, "responder", lambda *a: {"legenda": 'Técnico: "Gostei."'})
    f = cliente.post("/api/carreiras/1/coletiva/respostas", json={"respostas": ["Gostei."]}).json()
    assert f["posts"][0]["legenda"] == 'Técnico: "Gostei."'


def test_ficha_e_atencao(cliente, monkeypatch):
    monkeypatch.setattr(leitor, "ler_save", lambda raw: fazer_save("2026-03-01", [
        partida("2026-02-01", 0, 1, (2, 0), [atuacao(10, 0, 2)])]))
    (api.SAVES).mkdir()
    (api.SAVES / "ML00000000").write_bytes(b"x")
    cliente.post("/api/sincronizar")
    f = cliente.get("/api/carreiras/1/jogadores/10").json()
    assert f["total"]["gols"] == 2 and isinstance(f["sinais"], list)
    assert cliente.get("/api/carreiras/1/jogadores/999").status_code == 404
    assert set(cliente.get("/api/carreiras/1/atencao").json()) == {"propostas", "contratos", "promessas", "sem_espaco"}


def test_reacao_a_proposta(cliente, monkeypatch):
    con = banco.conectar(api.DB)
    banco.gravar_nomes(con, {10: "Titular"}, {10: 12})
    banco.gravar(con, "ML00000000", fazer_save("2026-03-01", elenco=(10,), propostas=[(1, 10, 9000)]),
                 datetime(2026, 10, 14))
    con.close()
    monkeypatch.setattr(ia, "responder", lambda *a: {"mensagem": "Quero ficar, professor.", "vontade": "ficar"})
    assert cliente.post("/api/carreiras/1/propostas/reacao", json={"player_id": 10}).json() == {"enviadas": 1}
    assert cliente.get("/api/carreiras/1/transferencias").json()["propostas"][0]["vontade"] == "ficar"
    assert cliente.get("/api/carreiras/1/conversas").json()[1]["nao_lidas"] == 1


def test_sincronizar_manda_a_mensagem_do_jogador(cliente, monkeypatch):
    monkeypatch.setattr(leitor, "ler_save", lambda raw: fazer_save("2026-03-01", elenco=(10,), propostas=[(1, 10, 9000)]))
    api.SAVES.mkdir()
    (api.SAVES / "ML00000000").write_bytes(b"x")
    monkeypatch.setattr(ia, "responder", lambda *a: {"posts": [], "mensagem": "Quero sair.", "vontade": "sair"})
    cliente.post("/api/sincronizar")
    assert cliente.get("/api/carreiras/1/transferencias").json()["propostas"][0]["vontade"] == "sair"


def test_sincronizar_sem_ia_avisa_das_mensagens(cliente, monkeypatch):
    monkeypatch.setattr(leitor, "ler_save", lambda raw: fazer_save("2026-03-01", elenco=(10,), propostas=[(1, 10, 9000)]))
    api.SAVES.mkdir()
    (api.SAVES / "ML00000000").write_bytes(b"x")
    avisos = cliente.post("/api/sincronizar").json()["avisos"]
    assert any("Mensagens dos jogadores" in a for a in avisos)
