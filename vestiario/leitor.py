"""Lê um save da Master League do PES 2021 (Football Life 2026 / Transfer Patch). Tudo na memória."""
import struct
from collections import Counter
from dataclasses import dataclass, field
from datetime import date

from .pesdecrypt import decrypt

TIME0, TIME_TAM = 84, 1680           # nome do time i em TIME0 + i*TIME_TAM
TIME_ID = 80                         # u32 em i*TIME_TAM + TIME_ID: id do time no PES << 14 | i
ELENCO = 412                         # (u32 vaga, u32 player_id) a partir de i*TIME_TAM + ELENCO
ELENCO_MAX = 40                      # elenco cheio não tem a vaga 0xFFFF que marca o fim
PARTIDA0, PARTIDA_TAM, PARTIDAS = 3_316_488, 596, 13_000
VAGAS, VAGA_TAM = 34, 16             # 17 por lado, mandante primeiro
VAZIO = bytes.fromhex("ffff000003000000")
INDEFINIDO = 0x3FFF                  # time ainda não definido (mata-mata)
PID = 0x3FFFFFFF                     # bits altos do player_id são flags
# Livro de transferências do clube do usuário (tela "Taxa de transferência"): 100 registros de 52 bytes,
# (u32 vaga, u32 player_id, 6×0, i32 valor, u32 tipo, 2×0, u32 0xFFFF); vaga 0xFFFF = vazio.
LIVRO0, LIVRO_TAM, LIVRO_N = 13_108_192, 52, 100
MOEDA = 430                          # R$ por unidade de dinheiro do save (conferido nas telas do PES em 31/01/2026)
ORCAMENTO = 13_098_240               # u32 orçamento de transferências (× MOEDA), fixo nos 3 saves conferidos
CONTRATO_TAM = 48                    # contratos do clube do usuário; a tabela muda de lugar (veja ler_contratos)


class FormatoInvalido(Exception):
    pass


@dataclass
class Atuacao:
    player_id: int
    lado: int                        # 0 = mandante, 1 = visitante
    gols: int
    assistencias: int


@dataclass
class Negocio:
    player_id: int
    valor: int                       # unidades do save (× MOEDA = R$); negativo = o clube pagou
    tipo: int                        # 1 = contratação, 5 = venda, 8 = troca


@dataclass
class Contrato:
    salario_anual: int               # unidades do save; o semanal da tela é salario_anual // 52 * MOEDA
    multa: int                       # × MOEDA = R$; 0 = sem multa rescisória
    fim: date


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
    ids: list[int] = field(default_factory=list)  # id PES de cada time (o do escudo)
    elencos: list[list[int]] = field(default_factory=list)  # elenco de cada time, na ordem da tabela
    negocios: list[Negocio] = field(default_factory=list)   # livro de transferências do clube do usuário
    contratos: dict[int, Contrato] = field(default_factory=dict)  # player_id → contrato, só do clube do usuário
    orcamento: int | None = None     # orçamento de transferências (× MOEDA = R$)


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


def ler_ids(data: bytes, n_times: int) -> list[int]:
    ids = []
    for i in range(n_times):
        v = struct.unpack_from("<I", data, i * TIME_TAM + TIME_ID)[0]
        if v & INDEFINIDO != i:
            raise FormatoInvalido(f"time {i}: id PES não confere com o índice")
        ids.append(v >> 14)
    return ids


def ler_elenco(data: bytes, idx: int) -> list[int]:
    o = idx * TIME_TAM + ELENCO
    pids = []
    for k in range(ELENCO_MAX):
        vaga, pid = struct.unpack_from("<II", data, o + k * 8)
        if vaga == 0xFFFF:
            break
        pids.append(pid & PID)
    return pids


def ler_negocios(data: bytes) -> list[Negocio]:
    negocios = []
    for k in range(LIVRO_N):
        vaga, pid, *zeros, valor, tipo, _, _, fim = struct.unpack_from("<II6IiI3I", data, LIVRO0 + k * LIVRO_TAM)
        # ponytail: posição fixa conferida em 3 saves; num layout diferente o livro fica vazio em vez de quebrar a sincronização
        if fim != 0xFFFF or any(zeros):
            return []
        if vaga != 0xFFFF:
            negocios.append(Negocio(pid & PID, valor, tipo))
    return negocios


def _data(data: bytes, o: int) -> date | None:
    a, m, d = struct.unpack_from("<HBB", data, o)
    try:
        return date(a, m, d)
    except ValueError:
        return None


def ler_contratos(data: bytes, elenco: list[int]) -> dict[int, Contrato]:
    """Registros de 48 bytes fora de alinhamento: (u32 vaga, u32 player_id, u32 salário anual, u32 multa, data do fim,
    u32, 4 bytes do id da carreira, u32, data, …, 8 × 0xFF em +38). A tabela muda de lugar entre saves, então cada
    jogador do elenco é achado pelo formato do registro. O id da carreira é o mesmo em quase todos e confirma a tabela;
    recém-chegado e emprestado vêm sem ele, e entram por estarem a um múltiplo de 48 bytes dos confirmados."""
    candidatos = []
    for pid in elenco:
        alvo = struct.pack("<I", pid)
        p = data.find(alvo, 4)
        while p != -1:
            o = p - 4
            if o + CONTRATO_TAM <= len(data) and data[o + 38:o + 46] == b"\xff" * 8 and (fim := _data(data, o + 16)):
                anual, multa = struct.unpack_from("<II", data, o + 8)
                candidatos.append((o, data[o + 24:o + 28], pid, Contrato(anual, multa, fim)))
            p = data.find(alvo, p + 1)
    if not candidatos:
        return {}
    carreira = Counter(c[1] for c in candidatos).most_common(1)[0][0]
    base = min(o for o, chave, *_ in candidatos if chave == carreira)
    return {pid: c for o, chave, pid, c in candidatos
            if chave == carreira or ((o - base) % CONTRATO_TAM == 0 and abs(o - base) <= CONTRATO_TAM * 64)}


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
    elencos = [ler_elenco(data, i) for i in range(len(times))]
    return Save(nome, clube, data_jogo, times, idx, elencos[idx], ler_partidas(data, len(times)),
                ler_ids(data, len(times)), elencos, ler_negocios(data), ler_contratos(data, elencos[idx]),
                struct.unpack_from("<I", data, ORCAMENTO)[0])
