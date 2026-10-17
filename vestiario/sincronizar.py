"""Lê a pasta de saves (e a backup/ dentro dela) e grava o que mudou."""
import sqlite3
from datetime import datetime
from pathlib import Path

from . import banco, conversas, diretoria, feed, ia, leitor, patch


def _faltam(pasta: Path, ids: set[int]) -> set[int]:
    pasta.mkdir(parents=True, exist_ok=True)
    return ids - {int(p.stem) for p in pasta.glob("*.png") if p.stem.isdigit()}


def extrair_do_patch(con: sqlite3.Connection, pasta_pes: Path, pasta_escudos: Path, pasta_rostos: Path) -> int:
    """Grava as cores dos uniformes de todos os times e copia do patch os escudos (pasta_escudos/<id>.png)
    e as minifaces dos jogadores do clube (pasta_rostos/<player_id>.png) que ainda faltam. Devolve quantas copiou."""
    escudos = {f"common/render/symbol/flag/e_{i:06d}_r.png": i for i in _faltam(pasta_escudos, banco.escudos(con))}
    rostos = {patch.ROSTO.format(i): i for i in _faltam(pasta_rostos, banco.rostos(con))}
    achados = patch.ler_arquivos(pasta_pes, {*escudos, *rostos, patch.UNICOLOR})
    if (uni := achados.pop(patch.UNICOLOR, None)) is not None:
        banco.gravar_cores(con, patch.ler_cores(patch.desembrulhar(uni)))
    for alvo, blob in achados.items():
        if alvo in escudos:
            (pasta_escudos / f"{escudos[alvo]}.png").write_bytes(blob)
        else:
            try:
                (pasta_rostos / f"{rostos[alvo]}.png").write_bytes(patch.dds_para_png(blob))
            except Exception:  # um DDS que o Pillow não entende só deixa aquele jogador sem foto
                pass
    return len(achados)


def sincronizar(con: sqlite3.Connection, pasta_saves: Path, pasta_pes: Path, pasta_escudos: Path,
                pasta_rostos: Path) -> dict:
    if not pasta_saves.is_dir():
        raise FileNotFoundError(f"Pasta de saves não encontrada: {pasta_saves} (ajuste VESTIARIO_SAVES)")
    avisos = []
    try:
        raw = patch.carregar_player_bin(pasta_pes)
        banco.gravar_nomes(con, patch.ler_nomes(raw), patch.ler_posicoes(raw))
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

    # ponytail: só olha o patch quando algum save mudou (ou ainda não tem cores ou minifaces);
    # um escudo, minifaces ou uniforme novo no patch aparece na próxima mudança de save
    if any(r.get("status") == "ok" for r in resultados) or not banco.tem_cores(con) or not pasta_rostos.is_dir():
        try:
            extrair_do_patch(con, pasta_pes, pasta_escudos, pasta_rostos)
        except Exception as e:  # fronteira de confiança: escudos, minifaces e cores são opcionais
            avisos.append(f"Escudos, minifaces e cores dos times indisponíveis ({e}).")

    # a cada carreira que mudou: os jogadores falam das propostas por eles e o feed sai (chamadas à IA)
    for cid in dict.fromkeys(r["carreira_id"] for r in resultados if r.get("status") == "ok"):
        nome = next(r["carreira"] for r in resultados if r.get("carreira_id") == cid)
        if banco.carreira(con, cid)["encerrada"]:
            continue  # um save antigo (backup) do clube anterior: a passagem encerrada não ganha diretoria nem feed
        try:
            diretoria.atualizar(con, cid)
        except Exception as e:  # fronteira: um erro da diretoria nunca derruba a sincronização
            avisos.append(f"Diretoria de {nome} não atualizada ({e}).")
        try:
            conversas.reagir_propostas(con, cid)
        except ia.IAIndisponivel as e:
            avisos.append(f"Mensagens dos jogadores de {nome} sobre as propostas não enviadas: {e} "
                          "Use o botão na carta da proposta.")
        except Exception as e:  # fronteira de confiança: as mensagens são opcionais, o feed sai mesmo assim
            avisos.append(f"Mensagens dos jogadores de {nome} não enviadas ({e}).")
        try:
            feed.atualizar(con, cid)
        except ia.IAIndisponivel as e:
            avisos.append(f"Feed de {nome} não publicado: {e} Use o botão na aba Feed.")
    return {"avisos": avisos, "arquivos": resultados}
