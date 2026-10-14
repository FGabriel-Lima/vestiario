"""Lê a pasta de saves (e a backup/ dentro dela) e grava o que mudou."""
import sqlite3
from datetime import datetime
from pathlib import Path

from . import banco, leitor, patch


def sincronizar(con: sqlite3.Connection, pasta_saves: Path, pasta_pes: Path) -> dict:
    if not pasta_saves.is_dir():
        raise FileNotFoundError(f"Pasta de saves não encontrada: {pasta_saves} (ajuste VESTIARIO_SAVES)")
    avisos = []
    try:
        banco.gravar_nomes(con, patch.carregar_nomes(pasta_pes))
    except (OSError, ValueError) as e:
        avisos.append(f"Nomes dos jogadores indisponíveis ({e}). Ajuste VESTIARIO_PES.")

    arquivos = sorted([*pasta_saves.glob("backup/ML0*"), *pasta_saves.glob("ML0*")],
                      key=lambda a: a.stat().st_mtime)
    resultados = []
    for arq in arquivos:
        r = {"arquivo": arq.relative_to(pasta_saves).as_posix()}
        resultados.append(r)
        try:
            st = arq.stat()
            if banco.arquivo_visto(con, str(arq), st.st_size, st.st_mtime):
                r["status"] = "sem mudanças"
                continue
            raw = arq.read_bytes()
        except OSError:
            r.update(status="erro", mensagem="Arquivo em uso. Tente de novo em instantes.")
            continue
        try:
            save = leitor.ler_save(raw)
        except Exception as e:  # fronteira de confiança: qualquer falha de leitura = arquivo pulado, nada gravado
            r.update(status="erro", mensagem=f"Formato não reconhecido: {e}")
            continue
        r.update(banco.gravar(con, arq.name, save, datetime.now()), status="ok",
                 carreira=save.nome, clube=save.clube, data_jogo=save.data_jogo.isoformat())
        banco.marcar_arquivo(con, str(arq), st.st_size, st.st_mtime)
    return {"avisos": avisos, "arquivos": resultados}
