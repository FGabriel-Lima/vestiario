from datetime import date
from pathlib import Path

import pytest

from vestiario.leitor import Atuacao, Contrato, Negocio, Partida, Save, ler_save

SAVES = Path(__file__).resolve().parent.parent / "saves"


@pytest.fixture(scope="session")
def save_atual() -> Save:
    """Cópia de um save real em saves/ML00000002 (fora do git). Sem ela, o teste é pulado."""
    arq = SAVES / "ML00000002"
    if not arq.exists():
        pytest.skip("copie um save de Master League para saves/ML00000002")
    return ler_save(arq.read_bytes())


def partida(dia, mandante, visitante, gols=(0, 0), escalacao=(), penaltis=(0, 0)) -> Partida:
    return Partida(date.fromisoformat(dia), mandante, visitante, gols, penaltis, list(escalacao))


def fazer_save(data_jogo="2026-03-01", partidas=(), elenco=(10, 11, 12), nome="Liga Master 01",
               outros=((), ()), negocios=(), contratos=None, orcamento=None) -> Save:
    """outros = elencos do Clube B e do Clube C; o do Clube A é o elenco. negocios = (player_id, valor, tipo).
    contratos = {player_id: (salário anual, multa, "AAAA-MM-DD")}."""
    return Save(nome=nome, clube="Clube A", data_jogo=date.fromisoformat(data_jogo),
                times=["Clube A", "Clube B", "Clube C"], clube_idx=0, elenco=list(elenco), partidas=list(partidas),
                elencos=[list(elenco), *map(list, outros)], negocios=[Negocio(*n) for n in negocios],
                contratos={p: Contrato(a, m, date.fromisoformat(f)) for p, (a, m, f) in (contratos or {}).items()},
                orcamento=orcamento)


def atuacao(pid, lado, gols=0, assist=0) -> Atuacao:
    return Atuacao(pid, lado, gols, assist)
