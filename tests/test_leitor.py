import struct
from datetime import date

import pytest

from vestiario.leitor import (PARTIDA0, PARTIDA_TAM, PARTIDAS, VAZIO, FormatoInvalido, ler_descricao,
                              ler_partidas)


def tabela_vazia() -> bytearray:
    data = bytearray(PARTIDA0 + PARTIDAS * PARTIDA_TAM)
    for i in range(PARTIDAS):
        data[PARTIDA0 + i * PARTIDA_TAM:PARTIDA0 + i * PARTIDA_TAM + 8] = VAZIO
    return data


def escrever_partida(data, i, ano, mes, dia, mandante, visitante, placar=b"\0" * 6, vagas=()):
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
    escrever_partida(data, 5, 2026, 2, 4, 2, 1)                 # futura
    escrever_partida(data, 9, 2026, 3, 1, 1, 0x3FFF)            # adversário indefinido: ignorada
    ps = ler_partidas(bytes(data), n_times=3)
    assert len(ps) == 2
    p = ps[0]
    assert (p.data, p.mandante, p.visitante, p.gols, p.disputada) == (date(2026, 1, 22), 1, 2, (2, 1), True)
    assert [(a.player_id, a.lado, a.gols, a.assistencias) for a in p.escalacao] == [
        (500, 0, 2, 0), (600, 1, 1, 0), (601, 1, 0, 1)]
    assert ps[1].disputada is False


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
