import io
import struct
import zlib
from pathlib import Path

import pytest
from PIL import Image

from vestiario.patch import (COACH, REG, ROSTO, TEAM, UNICOLOR, WESYS, carregar_player_bin, dds_para_png,
                              desembrulhar, ler_arquivos, ler_cores, ler_nomes, ler_posicoes, ler_tecnicos)


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
    assert ler_nomes(carregar_player_bin(tmp_path)) == {7: "Do Root"}


def test_sem_player_bin(tmp_path):
    with pytest.raises(FileNotFoundError):
        carregar_player_bin(tmp_path)


def test_patch_instalado():
    pes = Path(r"D:\Transferpatch")
    if not pes.exists():
        pytest.skip(r"Transfer Patch não instalado em D:\Transferpatch")
    raw = carregar_player_bin(pes)
    assert ler_nomes(raw)[60657] == "Jonathan Calleri"
    # posições da tela do PES: Calleri CA, Rafael GO, Hezze VOL, Cauly MAT
    assert {p: ler_posicoes(raw)[p] for p in (60657, 41204, 135214, 160150)} == {60657: 12, 41204: 0, 135214: 4, 160150: 8}


def test_player_bin_corrompido_vira_valueerror(tmp_path):
    alvo = tmp_path / "SiderAddons" / "livecpk" / "root" / "common/etc/pesdb"
    alvo.mkdir(parents=True)
    (alvo / "Player.bin").write_bytes(WESYS + struct.pack("<II", 4, 312) + b"lixo")
    (tmp_path / "SiderAddons" / "sider.ini").write_text(r'cpk.root = ".\livecpk\root"' + "\n", encoding="utf8")
    with pytest.raises(ValueError, match="corrompido"):
        carregar_player_bin(tmp_path)


def test_ler_arquivos_do_sider_ignora_os_que_nao_existem(tmp_path):
    flag = tmp_path / "SiderAddons" / "livecpk" / "root" / "common/render/symbol/flag"
    flag.mkdir(parents=True)
    (flag / "e_000007_r.png").write_bytes(b"png 7")
    (tmp_path / "SiderAddons" / "sider.ini").write_text(r'cpk.root = ".\livecpk\root"' + "\n", encoding="utf8")
    alvos = {"common/render/symbol/flag/e_000007_r.png", "common/render/symbol/flag/e_000008_r.png"}
    assert ler_arquivos(tmp_path, alvos) == {"common/render/symbol/flag/e_000007_r.png": b"png 7"}


def test_escudos_instalados():
    pes = Path(r"D:\Transferpatch")
    if not pes.exists():
        pytest.skip(r"Transfer Patch não instalado em D:\Transferpatch")
    sp, real = "common/render/symbol/flag/e_001255_r.png", "common/render/symbol/flag/e_000109_r.png"
    achados = ler_arquivos(pes, {sp, real})          # São Paulo vem do Sider, Real Madrid do dt15 do jogo
    assert achados[sp][:4] == achados[real][:4] == b"\x89PNG"


def test_ler_cores_junta_uniformes_1_e_2_sem_tons_repetidos():
    entradas = [(0, "191c19", "191c19"), (1, "282828", "ffffff"), (4, "d6d7d6", "d6d7d6"), (8, "ff0000", "ff0000")]
    reg = struct.pack("<IB", 2454, len(entradas)) + b"".join(
        bytes([k, 0]) + bytes.fromhex(a) + bytes.fromhex(b) for k, a, b in entradas)
    reg += bytes(85 - len(reg))
    assert ler_cores(reg + reg) == {2454: ["#191c19", "#ffffff", "#d6d7d6"]}  # 282828 ≈ 191c19; o terceiro (8) fica fora


def test_cores_instaladas():
    pes = Path(r"D:\Transferpatch")
    if not pes.exists():
        pytest.skip(r"Transfer Patch não instalado em D:\Transferpatch")
    cores = ler_cores(desembrulhar(ler_arquivos(pes, {UNICOLOR})[UNICOLOR]))
    assert cores[2454] == ["#191c19", "#ffffff", "#d6d7d6"]  # Ceará: preto, branco e cinza
    assert cores[1248][:2] == ["#ee012e", "#211e1e"]          # Flamengo: vermelho e preto


def test_minifaces_instaladas_viram_png():
    pes = Path(r"D:\Transferpatch")
    if not pes.exists():
        pytest.skip(r"Transfer Patch não instalado em D:\Transferpatch")
    alvo = ROSTO.format(100057)  # DXT5 de 256 px
    png = dds_para_png(ler_arquivos(pes, {alvo})[alvo])
    assert png[:4] == b"\x89PNG" and Image.open(io.BytesIO(png)).size == (128, 128)


def test_posicao_no_player_bin():
    reg = bytearray(REG)
    struct.pack_into("<I", reg, 8, 7)
    reg[54] = 0b1100_0000 | 0b0010  # bits 434..437 (byte 54, bits 2..5) = 12 (CA); o resto do byte é de outro campo
    reg[54] = (reg[54] & ~(0b1111 << 2)) | (12 << 2)
    assert ler_posicoes(bytes(reg)) == {7: 12}


def test_ler_tecnicos_pelo_id_do_time():
    coach = b"".join(struct.pack("<II", k, 0) + n.encode().ljust(92, b"\0") for k, n in ((7, "Abel Ferreira"), (9, "Tite")))
    team = b"".join(struct.pack("<III", k, 0, tid).ljust(1532, b"\0") for k, tid in ((7, 137), (9, 1250), (5, 2)))
    assert ler_tecnicos(coach, team) == {137: "Abel Ferreira", 1250: "Tite"}  # técnico 5 não existe: o time fica fora


def test_tecnicos_instalados():
    pes = Path(r"D:\Transferpatch")
    if not pes.exists():
        pytest.skip(r"Transfer Patch não instalado em D:\Transferpatch")
    a = ler_arquivos(pes, {COACH, TEAM})
    tecnicos = ler_tecnicos(desembrulhar(a[COACH]), desembrulhar(a[TEAM]))
    assert (tecnicos[137], tecnicos[1247], tecnicos[1248]) == ("Abel Ferreira", "Léo Porto", "Leonardo Jardim")
