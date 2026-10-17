from datetime import date
from pathlib import Path

import pytest

from vestiario.leitor import Atuacao, Contrato, Negocio, Partida, Proposta, Save, ler_save

SAVES = Path(__file__).resolve().parent.parent / "saves"


from vestiario import ia as _ia

RESPONDER_REAL = _ia.responder  # para o teste do próprio ia.responder


@pytest.fixture(autouse=True)
def sem_ia_de_verdade(monkeypatch):
    """Nenhum teste chama o Gemini: quem precisa da IA troca ia.responder por uma resposta pronta."""
    from vestiario import ia

    def sem_ia(*_):
        raise ia.IAIndisponivel("IA desligada nos testes.")

    monkeypatch.setattr(ia, "responder", sem_ia)


@pytest.fixture(scope="session")
def save_atual() -> Save:
    """Cópia de um save real em saves/ML00000002 (fora do git). Sem ela, o teste é pulado."""
    arq = SAVES / "ML00000002"
    if not arq.exists():
        pytest.skip("copie um save de Master League para saves/ML00000002")
    return ler_save(arq.read_bytes())


def partida(dia, mandante, visitante, gols=(0, 0), escalacao=(), penaltis=(0, 0), comp=None, grupo=0,
            rodada=0) -> Partida:
    return Partida(date.fromisoformat(dia), mandante, visitante, gols, penaltis, list(escalacao), comp, grupo, rodada)


def fazer_save(data_jogo="2026-03-01", partidas=(), elenco=(10, 11, 12), nome="Liga Master 01",
               outros=((), ()), negocios=(), contratos=None, orcamento=None, idades=None,
               competicoes=None, valores=None, propostas=(), times4=False, folga_salarial=None, receitas=None,
               clube_idx=0) -> Save:
    """outros = elencos do Clube B e do Clube C; o do Clube A é o elenco. negocios = (player_id, valor, tipo).
    contratos = {player_id: (salário anual, multa, "AAAA-MM-DD"[, empréstimo])}.
    clube_idx = índice do clube do usuário (o elenco dele vai para esse índice)."""
    times = ["Clube A", "Clube B", "Clube C"] + (["Seleção"] if times4 else [])
    elencos = [list(elenco), *map(list, outros)]
    if clube_idx:  # o elenco do usuário fica no índice do clube dele
        elencos[0], elencos[clube_idx] = elencos[clube_idx], elencos[0]
    return Save(nome=nome, clube=times[clube_idx], data_jogo=date.fromisoformat(data_jogo),
                times=times, clube_idx=clube_idx,
                elenco=list(elenco), partidas=list(partidas),
                elencos=elencos, negocios=[Negocio(*n) for n in negocios],
                contratos={p: Contrato(c[0], c[1], date.fromisoformat(c[2]), *c[3:]) for p, c in (contratos or {}).items()},
                orcamento=orcamento, idades=dict(idades or {}), valores=dict(valores or {}),
                competicoes=dict(competicoes or {}), propostas=[Proposta(*p) for p in propostas],
                folga_salarial=folga_salarial, receitas=dict(receitas or {}))


def atuacao(pid, lado, gols=0, assist=0, minutos=90, nota=60) -> Atuacao:
    return Atuacao(pid, lado, gols, assist, minutos, nota)
