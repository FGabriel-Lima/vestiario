"""Lê um save da Master League do PES 2021 (Football Life 2026 / Transfer Patch). Tudo na memória."""
import struct
from dataclasses import dataclass
from datetime import date

from .pesdecrypt import decrypt

TIME0, TIME_TAM = 84, 1680           # nome do time i em TIME0 + i*TIME_TAM
ELENCO = 412                         # (u32 vaga, u32 player_id) a partir de i*TIME_TAM + ELENCO
PARTIDA0, PARTIDA_TAM, PARTIDAS = 3_316_488, 596, 13_000
VAGAS, VAGA_TAM = 34, 16             # 17 por lado, mandante primeiro
VAZIO = bytes.fromhex("ffff000003000000")
INDEFINIDO = 0x3FFF                  # time ainda não definido (mata-mata)
PID = 0x3FFFFFFF                     # bits altos do player_id são flags


class FormatoInvalido(Exception):
    pass


@dataclass
class Atuacao:
    player_id: int
    lado: int                        # 0 = mandante, 1 = visitante
    gols: int
    assistencias: int


@dataclass
class Partida:
    data: date
    mandante: int
    visitante: int
    gols: tuple[int, int]
    penaltis: tuple[int, int]
    escalacao: list[Atuacao]

    @property
    def disputada(self) -> bool:
        return bool(self.escalacao) or self.gols != (0, 0)


@dataclass
class Save:
    nome: str
    clube: str
    data_jogo: date
    times: list[str]
    clube_idx: int
    elenco: list[int]                # player_ids do clube do usuário
    partidas: list[Partida]


def _cstr(b: bytes, o: int = 0) -> str:
    return b[o:b.index(b"\0", o)].decode("utf8", "replace")


def ler_descricao(desc: bytes) -> tuple[str, str, date]:
    nome = _cstr(desc)
    clube_liga, data_txt, *_ = _cstr(desc, 128).split("\n")
    # ponytail: assume D/M/AAAA (jogo em português); outro idioma pode inverter
    d, m, a = (int(x) for x in data_txt.split()[0].split("/"))
    return nome, clube_liga.rsplit(" / ", 1)[0], date(a, m, d)


def ler_times(data: bytes) -> list[str]:
    times = []
    while TIME0 + len(times) * TIME_TAM < PARTIDA0 and data[TIME0 + len(times) * TIME_TAM]:
        times.append(_cstr(data, TIME0 + len(times) * TIME_TAM))
    return times


def ler_elenco(data: bytes, idx: int) -> list[int]:
    o = idx * TIME_TAM + ELENCO
    pids = []
    for k in range(64):
        vaga, pid = struct.unpack_from("<II", data, o + k * 8)
        if vaga == 0xFFFF:
            return pids
        pids.append(pid & PID)
    raise FormatoInvalido(f"elenco do time {idx} sem fim")


def ler_partidas(data: bytes, n_times: int) -> list[Partida]:
    partidas = []
    for i in range(PARTIDAS):
        h = PARTIDA0 + i * PARTIDA_TAM
        if data[h:h + 8] == VAZIO:
            continue
        a, m, d = struct.unpack_from("<HBB", data, h)
        try:
            dia = date(a, m, d)
        except ValueError:
            raise FormatoInvalido(f"partida {i}: data inválida {a}-{m}-{d}") from None
        mand, vis = (struct.unpack_from("<H", data, h + o)[0] & INDEFINIDO for o in (12, 16))
        if any(t >= n_times and t != INDEFINIDO for t in (mand, vis)):
            raise FormatoInvalido(f"partida {i}: time {mand}/{vis} fora da tabela de {n_times}")
        if INDEFINIDO in (mand, vis):
            continue
        escalacao = []
        for s in range(VAGAS):
            vaga, pid, x = struct.unpack_from("<III", data, h + 28 + s * VAGA_TAM)
            if vaga != 0xFFFF:
                escalacao.append(Atuacao(pid & PID, s // 17, x & 0xFF, (x >> 8) & 0xFF))
        p = data[h + 20:h + 26]
        partidas.append(Partida(dia, mand, vis, (p[0] + p[1], p[3] + p[4]), (p[2], p[5]), escalacao))
    return partidas


def ler_save(raw: bytes) -> Save:
    partes = decrypt(raw)
    if partes["header.dat"][144:146] != b"ML":
        raise FormatoInvalido("não é um save de Master League")
    nome, clube, data_jogo = ler_descricao(partes["description.dat"])
    data = partes["data.dat"]
    times = ler_times(data)
    if clube not in times:
        raise FormatoInvalido(f"clube {clube!r} não está na tabela de times")
    idx = times.index(clube)
    return Save(nome, clube, data_jogo, times, idx, ler_elenco(data, idx), ler_partidas(data, len(times)))
