"""Lê a pasta de saves (e a backup/ dentro dela) e grava o que mudou."""
import sqlite3
from datetime import datetime
from pathlib import Path

from . import banco, leitor, patch


def extrair_escudos(con: sqlite3.Connection, pasta_pes: Path, pasta_escudos: Path) -> int:
    """Copia do patch para pasta_escudos/<id>.png os escudos que ainda faltam. Devolve quantos copiou."""
    pasta_escudos.mkdir(parents=True, exist_ok=True)
    ja_tem = {int(p.stem) for p in pasta_escudos.glob("*.png") if p.stem.isdigit()}
    alvos = {f"common/render/symbol/flag/e_{i:06d}_r.png": i for i in banco.escudos(con) - ja_tem}
    if not alvos:
        return 0
    achados = patch.ler_arquivos(pasta_pes, set(alvos))
    for alvo, png in achados.items():
        (pasta_escudos / f"{alvos[alvo]}.png").write_bytes(png)
    return len(achados)


def sincronizar(con: sqlite3.Connection, pasta_saves: Path, pasta_pes: Path, pasta_escudos: Path) -> dict:
    if not pasta_saves.is_dir():
        raise FileNotFoundError(f"Pasta de saves não encontrada: {pasta_saves} (ajuste VESTIARIO_SAVES)")
    avisos = []
    try:
        banco.gravar_nomes(con, patch.carregar_nomes(pasta_pes))
    except Exception as e:  # fronteira de confiança: nomes são opcionais
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
        try:
            gravado = banco.gravar(con, arq.name, save, datetime.now())
            banco.marcar_arquivo(con, str(arq), st.st_size, st.st_mtime)
        except (sqlite3.Error, ValueError) as e:
            r.update(status="erro", mensagem=f"Erro ao gravar no banco: {e}")
            continue
        r.update(gravado, status="ok", carreira=save.nome, clube=save.clube, data_jogo=save.data_jogo.isoformat())

    # ponytail: só procura escudos quando algum save mudou; um escudo novo no patch aparece na próxima mudança de save
    if any(r.get("status") == "ok" for r in resultados):
        try:
            extrair_escudos(con, pasta_pes, pasta_escudos)
        except Exception as e:  # fronteira de confiança: escudos são opcionais
            avisos.append(f"Escudos indisponíveis ({e}).")
    return {"avisos": avisos, "arquivos": resultados}
