"""Acha o Player.bin que o jogo carrega e devolve {player_id: nome}."""
import re
import struct
import zlib
from pathlib import Path

from . import cpk

ALVO = "common/etc/pesdb/Player.bin"
WESYS = bytes.fromhex("ff10815745535953")
REG, OFF_ID, OFF_NOME = 312, 8, 68


def desembrulhar(blob: bytes) -> bytes:
    if blob[:8] != WESYS:
        raise ValueError("Player.bin sem cabeçalho WESYS")
    return zlib.decompress(blob[16:])


def ler_nomes(raw: bytes) -> dict[int, str]:
    nomes = {}
    for o in range(0, len(raw) - REG + 1, REG):
        pid = struct.unpack_from("<I", raw, o + OFF_ID)[0]
        nomes[pid] = raw[o + OFF_NOME:raw.index(b"\0", o + OFF_NOME)].decode("utf8", "replace")
    return nomes


def _do_sider(pasta_pes: Path) -> bytes | None:
    """Pastas cpk.root do sider.ini, na ordem do arquivo: a primeira que tiver o Player.bin vence."""
    ini = pasta_pes / "SiderAddons" / "sider.ini"
    if not ini.exists():
        return None
    for linha in ini.read_text(encoding="utf8", errors="replace").splitlines():
        m = re.match(r'\s*cpk\.root\s*=\s*"(.+)"', linha)
        if m:
            arq = pasta_pes / "SiderAddons" / m.group(1).replace("\\", "/") / ALVO
            if arq.exists():
                return arq.read_bytes()
    return None


def _do_download(pasta_pes: Path) -> bytes | None:
    """CPKs de download/ na ordem do spFileList.bin: o último que tiver o Player.bin vence."""
    lista = pasta_pes / "download" / "spFileList.bin"
    if not lista.exists():
        return None
    fl = lista.read_bytes()
    achado = None
    for o in range(4, len(fl) - 47, 48):
        nome = fl[o + 12:o + 48].split(b"\0")[0].decode("ascii", "replace")
        caminho = pasta_pes / "download" / nome
        if nome and caminho.is_file():
            with open(caminho, "rb") as f:
                for e in cpk.toc(f):
                    if e["path"].lower() == ALVO.lower():
                        achado = (caminho, e)
    if achado is None:
        return None
    caminho, e = achado
    if e["FileSize"] != e.get("ExtractSize", e["FileSize"]):
        raise ValueError(f"Player.bin comprimido dentro de {caminho.name} (CRILAYLA não suportado)")
    with open(caminho, "rb") as f:
        f.seek(e["abs"])
        return f.read(e["FileSize"])


def carregar_nomes(pasta_pes: Path) -> dict[int, str]:
    blob = _do_sider(pasta_pes) or _do_download(pasta_pes)
    if blob is None:
        raise FileNotFoundError(f"Player.bin não encontrado em {pasta_pes}")
    return ler_nomes(desembrulhar(blob))
