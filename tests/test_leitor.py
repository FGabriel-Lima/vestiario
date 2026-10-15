import struct
import zlib
from datetime import date

import pytest

from vestiario.leitor import (ELENCO, LIVRO0, LIVRO_N, LIVRO_TAM, MOEDA, PARTIDA0, PARTIDA_TAM, PARTIDAS, TIME_ID,
                              TIME_TAM, VAZIO, BLOCO0, COMPETICAO_TAM, COMPETICOES0, FormatoInvalido, ler_competicoes,
                              ler_contratos, ler_descricao, ler_elenco, ler_idades, ler_ids, ler_negocios, ler_partidas)


def tabela_vazia() -> bytearray:
    data = bytearray(PARTIDA0 + PARTIDAS * PARTIDA_TAM)
    for i in range(PARTIDAS):
        data[PARTIDA0 + i * PARTIDA_TAM:PARTIDA0 + i * PARTIDA_TAM + 8] = VAZIO
    return data


def escrever_partida(data, i, ano, mes, dia, mandante, visitante, placar=b"\0" * 6, vagas=(), competicao=0, rodada=0):
    h = PARTIDA0 + i * PARTIDA_TAM
    data[h:h + PARTIDA_TAM] = bytes(PARTIDA_TAM)
    struct.pack_into("<HBB", data, h, ano, mes, dia)
    struct.pack_into("<H", data, h + 12, mandante)
    struct.pack_into("<H", data, h + 16, visitante)
    data[h + 20:h + 26] = placar
    for s in range(34):
        struct.pack_into("<I", data, h + 28 + s * 16, 0xFFFF)
    for s, pid, gols, assist in vagas:
        struct.pack_into("<IIII", data, h + 28 + s * 16, 1, pid, gols | assist << 8, 0)
    struct.pack_into("<HH", data, h + 592, competicao, rodada)


def test_descricao():
    desc = bytearray(384)
    desc[0:14] = b"Liga Master 03"
    texto = "São Paulo FC / Brasileirão Série A\n31/1/2026 12:00\nBrasileirão Série A".encode()
    desc[128:128 + len(texto)] = texto
    assert ler_descricao(bytes(desc)) == ("Liga Master 03", "São Paulo FC", date(2026, 1, 31))


def test_partidas_sinteticas():
    data = tabela_vazia()
    # 2 x 1 com gol de prorrogação do mandante; vagas 0..16 = mandante, 17..33 = visitante
    escrever_partida(data, 0, 2026, 1, 22, 1, 2, bytes([1, 1, 0, 1, 0, 0]),
                     [(0, 0x80000000 | 500, 2, 0), (17, 600, 1, 0), (18, 601, 0, 1)])
    escrever_partida(data, 5, 2026, 2, 4, 2, 1, competicao=12 << 8 | 9, rodada=0x6000 | 3)  # futura, grupo C
    escrever_partida(data, 9, 2026, 3, 1, 1, 0x3FFF)            # adversário indefinido: ignorada
    ps = ler_partidas(bytes(data), n_times=3)
    assert len(ps) == 2
    p = ps[0]
    assert (p.data, p.mandante, p.visitante, p.gols, p.disputada) == (date(2026, 1, 22), 1, 2, (2, 1), True)
    assert [(a.player_id, a.lado, a.gols, a.assistencias) for a in p.escalacao] == [
        (500, 0, 2, 0), (600, 1, 1, 0), (601, 1, 0, 1)]
    assert ps[1].disputada is False
    assert (ps[1].competicao, ps[1].grupo, ps[1].rodada) == (9, 3, 3)


def test_tabela_de_competicoes():
    data = bytearray(COMPETICOES0 + 4 * COMPETICAO_TAM)
    for k, (cid, nome) in enumerate(((1, "FIFA Club World Cup"), (29, "Brasileirão Série A"), (31, "Copa do Brasil"))):
        struct.pack_into("<H", data, COMPETICOES0 + k * COMPETICAO_TAM, cid)
        o = COMPETICOES0 + k * COMPETICAO_TAM + 2
        data[o:o + len(nome.encode())] = nome.encode()
    assert ler_competicoes(bytes(data)) == {1: "FIFA Club World Cup", 29: "Brasileirão Série A", 31: "Copa do Brasil"}
    assert ler_competicoes(bytes(COMPETICOES0 + 10)) == {}


def test_data_invalida_recusa_o_save():
    data = tabela_vazia()
    escrever_partida(data, 3, 2026, 13, 40, 1, 2)
    with pytest.raises(FormatoInvalido, match="partida 3"):
        ler_partidas(bytes(data), n_times=3)


def test_time_fora_da_tabela_recusa_o_save():
    data = tabela_vazia()
    escrever_partida(data, 0, 2026, 1, 1, 1, 7)
    with pytest.raises(FormatoInvalido, match="fora da tabela"):
        ler_partidas(bytes(data), n_times=3)


# --- save real (pulado se saves/ML00000002 não existir) ---

def test_save_real_cabecalho(save_atual):
    assert save_atual.times[0] == "Arsenal FC"
    assert save_atual.clube == "São Paulo FC"
    assert save_atual.times[save_atual.clube_idx] == "São Paulo FC"


def test_save_real_elenco(save_atual):
    assert 60657 in save_atual.elenco               # Jonathan Calleri
    assert 18 <= len(save_atual.elenco) <= 40


def test_save_real_placar_bate_com_escalacao(save_atual):
    jogadas = [p for p in save_atual.partidas if p.escalacao]
    assert jogadas and any(not p.disputada for p in save_atual.partidas)
    for p in jogadas:
        soma = [sum(a.gols for a in p.escalacao if a.lado == lado) for lado in (0, 1)]
        assert list(p.gols) == soma, p


def test_ids_pes_dos_times():
    data = bytearray(3 * TIME_TAM + 100)
    for i, pes_id in enumerate((101, 1255, 9)):
        struct.pack_into("<I", data, i * TIME_TAM + TIME_ID, pes_id << 14 | i)
    assert ler_ids(bytes(data), 3) == [101, 1255, 9]
    struct.pack_into("<I", data, 2 * TIME_TAM + TIME_ID, 9 << 14 | 7)
    with pytest.raises(FormatoInvalido, match="time 2"):
        ler_ids(bytes(data), 3)


def test_save_real_competicoes(save_atual):
    assert save_atual.competicoes[29] == "Brasileirão Série A" and save_atual.competicoes[31] == "Copa do Brasil"
    serie_a = [p for p in save_atual.partidas if p.competicao == 29 and p.data.year == 2026]
    assert len({t for p in serie_a for t in (p.mandante, p.visitante)}) == 20
    assert {p.rodada for p in serie_a} == set(range(38))


def test_save_real_ids_pes(save_atual):
    assert len(save_atual.ids) == len(save_atual.times)
    assert save_atual.ids[0] == 101                                 # Arsenal
    assert save_atual.ids[save_atual.clube_idx] == 1255             # São Paulo


def test_elenco_cheio_nao_tem_terminador():
    data = bytearray(2 * TIME_TAM)
    for k in range(41):  # 40 vagas cheias; a 41ª entrada já é outro dado do registro
        struct.pack_into("<II", data, ELENCO + k * 8, k, 0x40000000 | 1000 + k)
    assert ler_elenco(bytes(data), 0) == list(range(1000, 1040))
    struct.pack_into("<II", data, TIME_TAM + ELENCO, 0, 7)
    struct.pack_into("<II", data, TIME_TAM + ELENCO + 8, 0xFFFF, 0)
    assert ler_elenco(bytes(data), 1) == [7]


def test_save_real_elencos_de_todos_os_times(save_atual):
    times = save_atual.times
    assert len(save_atual.elencos) == len(times)
    assert save_atual.elencos[save_atual.clube_idx] == save_atual.elenco
    assert len(save_atual.elencos[times.index("Galatasaray SK")]) == 40     # elenco cheio, sem terminador
    assert 60657 in save_atual.elencos[save_atual.clube_idx]                 # Calleri


def livro_vazio() -> bytearray:
    data = bytearray(LIVRO0 + LIVRO_N * LIVRO_TAM)
    for k in range(LIVRO_N):
        struct.pack_into("<I", data, LIVRO0 + k * LIVRO_TAM, 0xFFFF)
        struct.pack_into("<I", data, LIVRO0 + k * LIVRO_TAM + 48, 0xFFFF)
    return data


def test_livro_de_transferencias():
    data = livro_vazio()
    struct.pack_into("<II", data, LIVRO0, 3471, 101544)
    struct.pack_into("<iI", data, LIVRO0 + 32, -93655, 1)
    struct.pack_into("<II", data, LIVRO0 + 2 * LIVRO_TAM, 4025, 0x40000000 | 115056)
    struct.pack_into("<iI", data, LIVRO0 + 2 * LIVRO_TAM + 32, 77791, 5)
    assert [(n.player_id, n.valor, n.tipo) for n in ler_negocios(bytes(data))] == [(101544, -93655, 1), (115056, 77791, 5)]
    struct.pack_into("<I", data, LIVRO0 + 5 * LIVRO_TAM + 48, 7)  # layout diferente: sem negócios, sem quebrar
    assert ler_negocios(bytes(data)) == []


def test_save_real_livro_de_transferencias(save_atual):
    # tela "Taxa de transferência" do PES em 31/01/2026: Scarpa R$ -40.271.650 (contratar)
    assert any((n.player_id, n.valor, n.tipo) == (101544, -93655, 1) for n in save_atual.negocios)


def registro_de_contrato(vaga, pid, anual, multa, fim, inicio, carreira=bytes.fromhex("83c03901")) -> bytes:
    r = struct.pack("<IIII", vaga, pid, anual, multa) + struct.pack("<HBB", *fim) + bytes.fromhex("03000000")
    return r + carreira + bytes.fromhex("05000000") + struct.pack("<HBB", *inicio) + b"\xff" * 10 + bytes.fromhex("0030")


def test_contratos_sinteticos():
    lixo = struct.pack("<II", 0, 41204) + bytes(40)  # o mesmo player_id fora da tabela não confunde
    tabela = (registro_de_contrato(0x0F9B, 41204, 17967, 60458, (2027, 1, 31), (2026, 1, 9))
              + registro_de_contrato(0xE63755E3, 122283, 14759, 0, (2030, 1, 31), (2025, 1, 1)))
    data = b"\x1b" * 101 + lixo + tabela  # posição ímpar, como no save
    c = ler_contratos(data, [41204, 122283, 999])
    assert set(c) == {41204, 122283}
    assert (c[41204].salario_anual, c[41204].multa, c[41204].fim) == (17967, 60458, date(2027, 1, 31))
    assert c[122283].fim == date(2030, 1, 31)


def test_save_real_contratos(save_atual):
    # telas do PES em 31/01/2026: Rafael R$ 148.350/semana, multa R$ 25.996.940, contrato até 31/1/2027
    rafael = save_atual.contratos[41204]
    assert (rafael.salario_anual // 52 * MOEDA, rafael.multa * MOEDA, rafael.fim) == (148_350, 25_996_940, date(2027, 1, 31))
    assert save_atual.contratos[160150].fim == date(2030, 1, 31)                         # Cauly
    assert len(save_atual.contratos) >= len(save_atual.elenco) - 3


def test_save_real_orcamento(save_atual):
    assert save_atual.orcamento * MOEDA == 443_590_580  # "Orçam. transf." na tela do PES em 31/01/2026


def bloco_compactado(registros: list[tuple[int, int]]) -> bytes:
    """Bloco como o do save: registros de 156 bytes (idade em +18, bits 2..7; player_id em +36), em pedaços zlib."""
    raw = bytearray(156 * len(registros))
    for k, (pid, idade) in enumerate(registros):
        raw[k * 156 + 18] = idade << 2 | 0b01
        struct.pack_into("<I", raw, k * 156 + 36, pid)
    pedacos = b""
    for i in range(0, len(raw), 200):
        z = zlib.compress(bytes(raw[i:i + 200]))
        pedacos += struct.pack(">III", len(raw[i:i + 200]), len(z), 0) + z
    return bytes.fromhex("20110912") + bytes(4) + struct.pack(">II", len(raw), len(pedacos)) + pedacos


def test_idades_do_bloco_compactado():
    data = bytes(BLOCO0) + bloco_compactado([(60657, 33), (0x40000000 | 65134, 35), (0, 0)])
    assert ler_idades(data) == {60657: 33, 65134: 35}
    assert ler_idades(bytes(BLOCO0 + 100)) == {}  # sem a assinatura: sem idades, sem quebrar


def test_save_real_idades(save_atual):
    # telas do PES em 31/01/2026: Calleri 33, Artur 28, Arboleda 35
    assert {p: save_atual.idades[p] for p in (60657, 113479, 65134)} == {60657: 33, 113479: 28, 65134: 35}
