# Vestiário

Companheiro de Master League para o **PES 2021 (PC)**. Você joga as partidas no PES e acompanha o clube no Vestiário: elenco, resultados, estatísticas e a história da carreira.

Os dados vêm do save do jogo, sem cadastro manual. É só salvar no PES e clicar em **Sincronizar**.

## O que ele faz

- **Lê os saves da Master League.** Descriptografa o save na memória, sem alterar o arquivo original, e encontra o clube, o elenco e todas as partidas.
- **Guarda a história da carreira.** O PES apaga as partidas antigas do save (ele guarda cerca de um ano). O Vestiário acumula tudo num banco local, então nada se perde. Ele também lê a pasta `backup/` dos saves, o que permite recuperar temporadas que já sumiram do save principal.
- **Mostra o clube por temporada:**
  - **Visão geral:** aproveitamento, vitórias, empates, derrotas, gols e a sequência dos últimos resultados.
  - **Elenco:** jogos, gols e assistências de cada jogador, com ordenação por coluna.
  - **Partidas:** os jogos disputados e os próximos do calendário.
  - **Lendas:** artilheiros, garçons e quem mais jogou pelo clube em toda a carreira.
- **Usa os nomes e os escudos do seu patch.** Os nomes dos jogadores e os escudos dos times saem dos arquivos do patch instalado, na mesma ordem em que o jogo os carrega.

## Requisitos

- Windows, com o PES 2021 no PC e um patch baseado no Football Life 2026. O Vestiário foi testado com o Football Life 2026 e com o Transfer Patch.
- Python 3.12 ou mais novo.
- Node.js 20.19 ou 22.12 em diante (só para gerar as telas).

## Instalação

```bash
git clone https://github.com/FGabriel-Lima/vestiario.git
cd vestiario

python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"

cd web
npm install
npm run build
cd ..
```

## Como usar

```bash
.venv/Scripts/python -m vestiario
```

O navegador abre em `http://127.0.0.1:8765`. Clique em **Sincronizar** e escolha uma carreira.

Depois de jogar, salve a Master League no PES e clique em **Sincronizar** de novo. Só os saves que mudaram são lidos outra vez (uns 7 segundos por save).

## Configuração

Os caminhos padrão funcionam numa instalação comum. Para trocar algum, defina a variável de ambiente antes de iniciar:

| Variável | O que é | Padrão |
|---|---|---|
| `VESTIARIO_SAVES` | Pasta de saves do PES | `Documentos\KONAMI\eFootball PES 2021 SEASON UPDATE\2026\save` |
| `VESTIARIO_PES` | Pasta de instalação do patch | `D:\Transferpatch` |
| `VESTIARIO_DB` | Banco de dados do Vestiário | `%LOCALAPPDATA%\Vestiario\vestiario.db` |

Se o Vestiário não achar o patch, ele sincroniza mesmo assim. Nesse caso, os jogadores aparecem como "Jogador #id" e os times aparecem com as iniciais no lugar do escudo.

## Seus dados

- **Os saves do PES nunca são alterados.** O Vestiário só lê os arquivos.
- **Tudo fica no seu PC:**
  - O banco e os escudos ficam em `%LOCALAPPDATA%\Vestiario\`.
  - O servidor só aceita conexões do próprio computador (`127.0.0.1`).
- **Saves, arquivos extraídos do jogo e o banco não entram no repositório.** São dados pessoais e conteúdo da Konami ou do patch.

## Testes

```bash
.venv/Scripts/python -m pytest -q
```

Alguns testes usam dados reais e são pulados quando eles não existem:
- os que precisam de um save usam uma cópia em `saves/ML00000002`;
- os que precisam do patch procuram o Transfer Patch instalado.

## Estrutura

```
vestiario/
  pesdecrypt.py    descriptografia dos saves do PES 2021
  cpk.py           leitura dos pacotes CPK do jogo
  leitor.py        save → times, elenco e partidas, com validação do formato
  patch.py         arquivos do patch (nomes dos jogadores e escudos)
  banco.py         banco SQLite e consultas das telas
  sincronizar.py   lê a pasta de saves e grava o que mudou
  api.py           API local (FastAPI)
web/               telas (React, Vite e Tailwind)
tests/
```

## Próximos passos

- Decodificar a competição de cada partida, para mostrar classificação, títulos, campeões pelo mundo e Bola de Ouro.
- Posição, idade e overall dos jogadores.
- Tela de transferências: quem entrou e quem saiu entre uma sincronização e outra.
- Auxiliar técnico e conversa com jogadores usando IA, sempre com base nos dados reais do save.

## Créditos

A descriptografia dos saves é um port do [pesXdecrypter](https://github.com/the4chancup/pesXdecrypter), que é de domínio público.
