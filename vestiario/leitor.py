"""Lê um save da Master League do PES 2021 (Football Life 2026 / Transfer Patch). Tudo na memória."""
import struct
import zlib
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
COMPETICAO, RODADA = 592, 594        # u16 (grupo << 8 | competição) e u16 (flags << 8 | rodada) no registro da partida
# Tabela de competições (fixa nos 4 saves conferidos): registros de 788 bytes (u16 id, nome UTF-8)
COMPETICOES0, COMPETICAO_TAM = 2_040_080, 788
VAZIO = bytes.fromhex("ffff000003000000")
INDEFINIDO = 0x3FFF                  # time ainda não definido (mata-mata)
PID = 0x3FFFFFFF                     # bits altos do player_id são flags
# Livro de transferências do clube do usuário (tela "Taxa de transferência"): 100 registros de 52 bytes,
# (u32 vaga, u32 player_id, 6×0, i32 valor, u32 tipo, 2×0, u32 0xFFFF); vaga 0xFFFF = vazio.
LIVRO0, LIVRO_TAM, LIVRO_N = 13_108_192, 52, 100
MOEDA = 430                          # R$ por unidade de dinheiro do save (conferido nas telas do PES em 31/01/2026)
ORCAMENTO = 13_098_240               # u32 orçamento de transferências (× MOEDA), fixo nos 3 saves conferidos
# Bloco do orçamento (conferido com as telas "Relatório de orçamento" e "Saldo da conta do clube" do PES, ML04 em
# 19/04/2026): +28 = folga anual de salários (÷ 52 = "Orç. de salário" semanal); +44/+48/+52 = TV, patrocínio e
# sócios-torcedores da temporada; +9344 = venda de produtos (fim da lista por jogador). A bilheteria não fica gravada
# como total (o jogo deve calcular pelo público), nem os prêmios.
FOLGA_SALARIAL = ORCAMENTO + 28
RECEITAS = {"tv": ORCAMENTO + 44, "patrocinio": ORCAMENTO + 48, "socios": ORCAMENTO + 52, "produtos": ORCAMENTO + 9344}
# Bloco compactado (assinatura 20 11 09 12, fixo nos 4 saves conferidos): pedaços zlib com cabeçalho BE.
# Descompactado, 30.001 registros de 156 bytes, um por jogador da ML (inclusive os gerados por ela).
BLOCO0, BLOCO_REG, BLOCO_ID, BLOCO_IDADE = 18_088_888, 156, 36, 18  # idade em +18, bits 2..7
BLOCO_VALOR = 120                    # u32 valor de mercado (× MOEDA = R$; conferido com Tolói e Sabino na Liga Master 04)
CONTRATO_TAM = 48                    # contratos do clube do usuário; a tabela muda de lugar (veja ler_contratos)


class FormatoInvalido(Exception):
    pass


@dataclass
class Atuacao:
    player_id: int
    lado: int                        # 0 = mandante, 1 = visitante
    gols: int
    assistencias: int
    minutos: int = 0                 # nas partidas simuladas pelo jogo, sempre 90 para os 11
    nota: int | None = None          # em décimos (76 = 7.6); None = jogou pouco e ficou sem nota


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
    emprestimo: bool = False         # emprestado ao clube: o save só guarda o fim do empréstimo (sem salário nem dono)


@dataclass
class Proposta:
    clube: int                       # índice do clube que fez a proposta
    player_id: int
    valor: int                       # × MOEDA = R$


@dataclass
class Partida:
    data: date
    mandante: int
    visitante: int
    gols: tuple[int, int]
    penaltis: tuple[int, int]
    escalacao: list[Atuacao]
    competicao: int | None = None    # id na tabela de competições
    grupo: int = 0                   # 0 = sem grupo; 1 = A, 2 = B… (fase de grupos)
    rodada: int = 0                  # 0.. em pontos corridos e grupos; 46..53 no mata-mata (53 = final)

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
    idades: dict[int, int] = field(default_factory=dict)  # player_id → idade atual na ML
    valores: dict[int, int] = field(default_factory=dict)  # player_id → valor de mercado (× MOEDA = R$)
    competicoes: dict[int, str] = field(default_factory=dict)  # id → nome
    propostas: list[Proposta] = field(default_factory=list)  # propostas de outros clubes por jogadores do clube
    folga_salarial: int | None = None  # folga anual para salários (÷ 52 × MOEDA = "Orç. de salário" da tela)
    receitas: dict[str, int] = field(default_factory=dict)  # receitas da temporada (× MOEDA), veja RECEITAS


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
    return contratos_e_carreira(data, elenco)[0]


def contratos_e_carreira(data: bytes, elenco: list[int]) -> tuple[dict[int, Contrato], tuple[bytes, int] | None]:
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
        return {}, None
    carreira = Counter(c[1] for c in candidatos).most_common(1)[0][0]
    base = min(o for o, chave, *_ in candidatos if chave == carreira)
    contratos = {pid: c for o, chave, pid, c in candidatos if chave == carreira}
    fim_tabela = max(o for o, chave, *_ in candidatos if chave == carreira)
    # sem o id da carreira só entra quem não tem contrato com ele e está na tabela (ou colado nela). Mais adiante, no
    # mesmo alinhamento, ficam os termos das propostas de outros clubes (Flamengo pelo Tolói na Liga Master 04)
    for o, chave, pid, c in candidatos:
        if pid not in contratos and (o - base) % CONTRATO_TAM == 0 and base - CONTRATO_TAM * 64 <= o <= fim_tabela + CONTRATO_TAM * 3:
            contratos[pid] = c
    # quem veio emprestado fica noutra tabela, perto desta: (vaga, player_id, 8 bytes zerados, fim do empréstimo, 0xFFFF)
    # (conferido com Cauly, Artur e Pedro Lima, emprestados ao São Paulo no começo da Liga Master 04)
    for pid in set(elenco) - contratos.keys():
        p = data.find(struct.pack("<I", pid), max(4, base - 1_000_000))
        while p != -1 and p < base + 1_000_000:
            o = p - 4
            if data[o + 8:o + 16] == bytes(8) and data[o + 20:o + 22] == bytes.fromhex("ffff") and (fim := _data(data, o + 16)):
                contratos[pid] = Contrato(0, 0, fim, emprestimo=True)
                break
            p = data.find(struct.pack("<I", pid), p + 1)
    return contratos, (carreira, base)


def ler_propostas(data: bytes, carreira: tuple[bytes, int] | None, n_times: int, elenco: list[int]) -> list[Proposta]:
    """Propostas de outros clubes por jogadores do clube (tela de negociações): registros de 60 bytes perto da
    tabela de contratos, (u16 clube com flags, …, id da carreira em +24, vaga, player_id, valor, valor). Conferido
    com Flamengo → Tolói e Estoril → Sabino na Liga Master 04."""
    if not carreira:
        return []
    chave, base = carreira
    propostas = []
    o = data.find(chave, max(24, base - 200_000))
    while o != -1 and o < base + 400_000:
        r = o - 24
        clube = struct.unpack_from("<H", data, r)[0] & INDEFINIDO
        pid = struct.unpack_from("<I", data, r + 32)[0] & PID
        valor, repetido = struct.unpack_from("<II", data, r + 36)
        # só jogadores do elenco: o id da carreira também aparece em outros registros que não são propostas
        if clube < n_times and pid in elenco and 0 < valor == repetido:
            propostas.append(Proposta(clube, pid, valor))
        o = data.find(chave, o + 1)
    return propostas


def ler_bloco(data: bytes) -> tuple[dict[int, int], dict[int, int]]:
    """Idade atual e valor de mercado de cada jogador na ML (a idade do Player.bin é a do patch e não avança)."""
    if data[BLOCO0:BLOCO0 + 4] != bytes.fromhex("20110912"):
        return {}, {}  # ponytail: posição fixa nos saves conferidos; noutro layout o elenco fica sem idade e valor
    total = struct.unpack_from(">I", data, BLOCO0 + 8)[0]
    p, raw = BLOCO0 + 16, bytearray()
    try:
        while len(raw) < total:
            tam = struct.unpack_from(">I", data, p + 4)[0]
            raw += zlib.decompress(data[p + 12:p + 12 + tam])
            p += 12 + tam
    except (struct.error, zlib.error):
        return {}, {}
    idades, valores = {}, {}
    for o in range(0, len(raw) - BLOCO_REG + 1, BLOCO_REG):
        if pid := struct.unpack_from("<I", raw, o + BLOCO_ID)[0] & PID:
            idades[pid] = raw[o + BLOCO_IDADE] >> 2
            valores[pid] = struct.unpack_from("<I", raw, o + BLOCO_VALOR)[0]
    return idades, valores


def ler_competicoes(data: bytes) -> dict[int, str]:
    nomes = {}
    for o in range(COMPETICOES0, len(data) - COMPETICAO_TAM + 1, COMPETICAO_TAM):
        if not (nome := data[o + 2:o + 80].split(b"\0")[0]):
            break
        nomes[struct.unpack_from("<H", data, o)[0]] = nome.decode("utf8", "replace")
    return nomes


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
            vaga, pid, x, y = struct.unpack_from("<IIII", data, h + 28 + s * VAGA_TAM)
            if vaga != 0xFFFF:
                # y: minutos nos bits 0-6 e nota (em décimos) nos bits 7-13; conferido com a tela do PES
                escalacao.append(Atuacao(pid & PID, s // 17, x & 0xFF, (x >> 8) & 0xFF, y & 0x7F,
                                         ((y >> 7) & 0x7F) or None))
        p = data[h + 20:h + 26]
        comp, rodada = struct.unpack_from("<HH", data, h + COMPETICAO)
        # o byte alto da competição vem em passos de 4 (4 = grupo A, 8 = B…)
        partidas.append(Partida(dia, mand, vis, (p[0] + p[1], p[3] + p[4]), (p[2], p[5]), escalacao,
                                comp & 0xFF, comp >> 10, rodada & 0xFF))
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
    contratos, carreira = contratos_e_carreira(data, elencos[idx])
    return Save(nome, clube, data_jogo, times, idx, elencos[idx], ler_partidas(data, len(times)),
                ler_ids(data, len(times)), elencos, ler_negocios(data), contratos,
                struct.unpack_from("<I", data, ORCAMENTO)[0], *ler_bloco(data), ler_competicoes(data),
                ler_propostas(data, carreira, len(times), elencos[idx]),
                struct.unpack_from("<I", data, FOLGA_SALARIAL)[0],
                {k: struct.unpack_from("<I", data, o)[0] for k, o in RECEITAS.items()})
