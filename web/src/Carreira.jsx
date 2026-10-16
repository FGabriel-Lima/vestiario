import { useEffect, useRef, useState } from "react";
import { api, dataBR } from "./api.js";
import Escudo from "./Escudo.jsx";
import Rosto from "./Rosto.jsx";

// As dez seções em quatro grupos: o clube por dentro, os jogos, o que se fala dele e a história
const GRUPOS = [
  { nome: "Clube", icone: "shield", abas: ["Visão geral", "Elenco", "Transferências"] },
  { nome: "Jogos", icone: "sports_soccer", abas: ["Partidas", "Campeonatos", "Adversários"] },
  { nome: "Bastidores", icone: "forum", abas: ["Feed", "Conversas"] },
  { nome: "História", icone: "emoji_events", abas: ["Lendas", "Pelo mundo"] },
];
const ABAS = GRUPOS.flatMap((g) => g.abas);
const SOBRE = {
  "Visão geral": "A campanha da temporada, o caixa e os próximos jogos.",
  Elenco: "Números, valor e contrato de cada jogador. O balão chama o jogador pra conversa.",
  Transferências: "Propostas recebidas e quem chegou e saiu em cada janela.",
  Partidas: "Os jogos da temporada. Um jogo disputado abre a súmula.",
  Campeonatos: "Classificação e chave de cada competição.",
  Adversários: "Retrospecto contra cada time, na carreira inteira.",
  Feed: "O que o clube, a imprensa e o mercado postaram a cada sincronização.",
  Conversas: "O auxiliar técnico e os jogadores do elenco.",
  Lendas: "Títulos, recordes e os maiores do clube.",
  "Pelo mundo": "Artilheiros, garçons e campeões do resto do mundo.",
};
// Abas que olham a carreira inteira e não usam o seletor de temporada
// (Campeonatos tem o próprio seletor de edição, porque temporada de liga europeia atravessa o ano)
const DA_CARREIRA = new Set(["Feed", "Conversas", "Campeonatos", "Transferências", "Adversários", "Lendas"]);

const GRAMADO = "#0b1a10"; // --color-pitch-950
const canais = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
const clarear = (hex, t) => "#" + canais(hex).map((c) => Math.round(c + (255 - c) * t).toString(16).padStart(2, "0")).join("");

function luminancia(hex) {
  const [r, g, b] = canais(hex).map((c) => c / 255).map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contraste(a, b) {
  const [claro, escuro] = [luminancia(a), luminancia(b)].sort((x, y) => y - x);
  return (claro + 0.05) / (escuro + 0.05);
}

// Cor do clube para texto e linhas sobre o gramado. Cor viva e escura (o verde do Palmeiras) é clareada;
// preto e cinza escuro (o do Ceará) cedem a vez para a próxima cor do clube.
function destaque(cores) {
  for (const c of cores) {
    const viva = Math.max(...canais(c)) - Math.min(...canais(c)) > 40;
    for (let t = 0; t <= (viva ? 0.6 : 0); t += 0.1) {
      if (contraste(clarear(c, t), GRAMADO) >= 3) return clarear(c, t);
    }
  }
}

// Cores do uniforme 1 e 2 (vindas do patch) viram as variáveis que o CSS usa; sem cores, fica o padrão do vestiário.
function estiloDoClube(cores = []) {
  if (!cores.length) return undefined;
  const [c1, c2 = c1, c3 = c2] = cores;
  const d = destaque(cores);
  return {
    "--time-1": c1,
    "--time-2": c2,
    "--time-3": c3,
    "--color-camisa": c1,
    "--color-numero": [c2, "#ffffff", "#1c2620"].find((c) => contraste(c, c1) >= 3) ?? "#ffffff",
    ...(d && { "--color-destaque": d }),
  };
}

export default function Carreira({ id, onVoltar }) {
  const [carreira, setCarreira] = useState(null);
  const [ano, setAno] = useState(null);
  const [aba, setAba] = useState(ABAS[0]);
  const [contato, setContato] = useState(null);
  const [ficha, setFicha] = useState(null);
  const [contatos, setContatos] = useState([]);
  useEffect(() => {
    let vivo = true; // a resposta de uma troca anterior não sobrescreve a mais nova
    api
      .contatos(id)
      .then((l) => vivo && setContatos(l))
      .catch(() => vivo && setContatos([]));
    return () => {
      vivo = false;
    };
  }, [id, aba, contato]);
  // a conversa aberta já foi lida, mesmo que a lista tenha vindo antes de o servidor marcar
  const naoLidas = contatos.reduce((n, c) => n + (aba === "Conversas" && c.contato === contato ? 0 : c.nao_lidas ?? 0), 0);
  const contador = (a) =>
    a === "Conversas" &&
    naoLidas > 0 && (
      <span className="ml-2 rounded-full bg-destaque px-1.5 align-middle font-sans text-xs font-bold not-italic text-pitch-950">
        {naoLidas}
        <span className="sr-only"> não lida{naoLidas > 1 ? "s" : ""}</span>
      </span>
    );
  const conversar = (c) => {
    setFicha(null);
    setContato(c);
    setAba("Conversas");
  };
  const [erro, setErro] = useState(null);

  useEffect(() => {
    api
      .carreira(id)
      .then((c) => {
        setCarreira(c);
        setAno(c.temporadas[0] ?? null);
      })
      .catch((e) => setErro(e.message));
  }, [id]);

  if (erro) {
    return (
      <>
        <button onClick={onVoltar} className="mb-6 text-muted hover:text-chalk">
          <span className="icone">arrow_back</span> Carreiras
        </button>
        <Erro mensagem={erro} />
      </>
    );
  }
  if (!carreira) return <p className="text-muted">Abrindo o vestiário…</p>;

  const grupo = GRUPOS.find((g) => g.abas.includes(aba));
  const usaAno = !DA_CARREIRA.has(aba) && ano !== null;
  // a aba aberta leva o rótulo de fita crepe, como o nome no armário; as outras ficam a giz
  const item = (a, extra = "") => (
    <button
      key={a}
      onClick={() => setAba(a)}
      aria-current={a === aba ? "page" : undefined}
      className={`whitespace-nowrap ${extra} ${
        a === aba ? "fita text-base" : "px-3 py-1 font-kit text-lg font-semibold uppercase tracking-wide text-muted hover:text-chalk"
      }`}
    >
      {a}
      {contador(a)}
    </button>
  );

  return (
    <div style={estiloDoClube(carreira.cores)} className="pb-24 lg:grid lg:grid-cols-[14rem_minmax(0,1fr)] lg:gap-12 lg:pb-0">
      <aside className="lg:sticky lg:top-10 lg:-ml-2 lg:max-h-[calc(100vh-5rem)] lg:self-start lg:overflow-y-auto lg:overscroll-contain lg:pl-2 lg:pr-2 lg:[scrollbar-width:thin]">
        <button onClick={onVoltar} className="mb-5 hidden text-sm text-muted hover:text-chalk lg:block">
          <span className="icone">arrow_back</span> Carreiras
        </button>
        {carreira.cores?.length > 0 && <div aria-hidden="true" className="cachecol mb-6 hidden lg:block" />}
        <div className="flex items-center gap-3 lg:flex-col lg:items-start lg:gap-3">
          <button onClick={onVoltar} aria-label="Voltar às carreiras" className="-ml-2 grid size-9 shrink-0 place-items-center rounded-full text-muted hover:bg-pitch-800 hover:text-chalk lg:hidden">
            <span aria-hidden="true" className="icone text-2xl">arrow_back</span>
          </button>
          <Escudo id={carreira.escudo} nome={carreira.clube_nome} className="size-14 shrink-0 drop-shadow-lg lg:size-20" />
          <div className="min-w-0">
            <p className="font-kit text-3xl font-extrabold uppercase leading-none tracking-tight lg:text-4xl">{carreira.clube_nome}</p>
            <p className="mt-1 font-kit text-sm uppercase tracking-[0.15em] text-muted">No jogo: {dataBR(carreira.data_jogo)}</p>
          </div>
        </div>
        <nav aria-label="Seções da carreira" className="mt-8 hidden space-y-6 lg:block">
          {GRUPOS.map((g) => (
            <div key={g.nome}>
              <p className="mb-1.5 flex items-center gap-2 font-kit text-xs uppercase tracking-[0.25em] text-muted/70">
                <span aria-hidden="true" className="icone text-base">{g.icone}</span>
                {g.nome}
              </p>
              <ul className="space-y-1">
                {g.abas.map((a) => (
                  <li key={a}>{item(a, "-ml-0.5 text-left")}</li>
                ))}
              </ul>
            </div>
          ))}
        </nav>
      </aside>

      <div className="min-w-0">
        {/* no celular as abas do grupo dividem a largura; o rótulo de fita crepe não caberia em três */}
        <nav
          aria-label={`Seções de ${grupo.nome}`}
          className="mt-5 grid border-b border-pitch-800 lg:hidden"
          style={{ gridTemplateColumns: `repeat(${grupo.abas.length}, minmax(0, 1fr))` }}
        >
          {grupo.abas.map((a) => (
            <button
              key={a}
              onClick={() => setAba(a)}
              aria-current={a === aba ? "page" : undefined}
              className={`-mb-px truncate border-b-2 px-1 pb-2 pt-1 font-kit text-base font-semibold uppercase ${
                a === aba ? "border-destaque text-chalk" : "border-transparent text-muted"
              }`}
            >
              {a}
              {contador(a)}
            </button>
          ))}
        </nav>
        <header className="mb-8 mt-6 flex flex-wrap items-end justify-between gap-x-4 gap-y-3 border-b border-pitch-800 pb-5 lg:mt-12">
          <div>
            <h1 className="font-kit text-4xl font-extrabold uppercase leading-none sm:text-5xl">{aba}</h1>
            <p className="mt-2 text-sm text-muted">{SOBRE[aba]}</p>
          </div>
          {usaAno && (
            <select
              aria-label="Temporada"
              value={ano}
              onChange={(e) => setAno(Number(e.target.value))}
              className="rounded-md border border-pitch-700 bg-pitch-800 px-3 py-2 font-kit text-lg uppercase"
            >
              {carreira.temporadas.map((t) => (
                <option key={t} value={t}>
                  Temporada {t}
                </option>
              ))}
            </select>
          )}
        </header>

        <div>
          {ano === null && !DA_CARREIRA.has(aba) ? (
            <p className="text-muted">Nenhuma partida do clube registrada ainda. Jogue uma partida, salve e sincronize.</p>
          ) : (
            <>
              {aba === "Visão geral" && (
                <>
                  <Atencao id={id} onFicha={setFicha} onConversar={conversar} onAba={setAba} />
                  <VisaoGeral id={id} ano={ano} clube={carreira.clube_idx} carreira={carreira} dataJogo={carreira.data_jogo} />
                </>
              )}
              {aba === "Elenco" && <Elenco id={id} ano={ano} dataJogo={carreira.data_jogo} onConversar={conversar} onFicha={setFicha} />}
              {aba === "Partidas" && <Partidas id={id} ano={ano} clube={carreira.clube_idx} />}
              {aba === "Feed" && <Feed id={id} />}
              {aba === "Conversas" && <Conversas id={id} contato={contato} onContato={setContato} onFicha={setFicha} />}
              {aba === "Campeonatos" && <Campeonatos id={id} clube={carreira.clube_idx} dataJogo={carreira.data_jogo} />}
              {aba === "Transferências" && <Transferencias id={id} onConversar={conversar} />}
              {aba === "Adversários" && <Adversarios id={id} clube={carreira.clube_idx} />}
              {aba === "Lendas" && <Lendas id={id} clube={carreira.clube_idx} />}
              {aba === "Pelo mundo" && <PeloMundo id={id} ano={ano} clube={carreira.clube_idx} />}
            </>
          )}
        </div>
      </div>

      {ficha !== null && (
        <Ficha key={ficha} id={id} pid={ficha} clube={carreira.clube_nome} onFechar={() => setFicha(null)} onConversar={conversar} />
      )}

      {/* celular: os quatro grupos numa barra embaixo, ao alcance do polegar; as abas do grupo ficam no topo */}
      <nav
        aria-label="Grupos de seções"
        className="fixed inset-x-0 bottom-0 z-20 grid grid-cols-4 border-t border-pitch-700 bg-pitch-950/95 pb-[env(safe-area-inset-bottom)] backdrop-blur lg:hidden"
      >
        {/* no celular o cachecol vira a borda da barra, nas cores do uniforme */}
        {carreira.cores?.length > 0 && (
          <span
            aria-hidden="true"
            className="absolute inset-x-0 -top-px h-[3px]"
            style={{ background: "repeating-linear-gradient(90deg, var(--time-1) 0 3rem, var(--time-2) 3rem 4rem)" }}
          />
        )}
        {GRUPOS.map((g) => (
          <button
            key={g.nome}
            onClick={() => g !== grupo && setAba(g.abas[0])}
            aria-current={g === grupo ? "true" : undefined}
            aria-label={g.nome === "Bastidores" && naoLidas > 0 ? `${g.nome}, ${naoLidas} mensage${naoLidas > 1 ? "ns" : "m"} não lida${naoLidas > 1 ? "s" : ""}` : undefined}
            className={`relative flex flex-col items-center gap-0.5 py-2 font-kit text-sm font-semibold uppercase tracking-wide ${
              g === grupo ? "text-destaque" : "text-muted"
            }`}
          >
            <span aria-hidden="true" className="icone text-2xl">{g.icone}</span>
            {g.nome === "Bastidores" && naoLidas > 0 && (
              <span aria-hidden="true" className="absolute top-1.5 ml-7 size-2.5 rounded-full bg-destaque ring-2 ring-pitch-950" />
            )}
            {g.nome}
          </button>
        ))}
      </nav>
    </div>
  );
}

function useDados(buscar, deps) {
  const [estado, setEstado] = useState({ dados: null, erro: null });
  useEffect(() => {
    let valido = true;
    setEstado({ dados: null, erro: null });
    buscar()
      .then((dados) => valido && setEstado({ dados, erro: null }))
      .catch((e) => valido && setEstado({ dados: null, erro: e.message }));
    return () => {
      valido = false;
    };
  }, deps); // eslint-disable-line react-hooks/exhaustive-deps
  return estado;
}

function Erro({ mensagem }) {
  return <p className="rounded-md border-l-4 border-cartao bg-pitch-900 p-4">{mensagem}</p>;
}

// Placar e resultado do ponto de vista do clube do usuário. Decisão nos pênaltis conta como empate.
const placar = (p, clube) =>
  p.mandante_idx === clube ? [p.gols_mandante, p.gols_visitante] : [p.gols_visitante, p.gols_mandante];

function resultado(p, clube) {
  const [pro, contra] = placar(p, clube);
  return pro > contra ? "V" : pro < contra ? "D" : "E";
}

const adversario = (p, clube) => (p.mandante_idx === clube ? p.visitante : p.mandante);
const plural = (n, um, varios) => `${n} ${n === 1 ? um : varios}`;

const COR_RESULTADO = { V: "bg-neon text-pitch-950", E: "bg-muted text-pitch-950", D: "bg-cartao text-pitch-950" };
const BORDA_RESULTADO = { V: "border-neon", E: "border-muted", D: "border-cartao" };

function VisaoGeral({ id, ano, clube, carreira, dataJogo }) {
  const { dados: r, erro } = useDados(() => api.resumo(id, ano), [id, ano]);
  if (erro) return <Erro mensagem={erro} />;
  if (!r) return null;
  if (r.jogos === 0) return <TemporadaPorComecar id={id} ano={ano} clube={clube} carreira={carreira} dataJogo={dataJogo} />;
  const aproveitamento = Math.round(((3 * r.vitorias + r.empates) / (3 * r.jogos)) * 100);
  const campanha = [
    ["vitorias", "Vitórias", r.vitorias],
    ["empates", "Empates", r.empates],
    ["derrotas", "Derrotas", r.derrotas],
  ];
  return (
    <>
      <section className="mb-10 grid grid-cols-1 gap-8 md:grid-cols-[auto_1fr] md:items-end">
        <div>
          <p className="font-kit text-sm uppercase tracking-[0.2em] text-muted">Aproveitamento</p>
          <p className="font-kit text-8xl font-extrabold leading-none text-gold">
            {aproveitamento}
            <span className="text-5xl">%</span>
          </p>
          <p className="mt-1 text-muted">dos pontos em {r.jogos} jogos</p>
        </div>
        <dl className="grid grid-cols-3 gap-px overflow-hidden rounded-md bg-pitch-700 sm:grid-cols-6">
          {campanha.map(([k, rotulo, valor]) => (
            <div key={k} className="bg-pitch-900 px-4 py-3">
              <dt className="text-xs uppercase text-muted">{rotulo}</dt>
              <dd className="font-kit text-4xl font-bold">{valor}</dd>
            </div>
          ))}
          <div className="bg-pitch-900 px-4 py-3">
            <dt className="text-xs uppercase text-muted">Gols pró</dt>
            <dd className="font-kit text-4xl font-bold">{r.gols_pro}</dd>
          </div>
          <div className="bg-pitch-900 px-4 py-3">
            <dt className="text-xs uppercase text-muted">Gols contra</dt>
            <dd className="font-kit text-4xl font-bold">{r.gols_contra}</dd>
          </div>
          <div className="bg-pitch-900 px-4 py-3">
            <dt className="text-xs uppercase text-muted">Saldo</dt>
            <dd className="font-kit text-4xl font-bold">{r.gols_pro - r.gols_contra > 0 ? "+" : ""}{r.gols_pro - r.gols_contra}</dd>
          </div>
        </dl>
      </section>

      <Caixa c={carreira} dataJogo={dataJogo} />

      <div className="mb-3 flex flex-wrap items-center gap-4">
        <h2 className="font-kit text-2xl font-semibold uppercase">Últimos resultados</h2>
        <ol aria-label="Sequência, do mais recente ao mais antigo" className="flex gap-1">
          {r.ultimas.map((p) => {
            const res = resultado(p, clube);
            return (
              <li key={p.id} className={`grid size-7 place-items-center rounded-sm font-kit font-bold ${COR_RESULTADO[res]}`}>
                {res}
              </li>
            );
          })}
        </ol>
      </div>
      <ListaPartidas id={id} partidas={r.ultimas} clube={clube} />
      <ProximosJogos id={id} ano={ano} clube={clube} />
    </>
  );
}

// O caixa como nas telas de orçamento do PES: os dois orçamentos, a folha por semana e o que entrou na temporada.
// Bilheteria e prêmios ficam de fora porque o save não guarda esses totais.
const RECEITAS = [["tv", "TV"], ["patrocinio", "Patrocínio"], ["socios", "Sócios"], ["produtos", "Produtos"]];

function Caixa({ c, dataJogo }) {
  const blocos = [
    ["Orçamento de transferências", c.orcamento, ""],
    ["Orçamento de salário", c.orcamento_salario, "por semana"],
    ["Folha salarial", c.folha_semanal, "por semana"],
  ].filter(([, v]) => v != null);
  if (blocos.length === 0) return null;
  return (
    <section aria-labelledby="caixa" className="mb-10">
      <h2 id="caixa" className="mb-3 flex flex-wrap items-baseline gap-x-3 font-kit text-2xl font-semibold uppercase">
        Caixa
        <span className="font-sans text-sm font-normal normal-case text-muted">em {dataBR(dataJogo)}</span>
      </h2>
      <dl className="grid grid-cols-1 gap-px overflow-hidden rounded-md bg-pitch-700 sm:grid-cols-3">
        {blocos.map(([rotulo, valor, unidade]) => (
          <div key={rotulo} className="bg-pitch-900 px-4 py-3">
            <dt className="text-xs uppercase text-muted">{rotulo}</dt>
            <dd className="flex items-baseline gap-2">
              <Dinheiro valor={valor} className="font-kit text-3xl font-bold text-gold" />
              {unidade && <span className="text-sm text-muted">{unidade}</span>}
            </dd>
          </div>
        ))}
      </dl>
      {c.receitas && (
        <div className="mt-3 text-sm">
          <p className="font-kit uppercase tracking-wide text-muted">Receitas da temporada</p>
          <ul className="grid grid-cols-2 gap-x-4 gap-y-1 sm:flex sm:flex-wrap sm:gap-x-6">
            {RECEITAS.filter(([k]) => c.receitas[k] != null).map(([k, rotulo]) => (
              <li key={k}>
                {rotulo} <Dinheiro valor={c.receitas[k]} className="font-kit text-lg font-semibold" />
              </li>
            ))}
          </ul>
          <p className="mt-1 text-xs text-muted">Sem bilheteria e prêmios: o save não guarda esses totais.</p>
        </div>
      )}
    </section>
  );
}

function ProximosJogos({ id, ano, clube }) {
  const { dados: ps } = useDados(() => api.partidas(id, ano), [id, ano]);
  const proximas = (ps ?? []).filter((p) => !p.disputada).slice(0, 3);
  if (proximas.length === 0) return null;
  return (
    <>
      <h2 className="mb-3 mt-10 font-kit text-2xl font-semibold uppercase">Próximos jogos</h2>
      <ListaPartidas id={id} partidas={proximas} clube={clube} />
    </>
  );
}

// Códigos de posição do Player.bin, com os nomes da versão em português do PES
const POSICOES = ["GO", "ZC", "LE", "LD", "VOL", "MLG", "MLE", "MLD", "MAT", "PTE", "PTD", "SA", "CA"];
// Cor por setor, como nas telas do PES: goleiro, defesa, meio e ataque
const setor = (c) => (c === 0 ? "text-pos-gol" : c <= 3 ? "text-pos-def" : c <= 8 ? "text-pos-meio" : "text-pos-ata");

function Posicao({ codigo, className = "" }) {
  if (codigo == null || !POSICOES[codigo]) return null;
  return (
    <span className={`inline-block w-10 rounded-sm bg-pitch-800 py-0.5 text-center font-kit text-sm font-bold ${setor(codigo)} ${className}`}>
      {POSICOES[codigo]}
    </span>
  );
}

// Antes do primeiro jogo, aproveitamento de 0% pareceria campanha ruim: mostra o que vem pela frente
function TemporadaPorComecar({ id, ano, clube, carreira, dataJogo }) {
  const { dados: ps } = useDados(() => api.partidas(id, ano), [id, ano]);
  const proximas = (ps ?? []).filter((p) => !p.disputada).slice(0, 5);
  return (
    <>
      <p className="mb-2 font-kit text-sm uppercase tracking-[0.2em] text-muted">Temporada {ano}</p>
      <p className="mb-8 font-kit text-5xl font-extrabold uppercase leading-none">Ainda não começou</p>
      <Caixa c={carreira} dataJogo={dataJogo} />
      {proximas.length > 0 && (
        <>
          <h2 className="mb-3 font-kit text-2xl font-semibold uppercase">Próximos jogos</h2>
          <ListaPartidas id={id} partidas={proximas} clube={clube} />
        </>
      )}
    </>
  );
}

// [chave, rótulo, valor para ordenar, ordem crescente?, só a partir do sm (no celular, idade e contrato vão para baixo do nome)]
const COLUNAS = [
  ["posicao", "Pos.", (l) => l.posicao ?? 99, true, true],
  ["nome", "Jogador", (l) => l.nome, true],
  ["idade", "Idade", (l) => l.idade ?? 99, true, true],
  ["jogos", "Jogos", (l) => l.jogos],
  ["gols", "Gols", (l) => l.gols],
  ["assistencias", "Assist.", (l) => l.assistencias],
  ["minutos", "Min.", (l) => l.minutos ?? 0, false, true],
  ["nota", "Nota", (l) => l.nota ?? 0, false, true],
  ["valor", "Valor", (l) => l.valor ?? -1, false, true],
  ["salario", "Salário/sem.", (l) => l.contrato?.salario_semanal ?? -1, false, true],
  ["multa", "Multa", (l) => l.contrato?.multa ?? -1, false, true],
  ["fim", "Contrato até", (l) => l.contrato?.fim ?? "9999", true, true],
];

const CURTOS = { jogos: "J", gols: "G", assistencias: "A" };

const comparar = (x, y) => (typeof x === "string" ? x.localeCompare(y, "pt-BR") : x - y);

function Elenco({ id, ano, dataJogo, onConversar, onFicha }) {
  const { dados: linhas, erro } = useDados(() => api.elenco(id, ano), [id, ano]);
  const [ordem, setOrdem] = useState("jogos");
  if (erro) return <Erro mensagem={erro} />;
  if (!linhas) return null;
  const [, , valor, crescente] = COLUNAS.find(([k]) => k === ordem);
  const ordenadas = [...linhas].sort(
    (a, b) => (crescente ? comparar(valor(a), valor(b)) : comparar(valor(b), valor(a))) || a.nome.localeCompare(b.nome, "pt-BR"),
  );
  // contrato que acaba em até 6 meses da data do jogo: hora de renovar ou vender
  const limite = new Date(dataJogo);
  limite.setMonth(limite.getMonth() + 6);
  const vencendo = (c) => c && c.fim <= limite.toISOString().slice(0, 10);
  return (
    <table className="w-full text-left">
      <thead>
        <tr className="border-b border-pitch-700 font-kit text-base uppercase tracking-wide text-muted sm:text-lg">
          {COLUNAS.map(([k, rotulo, , cresc, contrato]) => (
            <th
              key={k}
              aria-sort={ordem === k ? (cresc ? "ascending" : "descending") : "none"}
              className={`py-2 font-semibold ${
                k === "nome" ? "" : k === "posicao" ? "hidden w-14 sm:table-cell" : k === "idade" ? "hidden w-16 text-right sm:table-cell" : contrato ? "hidden w-32 text-right sm:table-cell" : "w-9 text-right sm:w-20"
              }`}
            >
              <button onClick={() => setOrdem(k)} aria-label={rotulo} className={ordem === k ? "text-destaque" : "hover:text-chalk"}>
                {/* no celular as colunas de números são estreitas: J, G e A */}
                {CURTOS[k] ? (
                  <>
                    <span className="sm:hidden">{CURTOS[k]}</span>
                    <span className="hidden sm:inline">{rotulo}</span>
                  </>
                ) : (
                  rotulo
                )}
              </button>
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {ordenadas.map((l) => {
          const c = l.contrato;
          return (
            <tr key={l.player_id} className={`border-b border-pitch-800 ${l.no_elenco ? "" : "text-muted"}`}>
              <td className="hidden sm:table-cell">
                <Posicao codigo={l.posicao} />
              </td>
              <td className="py-2">
                <div className="flex items-center gap-3">
                  <Rosto id={l.player_id} className={`size-9 ${l.no_elenco ? "" : "opacity-60 grayscale"}`} />
                  <span className="min-w-0">
                    <span className="flex items-center gap-2">
                      <button onClick={() => onFicha(l.player_id)} className="text-left hover:text-destaque hover:underline">
                        {l.nome}
                      </button>
                      {!l.no_elenco && <span className="font-kit text-sm uppercase tracking-wide">saiu</span>}
                      {l.no_elenco && (
                        <button
                          onClick={() => onConversar(String(l.player_id))}
                          aria-label={`Chamar ${l.nome} pra conversa`}
                          title="Chamar pra conversa"
                          className="grid size-7 place-items-center rounded-full text-muted hover:bg-pitch-800 hover:text-destaque"
                        >
                          <span aria-hidden="true" className="icone text-lg">chat</span>
                        </button>
                      )}
                    </span>
                    <span className={`flex items-center gap-2 text-sm sm:hidden ${vencendo(c) ? "text-gold" : "text-muted"}`}>
                      <Posicao codigo={l.posicao} className="w-9 py-0 text-xs" />
                      {/* no celular só idade e mês/ano do fim do contrato; salário e multa ficam nas colunas do desktop */}
                      {[l.idade && `${l.idade} anos`, c && `${c.emprestimo ? "emprestado " : ""}até ${dataBR(c.fim).slice(3)}`]
                        .filter(Boolean)
                        .join(" · ")}
                    </span>
                  </span>
                </div>
              </td>
              <td className="hidden text-right font-kit text-xl sm:table-cell">{l.idade}</td>
              <td className="text-right font-kit text-xl">{l.jogos}</td>
              <td className="text-right font-kit text-xl">{l.gols}</td>
              <td className="text-right font-kit text-xl">{l.assistencias}</td>
              <td className="hidden text-right font-kit text-xl sm:table-cell">{l.minutos || ""}</td>
              <td className="hidden text-right font-kit text-xl sm:table-cell">{l.nota?.toFixed(1)}</td>
              <td className="hidden text-right font-kit text-xl text-gold sm:table-cell">{l.valor ? <Dinheiro valor={l.valor} /> : null}</td>
              <td className="hidden text-right font-kit text-xl sm:table-cell">
                {/* o save não guarda salário de quem veio emprestado, só o fim do empréstimo */}
                {c && (c.emprestimo ? <span className="rounded-sm bg-pitch-700 px-1.5 text-xs uppercase text-muted">emprestado</span> : <Dinheiro valor={c.salario_semanal} />)}
              </td>
              <td className="hidden text-right font-kit text-xl sm:table-cell">
                {c && (c.emprestimo ? <span className="text-muted">–</span> : c.multa ? <Dinheiro valor={c.multa} /> : <span className="text-base text-muted">sem multa</span>)}
              </td>
              <td className={`hidden text-right font-kit text-xl sm:table-cell ${vencendo(c) ? "text-gold" : ""}`}>
                {c && (
                  <>
                    {vencendo(c) && (
                      <span className="icone mr-1 text-base" role="img" aria-label="vence em menos de 6 meses" title="Vence em menos de 6 meses">
                        hourglass_bottom
                      </span>
                    )}
                    {dataBR(c.fim)}
                  </>
                )}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function Partidas({ id, ano, clube }) {
  const { dados: ps, erro } = useDados(() => api.partidas(id, ano), [id, ano]);
  if (erro) return <Erro mensagem={erro} />;
  if (!ps) return null;
  const futuras = ps.filter((p) => !p.disputada);
  return (
    <>
      <h2 className="mb-3 font-kit text-2xl font-semibold uppercase">Disputadas</h2>
      <ListaPartidas id={id} partidas={ps.filter((p) => p.disputada)} clube={clube} />
      {futuras.length > 0 && (
        <>
          <h2 className="mb-3 mt-10 font-kit text-2xl font-semibold uppercase text-muted">Próximas</h2>
          <Proximas id={id} partidas={futuras} clube={clube} />
        </>
      )}
    </>
  );
}

// Jogos que ainda vão acontecer: os próximos à vista, o resto da tabela atrás de um botão.
function Proximas({ id, partidas, clube, mostrar = 5 }) {
  const [todas, setTodas] = useState(false);
  return (
    <>
      <ListaPartidas id={id} partidas={todas ? partidas : partidas.slice(0, mostrar)} clube={clube} />
      {partidas.length > mostrar && (
        <button onClick={() => setTodas(!todas)} className="mt-3 flex items-center gap-1 text-sm font-semibold text-destaque hover:underline">
          <span aria-hidden="true" className="icone">{todas ? "expand_less" : "expand_more"}</span>
          {todas ? "Mostrar só os próximos" : `Mostrar os ${partidas.length} jogos`}
        </button>
      )}
    </>
  );
}

// Partida disputada abre a súmula; jogo futuro é só uma linha.
function ListaPartidas({ id, partidas, clube }) {
  const [aberta, setAberta] = useState(null);
  if (partidas.length === 0) return <p className="text-muted">Nenhuma partida nesta temporada.</p>;
  return (
    <>
      <ul className="divide-y divide-pitch-800">
        {partidas.map((p) => {
          const Linha = p.disputada ? "button" : "div";
          return (
            <li key={p.id}>
              <Linha
                {...(p.disputada && { onClick: () => setAberta(p.id), "aria-haspopup": "dialog" })}
                className={`grid w-full grid-cols-[1fr_auto_1fr] items-center gap-x-3 gap-y-1 border-l-4 py-2.5 pl-3 text-left sm:grid-cols-[6rem_1fr_auto_1fr] ${
                  p.disputada
                    ? `${clube === p.mandante_idx || clube === p.visitante_idx ? BORDA_RESULTADO[resultado(p, clube)] : "border-pitch-700"} hover:bg-pitch-900`
                    : "border-transparent"
                }`}
              >
                {/* no celular a data fica numa linha própria, para os nomes dos times caberem */}
                <span className="col-span-3 text-xs text-muted sm:col-span-1 sm:text-sm">{dataBR(p.data)}</span>
                <span className={`flex min-w-0 items-center justify-end gap-2 ${p.mandante_idx === clube ? "font-semibold" : "text-muted"}`}>
                  <span className="truncate">{p.mandante}</span>
                  <Escudo id={p.mandante_escudo} nome={p.mandante} />
                </span>
                <span className="min-w-16 rounded-sm bg-pitch-800 px-2 text-center font-kit text-2xl font-bold">
                  {p.disputada ? `${p.gols_mandante}–${p.gols_visitante}` : "×"}
                  {p.penaltis_mandante + p.penaltis_visitante > 0 && (
                    <span className="block text-xs font-normal text-muted">
                      pên. {p.penaltis_mandante}–{p.penaltis_visitante}
                    </span>
                  )}
                </span>
                <span className={`flex min-w-0 items-center gap-2 ${p.visitante_idx === clube ? "font-semibold" : "text-muted"}`}>
                  <Escudo id={p.visitante_escudo} nome={p.visitante} />
                  <span className="truncate">{p.visitante}</span>
                </span>
              </Linha>
            </li>
          );
        })}
      </ul>
      {aberta !== null && <Sumula id={id} pid={aberta} onFechar={() => setAberta(null)} />}
    </>
  );
}

// Assinatura desta parte: a súmula do jogo, uma folha de papel presa com fita crepe e o placar escrito a pincel.
// <dialog> nativo: prende o foco, fecha no Esc e devolve o foco à linha que a abriu.
function Sumula({ id, pid, onFechar }) {
  const ref = useRef(null);
  const { dados: p, erro } = useDados(() => api.partida(id, pid), [id, pid]);
  useEffect(() => ref.current.showModal(), []);
  const fechar = () => ref.current.close();
  return (
    <dialog
      ref={ref}
      onClose={onFechar}
      onClick={(e) => e.target === ref.current && fechar()}
      aria-label="Súmula da partida"
      className="sumula"
    >
      <span aria-hidden="true" className="fita absolute -top-4 left-1/2 z-10 -translate-x-1/2 text-xl">
        Súmula
      </span>
      <div className="max-h-[calc(100dvh-4rem)] overflow-y-auto px-5 pb-7 pt-9 sm:px-9">
        <div className="mb-4 flex items-center justify-between font-kit text-lg font-semibold uppercase tracking-wide text-pincel/70">
          <span>{p && dataBR(p.data)}</span>
          <button onClick={fechar} aria-label="Fechar a súmula" className="-mr-2 rounded-sm p-1 hover:bg-pincel/10">
            <span className="icone">close</span>
          </button>
        </div>
        {erro && <p>{erro}</p>}
        {p && <Folha p={p} />}
      </div>
    </dialog>
  );
}

function Folha({ p }) {
  const lados = [
    [p.mandante, p.mandante_escudo],
    [p.visitante, p.visitante_escudo],
  ];
  return (
    <>
      <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3 sm:gap-6">
        {lados.map(([nome, escudo], lado) => (
          <div key={lado} className={`flex flex-col items-center gap-2 text-center ${lado ? "order-3" : ""}`}>
            <Escudo id={escudo} nome={nome} className="size-12 sm:size-16" />
            <span className="font-kit text-lg font-bold uppercase leading-tight sm:text-2xl">{nome}</span>
          </div>
        ))}
        <div className="order-2 text-center font-pincel">
          <p className="text-5xl leading-none sm:text-7xl">
            {p.gols_mandante}
            <span className="mx-2 text-3xl text-pincel/60 sm:text-4xl">×</span>
            {p.gols_visitante}
          </p>
          {p.penaltis_mandante + p.penaltis_visitante > 0 && (
            <p className="mt-2 text-lg">
              pên. {p.penaltis_mandante} × {p.penaltis_visitante}
            </p>
          )}
        </div>
      </div>

      <div className="mt-7 border-t-2 border-dashed border-pincel/30 pt-5">
        {p.escalacao.length === 0 ? (
          <p className="text-center">O save não guardou a escalação deste jogo.</p>
        ) : (
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
            {lados.map(([nome], lado) => (
              <section key={lado} aria-label={`Escalação: ${nome}`}>
                <ul>
                  {p.escalacao
                    .filter((j) => j.lado === lado)
                    .map((j) => (
                      <li key={j.player_id} className="flex min-h-10 items-center gap-2.5 border-b border-pincel/15">
                        <Rosto id={j.player_id} className="size-8 bg-pincel/10! ring-pincel/20!" />
                        <span className="min-w-0 flex-1 truncate">{j.nome}</span>
                        {j.gols > 0 && (
                          <span role="img" aria-label={plural(j.gols, "gol", "gols")} className="flex">
                            {Array.from({ length: j.gols }, (_, k) => (
                              <span key={k} className="icone text-lg">
                                sports_soccer
                              </span>
                            ))}
                          </span>
                        )}
                        {j.assistencias > 0 && (
                          <span className="font-kit text-base font-semibold uppercase">{j.assistencias} assist.</span>
                        )}
                        {j.minutos > 0 && j.minutos < 90 && (
                          <span title="minutos jogados" className="font-kit text-sm text-pincel/60">{j.minutos}'</span>
                        )}
                        {j.nota != null && (
                          <span title="nota do PES" className="w-8 rounded-sm bg-pincel/10 text-center font-kit text-base font-bold">
                            {j.nota.toFixed(1)}
                          </span>
                        )}
                      </li>
                    ))}
                </ul>
              </section>
            ))}
          </div>
        )}
      </div>
    </>
  );
}

function Campeonatos({ id, clube, dataJogo }) {
  const { dados: edicoes, erro } = useDados(() => api.campeonatos(id), [id]);
  const [chave, setChave] = useState(null);
  if (erro) return <Erro mensagem={erro} />;
  if (!edicoes) return null;
  if (edicoes.length === 0) {
    return <p className="max-w-xl text-muted">Nenhuma competição registrada ainda. Salve a Master League no PES e sincronize.</p>;
  }
  const atual = chave ?? edicoes[0].chave;
  const grupos = [
    ["Seu clube", edicoes.filter((e) => e.do_clube)],
    ["Outras competições", edicoes.filter((e) => !e.do_clube)],
  ];
  return (
    <>
      <label className="mb-8 flex max-w-md flex-col gap-1">
        <span className="font-kit text-sm uppercase tracking-[0.2em] text-muted">Competição</span>
        <select
          value={atual}
          onChange={(e) => setChave(e.target.value)}
          className="rounded-md border border-pitch-700 bg-pitch-800 px-3 py-2 font-kit text-lg uppercase"
        >
          {grupos.map(([rotulo, lista]) =>
            lista.length > 0 && (
              <optgroup key={rotulo} label={rotulo}>
                {lista.map((e) => (
                  <option key={e.chave} value={e.chave}>
                    {e.nome} {e.temporada}
                  </option>
                ))}
              </optgroup>
            ),
          )}
        </select>
      </label>
      <Edicao key={atual} id={id} chave={atual} clube={clube} dataJogo={dataJogo} />
    </>
  );
}

function Edicao({ id, chave, clube, dataJogo }) {
  const { dados: e, erro } = useDados(() => api.campeonato(id, chave), [id, chave]);
  if (erro) return <Erro mensagem={erro} />;
  if (!e) return null;
  const temTabela = e.fases.some((f) => f.tipo === "tabela");
  return (
    <>
      <header className="mb-8 flex flex-wrap items-end gap-x-5 gap-y-2">
        <h2 className="font-kit text-4xl font-extrabold uppercase leading-none sm:text-5xl">{e.nome}</h2>
        <span className="fita text-xl">{e.temporada}</span>
      </header>
      {e.campeao && <FaixaDeCampeao campeao={e.campeao} vice={e.vice} clube={clube} />}

      {e.fases.map((f, i) =>
        f.tipo === "jogos" && f.titulo !== "Fase preliminar" && e.chaveamento.length > 0 ? null : f.tipo === "tabela" ? (
          <section key={i} className="mb-12">
            <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
              <h3 className="font-kit text-2xl font-semibold uppercase">{f.titulo}</h3>
              <p className="text-sm text-muted">
                {f.rodadas_jogadas} de {plural(f.rodadas_total, "rodada", "rodadas")} jogadas
              </p>
            </div>
            {f.incompleta && (
              <p className="mb-4 flex items-start gap-2 rounded-md border-l-4 border-gold bg-pitch-900 px-4 py-3 text-sm">
                <span aria-hidden="true" className="icone text-gold">history</span>
                <span>
                  O Vestiário tem {f.rodadas_jogadas} das {f.rodadas_total} rodadas. As outras já tinham saído do save do PES
                  quando ele foi sincronizado, então esta tabela não é a final. Sincronize ao longo da temporada para guardar
                  todas as rodadas.
                </span>
              </p>
            )}
            <div className={f.grupos.length > 1 ? "grid grid-cols-1 gap-x-8 gap-y-10 lg:grid-cols-2" : ""}>
              {f.grupos.map((g, k) => (
                <Classificacao key={k} titulo={g.titulo} linhas={g.linhas} clube={clube} compacta={f.grupos.length > 1}
                  zona={zonaDaLinha(e.nome, f)} />
              ))}
            </div>
            <Legenda nome={e.nome} fase={f} />
          </section>
        ) : (
          <section key={i} className="mb-10">
            <h3 className="mb-3 flex items-baseline gap-3 font-kit text-2xl font-semibold uppercase">
              {f.titulo}
              <span className="text-base font-normal text-muted">{plural(f.partidas.length, "jogo", "jogos")}</span>
            </h3>
            <ListaPartidas id={id} partidas={f.partidas} clube={clube} />
          </section>
        ),
      )}

      {e.chaveamento.length > 0 && <Chaveamento id={id} colunas={e.chaveamento} clube={clube} dataJogo={dataJogo} />}

      {temTabela && e.partidas_clube.length > 0 && (
        <section>
          <h3 className="mb-3 font-kit text-2xl font-semibold uppercase">Seus jogos</h3>
          {e.partidas_clube.some((p) => p.disputada) && (
            <ListaPartidas id={id} partidas={e.partidas_clube.filter((p) => p.disputada)} clube={clube} />
          )}
          <div className="mt-2">
            <Proximas id={id} partidas={e.partidas_clube.filter((p) => !p.disputada)} clube={clube} mostrar={3} />
          </div>
        </section>
      )}
    </>
  );
}

// Assinatura do mata-mata: a chave riscada a giz. As linhas só aparecem quando os times da fase seguinte vêm mesmo
// do par (o banco confere); com dado faltando ou trocado no save, os cards ficam soltos para não ligar times errados.
// Como no ge e na UEFA, a chave começa nas oitavas; fases maiores ficam numa grade à parte. No desktop largo, as duas
// metades se espelham e se encontram na final, no meio.
const POR_TAMANHO = { 1: "Final", 2: "Semifinal", 4: "Quartas de final", 8: "Oitavas de final" };
const dias = (a, b) => (new Date(a) - new Date(b)) / 864e5;
// nos cards da chave falta largura: sai a sigla do clube, como nas artes de TV (CA Boca Juniors → Boca Juniors)
const curto = (nome) => nome?.replace(/^(CA|CD|CR|SE|SC|EC|FC|AA|Club)\s+|\s+(FC|EC|SC|AC)$/g, "") ?? nome;

function Chaveamento({ id, colunas, clube, dataJogo }) {
  const [aberta, setAberta] = useState(null);
  let inicio = colunas.length;
  while (inicio > 0 && colunas[inicio - 1].confrontos.length <= 8) inicio--;
  const anteriores = colunas.slice(0, inicio);
  const chave = colunas.slice(inicio);

  // copa em andamento (jogo há até 60 dias da data do save): as fases que faltam até a final entram como vagas
  const ultima = chave.at(-1);
  const n = ultima?.confrontos.length ?? 0;
  const ultimoJogo = chave.flatMap((c) => c.confrontos.flatMap((x) => x.jogos.map((j) => j.data))).sort().at(-1);
  if (ultima && ultima.titulo !== "Final" && n > 1 && (n & (n - 1)) === 0 && dias(dataJogo, ultimoJogo) <= 60) {
    chave[chave.length - 1] = { ...ultima, encaixa: true };
    for (let k = n / 2; k >= 1; k /= 2) chave.push({ titulo: POR_TAMANHO[k], confrontos: Array(k).fill(null), encaixa: k > 1 });
  }
  const espelha = chave.length > 1 && chave.at(-1).confrontos.length === 1 &&
    chave.slice(0, -1).every((c, i) => c.encaixa && c.confrontos.length === 2 * chave[i + 1].confrontos.length);
  const final = chave.at(-1);
  const lados = chave.slice(0, -1);
  const metade = (col, lado) => {
    const m = col.confrontos.length / 2;
    return { ...col, confrontos: lado ? col.confrontos.slice(m) : col.confrontos.slice(0, m) };
  };
  const props = { clube, onAbrir: setAberta };
  // fase com times leva mais largura que fase só com vagas "A definir"
  const trilhas = lados.map((c) => (c.confrontos.some(Boolean) ? "minmax(0, 1.4fr)" : "minmax(0, 1fr)"));

  return (
    <section className="mb-12" aria-label="Chaveamento">
      <h3 className="mb-4 font-kit text-2xl font-semibold uppercase">Mata-mata</h3>
      {chave.length > 0 && (
        <>
          {espelha && (
            <div
              className="chave chave-espelhada mb-4 hidden xl:grid"
              style={{ gridTemplateColumns: [...trilhas, "minmax(0, 1.1fr)", ...trilhas.toReversed()].join(" ") }}
            >
              {lados.map((col, i) => (
                <Coluna key={`e${i}`} col={metade(col, 0)} liga recebe={i > 0} compacto {...props} />
              ))}
              <div className="flex min-w-0 flex-col">
                <h4 className="mb-3 text-center font-kit text-lg font-semibold uppercase text-gold">{final.titulo}</h4>
                <div className="flex flex-1 flex-col justify-center">
                  <div className="relative">
                    <span aria-hidden="true" className="icone taca absolute bottom-full left-1/2 mb-2 -translate-x-1/2 text-gold" style={{ fontSize: "3.5rem" }}>emoji_events</span>
                    <Confronto c={final.confrontos[0]} final compacto {...props} />
                  </div>
                </div>
              </div>
              {lados.map((col, i) => (
                <Coluna key={`d${i}`} col={metade(col, 1)} liga recebe={i > 0} compacto espelho {...props} />
              )).reverse()}
            </div>
          )}
          <div className={`relative -mx-4 overflow-x-auto px-4 pb-4 sm:mx-0 sm:px-0 ${espelha ? "xl:hidden" : ""}`}>
            {/* colunas flexíveis: no desktop a chave inteira cabe; só rola de lado quando falta espaço */}
            <div className="chave grid auto-cols-[minmax(11rem,1fr)] grid-flow-col" style={{ maxWidth: `${chave.length * 18}rem` }}>
              {chave.map((col, i) => (
                <Coluna key={i} col={col} liga={col.encaixa} recebe={i > 0 && chave[i - 1].encaixa} compacto {...props} />
              ))}
            </div>
          </div>
        </>
      )}
      {anteriores.map((col, i) => (
        <div key={i} className="mt-8">
          <h4 className="mb-3 font-kit text-lg font-semibold uppercase text-muted">
            {col.titulo} <span className="font-normal">· {plural(col.confrontos.length, "confronto", "confrontos")}</span>
          </h4>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {col.confrontos.map((c, k) => (
              <Confronto key={k} c={c} {...props} />
            ))}
          </div>
        </div>
      ))}
      {aberta !== null && <Sumula id={id} pid={aberta} onFechar={() => setAberta(null)} />}
    </section>
  );
}

// Uma fase da chave. Com `liga`, os confrontos vão em pares com o colchete de giz até a fase seguinte (um confronto
// sozinho, como a semifinal de cada lado, sai num traço reto); `espelho` vira os traços para a esquerda.
function Coluna({ col, liga, recebe, espelho, compacto, clube, onAbrir }) {
  const pares = liga && col.confrontos.length > 1
    ? col.confrontos.filter((_, k) => k % 2 === 0).map((c, k) => [c, col.confrontos[2 * k + 1]])
    : col.confrontos.map((c) => [c]);
  const sozinho = liga && col.confrontos.length === 1;
  return (
    <div className={`flex min-w-0 flex-col ${espelho ? "espelho" : ""}`}>
      <h4 className={`mb-3 font-kit text-lg font-semibold uppercase text-muted ${espelho ? "text-right" : ""}`}>
        {col.titulo}
      </h4>
      <div className="flex flex-1 flex-col justify-around gap-4">
        {pares.map((par, k) => (
          <div key={k} className={`flex flex-1 flex-col justify-around gap-4 ${par.length === 2 ? "chave-par" : ""}`}>
            {par.map((c, j) => (
              <Confronto key={j} c={c} recebe={recebe} sai={sozinho} compacto={compacto} clube={clube} onAbrir={onAbrir} />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

function Confronto({ c, clube, recebe, sai, final, compacto, onAbrir }) {
  const ligacoes = `${recebe ? "chave-entrada" : ""} ${sai ? "chave-saida" : ""} ${final ? "chave-final" : ""}`;
  if (!c) {
    // vaga de uma fase que ainda não tem jogo marcado no save
    return (
      <div className={`relative rounded-md border border-dashed border-pitch-700 ${ligacoes}`}>
        <ul className="px-3 pt-2.5 text-sm text-muted/70">
          {[0, 1].map((k) => (
            <li key={k} className="flex items-center gap-2 py-0.5">
              <span className="size-5 shrink-0 rounded-full border border-dashed border-giz" />A definir
            </li>
          ))}
        </ul>
        <p className="mt-1.5 border-t border-dashed border-pitch-700 px-4 py-1.5 font-kit text-sm uppercase tracking-wide text-muted/60">
          {final ? "Final" : "Sem data"}
        </p>
      </div>
    );
  }
  const decidido = c.times.some((t) => t.vencedor);
  const nosso = c.times.some((t) => t.idx === clube);
  return (
    <div className={`relative rounded-md bg-pitch-900 ${nosso ? "ring-1 ring-destaque/70" : ""} ${final ? "ring-1 ring-gold/70" : ""} ${ligacoes}`}>
      <ul className={`px-3 pt-2.5 ${compacto ? "text-sm" : ""}`}>
        {c.times.map((t) => (
          <li
            key={t.idx}
            className={`flex items-center gap-2 py-0.5 ${decidido && !t.vencedor ? "text-muted" : ""} ${t.vencedor ? "font-semibold" : ""}`}
          >
            <Escudo id={t.escudo} nome={t.nome ?? "?"} className={`size-5 ${decidido && !t.vencedor ? "opacity-50" : ""}`} />
            <span title={t.nome} className={`min-w-0 flex-1 truncate ${t.idx === clube ? "text-destaque" : ""}`}>
              {compacto ? curto(t.nome) : t.nome}
            </span>
            {t.vencedor && <span className="sr-only">(passou)</span>}
            <span className={`font-kit text-xl font-bold ${t.vencedor && final ? "text-gold" : ""}`}>{t.gols ?? "–"}</span>
            {t.penaltis !== null && <span className="w-6 font-kit text-sm text-muted">({t.penaltis})</span>}
          </li>
        ))}
      </ul>
      <div className="mt-1.5 flex flex-wrap gap-x-1 border-t border-pitch-800 px-2 py-1.5">
        {c.jogos.map((j, k) => {
          const rotulo = c.jogos.length === 1 ? "Jogo único" : k === 0 ? "Ida" : "Volta";
          return j.disputada ? (
            <button
              key={j.id}
              onClick={() => onAbrir(j.id)}
              aria-haspopup="dialog"
              className="rounded-sm px-1.5 py-0.5 font-kit text-sm uppercase tracking-wide text-muted hover:bg-pitch-800 hover:text-chalk"
            >
              {rotulo} {j.placar.replace("-", "–")}
            </button>
          ) : (
            <span key={j.id} className="px-1.5 py-0.5 font-kit text-sm uppercase tracking-wide text-muted/70">
              {rotulo} {dataBR(j.data).slice(0, 5)}
            </span>
          );
        })}
      </div>
    </div>
  );
}

// Zonas da tabela, como no ge e na Premier League: a posição ganha a cor da vaga ou da queda. O save não diz quantas
// vagas o PES dá, então ligas seguem a regra da competição real (o Brasileirão foi conferido num save: 4 caem da
// Série A e 4 sobem da B). Na fase de grupos, quem passou sai do próprio mata-mata quando ele já está no banco.
const ZONAS = {
  avanca: ["Mata-mata", "#4d9fff"],
  lib: ["Libertadores", "#4d9fff"],
  pre: ["Pré-Libertadores", "#9cc9ff"],
  sula: ["Sul-Americana", "#3fcf8e"],
  ucl: ["Champions League", "#4d9fff"],
  uel: ["Europa League", "#f39c3d"],
  uecl: ["Conference League", "#3fcf8e"],
  acesso: ["Acesso", "#3fcf8e"],
  queda: ["Rebaixamento", "var(--color-cartao)"],
};
const EUROPA = [[1, 4, "ucl"], [5, 5, "uel"], [6, 6, "uecl"]];
const ZONAS_DA_LIGA = {
  "Brasileirão Série A": [[1, 4, "lib"], [5, 6, "pre"], [7, 12, "sula"], [17, 20, "queda"]],
  "Brasileirão Série B": [[1, 4, "acesso"], [17, 20, "queda"]],
  "Premier League": [...EUROPA, [18, 20, "queda"]],
  LaLiga: [...EUROPA, [18, 20, "queda"]],
  "Serie A TIM": [...EUROPA, [18, 20, "queda"]],
  "Ligue 1": [...EUROPA, [17, 18, "queda"]],
  Bundesliga: EUROPA, // sem 2ª divisão no patch: ninguém cai
};
const ZONAS_DO_GRUPO = {
  "Copa Libertadores": [[1, 2, "avanca"], [3, 3, "sula"]],
  "UEFA Champions League": [[1, 2, "avanca"], [3, 3, "uel"]],
};

function zonaDaLinha(nome, fase) {
  const regras = fase.grupos[0].titulo ? ZONAS_DO_GRUPO[nome] ?? [[1, 2, "avanca"]] : ZONAS_DA_LIGA[nome] ?? [];
  return (l) => {
    const pos = regras.find(([de, ate]) => l.posicao >= de && l.posicao <= ate)?.[2] ?? null;
    if (l.avancou === undefined) return pos;
    return l.avancou ? "avanca" : pos === "avanca" ? null : pos;
  };
}

function Legenda({ nome, fase }) {
  const zona = zonaDaLinha(nome, fase);
  const presentes = new Set(fase.grupos.flatMap((g) => g.linhas.map(zona)));
  const itens = Object.keys(ZONAS).filter((k) => presentes.has(k));
  const real = !fase.grupos[0].titulo && itens.length > 0;
  return (
    <div className="mt-4 space-y-2 text-xs text-muted">
      {itens.length > 0 && (
        <ul className="flex flex-wrap gap-x-5 gap-y-2 text-sm text-chalk">
          {itens.map((k) => (
            <li key={k} className="flex items-center gap-2">
              <span aria-hidden="true" className="h-3 w-3 rounded-sm" style={{ background: ZONAS[k][1] }} />
              {ZONAS[k][0]}
            </li>
          ))}
        </ul>
      )}
      <p>
        Ordem: pontos, vitórias, saldo de gols, gols pró e confronto direto. Empatados em tudo dividem a posição.
        {real && " Vagas e quedas pela regra da competição real; o PES pode distribuir diferente."}
        {fase.grupos.some((g) => g.linhas.some((l) => l.avancou !== undefined)) && " Mata-mata: quem está na chave."}
      </p>
    </div>
  );
}

// Colunas que somem no celular (e nas tabelas de grupo, que dividem a largura)
const DETALHE = "hidden sm:table-cell";
const FORMA = { V: "bg-neon", E: "bg-muted", D: "bg-cartao" };
const RESULTADO = { V: "vitória", E: "empate", D: "derrota" };

function Classificacao({ titulo, linhas, clube, compacta, zona }) {
  const detalhe = compacta ? "hidden" : DETALHE;
  const colunas = [
    ["J", "Jogos", ""],
    ["V", "Vitórias", detalhe],
    ["E", "Empates", detalhe],
    ["D", "Derrotas", detalhe],
    ["GP", "Gols pró", detalhe],
    ["GC", "Gols contra", detalhe],
    ["SG", "Saldo de gols", ""],
  ];
  return (
    <table className="w-full text-left">
      {titulo && <caption className="mb-2 text-left font-kit text-xl font-semibold uppercase text-muted">{titulo}</caption>}
      <thead>
        <tr className="border-b border-pitch-700 font-kit text-base uppercase tracking-wide text-muted">
          <th className="w-10 py-2 text-center font-semibold">
            <abbr title="Posição" className="no-underline">#</abbr>
          </th>
          <th className="py-2 pl-3 font-semibold">Time</th>
          <th className="w-12 text-right font-semibold">
            <abbr title="Pontos" className="no-underline">P</abbr>
          </th>
          {colunas.map(([sigla, nome, classe]) => (
            <th key={sigla} className={`w-10 text-right font-semibold ${classe}`}>
              <abbr title={nome} className="no-underline">{sigla}</abbr>
            </th>
          ))}
          <th className={`w-36 pl-6 text-left font-semibold ${detalhe}`}>Últimos 5</th>
        </tr>
      </thead>
      <tbody>
        {linhas.map((l, i) => {
          const nosso = l.idx === clube;
          const saldo = l.gols_pro - l.gols_contra;
          const z = zona(l);
          // linha de corte a giz onde muda a zona, como o técnico risca no quadro
          const corte = i > 0 && z !== zona(linhas[i - 1]);
          return (
            <tr
              key={l.idx}
              aria-current={nosso ? "true" : undefined}
              className={`border-b border-pitch-800 ${nosso ? "linha-do-clube" : ""} ${corte ? "corte" : ""}`}
            >
              <td className="py-2 text-center">
                <span
                  className={`inline-grid size-7 place-items-center rounded-sm font-kit text-lg leading-none ${z ? "font-bold text-pitch-950" : "text-muted"}`}
                  style={z ? { background: ZONAS[z][1] } : undefined}
                >
                  {l.posicao}
                </span>
                {z && <span className="sr-only">({ZONAS[z][0]})</span>}
              </td>
              <td className="py-2 pl-3">
                <span className="flex min-w-0 items-center gap-2">
                  <Escudo id={l.escudo} nome={l.nome ?? "?"} />
                  <span className={`truncate ${nosso ? "font-semibold text-destaque" : ""}`}>{l.nome}</span>
                </span>
              </td>
              <td className="text-right font-kit text-2xl font-bold">{l.pontos}</td>
              {[l.jogos, l.vitorias, l.empates, l.derrotas, l.gols_pro, l.gols_contra].map((v, k) => (
                <td key={k} className={`text-right font-kit text-lg ${colunas[k][2]}`}>
                  {v}
                </td>
              ))}
              <td className={`text-right font-kit text-lg ${saldo === 0 ? "text-muted" : ""}`}>{saldo > 0 ? `+${saldo}` : saldo}</td>
              <td className={`pl-6 ${detalhe}`}>
                <span className="flex gap-1">
                  {l.ultimos.map((u, k) => (
                    <span
                      key={k}
                      title={u.jogo}
                      aria-label={`${RESULTADO[u.r]}: ${u.jogo}`}
                      className={`grid size-5 place-items-center rounded-sm font-kit text-xs font-bold text-pitch-950 ${FORMA[u.r]}`}
                    >
                      {u.r}
                    </span>
                  ))}
                </span>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

// Feed: posts dos perfis que acompanham o clube. A arte de cada post é montada com os dados reais (placar, escudos,
// rostos, valores) na linguagem visual de cada perfil; a IA só escreveu a legenda.
const AVATAR = {
  tntsportsbr: ["TNT", "bg-[#d71920] text-white"],
  geglobo: ["ge", "bg-[#06aa48] text-white"],
  mercadodabola: ["MB", "bg-pitch-950 text-gold ring-1 ring-gold"],
};

function Feed({ id }) {
  const [versao, setVersao] = useState(0);
  const { dados: f, erro } = useDados(() => api.feed(id), [id, versao]);
  const [publicando, setPublicando] = useState(false);
  const [falha, setFalha] = useState(null);
  if (erro) return <Erro mensagem={erro} />;
  if (!f) return null;
  const publicar = () => {
    setPublicando(true);
    setFalha(null);
    api
      .atualizarFeed(id)
      .then(() => setVersao((v) => v + 1))
      .catch((e) => setFalha(e.message))
      .finally(() => setPublicando(false));
  };
  return (
    <div className="mx-auto max-w-lg">
      {!f.publicado && (
        <div aria-live="polite" className="mb-8 rounded-md border border-dashed border-pitch-700 p-4">
          {publicando ? (
            <p className="flex items-center gap-2 text-muted">
              <span aria-hidden="true" className="icone animate-spin text-gold motion-reduce:animate-none">progress_activity</span>
              Os perfis estão postando. Pode levar até meio minuto.
            </p>
          ) : (
            <button
              onClick={publicar}
              className="flex w-full items-center justify-center gap-2 rounded-md bg-gold px-4 py-2.5 font-kit text-lg font-bold uppercase tracking-wide text-pitch-950 hover:brightness-110"
            >
              <span aria-hidden="true" className="icone">refresh</span>
              Carregar os posts do save de {dataBR(f.atual)}
            </button>
          )}
          {falha && <p className="mt-2 text-sm text-cartao">{falha}</p>}
        </div>
      )}
      {f.coletiva && <Coletiva key={f.coletiva.jogo.data} id={id} coletiva={f.coletiva} onDada={() => setVersao((v) => v + 1)} />}
      {f.posts.length === 0 ? (
        <p className="text-muted">Nenhum post ainda. Carregue os posts do save mais recente.</p>
      ) : (
        <ol className="space-y-10">
          {f.posts.map((p) => (
            <li key={`${p.edicao}-${p.perfil}-${p.tipo}-${p.data}-${p.dados.player_id ?? ""}-${p.dados.mandante?.idx ?? ""}`}>
              <Post post={p} perfis={f.perfis} />
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

// Sala de imprensa: o repórter do ge pergunta sobre o último jogo e o que o treinador responde vira post do ge,
// com as falas copiadas como foram escritas.
function Coletiva({ id, coletiva, onDada }) {
  const { jogo, perguntas } = coletiva;
  const [respostas, setRespostas] = useState(() => (perguntas ?? []).map(() => ""));
  const [esperando, setEsperando] = useState(false);
  const [falha, setFalha] = useState(null);
  const chamar = (pedido) => {
    setEsperando(true);
    setFalha(null);
    pedido
      .then(onDada)
      .catch((e) => setFalha(e.message))
      .finally(() => setEsperando(false));
  };
  const placar = `${jogo.mandante.nome} ${jogo.mandante.gols} x ${jogo.visitante.gols} ${jogo.visitante.nome}`;
  return (
    <section aria-label="Coletiva pós-jogo" className="mb-10 overflow-hidden rounded-xl border border-pitch-700 bg-pitch-900">
      <header className="flex items-center gap-3 border-b border-pitch-800 px-4 py-3">
        <span className="grid size-10 shrink-0 place-items-center rounded-full bg-[#06aa48] text-white">
          <span aria-hidden="true" className="icone">mic</span>
        </span>
        <p className="min-w-0 leading-tight">
          <span className="block font-kit text-lg font-bold uppercase tracking-wide">Coletiva pós-jogo</span>
          <span className="block truncate text-sm text-muted">{placar} · {dataBR(jogo.data)}</span>
        </p>
      </header>
      {!perguntas ? (
        <div aria-live="polite" className="p-4">
          {esperando ? (
            <p className="flex items-center gap-2 text-muted">
              <span aria-hidden="true" className="icone animate-spin text-[#06aa48] motion-reduce:animate-none">progress_activity</span>
              O repórter do ge está preparando as perguntas.
            </p>
          ) : (
            <>
              <p className="mb-3 text-sm text-muted">O ge quer ouvir o técnico. O que você responder sai no perfil deles, do jeito que você escrever.</p>
              <button
                onClick={() => chamar(api.abrirColetiva(id))}
                className="flex w-full items-center justify-center gap-2 rounded-md bg-[#06aa48] px-4 py-2.5 font-kit text-lg font-bold uppercase tracking-wide text-white hover:brightness-110"
              >
                <span aria-hidden="true" className="icone">mic</span>
                Ir para a coletiva
              </button>
            </>
          )}
          {falha && <p className="mt-2 text-sm text-cartao">{falha}</p>}
        </div>
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            chamar(api.responderColetiva(id, respostas));
          }}
          className="space-y-5 p-4"
        >
          {perguntas.map((p, i) => (
            <div key={i}>
              <label htmlFor={`resposta-${i}`} className="mb-2 block border-l-4 border-[#06aa48] pl-3 font-semibold leading-snug">
                {p}
              </label>
              <textarea
                id={`resposta-${i}`}
                rows={2}
                value={respostas[i]}
                onChange={(e) => setRespostas(respostas.map((r, k) => (k === i ? e.target.value : r)))}
                placeholder="Sua resposta (em branco, você não comenta)"
                className="w-full resize-y rounded-md border border-pitch-700 bg-pitch-950 px-3 py-2 leading-relaxed placeholder:text-muted"
              />
            </div>
          ))}
          {falha && <p className="text-sm text-cartao">{falha}</p>}
          <button
            type="submit"
            disabled={esperando || !respostas.some((r) => r.trim())}
            className="flex w-full items-center justify-center gap-2 rounded-md bg-[#06aa48] px-4 py-2.5 font-kit text-lg font-bold uppercase tracking-wide text-white hover:brightness-110 disabled:opacity-50"
          >
            <span aria-hidden="true" className={`icone ${esperando ? "animate-spin motion-reduce:animate-none" : ""}`}>
              {esperando ? "progress_activity" : "send"}
            </span>
            {esperando ? "O ge está publicando" : "Encerrar a coletiva"}
          </button>
        </form>
      )}
    </section>
  );
}

function Post({ post, perfis }) {
  const perfil = perfis[post.perfil] ?? perfis.clube;
  const [sigla, cor] = AVATAR[post.perfil] ?? [];
  return (
    <article className="overflow-hidden rounded-xl border border-pitch-800 bg-pitch-900">
      <header className="flex items-center gap-3 px-4 py-3">
        {post.perfil === "clube" ? (
          <span className="grid size-10 place-items-center rounded-full bg-pitch-950 ring-2 ring-destaque">
            <Escudo id={perfil.escudo} nome={perfil.nome} className="size-7" />
          </span>
        ) : (
          <span aria-hidden="true" className={`grid size-10 place-items-center rounded-full font-kit text-sm font-extrabold ${cor}`}>
            {sigla}
          </span>
        )}
        <p className="min-w-0 leading-tight">
          <span className="flex items-center gap-1 font-semibold">
            {perfil.arroba}
            {post.perfil !== "mercadodabola" && (
              <span aria-label="conta verificada" className="icone text-base text-[#4aa3ff]">verified</span>
            )}
          </span>
          <span className="text-xs text-muted">{perfil.nome} · {dataBR(post.data)}</span>
        </p>
      </header>
      <ArteDoPost post={post} />
      <p className="px-4 py-3 text-sm leading-relaxed">
        <span className="mr-1.5 font-semibold">{perfil.arroba}</span>
        {post.legenda}
      </p>
      {post.tipo === "coletiva" && (
        <details className="border-t border-pitch-800 px-4 py-3 text-sm">
          <summary className="cursor-pointer font-semibold text-muted hover:text-chalk">Ler a entrevista completa</summary>
          <dl className="mt-3 space-y-3">
            {post.dados.entrevista.map((e, i) => (
              <div key={i}>
                <dt className="border-l-4 border-[#06aa48] pl-3 font-semibold">{e.pergunta}</dt>
                <dd className="mt-1 pl-4 leading-relaxed">{e.resposta}</dd>
              </div>
            ))}
          </dl>
        </details>
      )}
    </article>
  );
}

// Fundo e tipografia de cada perfil: o clube nas cores do uniforme; a TV em preto e vermelho; o portal em branco e
// verde; o mercado em preto e dourado.
const FUNDO = {
  clube: "bg-pitch-950 text-chalk",
  tntsportsbr: "bg-[#111] text-white",
  geglobo: "bg-[#f4f4f1] text-[#14181a]",
  mercadodabola: "bg-pitch-950 text-chalk",
};

function ArteDoPost({ post }) {
  const d = post.dados;
  const base = `relative flex aspect-square flex-col justify-between overflow-hidden p-6 ${FUNDO[post.perfil] ?? FUNDO.clube} ${
    post.perfil === "clube" ? "arte-do-clube" : ""
  }`;
  const selo = (texto, extra = "") => (
    <p className={`font-kit text-lg font-extrabold uppercase tracking-[0.15em] ${extra}`}>{texto}</p>
  );
  switch (post.tipo) {
    case "fim_de_jogo":
    case "goleada":
    case "proximo_jogo":
      return (
        <div className={base}>
          {post.perfil === "tntsportsbr" && <span aria-hidden="true" className="absolute inset-x-0 top-0 h-2 bg-[#d71920]" />}
          {selo(post.tipo === "proximo_jogo" ? "Próximo jogo" : post.tipo === "goleada" ? "Que goleada" : "Fim de jogo",
            post.perfil === "tntsportsbr" ? "text-[#ff4b55]" : "text-destaque")}
          <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3 text-center">
            {[d.mandante, d.visitante].map((t, i) => (
              <div key={i} className={`flex flex-col items-center gap-2 ${i ? "order-3" : ""}`}>
                <Escudo id={t.escudo} nome={t.nome} className="size-16 drop-shadow-lg sm:size-20" />
                <span className="font-kit text-base font-bold uppercase leading-tight">{t.nome}</span>
              </div>
            ))}
            <p className="order-2 font-kit text-6xl font-extrabold leading-none sm:text-7xl">
              {post.tipo === "proximo_jogo" ? "×" : `${d.mandante.gols}-${d.visitante.gols}`}
              {d.penaltis && <span className="block text-base font-semibold">pên. {d.penaltis[0]}-{d.penaltis[1]}</span>}
            </p>
          </div>
          <div className="font-kit text-sm font-semibold uppercase tracking-wide opacity-85">
            {d.melhor_em_campo && post.tipo !== "proximo_jogo" && (
              <p className="mb-1 flex items-center gap-x-2">
                <span aria-hidden="true" className="icone text-base text-gold">star</span>
                Melhor em campo: {d.melhor_em_campo.nome} · {d.melhor_em_campo.nota.toFixed(1)}
              </p>
            )}
            {d.gols_do_clube?.length > 0 && (
              <p className="mb-1 flex flex-wrap items-center gap-x-2">
                <span aria-hidden="true" className="icone text-base">sports_soccer</span>
                {d.gols_do_clube.join(" · ")}
              </p>
            )}
            <p>{d.competicao} · {dataBR(d.data)}</p>
          </div>
        </div>
      );
    case "classificacao":
      return (
        <div className={base}>
          <span aria-hidden="true" className="absolute inset-x-0 top-0 h-2 bg-[#d71920]" />
          <div>
            {selo("Classificação", "text-[#ff4b55]")}
            <p className="font-kit text-2xl font-bold uppercase">{d.competicao}</p>
          </div>
          <ol className="space-y-1.5">
            {d.linhas.map((l) => (
              <li key={l.nome} className={`grid grid-cols-[2rem_1fr_auto] items-center gap-2 rounded px-2 py-1 ${l.nosso ? "bg-white/15 font-bold" : ""}`}>
                <span className="font-kit text-xl">{l.posicao}º</span>
                <span className="flex min-w-0 items-center gap-2">
                  <Escudo id={l.escudo} nome={l.nome} className="size-6" />
                  <span className="truncate">{l.nome}</span>
                </span>
                <span className="font-kit text-xl">{l.pontos} pts</span>
              </li>
            ))}
          </ol>
          <p className="font-kit text-sm uppercase tracking-wide opacity-75">
            {d.rodadas_jogadas} de {d.rodadas_total} rodadas
          </p>
        </div>
      );
    case "chegada":
    case "saida":
    case "fechado": {
      const outro = d.veio_de ?? d.foi_para;
      const chegou = post.tipo === "chegada" || d.movimento === "chegada";
      const titulo = post.tipo === "fechado" ? "Tá fechado!" : chegou ? "Bem-vindo" : "Obrigado";
      return (
        <div className={base}>
          {selo(titulo, post.tipo === "fechado" ? "text-gold text-3xl tracking-normal" : "text-destaque text-3xl tracking-normal")}
          <div className="flex flex-col items-center gap-3 text-center">
            <Rosto id={d.player_id} className={`size-40 ring-4 ${post.tipo === "fechado" ? "ring-gold" : "ring-current"} ${!chegou && post.tipo === "saida" ? "grayscale" : ""}`} />
            <p className="font-kit text-4xl font-extrabold uppercase leading-none">{d.nome}</p>
          </div>
          <div className="flex items-end justify-between gap-3 font-kit text-base font-semibold uppercase">
            <span className="flex min-w-0 items-center gap-2">
              {outro ? (
                <>
                  {chegou ? "de" : "para o"}
                  <Escudo id={outro.escudo} nome={outro.nome} className="size-7" />
                  <span className="truncate">{outro.nome}</span>
                </>
              ) : d.fim_de_contrato ? "fim de contrato" : chegou ? "sem clube" : ""}
            </span>
            {d.valor ? <Dinheiro valor={d.valor} className="text-3xl font-extrabold text-gold" /> : null}
          </div>
        </div>
      );
    }
    case "mundo":
      return (
        <div className={base}>
          {selo("Tá fechado!", "text-gold text-3xl tracking-normal")}
          <div className="flex flex-col items-center gap-3 text-center">
            <Rosto id={d.player_id} className="size-36 ring-4 ring-gold" />
            <p className="font-kit text-4xl font-extrabold uppercase leading-none">{d.nome}</p>
          </div>
          <div className="flex items-center justify-between gap-3 font-kit text-base font-semibold uppercase">
            <span className="flex min-w-0 items-center gap-2">
              {d.de ? <Escudo id={d.de.escudo} nome={d.de.nome} className="size-8" /> : <span className="text-muted">sem clube</span>}
              <span aria-hidden="true" className="icone text-gold">arrow_forward</span>
              <Escudo id={d.para.escudo} nome={d.para.nome} className="size-8" />
              <span className="truncate">{d.para.nome}</span>
            </span>
            <span className="text-right text-sm normal-case opacity-80">
              valor de mercado
              <Dinheiro valor={d.valor_de_mercado} className="block font-kit text-2xl font-extrabold text-gold" />
            </span>
          </div>
        </div>
      );
    case "coletiva": {
      const fala = post.dados.entrevista[0].resposta;
      return (
        <div className={base}>
          <p className="flex items-center gap-1.5 self-start rounded-sm bg-[#06aa48] px-2 py-0.5 font-kit text-lg font-extrabold uppercase tracking-[0.15em] text-white">
            <span aria-hidden="true" className="icone text-xl">mic</span>
            Coletiva
          </p>
          <blockquote className={`line-clamp-5 font-kit font-extrabold uppercase leading-tight ${
            fala.length > 120 ? "text-xl sm:text-2xl" : fala.length > 50 ? "text-2xl sm:text-4xl" : "text-3xl sm:text-4xl"}`}>
            <span aria-hidden="true" className="text-[#06aa48]">“</span>
            {fala}
            <span aria-hidden="true" className="text-[#06aa48]">”</span>
          </blockquote>
          <p className="flex items-center gap-2 font-kit text-base font-semibold uppercase">
            <Escudo id={d.mandante.escudo} nome={d.mandante.nome} className="size-7" />
            {d.mandante.gols} x {d.visitante.gols}
            <Escudo id={d.visitante.escudo} nome={d.visitante.nome} className="size-7" />
            <span className="opacity-70">· o técnico depois do jogo</span>
          </p>
        </div>
      );
    }
    case "proposta":
      return (
        <div className={base}>
          <p className="self-start rounded-sm bg-[#06aa48] px-2 py-0.5 font-kit text-lg font-extrabold uppercase tracking-[0.15em] text-white">
            Informação
          </p>
          <div className="flex items-center gap-4">
            <Escudo id={d.clube.escudo} nome={d.clube.nome} className="size-20" />
            <span aria-hidden="true" className="icone text-4xl text-[#06aa48]">arrow_forward</span>
            <Rosto id={d.player_id} className="size-24" />
          </div>
          <div>
            <p className="font-kit text-3xl font-extrabold uppercase leading-tight">
              {d.clube.nome} faz proposta por {d.nome}
            </p>
            <p className="mt-2 font-kit text-xl">
              <Dinheiro valor={d.valor} className="font-bold" />
              {d.valor_de_mercado && <span className="opacity-70"> · valor de mercado <Dinheiro valor={d.valor_de_mercado} /></span>}
            </p>
          </div>
        </div>
      );
    case "contratos":
      return (
        <div className={base}>
          <p className="self-start rounded-sm bg-[#06aa48] px-2 py-0.5 font-kit text-lg font-extrabold uppercase tracking-[0.15em] text-white">
            Contratos no fim
          </p>
          <ul className="space-y-2">
            {d.jogadores.slice(0, 6).map((j) => (
              <li key={j.player_id} className="flex items-center gap-3">
                <Rosto id={j.player_id} className="size-10" />
                <span className="min-w-0 flex-1 truncate font-semibold">{j.nome}</span>
                <span className="font-kit text-lg">até {dataBR(j.fim)}</span>
              </li>
            ))}
          </ul>
          <p className="font-kit text-sm uppercase tracking-wide opacity-70">
            {plural(d.jogadores.length, "contrato vence", "contratos vencem")} nos próximos 6 meses
          </p>
        </div>
      );
    default:
      return (
        <div className={base}>
          {selo(post.tipo === "titulo" ? "Campeão!" : "Vice")}
          <span aria-hidden="true" className="icone mx-auto text-gold" style={{ fontSize: "8rem" }}>emoji_events</span>
          <p className="font-kit text-3xl font-extrabold uppercase leading-tight">{d.competicao} {d.temporada}</p>
        </div>
      );
  }
}

// Conversas: a agenda do celular do treinador. O auxiliar fica fixado no topo; os atletas vêm por setor, com os
// sinais que o código tirou dos números (quem joga pouco, contrato vencendo, proposta). A resposta do contato chega
// como um bilhete de papel, o mesmo do parecer do auxiliar: é a voz do vestiário, escrita só com fatos do save.
const SETORES = [
  ["Goleiros", (p) => p === 0],
  ["Defensores", (p) => p >= 1 && p <= 3],
  ["Meio-campistas", (p) => p >= 4 && p <= 8],
  ["Atacantes", (p) => p >= 9],
];
const SINAL_COR = {
  "joga pouco": "bg-cartao/20 text-cartao",
  "contrato vencendo": "bg-gold/20 text-gold",
  "fase ruim": "bg-cartao/20 text-cartao",
  "em boa fase": "bg-neon/15 text-neon",
};
const corDoSinal = (s) => SINAL_COR[s] ?? (s.startsWith("proposta") ? "bg-[#4aa3ff]/20 text-[#7cc0ff]" : "bg-pitch-800 text-muted");
// os sinais que puxam assunto vêm primeiro na agenda
const PESO = (s) => (s.startsWith("proposta") ? 0 : s === "contrato vencendo" ? 1 : s === "joga pouco" ? 2 : s === "fase ruim" ? 3 : 5);

function Conversas({ id, contato, onContato, onFicha }) {
  const [versao, setVersao] = useState(0);
  const { dados: lista, erro } = useDados(() => api.contatos(id), [id, versao]);
  // quem já foi aberto aqui está lido, mesmo com a lista vinda antes (no celular ela volta ao sair da conversa)
  const abertos = useRef(new Set()).current;
  if (contato) abertos.add(contato);
  if (erro) return <Erro mensagem={erro} />;
  if (!lista) return null;
  const auxiliar = lista[0];
  // quem mandou mensagem por conta própria sobe para o topo, como no WhatsApp (até a lista ser recarregada)
  const novas = lista.slice(1).filter((c) => c.nao_lidas > 0);
  const atletas = lista.slice(1).filter((c) => !(c.nao_lidas > 0));
  const grupos = [
    ["Mensagens novas", novas],
    ...SETORES.map(([titulo, do_setor]) => [titulo, atletas.filter((c) => c.posicao != null && do_setor(c.posicao))]),
  ];
  return (
    <div className="grid grid-cols-1 overflow-hidden rounded-xl border border-pitch-800 lg:h-[44rem] lg:grid-cols-[21rem_1fr]">
      <nav aria-label="Contatos" className={`overflow-y-auto border-pitch-800 bg-pitch-900 lg:border-r ${contato ? "hidden lg:block" : ""}`}>
        <Contato c={auxiliar} ativo={contato === "auxiliar"} lido={abertos.has("auxiliar")} onClick={() => onContato("auxiliar")} fixado />
        {grupos.map(
          ([titulo, doSetor]) =>
            doSetor.length > 0 && (
              <section key={titulo}>
                <h3 className={`sticky top-0 z-10 bg-pitch-900/95 px-4 pb-1 pt-4 font-kit text-sm font-semibold uppercase tracking-[0.2em] ${
                  doSetor === novas ? "text-destaque" : "text-muted"
                }`}>
                  {titulo}
                </h3>
                {doSetor.map((c) => (
                  <Contato key={c.contato} c={c} ativo={contato === c.contato} lido={abertos.has(c.contato)} onClick={() => onContato(c.contato)} />
                ))}
              </section>
            ),
        )}
      </nav>
      <div className={`min-h-[36rem] bg-pitch-950 ${contato ? "" : "hidden lg:grid lg:place-items-center"}`}>
        {contato ? (
          <Conversa key={contato} id={id} contato={contato} onVoltar={() => onContato(null)} onMudou={() => setVersao((v) => v + 1)}
            onFicha={onFicha} />
        ) : (
          <p className="max-w-xs text-center text-muted">
            Escolha um contato. O auxiliar conhece o elenco inteiro; cada atleta fala do próprio momento.
          </p>
        )}
      </div>
    </div>
  );
}

function Contato({ c, ativo, lido, onClick, fixado = false }) {
  const sinais = [...c.sinais].sort((a, b) => PESO(a) - PESO(b)).slice(0, 2);
  const novas = lido ? 0 : c.nao_lidas ?? 0;
  return (
    <button
      onClick={onClick}
      aria-current={ativo ? "true" : undefined}
      className={`flex w-full items-center gap-3 px-4 py-2.5 text-left ${ativo ? "bg-pitch-800" : "hover:bg-pitch-800/60"} ${
        fixado ? "border-b border-pitch-800 py-3.5" : ""
      }`}
    >
      {fixado ? (
        <span className="grid size-11 shrink-0 place-items-center rounded-full bg-destaque/15 ring-2 ring-destaque">
          <span aria-hidden="true" className="icone text-2xl text-destaque">sports</span>
        </span>
      ) : (
        <Rosto id={c.player_id} className="size-11" />
      )}
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-2">
          <span className="truncate font-semibold">{c.nome}</span>
          {fixado && <span aria-label="fixado" className="icone text-base text-muted">push_pin</span>}
          {!fixado && <Posicao codigo={c.posicao} className="w-9 shrink-0 py-0 text-xs" />}
          {novas > 0 && (
            <span className="ml-auto grid size-5 shrink-0 place-items-center rounded-full bg-destaque text-xs font-bold text-pitch-950">
              {novas}
              <span className="sr-only"> não lida{novas > 1 ? "s" : ""}</span>
            </span>
          )}
        </span>
        <span className={`block truncate text-sm ${novas > 0 ? "font-semibold text-chalk" : "text-muted"}`}>
          {c.ultima ?? (fixado ? "Elenco, propostas, renovações e próximo jogo" : `${c.idade ?? "?"} anos`)}
        </span>
        {sinais.length > 0 && (
          <span className="mt-1 flex flex-wrap gap-1">
            {sinais.map((s) => (
              <span key={s} className={`rounded-sm px-1.5 font-kit text-xs font-semibold uppercase tracking-wide ${corDoSinal(s)}`}>
                {s}
              </span>
            ))}
          </span>
        )}
      </span>
    </button>
  );
}

function Conversa({ id, contato, onVoltar, onMudou, onFicha }) {
  const { dados: c, erro } = useDados(() => api.conversa(id, contato), [id, contato]);
  const [mensagens, setMensagens] = useState(null);
  const [texto, setTexto] = useState("");
  const [digitando, setDigitando] = useState(false);
  const [falha, setFalha] = useState(null);
  const fim = useRef(null);
  const lista = mensagens ?? c?.mensagens ?? [];
  useEffect(() => {
    fim.current?.scrollIntoView({ block: "end" });
  }, [lista.length, digitando]);
  if (erro) return <div className="p-6"><Erro mensagem={erro} /></div>;
  if (!c) return null;
  const auxiliar = contato === "auxiliar";
  const j = c.fatos.jogador;
  const enviar = (t) => {
    const msg = t.trim();
    if (!msg || digitando) return;
    setFalha(null);
    setTexto("");
    setMensagens([...lista, { autor: "tecnico", texto: msg }]);
    setDigitando(true);
    api
      .enviar(id, contato, msg)
      .then((r) => {
        setMensagens(r.mensagens);
        onMudou();
      })
      .catch((e) => {
        setFalha(e.message);
        setMensagens(lista);
        setTexto(msg);
      })
      .finally(() => setDigitando(false));
  };
  const nome = auxiliar ? "Auxiliar técnico" : j.nome;
  const numeros = auxiliar
    ? [c.fatos.clube.orcamento_de_transferencias && `orçamento ${REAIS.format(c.fatos.clube.orcamento_de_transferencias)}`,
       c.fatos.classificacao?.[0] && `${c.fatos.classificacao[0].posicao}º no ${c.fatos.classificacao[0].competicao}`]
    : [j.temporada.minutos_jogados ? `${j.temporada.minutos_jogados} min` : `${j.temporada.jogos} jogos`,
       j.temporada.nota_media && `nota ${j.temporada.nota_media.toFixed(1)}`,
       j.contrato && (j.contrato.emprestado_ate ? `emprestado até ${dataBR(j.contrato.emprestado_ate).slice(3)}` : `contrato até ${dataBR(j.contrato.fim).slice(3)}`),
       j.valor_de_mercado && REAIS.format(j.valor_de_mercado)];
  return (
    <section aria-label={`Conversa com ${nome}`} className="flex h-[36rem] flex-col lg:h-[44rem]">
      <header className="flex items-center gap-3 border-b border-pitch-800 bg-pitch-900 px-4 py-3">
        <button onClick={onVoltar} aria-label="Voltar aos contatos" className="grid size-8 place-items-center rounded-full hover:bg-pitch-800 lg:hidden">
          <span aria-hidden="true" className="icone">arrow_back</span>
        </button>
        {auxiliar ? (
          <span className="grid size-11 place-items-center rounded-full bg-destaque/15 ring-2 ring-destaque">
            <span aria-hidden="true" className="icone text-2xl text-destaque">sports</span>
          </span>
        ) : (
          <Rosto id={Number(contato)} className="size-11" />
        )}
        <div className="min-w-0">
          <p className="flex items-center gap-2 font-semibold">
            {nome}
            {!auxiliar && j.posicao && <span className="font-kit text-sm text-muted">{j.posicao}{j.idade ? ` · ${j.idade} anos` : ""}</span>}
          </p>
          <p className="truncate font-kit text-sm uppercase tracking-wide text-muted">{numeros.filter(Boolean).join(" · ")}</p>
        </div>
        {!auxiliar && (
          <button
            onClick={() => onFicha(Number(contato))}
            className="ml-auto flex shrink-0 items-center gap-1 rounded-full border border-pitch-700 px-3 py-1 text-sm text-muted hover:border-destaque hover:text-destaque"
          >
            <span aria-hidden="true" className="icone text-base">badge</span>
            <span className="hidden sm:inline">Ver</span> ficha
          </button>
        )}
      </header>
      {c.fatos.promessas_do_professor?.length > 0 && (
        <ul aria-label="Promessas feitas" className="space-y-1 border-b border-pitch-800 bg-pitch-950/60 px-4 py-2 text-sm">
          {c.fatos.promessas_do_professor.map((p) => (
            <li key={p.feita_em + p.promessa} className="flex items-baseline gap-2">
              <span aria-hidden="true" className="icone text-base text-gold">handshake</span>
              <span className="min-w-0">
                <span className="font-semibold">{p.promessa}</span>
                <span className="text-muted">
                  {" "}· prometido em {dataBR(p.feita_em)} · depois disso: {p.desde_entao.jogos_do_clube} jogo{p.desde_entao.jogos_do_clube === 1 ? "" : "s"} do clube, {p.desde_entao.minutos} min dele
                </span>
              </span>
            </li>
          ))}
        </ul>
      )}

      <ol aria-live="polite" className="flex-1 space-y-3 overflow-y-auto px-4 py-5">
        {lista.length === 0 && !digitando && (
          <li className="mx-auto max-w-sm text-center text-sm text-muted">
            {auxiliar
              ? "Pergunte ao auxiliar sobre o elenco, as propostas ou o próximo jogo."
              : `Puxe o assunto com ${j.nome}. Ele responde com base nos números dele no save.`}
          </li>
        )}
        {lista.map((m, i) =>
          m.autor === "tecnico" ? (
            <li key={i} className="ml-auto max-w-[80%] rounded-2xl rounded-br-sm bg-pitch-700 px-4 py-2.5 leading-relaxed">
              {m.texto}
            </li>
          ) : (
            <li key={i} className="balao-papel mr-auto max-w-[85%] leading-relaxed">
              {m.texto}
            </li>
          ),
        )}
        {digitando && (
          <li className="balao-papel mr-auto flex w-16 items-center justify-center gap-1" aria-label={`${nome} está digitando`}>
            {[0, 1, 2].map((k) => (
              <span key={k} className="ponto-digitando" style={{ animationDelay: `${k * 160}ms` }} />
            ))}
          </li>
        )}
        <li ref={fim} aria-hidden="true" />
      </ol>

      {falha && <p className="px-4 pb-2 text-sm text-cartao">{falha}</p>}
      <div className="border-t border-pitch-800 bg-pitch-900 px-3 pb-3 pt-2">
        {c.atalhos.length > 0 && (
          <div className="mb-2 flex gap-2 overflow-x-auto pb-1">
            {c.atalhos.map((a) => (
              <button
                key={a}
                onClick={() => enviar(a)}
                disabled={digitando}
                className="shrink-0 rounded-full border border-pitch-700 px-3 py-1 text-sm hover:border-destaque hover:text-destaque disabled:opacity-50"
              >
                {a}
              </button>
            ))}
          </div>
        )}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            enviar(texto);
          }}
          className="flex gap-2"
        >
          <label className="sr-only" htmlFor="mensagem">Mensagem para {nome}</label>
          <input
            id="mensagem"
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            placeholder="Escreva uma mensagem"
            autoComplete="off"
            className="min-w-0 flex-1 rounded-full border border-pitch-700 bg-pitch-950 px-4 py-2 placeholder:text-muted"
          />
          <button
            type="submit"
            disabled={digitando || !texto.trim()}
            aria-label="Enviar"
            className="grid size-10 shrink-0 place-items-center rounded-full bg-destaque text-pitch-950 disabled:opacity-40"
          >
            <span aria-hidden="true" className="icone">send</span>
          </button>
        </form>
      </div>
    </section>
  );
}

// Quadro do topo da visão geral: o que pede uma decisão agora. O código escolhe; cada linha leva a quem resolve.
function Atencao({ id, onFicha, onConversar, onAba }) {
  const { dados: a } = useDados(() => api.atencao(id), [id]);
  if (!a) return null;
  const linhas = [
    ...a.propostas.map((p) => ({
      chave: `p${p.player_id}-${p.clube.nome}`,
      icone: "mail",
      cor: "text-[#7cc0ff]",
      rosto: p.player_id,
      texto: (
        <>
          <b>{p.clube.nome}</b> quer <b>{p.nome}</b> por <Dinheiro valor={p.valor} className="font-kit text-lg font-bold" />
          {p.valor_mercado && <span className="text-muted"> · vale <Dinheiro valor={p.valor_mercado} /></span>}
          {p.vontade && <> <SeloDeVontade vontade={p.vontade} /></>}
        </>
      ),
      acao: ["Ver proposta", () => onAba("Transferências")],
    })),
    ...a.contratos.map((c) => ({
      chave: `c${c.player_id}`,
      icone: "hourglass_bottom",
      cor: "text-gold",
      rosto: c.player_id,
      texto: (
        <>
          <b>{c.nome}</b>: {c.emprestimo ? "o empréstimo acaba" : "o contrato vence"} em {dataBR(c.fim)}
        </>
      ),
      acao: [c.emprestimo ? "Ver ficha" : "Renovar?", () => (c.emprestimo ? onFicha(c.player_id) : onConversar(String(c.player_id)))],
    })),
    ...a.promessas.map((p) => ({
      chave: `r${p.player_id}`,
      icone: "handshake",
      cor: "text-gold",
      rosto: p.player_id,
      texto: (
        <>
          Você prometeu <b>{p.promessa}</b> a <b>{p.nome}</b>
          <span className="text-muted">
            {" "}· depois: {plural(p.desde_entao.jogos_do_clube, "jogo", "jogos")} do clube, {p.desde_entao.minutos} min dele
          </span>
        </>
      ),
      acao: ["Abrir conversa", () => onConversar(String(p.player_id))],
    })),
    ...a.sem_espaco.map((j) => ({
      chave: `e${j.player_id}`,
      icone: "event_seat",
      cor: "text-muted",
      rosto: j.player_id,
      texto: (
        <>
          <b>{j.nome}</b> jogou {j.minutos} min em {plural(j.jogos_do_clube, "jogo", "jogos")} do clube
          {j.valor && <span className="text-muted"> · vale <Dinheiro valor={j.valor} /></span>}
        </>
      ),
      acao: ["Ver ficha", () => onFicha(j.player_id)],
    })),
  ];
  if (linhas.length === 0) return null;
  return (
    <section aria-labelledby="atencao" className="mb-10 rounded-md border border-pitch-800 bg-pitch-900">
      <h2 id="atencao" className="flex items-center gap-2 border-b border-pitch-800 px-4 py-3 font-kit text-xl font-semibold uppercase">
        <span aria-hidden="true" className="icone text-gold">priority_high</span>
        Precisa de atenção
        <span className="ml-1 rounded-full bg-pitch-700 px-2 text-sm text-muted">{linhas.length}</span>
      </h2>
      <ul className="divide-y divide-pitch-800">
        {linhas.map((l) => (
          <li key={l.chave}>
            {/* a linha inteira é o botão; no celular a ação vira só uma seta, para não ocupar outra linha */}
            <button onClick={l.acao[1]} className="group flex w-full items-center gap-3 px-4 py-2.5 text-left hover:bg-pitch-800/60">
              <span aria-hidden="true" className={`icone ${l.cor}`}>{l.icone}</span>
              <Rosto id={l.rosto} className="size-8 shrink-0" />
              <span className="min-w-0 flex-1 leading-snug">{l.texto}</span>
              <span className="hidden shrink-0 rounded-full border border-pitch-700 px-3 py-1 text-sm group-hover:border-destaque group-hover:text-destaque sm:inline">
                {l.acao[0]}
              </span>
              <span aria-hidden="true" className="icone text-muted sm:hidden">chevron_right</span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

// Ficha do jogador numa gaveta: quem ele é, a fase (nota jogo a jogo), o valor ao longo do tempo, o contrato e
// tudo o que passou por ele no clube. <dialog> nativo: prende o foco e fecha no Esc.
function Ficha({ id, pid, clube, onFechar, onConversar }) {
  const ref = useRef(null);
  const { dados: f, erro } = useDados(() => api.jogador(id, pid), [id, pid]);
  useEffect(() => ref.current.showModal(), []);
  const fechar = () => ref.current.close();
  const c = f?.contrato;
  return (
    <dialog ref={ref} onClose={onFechar} onClick={(e) => e.target === ref.current && fechar()} aria-label="Ficha do jogador" className="gaveta">
      <div className="h-full overflow-y-auto overscroll-contain">
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-pitch-800 bg-pitch-950/95 px-5 py-2 backdrop-blur">
          <span className="font-kit text-sm uppercase tracking-[0.2em] text-muted">Ficha · {clube}</span>
          <button onClick={fechar} aria-label="Fechar a ficha" className="-mr-2 grid size-9 place-items-center rounded-full hover:bg-pitch-800">
            <span aria-hidden="true" className="icone">close</span>
          </button>
        </div>
        {erro && <div className="p-5"><Erro mensagem={erro} /></div>}
        {f && (
          <div className="space-y-9 px-5 pb-10 pt-6 sm:px-7">
            <header className="flex items-center gap-5">
              <Rosto id={f.player_id} className={`size-24 shrink-0 ring-2 ring-destaque sm:size-28 ${f.no_elenco ? "" : "grayscale"}`} />
              <div className="min-w-0 space-y-2">
                <h2 className="font-kit text-4xl font-extrabold uppercase leading-none sm:text-5xl">{f.nome}</h2>
                <p className="flex flex-wrap items-center gap-2 text-muted">
                  {f.posicao != null && <Posicao codigo={f.posicao} />}
                  {[f.idade && `${f.idade} anos`, !f.no_elenco && "não está mais no elenco"].filter(Boolean).join(" · ")}
                  {f.valor && <Dinheiro valor={f.valor} className="font-kit text-xl font-bold text-gold" />}
                </p>
                {f.sinais.length > 0 && (
                  <ul className="flex flex-wrap gap-1">
                    {f.sinais.map((s) => (
                      <li key={s} className={`rounded-sm px-1.5 font-kit text-xs font-semibold uppercase tracking-wide ${corDoSinal(s)}`}>{s}</li>
                    ))}
                  </ul>
                )}
                {f.no_elenco && (
                  <button
                    onClick={() => onConversar(String(f.player_id))}
                    className="flex items-center gap-1.5 rounded-full bg-destaque px-3 py-1 text-sm font-semibold text-pitch-950 hover:brightness-110"
                  >
                    <span aria-hidden="true" className="icone text-base">chat</span>
                    Chamar pra conversa
                  </button>
                )}
              </div>
            </header>

            <section>
              <h3 className="mb-3 font-kit text-xl font-semibold uppercase">Pelo clube</h3>
              {f.total.jogos === 0 ? (
                <p className="text-muted">Ainda não entrou em campo pelo clube nos jogos que o Vestiário guardou.</p>
              ) : (
                <table className="w-full text-left">
                  <thead>
                    <tr className="border-b border-pitch-700 font-kit text-sm uppercase tracking-wide text-muted">
                      <th className="py-1 font-semibold">Temporada</th>
                      {["J", "G", "A", "Min.", "Nota"].map((t) => (
                        <th key={t} className="py-1 text-right font-semibold">{t}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="font-kit text-xl">
                    {[...f.temporadas.map((t) => [t.ano, t]), ...(f.temporadas.length > 1 ? [["Total", f.total]] : [])].map(([rotulo, n]) => (
                      <tr key={rotulo} className={`border-b border-pitch-800 ${rotulo === "Total" ? "font-bold" : ""}`}>
                        <td className="py-1.5">{rotulo}</td>
                        <td className="text-right">{n.jogos}</td>
                        <td className="text-right">{n.gols}</td>
                        <td className="text-right">{n.assistencias}</td>
                        <td className="text-right">{n.minutos}</td>
                        <td className="text-right">{n.nota?.toFixed(1) ?? "–"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>

            <Fase jogos={f.jogos} />
            <ValorNoTempo valores={f.valores} />

            {c && (
              <section>
                <h3 className="mb-3 font-kit text-xl font-semibold uppercase">{c.emprestimo ? "Empréstimo" : "Contrato"}</h3>
                <dl className="grid grid-cols-3 gap-px overflow-hidden rounded-md bg-pitch-800">
                  {(c.emprestimo
                    ? [["Emprestado até", dataBR(c.fim)]]
                    : [["Salário/sem.", <Dinheiro key="s" valor={c.salario_semanal} />], ["Multa", c.multa ? <Dinheiro key="m" valor={c.multa} /> : "sem multa"], ["Até", dataBR(c.fim)]]
                  ).map(([rotulo, valor]) => (
                    <div key={rotulo} className="bg-pitch-900 px-3 py-2">
                      <dt className="text-xs uppercase text-muted">{rotulo}</dt>
                      <dd className="font-kit text-xl font-bold">{valor}</dd>
                    </div>
                  ))}
                </dl>
              </section>
            )}

            {f.promessas.length > 0 && (
              <section>
                <h3 className="mb-3 font-kit text-xl font-semibold uppercase">Promessas</h3>
                <ul className="space-y-2">
                  {f.promessas.map((p) => (
                    <li key={p.feita_em + p.promessa} className="flex items-baseline gap-2">
                      <span aria-hidden="true" className="icone text-base text-gold">handshake</span>
                      <span>
                        <b>{p.promessa}</b>
                        <span className="text-muted"> · em {dataBR(p.feita_em)} · depois: {plural(p.desde_entao.jogos_do_clube, "jogo", "jogos")} do clube, {p.desde_entao.minutos} min dele</span>
                      </span>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {f.propostas.length > 0 && (
              <section>
                <h3 className="mb-3 font-kit text-xl font-semibold uppercase">Propostas recebidas</h3>
                <ul className="divide-y divide-pitch-800">
                  {f.propostas.map((p) => (
                    <li key={`${p.clube.idx}-${p.valor}`} className="flex items-center gap-2 py-2">
                      <Escudo id={p.clube.escudo} nome={p.clube.nome} className="size-6" />
                      <span className="min-w-0 flex-1 truncate">{p.clube.nome}</span>
                      <Dinheiro valor={p.valor} className="font-kit text-lg font-bold" />
                      <span className="w-24 text-right text-sm text-muted">{p.situacao === "aberta" ? "aberta" : `até ${dataBR(p.ultima)}`}</span>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {f.jogos.length > 0 && (
              <section>
                <h3 className="mb-3 font-kit text-xl font-semibold uppercase">Jogo a jogo</h3>
                <ul className="divide-y divide-pitch-800 text-sm">
                  {f.jogos.map((j) => {
                    const res = j.placar[0] > j.placar[1] ? "V" : j.placar[0] < j.placar[1] ? "D" : "E";
                    return (
                      <li key={j.partida_id} className={`grid grid-cols-[4.5rem_1fr_auto_3rem_2.5rem] items-center gap-2 border-l-4 py-2 pl-2 ${BORDA_RESULTADO[res]}`}>
                        <span className="text-muted">{dataBR(j.data).slice(0, 5)}</span>
                        <span className="flex min-w-0 items-center gap-2">
                          <Escudo id={j.adversario.escudo} nome={j.adversario.nome} className="size-5" />
                          <span className="truncate">{j.em_casa ? "" : "@ "}{j.adversario.nome}</span>
                        </span>
                        <span className="font-kit text-lg">
                          {j.placar[0]}–{j.placar[1]}
                          {j.gols + j.assistencias > 0 && (
                            <span className="ml-2 text-destaque">{[j.gols && `${j.gols}G`, j.assistencias && `${j.assistencias}A`].filter(Boolean).join(" ")}</span>
                          )}
                        </span>
                        <span className="text-right text-muted">{j.minutos}′</span>
                        <span className={`text-right font-kit text-lg ${corDaNota(j.nota)}`}>{j.nota?.toFixed(1) ?? "–"}</span>
                      </li>
                    );
                  })}
                </ul>
              </section>
            )}
          </div>
        )}
      </div>
    </dialog>
  );
}

const corDaNota = (n) => (n == null ? "text-muted" : n >= 6.8 ? "text-neon" : n <= 5.5 ? "text-cartao" : "");

// A fase: a nota do PES nos últimos jogos, em barras da mais antiga à mais recente
function Fase({ jogos }) {
  const notas = jogos.filter((j) => j.nota != null).slice(0, 15).reverse();
  if (notas.length < 2) return null;
  return (
    <section>
      <h3 className="mb-3 flex items-baseline justify-between font-kit text-xl font-semibold uppercase">
        Fase
        <span className="font-sans text-sm font-normal normal-case text-muted">nota nos últimos {notas.length} jogos</span>
      </h3>
      <ol className="flex h-28 items-end gap-1 border-b border-pitch-700">
        {notas.map((j) => (
          <li key={j.partida_id} className="flex h-full flex-1 flex-col justify-end" title={`${dataBR(j.data)} · ${j.adversario.nome} · nota ${j.nota.toFixed(1)}`}>
            <span className={`text-center font-kit text-xs ${corDaNota(j.nota)}`}>{j.nota.toFixed(1)}</span>
            <span
              className={`block rounded-t-sm ${j.nota >= 6.8 ? "bg-neon" : j.nota <= 5.5 ? "bg-cartao" : "bg-muted/60"}`}
              style={{ height: `${Math.max(4, (j.nota - 3) * 14)}%` }}
            />
          </li>
        ))}
      </ol>
    </section>
  );
}

// Valor de mercado em cada sincronização; só vira gráfico quando o valor mudou
function ValorNoTempo({ valores }) {
  if (valores.length === 0) return null;
  const [primeiro, ultimo] = [valores[0], valores[valores.length - 1]];
  const mudou = valores.some((v) => v.valor !== primeiro.valor);
  const [min, max] = [Math.min(...valores.map((v) => v.valor)), Math.max(...valores.map((v) => v.valor))];
  const pontos = valores.map((v, i) => `${(i / (valores.length - 1 || 1)) * 100},${28 - ((v.valor - min) / (max - min || 1)) * 24}`).join(" ");
  return (
    <section>
      <h3 className="mb-3 font-kit text-xl font-semibold uppercase">Valor de mercado</h3>
      {mudou ? (
        <>
          <svg viewBox="0 0 100 30" preserveAspectRatio="none" className="h-20 w-full" aria-hidden="true">
            <polyline points={pontos} fill="none" stroke="var(--color-gold)" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
          </svg>
          <p className="mt-1 flex justify-between text-sm text-muted">
            <span><Dinheiro valor={primeiro.valor} className="font-kit text-lg text-chalk" /> em {dataBR(primeiro.data)}</span>
            <span><Dinheiro valor={ultimo.valor} className="font-kit text-lg text-gold" /> em {dataBR(ultimo.data)}</span>
          </p>
        </>
      ) : (
        <p className="text-muted">
          <Dinheiro valor={ultimo.valor} className="font-kit text-2xl font-bold text-gold" /> sem mudança desde {dataBR(primeiro.data)}
        </p>
      )}
    </section>
  );
}

const REAIS = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", notation: "compact", maximumFractionDigits: 1 });
const REAIS_EXATO = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });

function Dinheiro({ valor, sinal = false, className = "" }) {
  const texto = REAIS.format(Math.abs(valor));
  return (
    <span title={REAIS_EXATO.format(valor)} className={className}>
      {sinal && valor !== 0 && (valor > 0 ? "+" : "−")}
      {texto}
    </span>
  );
}

function Transferencias({ id, onConversar }) {
  const { dados: t, erro } = useDados(() => api.transferencias(id), [id]);
  if (erro) return <Erro mensagem={erro} />;
  if (!t) return null;
  if (t.janelas.length === 0) {
    return (
      <>
      <Propostas id={id} lista={t.propostas} onConversar={onConversar} />
      <p className="max-w-xl text-muted">
        Nenhuma mudança no elenco{t.primeira && ` desde ${dataBR(t.primeira)}`}. Depois da próxima janela de
        transferências no jogo, salve e sincronize: quem chegou e quem saiu aparece aqui, com clube e valor.
      </p>
      </>
    );
  }
  return (
    <>
      <Propostas id={id} lista={t.propostas} onConversar={onConversar} />
      <p className="mb-8 max-w-xl text-muted">
        O elenco de cada data do jogo sincronizada, comparado com o da data anterior. Os números são pelo clube, na
        carreira toda.
      </p>
      {t.janelas.map((j) => (
        <section key={`${j.de}-${j.ate}`} className="mb-12">
          <div className="flex flex-wrap items-center justify-between gap-x-8 gap-y-4">
            <h2>
              <span className="fita text-xl">{j.de ? `De ${dataBR(j.de)} a ${dataBR(j.ate)}` : `Até ${dataBR(j.ate)}`}</span>
            </h2>
            {j.gastos + j.receitas > 0 && (
              <dl className="flex gap-6 font-kit uppercase">
                {[
                  ["Gastos", -j.gastos, "text-chalk"],
                  ["Receitas", j.receitas, "text-chalk"],
                  ["Saldo", j.receitas - j.gastos, j.receitas >= j.gastos ? "text-neon" : "text-cartao"],
                ].map(([rotulo, valor, cor]) => (
                  <div key={rotulo}>
                    <dt className="text-sm tracking-wide text-muted">{rotulo}</dt>
                    <dd className={`text-2xl font-bold normal-case ${cor}`}>
                      <Dinheiro valor={valor} sinal={rotulo === "Saldo"} />
                    </dd>
                  </div>
                ))}
              </dl>
            )}
          </div>
          {!j.de && (
            <p className="mt-3 text-sm text-muted">Negócios que o livro do PES já tinha na primeira sincronização.</p>
          )}
          <div className="mt-6 grid grid-cols-1 gap-5 md:grid-cols-2">
            {(j.de || j.chegaram.length > 0) && (
              <Movimento titulo="Chegaram" icone="login" cor="text-neon" jogadores={j.chegaram} clubeConhecido={j.origem_conhecida} />
            )}
            {(j.de || j.sairam.length > 0) && (
              <Movimento titulo="Saíram" icone="logout" cor="text-cartao" jogadores={j.sairam} clubeConhecido={j.destino_conhecido} saiu />
            )}
          </div>
        </section>
      ))}
    </>
  );
}

// Quem chegou vem "de" um clube, quem saiu vai "para" outro. Sem o clube conhecido (sincronização anterior a esta
// versão, com o save já sobrescrito), a linha some.
// Propostas de outros clubes pelos jogadores do clube. A régua compara a oferta com o valor de mercado, que é a
// pergunta de quem decide: estão pagando mais ou menos do que ele vale?
function Propostas({ id, lista, onConversar }) {
  if (!lista?.length) return null;
  const abertas = lista.filter((p) => p.situacao === "aberta");
  const antigas = lista.filter((p) => p.situacao !== "aberta");
  return (
    <section className="mb-14" aria-labelledby="propostas">
      <h2 id="propostas" className="mb-1 font-kit text-3xl font-semibold uppercase">
        Propostas recebidas
      </h2>
      <p className="mb-5 max-w-2xl text-sm text-muted">
        Ofertas de outros clubes pelos seus jogadores e o que cada um achou. Responda no PES; aqui fica o histórico.
      </p>
      {abertas.length > 0 ? (
        <ul className="grid grid-cols-1 items-start gap-5 md:grid-cols-2">
          {abertas.map((p) => (
            <li key={`${p.player_id}-${p.clube.nome}-${p.valor}`}>
              <CartaDeProposta id={id} p={p} onConversar={onConversar} />
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-muted">Nenhuma proposta aberta no último save.</p>
      )}
      {antigas.length > 0 && (
        <>
          <h3 className="mb-2 mt-8 font-kit text-xl font-semibold uppercase text-muted">Anteriores</h3>
          <ul className="divide-y divide-pitch-800">
            {antigas.map((p) => (
              <li key={`${p.player_id}-${p.clube.nome}-${p.valor}`} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2 text-muted">
                <Escudo id={p.clube.escudo} nome={p.clube.nome ?? "?"} className="size-5" />
                <span className="min-w-0 truncate">
                  {p.clube.nome} por <span className="text-chalk">{p.nome}</span>
                </span>
                <SeloDeVontade vontade={p.vontade} />
                <Dinheiro valor={p.valor} className="font-kit text-lg text-chalk" />
                <span className="text-sm">{p.situacao === "saiu" ? "· o jogador saiu do clube" : "· recusada ou expirou"}</span>
                <span className="ml-auto text-sm">até {dataBR(p.ultima)}</span>
                {p.fala &&
                  (p.situacao === "saiu" ? (
                    <p className="basis-full truncate pl-8 text-sm italic">“{p.fala}”</p>
                  ) : (
                    <button
                      onClick={() => onConversar(String(p.player_id))}
                      className="group flex min-w-0 basis-full items-baseline gap-2 pl-8 text-left text-sm"
                    >
                      <span className="min-w-0 truncate italic group-hover:text-chalk">“{p.fala}”</span>
                      <span className="flex shrink-0 items-center gap-1 text-chalk group-hover:text-destaque">
                        <span aria-hidden="true" className="icone text-base">reply</span>
                        Falar com ele
                      </span>
                    </button>
                  ))}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

const VONTADE = {
  ficar: ["Quer ficar", "bg-neon/15 text-neon"],
  sair: ["Quer sair", "bg-cartao/20 text-cartao"],
  dividido: ["Dividido", "bg-gold/20 text-gold"],
};

function SeloDeVontade({ vontade }) {
  const v = VONTADE[vontade];
  if (!v) return null;
  return <span className={`whitespace-nowrap rounded-sm px-1.5 font-kit text-xs font-semibold uppercase tracking-wide ${v[1]}`}>{v[0]}</span>;
}

// A palavra do jogador: a mensagem que ele mandou por conta própria quando a proposta chegou (ou acabou), com a cara
// de uma mensagem de WhatsApp dele (o bilhete de papel é do auxiliar). Sem mensagem ainda (a IA estava fora na
// sincronização), o botão pede na hora e abre a conversa.
function FalaDoJogador({ id, p, onConversar }) {
  const [ouvindo, setOuvindo] = useState(false);
  const [erro, setErro] = useState(null);
  const abrir = () => onConversar(String(p.player_id));
  const ouvir = () => {
    setOuvindo(true);
    setErro(null);
    api
      .reacao(id, p.player_id)
      .then(abrir)
      .catch((e) => setErro(e.message))
      .finally(() => setOuvindo(false));
  };
  return (
    <div className="mt-4" aria-live="polite">
      {p.fala ? (
        <button onClick={abrir} className="group flex w-full items-start gap-2.5 text-left">
          <Rosto id={p.player_id} className="size-9 shrink-0" />
          <span className="balao-zap min-w-0 flex-1 px-3 pb-2 pt-1.5">
            <span className="flex flex-wrap items-center gap-x-2 text-sm font-semibold text-destaque">
              {p.nome} <SeloDeVontade vontade={p.vontade} />
            </span>
            <span className="mt-0.5 block text-[0.95rem] leading-snug text-chalk">{p.fala}</span>
            <span className="mt-1.5 flex items-center justify-end gap-1 text-xs text-muted group-hover:text-destaque">
              <span aria-hidden="true" className="icone text-base">reply</span>
              Falar com ele
            </span>
          </span>
        </button>
      ) : ouvindo ? (
        <p className="flex items-center gap-2.5">
          <Rosto id={p.player_id} className="size-9 shrink-0" />
          <span className="sr-only">{p.nome} está escrevendo</span>
          <span aria-hidden="true" className="balao-zap flex items-center gap-1 px-4 py-3">
            {[0, 1, 2].map((k) => (
              <span key={k} className="ponto-digitando" style={{ background: "var(--color-chalk)", animationDelay: `${k * 160}ms` }} />
            ))}
          </span>
        </p>
      ) : (
        <button
          onClick={ouvir}
          className="flex items-center gap-2 rounded-md border border-pitch-700 px-3 py-2 font-kit text-base font-semibold uppercase tracking-wide hover:border-destaque hover:text-destaque"
        >
          <span aria-hidden="true" className="icone text-lg">chat</span>
          Ouvir o jogador
        </button>
      )}
      {erro && <p className="mt-2 text-sm text-cartao">{erro}</p>}
    </div>
  );
}

function CartaDeProposta({ id, p, onConversar }) {
  const diferenca = p.valor_mercado ? (p.valor - p.valor_mercado) / p.valor_mercado : null;
  // régua: o traço de giz é o valor de mercado; a barra vai até a oferta (no máximo o dobro do valor)
  const escala = p.valor_mercado ? Math.max(p.valor, p.valor_mercado) * 1.15 : null;
  const acima = diferenca !== null && diferenca >= 0;
  return (
    <article className="rounded-md bg-pitch-900 p-5">
      <header className="flex items-center gap-3">
        <Escudo id={p.clube.escudo} nome={p.clube.nome ?? "?"} className="size-10 drop-shadow-lg" />
        <p className="min-w-0 font-kit text-lg uppercase leading-tight text-muted">
          <span className="block truncate text-2xl font-bold text-chalk">{p.clube.nome}</span>
          quer
        </p>
        <span className="ml-auto flex min-w-0 items-center gap-2">
          <Rosto id={p.player_id} className="size-10" />
          <span className="min-w-0">
            <span className="block truncate font-semibold">{p.nome}</span>
            <Posicao codigo={p.posicao} className="w-9 py-0 text-xs" />
          </span>
        </span>
      </header>

      <div className="mt-5 flex flex-wrap items-end justify-between gap-x-4">
        <Dinheiro valor={p.valor} className="font-kit text-4xl font-extrabold text-gold" />
        {p.valor_mercado && (
          <span className="text-sm text-muted">
            valor de mercado <Dinheiro valor={p.valor_mercado} className="text-chalk" />
          </span>
        )}
      </div>
      {escala && (
        <div className="mt-3">
          <div className="relative h-2.5 rounded-full bg-pitch-800" aria-hidden="true">
            <div
              className={`absolute inset-y-0 left-0 rounded-full ${acima ? "bg-neon" : "bg-cartao"}`}
              style={{ width: `${(p.valor / escala) * 100}%` }}
            />
            <div className="absolute -inset-y-1.5 w-0.5 bg-chalk/80" style={{ left: `${(p.valor_mercado / escala) * 100}%` }} />
          </div>
          <p className={`mt-2 text-sm font-semibold ${acima ? "text-neon" : "text-cartao"}`}>
            {Math.abs(Math.round(diferenca * 100))}% {acima ? "acima" : "abaixo"} do valor de mercado
          </p>
        </div>
      )}
      <footer className="mt-4 flex items-center gap-2 border-t border-pitch-800 pt-3 text-sm text-muted">
        <span className="size-2 rounded-full bg-neon" aria-hidden="true" />
        Aberta · no save desde {dataBR(p.primeira)}
      </footer>
      <FalaDoJogador id={id} p={p} onConversar={onConversar} />
      <ParecerDoAuxiliar id={id} p={p} />
    </article>
  );
}

const RECOMENDACAO = {
  aceitar: ["Aceitar", "text-neon"],
  negociar: ["Pedir mais", "text-gold"],
  recusar: ["Recusar", "text-cartao"],
};

// Assinatura da IA: o parecer chega como um bilhete do auxiliar, papel preso com fita crepe e a decisão a pincel.
// A IA só vê os fatos do banco, e o bilhete mostra quais foram ("Baseado em").
function ParecerDoAuxiliar({ id, p }) {
  const [parecer, setParecer] = useState(p.parecer);
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState(null);
  const pedir = () => {
    setCarregando(true);
    setErro(null);
    api
      .parecer(id, p)
      .then(setParecer)
      .catch((e) => setErro(e.message))
      .finally(() => setCarregando(false));
  };
  if (!parecer) {
    return (
      <div className="mt-4" aria-live="polite">
        {carregando ? (
          <p className="flex items-center gap-2 text-sm text-muted">
            <span aria-hidden="true" className="icone animate-pulse text-gold motion-reduce:animate-none">
              edit_note
            </span>
            O auxiliar está olhando os números. Pode levar até meio minuto.
          </p>
        ) : (
          <button
            onClick={pedir}
            className="flex items-center gap-2 rounded-md border border-pitch-700 px-3 py-2 font-kit text-base font-semibold uppercase tracking-wide hover:border-gold hover:text-gold"
          >
            <span aria-hidden="true" className="icone text-lg">
              forum
            </span>
            Pedir opinião ao auxiliar
          </button>
        )}
        {erro && <p className="mt-2 text-sm text-cartao">{erro}</p>}
      </div>
    );
  }
  const [rotulo, cor] = RECOMENDACAO[parecer.recomendacao] ?? [parecer.recomendacao, "text-chalk"];
  return (
    <div className="bilhete mt-6" aria-live="polite">
      <span aria-hidden="true" className="fita absolute -top-3 left-6 text-sm" style={{ "--giro": "-3deg" }}>
        Auxiliar
      </span>
      <p className="leading-relaxed">{parecer.parecer}</p>
      <p className="mt-3 flex items-center gap-2 font-kit text-sm uppercase tracking-wide text-pincel/70">
        Recomendação
        <span className={`rounded-sm bg-pitch-950 px-2 py-0.5 font-pincel text-lg normal-case ${cor}`}>{rotulo}</span>
      </p>
      <details className="mt-3 text-sm text-pincel/80">
        <summary className="cursor-pointer font-kit uppercase tracking-wide">Baseado em</summary>
        <ul className="mt-2 list-inside list-disc space-y-0.5">
          {baseDoParecer(parecer.fatos).map((f) => (
            <li key={f}>{f}</li>
          ))}
        </ul>
      </details>
    </div>
  );
}

// Os fatos que a IA recebeu, em linhas legíveis
function baseDoParecer(f) {
  const j = f.jogador ?? {};
  const t = j.temporada ?? {};
  const c = j.contrato ?? {};
  return [
    `oferta de ${REAIS_EXATO.format(f.proposta.valor_oferecido)}`,
    j.valor_de_mercado && `valor de mercado de ${REAIS_EXATO.format(j.valor_de_mercado)}`,
    j.idade && `${j.idade} anos, ${j.posicao ?? ""}`.trim(),
    c.fim && `contrato até ${dataBR(c.fim)}, salário de ${REAIS_EXATO.format(c.salario_semanal)}/sem.`,
    c.emprestado_ate && `emprestado até ${dataBR(c.emprestado_ate)}`,
    t.jogos_do_clube
      ? `${plural(t.jogos ?? 0, "jogo", "jogos")} de ${t.jogos_do_clube} do clube na temporada, ${plural(t.gols ?? 0, "gol", "gols")}`
      : "o clube ainda não jogou na temporada",
    `${plural(f.elenco_na_mesma_posicao.length, "colega", "colegas")} na mesma posição`,
    f.clube.orcamento_de_transferencias && `orçamento de ${REAIS_EXATO.format(f.clube.orcamento_de_transferencias)}`,
  ].filter(Boolean);
}

function Movimento({ titulo, icone, cor, jogadores, clubeConhecido, saiu = false }) {
  return (
    <div className="rounded-md bg-pitch-900 p-5">
      <h3 className="mb-4 flex items-center gap-2 font-kit text-2xl font-semibold uppercase">
        <span aria-hidden="true" className={`icone ${cor}`}>
          {icone}
        </span>
        {titulo}
        <span className="font-normal text-muted">{jogadores.length}</span>
      </h3>
      {jogadores.length === 0 ? (
        <p className="text-muted">Ninguém.</p>
      ) : (
        <ul className="space-y-2">
          {jogadores.map((j) => {
            const numeros =
              j.jogos === 0
                ? "não jogou"
                : `${plural(j.jogos, "jogo", "jogos")} · ${plural(j.gols, "gol", "gols")} · ${j.assistencias} assist.`;
            return (
            <li key={j.player_id} className="flex items-center gap-3">
              <Rosto id={j.player_id} className={`size-9 ${saiu ? "opacity-60 grayscale" : ""}`} />
              <span className="min-w-0 flex-1">
                <span className="block truncate">{j.nome}</span>
                {clubeConhecido && (
                  <span className="flex min-w-0 items-center gap-1.5 text-sm text-muted">
                    {j.clube ? (
                      <>
                        {saiu ? "para" : "de"}
                        <Escudo id={j.clube.escudo} nome={j.clube.nome} className="size-4" />
                        <span className="truncate text-chalk">{j.clube.nome}</span>
                      </>
                    ) : (
                      "sem clube"
                    )}
                  </span>
                )}
                {/* no celular os números descem para baixo do nome; o valor fica sozinho à direita */}
                <span className="block text-sm text-muted sm:hidden">{numeros}</span>
              </span>
              <span className="shrink-0 text-right">
                {j.valor === null && j.fim_de_contrato && (
                  <span className="rounded-sm bg-pitch-700 px-1.5 text-xs uppercase text-muted">fim de contrato</span>
                )}
                {j.valor !== null && (
                  <span className="flex items-center justify-end gap-2">
                    {j.tipo === 8 && <span className="rounded-sm bg-pitch-700 px-1.5 text-xs uppercase text-muted">troca</span>}
                    <Dinheiro valor={j.valor} className="font-kit text-xl font-bold text-gold" />
                  </span>
                )}
                <span className="hidden text-sm text-muted sm:block">{numeros}</span>
              </span>
            </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

const COLUNAS_CONFRONTO = "grid-cols-[1fr_repeat(4,1.25rem)_2.5rem_1.25rem] gap-2 sm:grid-cols-[1fr_repeat(5,3rem)_4rem_1.5rem]";

function Adversarios({ id, clube }) {
  const { dados: lista, erro } = useDados(() => api.confrontos(id), [id]);
  if (erro) return <Erro mensagem={erro} />;
  if (!lista) return null;
  if (lista.length === 0) return <p className="text-muted">Nenhuma partida disputada ainda.</p>;
  // Freguês: quem mais perdeu para o clube; carrasco: quem mais ganhou dele. Desempate pelo outro lado do placar e
  // pelo saldo. Com menos de 2 resultados não é freguesia, é acaso.
  const saldo = (a) => a.gols_pro - a.gols_contra;
  const melhor = (k, oposto, sinal) =>
    [...lista].sort((a, b) => b[k] - a[k] || a[oposto] - b[oposto] || sinal * (saldo(b) - saldo(a)))[0];
  const fregues = melhor("vitorias", "derrotas", 1);
  const carrasco = melhor("derrotas", "vitorias", -1);
  return (
    <>
      <div className="mb-10 grid grid-cols-1 gap-5 empty:hidden sm:grid-cols-2">
        {fregues.vitorias >= 2 && (
          <Destaque titulo="Freguês" a={fregues} cor="text-neon"
            frase={`${plural(fregues.vitorias, "vitória", "vitórias")} em ${plural(fregues.jogos, "jogo", "jogos")}`} />
        )}
        {carrasco.derrotas >= 2 && (
          <Destaque titulo="Carrasco" a={carrasco} cor="text-cartao"
            frase={`${plural(carrasco.derrotas, "derrota", "derrotas")} em ${plural(carrasco.jogos, "jogo", "jogos")}`} />
        )}
      </div>

      <div aria-hidden="true" className={`grid ${COLUNAS_CONFRONTO} border-b border-pitch-700 pb-2 pl-3 font-kit text-base sm:text-lg font-semibold uppercase tracking-wide text-muted`}>
        <span>Adversário</span>
        {["J", "V", "E", "D", "Saldo"].map((c) => (
          <span key={c} className="text-right">
            {c}
          </span>
        ))}
        <span className="hidden text-right sm:block">Aprov.</span>
      </div>
      <ul className="divide-y divide-pitch-800">
        {lista.map((a) => {
          const s = saldo(a);
          return (
            <li key={a.idx}>
              <details className="group">
                <summary
                  aria-label={`${a.nome}: ${plural(a.jogos, "jogo", "jogos")}, ${plural(a.vitorias, "vitória", "vitórias")}, ${plural(a.empates, "empate", "empates")}, ${plural(a.derrotas, "derrota", "derrotas")}, ${a.gols_pro} gols pró e ${a.gols_contra} contra`}
                  className={`grid ${COLUNAS_CONFRONTO} cursor-pointer list-none items-center py-2.5 pl-3 hover:bg-pitch-900 [&::-webkit-details-marker]:hidden`}
                >
                  <span className="flex min-w-0 items-center gap-2">
                    <Escudo id={a.escudo} nome={a.nome} />
                    <span className="truncate">{a.nome}</span>
                  </span>
                  {[a.jogos, a.vitorias, a.empates, a.derrotas].map((n, i) => (
                    <span key={i} className="text-right font-kit text-xl">
                      {n}
                    </span>
                  ))}
                  <span className={`text-right font-kit text-xl ${s > 0 ? "text-neon" : s < 0 ? "text-cartao" : ""}`}>
                    {s > 0 ? `+${s}` : s}
                  </span>
                  <span className="hidden text-right font-kit text-xl text-muted sm:block">
                    {Math.round(((3 * a.vitorias + a.empates) / (3 * a.jogos)) * 100)}%
                  </span>
                  <span aria-hidden="true" className="icone justify-self-end text-muted transition-transform group-open:rotate-180 motion-reduce:transition-none">
                    expand_more
                  </span>
                </summary>
                <div className="mb-4 ml-3 mt-1">
                  <ListaPartidas id={id} partidas={a.partidas} clube={clube} />
                </div>
              </details>
            </li>
          );
        })}
      </ul>
    </>
  );
}

function Destaque({ titulo, a, frase, cor }) {
  return (
    <section className="flex items-center gap-4 rounded-md bg-pitch-900 p-5">
      <Escudo id={a.escudo} nome={a.nome} className="size-14 drop-shadow-lg" />
      <div className="min-w-0">
        <h2 className={`font-kit text-sm font-semibold uppercase tracking-[0.2em] ${cor}`}>{titulo}</h2>
        <p className="truncate font-kit text-3xl font-bold uppercase leading-tight">{a.nome}</p>
        <p className="text-muted">{frase}</p>
      </div>
    </section>
  );
}

function Lendas({ id, clube }) {
  const { dados: l, erro } = useDados(() => api.lendas(id), [id]);
  if (erro) return <Erro mensagem={erro} />;
  if (!l) return null;
  // quem tem zero não entra no ranking
  const rankings = [
    ["Artilheiros", "gols", "gols", l.artilheiros],
    ["Garçons", "assistencias", "assistências", l.garcons],
    ["Mais jogos", "jogos", "jogos", l.mais_jogos],
  ].map(([titulo, campo, unidade, lista]) => [titulo, campo, unidade, lista.filter((j) => j[campo] > 0)]);
  return (
    <>
      <SalaDeTrofeus id={id} clube={clube} />
      <div className="grid grid-cols-1 gap-5 md:grid-cols-3">
        {rankings.map(([titulo, campo, unidade, lista]) => (
          <section key={titulo} className="rounded-md bg-pitch-900 p-5">
            <h2 className="mb-4 font-kit text-2xl font-semibold uppercase">{titulo}</h2>
            {lista[0] ? (
              <div className="flex items-center justify-center gap-4">
                <Rosto id={lista[0].player_id} className="size-20" />
                <Camisa nome={lista[0].nome} numero={lista[0][campo]} unidade={unidade} />
              </div>
            ) : (
              <p className="text-muted">Ninguém ainda.</p>
            )}
            <ol className="mt-5 space-y-1.5 text-sm">
              {lista.slice(1).map((j, i) => (
                <li key={j.player_id} className="flex items-baseline justify-between gap-3">
                  <span className="flex min-w-0 items-center gap-2">
                    <span className="font-kit text-muted">{i + 2}.</span>
                    <Rosto id={j.player_id} className="size-6" />
                    <span className="truncate">{j.nome}</span>
                  </span>
                  <span className="font-kit text-lg">{j[campo]}</span>
                </li>
              ))}
            </ol>
          </section>
        ))}
      </div>
      <Recordes id={id} r={l.recordes} clube={clube} />
    </>
  );
}

function Recordes({ id, r, clube }) {
  const [aberta, setAberta] = useState(null);
  const periodo = (s) => (s.de === s.ate ? `em ${dataBR(s.de)}` : `de ${dataBR(s.de)} a ${dataBR(s.ate)}`);
  const contra = (p) => `contra ${adversario(p, clube)}, ${p.mandante_idx === clube ? "em casa" : "fora"}, em ${dataBR(p.data)}`;
  const blocos = [
    r.goleada && ["Maior goleada", placar(r.goleada, clube).join("–"), contra(r.goleada), "text-neon", r.goleada.id],
    r.derrota && ["Pior derrota", placar(r.derrota, clube).join("–"), contra(r.derrota), "text-cartao", r.derrota.id],
    r.vitorias && ["Vitórias seguidas", r.vitorias.jogos, periodo(r.vitorias), "text-gold"],
    r.invencibilidade && ["Jogos sem perder", r.invencibilidade.jogos, periodo(r.invencibilidade), "text-gold"],
  ].filter(Boolean);
  if (blocos.length === 0) return null;
  return (
    <section className="mt-14">
      <h2 className="mb-5 font-kit text-3xl font-semibold uppercase">Recordes</h2>
      <div className="grid grid-cols-1 gap-px overflow-hidden rounded-md bg-pitch-700 sm:grid-cols-2 lg:grid-cols-4">
        {blocos.map(([titulo, valor, detalhe, cor, pid]) => {
          const Bloco = pid ? "button" : "div";
          return (
            <Bloco
              key={titulo}
              {...(pid && { onClick: () => setAberta(pid), "aria-haspopup": "dialog" })}
              className={`bg-pitch-900 p-5 text-left ${pid ? "hover:bg-pitch-800" : ""}`}
            >
              <span className="block text-xs uppercase text-muted">{titulo}</span>
              <span className={`block font-kit text-6xl font-extrabold leading-tight ${cor}`}>{valor}</span>
              <span className="block text-sm text-muted">{detalhe}</span>
              {pid && (
                <span className="mt-3 flex items-center gap-1 font-kit text-sm font-semibold uppercase tracking-wide text-muted">
                  Ver súmula <span aria-hidden="true" className="icone text-base">arrow_forward</span>
                </span>
              )}
            </Bloco>
          );
        })}
      </div>

      {r.hat_tricks.length > 0 && (
        <>
          <h3 className="mb-3 mt-10 font-kit text-2xl font-semibold uppercase">Hat-tricks</h3>
          <ul className="max-w-2xl divide-y divide-pitch-800">
            {r.hat_tricks.map((h) => (
              <li key={`${h.player_id}-${h.partida_id}`}>
                <button
                  onClick={() => setAberta(h.partida_id)}
                  aria-haspopup="dialog"
                  className="flex w-full items-center gap-3 py-2.5 pl-1 text-left hover:bg-pitch-900"
                >
                  <Rosto id={h.player_id} className="size-9" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-semibold">{h.nome}</span>
                    <span className="block truncate text-sm text-muted">{contra(h.partida)}</span>
                  </span>
                  <span className="font-kit text-3xl font-bold text-gold">{h.gols}</span>
                  <span className="w-10 text-sm text-muted">gols</span>
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
      {aberta !== null && <Sumula id={id} pid={aberta} onFechar={() => setAberta(null)} />}
    </section>
  );
}

function PeloMundo({ id, ano, clube }) {
  const { dados: m, erro } = useDados(() => api.mundo(id, ano), [id, ano]);
  if (erro) return <Erro mensagem={erro} />;
  if (!m) return null;
  return (
    <>
      <p className="mb-8 max-w-2xl text-sm text-muted">
        Somando as {m.partidas.toLocaleString("pt-BR")} partidas do mundo em {ano} que o Vestiário guardou, com todas as
        competições somadas. O time é o do último jogo de cada jogador.
      </p>
      <div className="grid grid-cols-1 gap-10 md:grid-cols-2">
        <RankingMundo titulo="Artilheiros" campo="gols" lista={m.artilheiros} clube={clube} />
        <RankingMundo titulo="Garçons" campo="assistencias" lista={m.garcons} clube={clube} />
      </div>
      <CampeoesDoAno id={id} ano={ano} clube={clube} />
    </>
  );
}

// "2025/26" vale para 2025 e para 2026
const daTemporada = (temporada, ano) => temporada.startsWith(String(ano)) || temporada.endsWith(`/${String(ano).slice(2)}`);

function CampeoesDoAno({ id, ano, clube }) {
  const { dados: titulos } = useDados(() => api.titulos(id), [id]);
  if (!titulos) return null;
  const doAno = titulos.filter((t) => daTemporada(t.temporada, ano));
  return (
    <section className="mt-14">
      <h2 className="mb-1 font-kit text-2xl font-semibold uppercase">Campeões</h2>
      <p className="mb-4 max-w-2xl text-sm text-muted">
        Competições de {ano} já decididas no save: a final jogada ou a liga com todos os jogos no Vestiário.
      </p>
      {doAno.length === 0 ? (
        <p className="text-muted">Nenhuma competição de {ano} decidida ainda.</p>
      ) : (
        <ul className="divide-y divide-pitch-800">
          {doAno.map((t) => {
            const nosso = t.campeao.idx === clube;
            return (
              <li key={t.chave} className={`grid grid-cols-1 gap-x-6 gap-y-1 border-l-4 py-2.5 pl-3 sm:grid-cols-[1fr_1.2fr] ${nosso ? "border-gold bg-pitch-900" : "border-transparent"}`}>
                <span className="min-w-0 truncate text-muted">
                  {t.nome} <span className="font-kit">{t.temporada}</span>
                </span>
                <span className="flex min-w-0 items-center gap-2">
                  <span aria-hidden="true" className="icone text-base text-gold">emoji_events</span>
                  <Escudo id={t.campeao.escudo} nome={t.campeao.nome} className="size-5" />
                  <span className={`truncate font-semibold ${nosso ? "text-destaque" : ""}`}>{t.campeao.nome}</span>
                  <span className="truncate text-sm text-muted">· vice {t.vice.nome}</span>
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function FaixaDeCampeao({ campeao, vice, clube }) {
  return (
    <div className="mb-10 flex flex-wrap items-center gap-x-5 gap-y-3 rounded-md border-l-4 border-gold bg-pitch-900 px-5 py-4">
      <span aria-hidden="true" className="icone text-gold" style={{ fontSize: "3rem" }}>emoji_events</span>
      <Escudo id={campeao.escudo} nome={campeao.nome} className="size-12 drop-shadow-lg" />
      <div className="min-w-0">
        <p className="font-kit text-sm font-semibold uppercase tracking-[0.2em] text-gold">Campeão</p>
        <p className={`truncate font-kit text-3xl font-extrabold uppercase leading-tight ${campeao.idx === clube ? "text-destaque" : ""}`}>
          {campeao.nome}
        </p>
      </div>
      {vice && (
        <p className="flex items-center gap-2 text-muted sm:ml-auto">
          <Escudo id={vice.escudo} nome={vice.nome} className="size-6" />
          vice: <span className={vice.idx === clube ? "text-destaque" : "text-chalk"}>{vice.nome}</span>
        </p>
      )}
    </div>
  );
}

// Assinatura dos títulos: a prateleira do vestiário, com as taças em pé e o rótulo de fita crepe embaixo de cada uma
function SalaDeTrofeus({ id, clube }) {
  const { dados: titulos } = useDados(() => api.titulos(id), [id]);
  if (!titulos) return null;
  const nossos = titulos.filter((t) => t.campeao.idx === clube);
  const vices = titulos.filter((t) => t.vice?.idx === clube);
  return (
    <section className="mb-14" aria-labelledby="sala-de-trofeus">
      <h2 id="sala-de-trofeus" className="mb-5 font-kit text-3xl font-semibold uppercase">
        Sala de troféus
      </h2>
      <div className={`prateleira ${nossos.length ? "" : "prateleira-vazia"}`}>
        {nossos.length > 0 ? (
          <ul className="flex flex-wrap items-end gap-x-8 gap-y-10 px-2">
            {nossos.map((t, i) => (
              <li key={t.chave} className="flex w-36 flex-col items-center text-center">
                <span aria-hidden="true" className="icone taca text-gold">emoji_events</span>
                <span className="fita mt-3 text-sm" style={{ "--giro": `${i % 2 ? 1.5 : -2}deg` }}>
                  {t.nome} {t.temporada}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="max-w-xl px-2 pb-1 text-muted">
            Nenhum título confirmado ainda. O Vestiário só conta um título quando tem o campeonato inteiro: a final jogada
            ou todas as rodadas da liga. Sincronize ao longo da temporada para nenhuma rodada se perder.
          </p>
        )}
      </div>
      {vices.length > 0 && (
        <p className="mt-4 text-sm text-muted">
          Vice: {vices.map((t) => `${t.nome} ${t.temporada}`).join(" · ")}
        </p>
      )}
    </section>
  );
}

function RankingMundo({ titulo, campo, lista, clube }) {
  return (
    <section>
      <h2 className="mb-4 font-kit text-2xl font-semibold uppercase">{titulo}</h2>
      {lista.length === 0 && <p className="text-muted">Ninguém ainda.</p>}
      <ol className="divide-y divide-pitch-800">
        {lista.map((l, i) => {
          const posicao = lista.findIndex((x) => x[campo] === l[campo]) + 1; // empatados dividem a posição
          const empatado = i > 0 && lista[i - 1][campo] === l[campo];
          const nosso = l.time_idx === clube;
          return (
            <li
              key={l.player_id}
              className={`flex items-center gap-3 border-l-4 py-2 pl-2 ${nosso ? "border-destaque bg-pitch-900" : "border-transparent"}`}
            >
              <span className={`w-6 text-right font-kit text-lg text-muted ${empatado ? "invisible" : ""}`}>{posicao}</span>
              <Rosto id={l.player_id} className="size-9" />
              <span className="min-w-0 flex-1">
                <span className={`block truncate ${nosso ? "font-semibold text-destaque" : ""}`}>{l.nome}</span>
                <span className="flex min-w-0 items-center gap-1.5 text-sm text-muted">
                  <Escudo id={l.escudo} nome={l.time ?? "?"} className="size-4" />
                  <span className="min-w-0 truncate">{l.time}</span>
                  <span className="whitespace-nowrap">· {plural(l.jogos, "jogo", "jogos")}</span>
                </span>
              </span>
              <span className={`font-kit text-3xl font-bold ${posicao === 1 ? "text-gold" : ""}`}>{l[campo]}</span>
            </li>
          );
        })}
      </ol>
    </section>
  );
}


// O líder de cada ranking vira a camisa do clube vista de costas: nome em cima, recorde como número.
function Camisa({ nome, numero, unidade }) {
  const sobrenome = nome.split(" ").at(-1);
  return (
    <figure className="flex flex-col items-center">
      <svg viewBox="0 0 100 100" className="h-36 w-36" role="img" aria-label={`${nome}: ${numero} ${unidade}`}>
        <path
          d="M30 8 L42 4 Q50 9 58 4 L70 8 L94 22 L84 42 L74 36 L74 96 L26 96 L26 36 L16 42 L6 22 Z"
          className="fill-camisa stroke-numero"
          strokeWidth="1.5"
          strokeLinejoin="round"
        />
        <text x="50" y="33" textAnchor="middle" className="fill-numero font-kit" fontSize="9" fontWeight="700" letterSpacing="0.5">
          {sobrenome.toUpperCase()}
        </text>
        <text x="50" y="78" textAnchor="middle" className="fill-numero font-kit" fontSize="40" fontWeight="800">
          {numero}
        </text>
      </svg>
      <figcaption className="mt-1 text-center font-kit text-xl font-semibold uppercase text-gold">{nome}</figcaption>
    </figure>
  );
}
