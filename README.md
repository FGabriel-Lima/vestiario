# Vestiário

Companheiro de Master League para o **PES 2021 (PC)**. Você joga as partidas no PES e acompanha o clube no Vestiário: elenco, resultados, estatísticas e a história da carreira.

Os dados vêm do save do jogo, sem cadastro manual. É só salvar no PES e clicar em **Sincronizar**.

## O que ele faz

- **Lê os saves da Master League.** Descriptografa o save na memória, sem alterar o arquivo original, e encontra o clube, o elenco e todas as partidas.
- **Guarda a história da carreira.** O PES apaga as partidas antigas do save (ele guarda cerca de um ano). O Vestiário acumula tudo num banco local, então nada se perde. Ele também lê a pasta `backup/` dos saves, o que permite recuperar temporadas que já sumiram do save principal.
- **Mostra o clube inteiro:**
  - **Visão geral:** aproveitamento, campanha, orçamento de transferências e os últimos resultados.
  - **Elenco:** posição, idade, jogos, gols, assistências, minutos, nota média do PES, valor de mercado, salário,
    multa e fim do contrato (ou do empréstimo).
  - **Partidas:** os jogos da temporada; cada um abre a súmula com as escalações, os gols e a nota de cada jogador.
  - **Campeonatos:** a classificação no critério do PES, as fases de grupos e a chave do mata-mata de cada competição.
  - **Transferências:** quem chegou e quem saiu, de onde veio e para onde foi, com o valor, e as propostas recebidas.
  - **Adversários, Lendas e Pelo mundo:** retrospecto contra cada time, recordes, sala de troféus, artilharia do
    mundo e campeões.
- **Tem IA (Gemini), sempre presa aos dados do save:**
  - **Feed:** posts no estilo Instagram do perfil oficial do clube, da TNT Sports, do ge e de um perfil de mercado.
    Quem publica o quê sai dos fatos do save; a IA só escreve as legendas. Os posts saem a cada sincronização.
  - **Parecer do auxiliar** sobre cada proposta recebida: aceitar, pedir mais ou recusar, com os números usados.
  - **Conversas:** com o auxiliar técnico e com cada jogador do elenco, que responde com base nos próprios números
    (minutos, nota, contrato, propostas).
  - A IA não inventa número nem fato: recebe só o que está no banco, e o que falta vai dito como desconhecido.
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

Dê dois cliques em **`Vestiario.bat`** (ou num atalho para ele na área de trabalho). Ele sobe o servidor numa
janela minimizada e abre o navegador em `http://127.0.0.1:8765`; se o Vestiário já estiver aberto, só abre o
navegador. Pelo terminal, o mesmo é:

```bash
.venv/Scripts/python -m vestiario
```

Clique em **Sincronizar** e escolha uma carreira.

Depois de jogar, salve a Master League no PES e clique em **Sincronizar** de novo. Só os saves que mudaram são lidos outra vez (uns 7 segundos por save).

## Configuração

Os caminhos padrão funcionam numa instalação comum. Para trocar algum, defina a variável de ambiente antes de iniciar:

| Variável | O que é | Padrão |
|---|---|---|
| `VESTIARIO_SAVES` | Pasta de saves do PES | `Documentos\KONAMI\eFootball PES 2021 SEASON UPDATE\2026\save` |
| `VESTIARIO_PES` | Pasta de instalação do patch | `D:\Transferpatch` |
| `VESTIARIO_DB` | Banco de dados do Vestiário | `%LOCALAPPDATA%\Vestiario\vestiario.db` |
| `VESTIARIO_GEMINI_KEY` | Chave da API do Gemini (para a IA) | o arquivo `%LOCALAPPDATA%\Vestiario\gemini.key` |

### IA (opcional)

A IA usa o Gemini do Google, só com os modelos Flash e Flash-Lite. Gere uma chave no
[Google AI Studio](https://aistudio.google.com/apikey) e salve-a, sozinha, no arquivo
`%LOCALAPPDATA%\Vestiario\gemini.key` (ou na variável `VESTIARIO_GEMINI_KEY`). Sem chave, tudo funciona, menos o
feed, o parecer e as conversas, que mostram como configurar. A chave nunca vai para o repositório.

Se o Vestiário não achar o patch, ele sincroniza mesmo assim. Nesse caso, os jogadores aparecem como "Jogador #id" e os times aparecem com as iniciais no lugar do escudo.

## Seus dados

- **Os saves do PES nunca são alterados.** O Vestiário só lê os arquivos.
- **Tudo fica no seu PC:**
  - O banco, os escudos, as minifaces e a chave do Gemini ficam em `%LOCALAPPDATA%\Vestiario\`.
  - Só a IA sai do computador: ela manda ao Gemini os fatos do clube que cada tela precisa (números do save, nunca
    os arquivos).
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
  leitor.py        save → times, elencos, partidas, contratos, propostas e competições
  patch.py         arquivos do patch (nomes e posições dos jogadores, escudos, minifaces e cores)
  banco.py         banco SQLite e consultas das telas
  sincronizar.py   lê a pasta de saves, grava o que mudou e publica o feed
  ia.py            único ponto que fala com o Gemini
  auxiliar.py      parecer do auxiliar sobre as propostas
  feed.py          posts do feed
  conversas.py     conversas com o auxiliar e os jogadores
  api.py           API local (FastAPI)
web/               telas (React, Vite e Tailwind)
tests/
Vestiario.bat      abre o Vestiário com dois cliques
```

## Próximos passos

- Promessas com memória nas conversas e coletiva de imprensa depois de cada jogo.
- Grandes transferências do mundo no feed.
- Títulos lidos do histórico do próprio jogo e o overall (CGJ) dos jogadores.

## Créditos

A descriptografia dos saves é um port do [pesXdecrypter](https://github.com/the4chancup/pesXdecrypter), que é de domínio público.
