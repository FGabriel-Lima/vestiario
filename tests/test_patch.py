import struct
import zlib
from pathlib import Path

import pytest

from vestiario.patch import REG, WESYS, carregar_nomes


def player_bin(jogadores: dict[int, str]) -> bytes:
    raw = bytearray()
    for pid, nome in jogadores.items():
        reg = bytearray(REG)
        struct.pack_into("<I", reg, 8, pid)
        reg[68:68 + len(nome.encode())] = nome.encode()
        raw += reg
    comp = zlib.compress(bytes(raw))
    return WESYS + struct.pack("<II", len(comp), len(raw)) + comp


def test_sider_primeira_pasta_vence(tmp_path):
    sider = tmp_path / "SiderAddons"
    for pasta, nome in (("root", "Do Root"), ("outra", "Da Outra")):
        alvo = sider / "livecpk" / pasta / "common/etc/pesdb"
        alvo.mkdir(parents=True)
        (alvo / "Player.bin").write_bytes(player_bin({7: nome}))
    (sider / "sider.ini").write_text(
        ';cpk.root = ".\\livecpk\\outra"\n'
        '\tcpk.root = ".\\livecpk\\vazia"\n'
        '\tcpk.root = ".\\livecpk\\root"\n'
        '\tcpk.root = ".\\livecpk\\outra"\n', encoding="utf8")
    assert carregar_nomes(tmp_path) == {7: "Do Root"}


def test_sem_player_bin(tmp_path):
    with pytest.raises(FileNotFoundError):
        carregar_nomes(tmp_path)


def test_patch_instalado():
    pes = Path(r"C:\Program Files (x86)\SP Football Life 2026")
    if not pes.exists():
        pytest.skip("SP Football Life 2026 não instalado")
    assert carregar_nomes(pes)[60657] == "Jonathan Calleri"
