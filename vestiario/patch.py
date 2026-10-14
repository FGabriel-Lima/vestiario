"""Lê arquivos do patch na ordem de carregamento do jogo: nomes e posições dos jogadores, escudos, minifaces e cores dos uniformes."""
import io
import re
import struct
import zlib
from pathlib import Path

from PIL import Image

from . import cpk

ALVO = "common/etc/pesdb/Player.bin"
ROSTO = "common/render/symbol/player/{}.dds"
UNICOLOR = "common/character0/model/character/uniform/team/UniColor.bin"
WESYS = bytes.fromhex("ff10815745535953")
REG, OFF_ID, OFF_NOME = 312, 8, 68
# Posição registrada: 4 bits a partir do bit 434 do registro (conferido com 17 jogadores na tela do PES).
# 0 GO, 1 ZC, 2 LE, 3 LD, 4 VOL, 5 MLG, 6 MLE, 7 MLD, 8 MAT, 9 PTE, 10 PTD, 11 SA, 12 CA
BIT_POSICAO = 434


def desembrulhar(blob: bytes) -> bytes:
    if blob[1:8] != WESYS[1:]:  # o 1º byte varia: ff no Player.bin, 00 no UniColor.bin
        raise ValueError("arquivo sem cabeçalho WESYS")
    try:
        return zlib.decompress(blob[16:])
    except zlib.error as e:
        raise ValueError(f"arquivo corrompido: {e}") from e


def ler_nomes(raw: bytes) -> dict[int, str]:
    nomes = {}
    for o in range(0, len(raw) - REG + 1, REG):
        pid = struct.unpack_from("<I", raw, o + OFF_ID)[0]
        nomes[pid] = raw[o + OFF_NOME:raw.index(b"\0", o + OFF_NOME)].decode("utf8", "replace")
    return nomes


def ler_posicoes(raw: bytes) -> dict[int, int]:
    byte, bit = divmod(BIT_POSICAO, 8)
    return {struct.unpack_from("<I", raw, o + OFF_ID)[0]: (raw[o + byte] >> bit) & 0xF
            for o in range(0, len(raw) - REG + 1, REG)}


def ler_cores(raw: bytes) -> dict[int, list[str]]:
    """Cores dos uniformes 1 e 2 de cada time (as da tela de seleção de kits), sem repetir tons parecidos.
    Registro de 85 bytes: u32 id do time, u8 quantidade, 10 × (kit, flag, RGB, RGB).
    Kit 0–3 = variações do uniforme 1, 4–7 = uniforme 2, 8 = terceiro, 16 = goleiro."""
    cores = {}
    for o in range(0, len(raw) - 84, 85):
        tid, n = struct.unpack_from("<IB", raw, o)
        rgbs = []
        for e in (raw[o + 5 + 8 * i:o + 13 + 8 * i] for i in range(min(n, 10))):
            if e[0] < 8:
                for rgb in (e[2:5], e[5:8]):
                    if all(max(abs(a - b) for a, b in zip(rgb, x)) >= 32 for x in rgbs):
                        rgbs.append(rgb)
        cores[tid] = ["#" + rgb.hex() for rgb in rgbs[:3]]
    return cores


def dds_para_png(blob: bytes) -> bytes:
    """Minifaces vêm em DDS (DXT1, DXT5 ou sem compressão, de 128 a 256 px); o navegador só entende PNG."""
    img = Image.open(io.BytesIO(blob))
    img.thumbnail((128, 128))
    saida = io.BytesIO()
    img.save(saida, "PNG")
    return saida.getvalue()


def _raizes_sider(pasta_pes: Path) -> list[Path]:
    """Pastas cpk.root do sider.ini, na ordem do arquivo (a primeira tem prioridade)."""
    ini = pasta_pes / "SiderAddons" / "sider.ini"
    if not ini.exists():
        return []
    return [pasta_pes / "SiderAddons" / m.group(1).replace("\\", "/")
            for linha in ini.read_text(encoding="utf8", errors="replace").splitlines()
            if (m := re.match(r'\s*cpk\.root\s*=\s*"(.+)"', linha))]


def _cpks(pasta_pes: Path) -> list[Path]:
    """CPKs em ordem crescente de prioridade: os do jogo (data/) e depois os de download/, na ordem do spFileList.bin."""
    cpks = sorted((pasta_pes / "data").glob("*.cpk"))
    lista = pasta_pes / "download" / "spFileList.bin"
    if lista.exists():
        fl = lista.read_bytes()
        for o in range(4, len(fl) - 47, 48):
            nome = fl[o + 12:o + 48].split(b"\0")[0].decode("ascii", "replace")
            if nome and (pasta_pes / "download" / nome).is_file():
                cpks.append(pasta_pes / "download" / nome)
    return cpks


def ler_arquivos(pasta_pes: Path, alvos: set[str]) -> dict[str, bytes]:
    """Lê os arquivos do jogo na mesma ordem que ele carrega: Sider, depois CPKs (o último que tiver vence).
    Alvos que não existem em lugar nenhum ficam fora do resultado."""
    achados = {}
    for raiz in _raizes_sider(pasta_pes):
        for alvo in alvos - achados.keys():
            if (raiz / alvo).is_file():
                achados[alvo] = (raiz / alvo).read_bytes()
    faltam = {a.lower(): a for a in alvos - achados.keys()}
    if not faltam:
        return achados
    nos_cpks = {}
    for caminho in _cpks(pasta_pes):
        try:
            with open(caminho, "rb") as f:
                toc = cpk.toc(f)
        except Exception:  # alguns CPKs do jogo usam um formato que o leitor não entende; não têm o que buscamos
            continue
        for e in toc:
            # ponytail: entrada comprimida (CRILAYLA) é ignorada; nenhum Player.bin ou escudo conhecido vem assim
            if (alvo := faltam.get(e["path"].lower())) and e["FileSize"] == e.get("ExtractSize", e["FileSize"]):
                nos_cpks[alvo] = (caminho, e)
    for alvo, (caminho, e) in nos_cpks.items():
        with open(caminho, "rb") as f:
            f.seek(e["abs"])
            achados[alvo] = f.read(e["FileSize"])
    return achados


def carregar_player_bin(pasta_pes: Path) -> bytes:
    """Player.bin já descompactado, para ler_nomes e ler_posicoes."""
    blob = ler_arquivos(pasta_pes, {ALVO}).get(ALVO)
    if blob is None:
        raise FileNotFoundError(f"Player.bin não encontrado em {pasta_pes}")
    return desembrulhar(blob)
