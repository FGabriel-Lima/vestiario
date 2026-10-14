import { useEffect, useState } from "react";
import { api, dataBR } from "./api.js";
import Escudo from "./Escudo.jsx";

const ABAS = ["Visão geral", "Elenco", "Partidas", "Lendas"];

export default function Carreira({ id, onVoltar }) {
  const [carreira, setCarreira] = useState(null);
  const [ano, setAno] = useState(null);
  const [aba, setAba] = useState(ABAS[0]);
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

  const voltar = (
    <button onClick={onVoltar} className="mb-6 text-muted hover:text-chalk">
      <span className="icone">arrow_back</span> Carreiras
    </button>
  );

  if (erro) return (<>{voltar}<Erro mensagem={erro} /></>);
  if (!carreira) return <p className="text-muted">Abrindo o vestiário…</p>;

  return (
    <>
      {voltar}
      <header className="mb-8 flex flex-wrap items-end justify-between gap-6">
        <div className="flex items-end gap-5">
          <Escudo id={carreira.escudo} nome={carreira.clube_nome} className="size-20 drop-shadow-lg sm:size-28" />
          <div>
            <span className="fita text-lg">No jogo: {dataBR(carreira.data_jogo)}</span>
            <h1 className="mt-3 font-kit text-6xl font-extrabold uppercase leading-none tracking-tight sm:text-8xl">
              {carreira.clube_nome}
            </h1>
          </div>
        </div>
        {aba !== "Lendas" && ano !== null && (
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

      <nav role="tablist" aria-label="Seções da carreira" className="mb-8 flex gap-1 overflow-x-auto shadow-[inset_0_-1px_0_var(--color-pitch-700)]">
        {ABAS.map((a) => (
          <button
            key={a}
            role="tab"
            aria-selected={a === aba}
            onClick={() => setAba(a)}
            className={`whitespace-nowrap border-b-2 px-4 py-2 font-kit text-xl font-semibold uppercase tracking-wide ${
              a === aba ? "border-neon text-chalk" : "border-transparent text-muted hover:text-chalk"
            }`}
          >
            {a}
          </button>
        ))}
      </nav>

      <div role="tabpanel" aria-label={aba}>
        {ano === null && aba !== "Lendas" ? (
          <p className="text-muted">Nenhuma partida do clube registrada ainda. Jogue uma partida, salve e sincronize.</p>
        ) : (
          <>
            {aba === "Visão geral" && <VisaoGeral id={id} ano={ano} clube={carreira.clube_idx} />}
            {aba === "Elenco" && <Elenco id={id} ano={ano} />}
            {aba === "Partidas" && <Partidas id={id} ano={ano} clube={carreira.clube_idx} />}
            {aba === "Lendas" && <Lendas id={id} />}
          </>
        )}
      </div>
    </>
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

// Resultado do ponto de vista do clube do usuário. Decisão nos pênaltis conta como empate.
function resultado(p, clube) {
  const [pro, contra] =
    p.mandante_idx === clube ? [p.gols_mandante, p.gols_visitante] : [p.gols_visitante, p.gols_mandante];
  return pro > contra ? "V" : pro < contra ? "D" : "E";
}

const COR_RESULTADO = { V: "bg-neon text-pitch-950", E: "bg-muted text-pitch-950", D: "bg-cartao text-pitch-950" };
const BORDA_RESULTADO = { V: "border-neon", E: "border-muted", D: "border-cartao" };

function VisaoGeral({ id, ano, clube }) {
  const { dados: r, erro } = useDados(() => api.resumo(id, ano), [id, ano]);
  if (erro) return <Erro mensagem={erro} />;
  if (!r) return null;
  const aproveitamento = r.jogos ? Math.round(((3 * r.vitorias + r.empates) / (3 * r.jogos)) * 100) : 0;
  const campanha = [
    ["vitorias", "Vitórias", r.vitorias],
    ["empates", "Empates", r.empates],
    ["derrotas", "Derrotas", r.derrotas],
  ];
  return (
    <>
      <section className="mb-10 grid gap-8 md:grid-cols-[auto_1fr] md:items-end">
        <div>
          <p className="font-kit text-sm uppercase tracking-[0.2em] text-muted">Aproveitamento</p>
          <p className="font-kit text-8xl font-extrabold leading-none text-gold">
            {aproveitamento}
            <span className="text-5xl">%</span>
          </p>
          <p className="mt-1 text-muted">dos pontos em {r.jogos} jogos</p>
        </div>
        <dl className="grid grid-cols-3 gap-px overflow-hidden rounded-md bg-pitch-700 sm:grid-cols-5">
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
        </dl>
      </section>

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
      <ListaPartidas partidas={r.ultimas} clube={clube} />
    </>
  );
}

const COLUNAS = [
  ["nome", "Jogador"],
  ["jogos", "Jogos"],
  ["gols", "Gols"],
  ["assistencias", "Assist."],
];

function Elenco({ id, ano }) {
  const { dados: linhas, erro } = useDados(() => api.elenco(id, ano), [id, ano]);
  const [ordem, setOrdem] = useState("jogos");
  if (erro) return <Erro mensagem={erro} />;
  if (!linhas) return null;
  const ordenadas = [...linhas].sort((a, b) =>
    ordem === "nome" ? a.nome.localeCompare(b.nome, "pt-BR") : b[ordem] - a[ordem] || a.nome.localeCompare(b.nome, "pt-BR"),
  );
  return (
    <table className="w-full text-left">
      <thead>
        <tr className="border-b border-pitch-700 font-kit text-lg uppercase tracking-wide text-muted">
          {COLUNAS.map(([k, rotulo]) => (
            <th
              key={k}
              aria-sort={ordem === k ? (k === "nome" ? "ascending" : "descending") : "none"}
              className={`py-2 font-semibold ${k !== "nome" ? "w-20 text-right" : ""}`}
            >
              <button onClick={() => setOrdem(k)} className={ordem === k ? "text-neon" : "hover:text-chalk"}>
                {rotulo}
              </button>
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {ordenadas.map((l) => (
          <tr key={l.player_id} className={`border-b border-pitch-800 ${l.no_elenco ? "" : "text-muted"}`}>
            <td className="py-2.5">
              {l.nome}
              {!l.no_elenco && <span className="ml-2 font-kit text-sm uppercase tracking-wide">saiu</span>}
            </td>
            <td className="text-right font-kit text-xl">{l.jogos}</td>
            <td className="text-right font-kit text-xl">{l.gols}</td>
            <td className="text-right font-kit text-xl">{l.assistencias}</td>
          </tr>
        ))}
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
      <ListaPartidas partidas={ps.filter((p) => p.disputada)} clube={clube} />
      {futuras.length > 0 && (
        <>
          <h2 className="mb-3 mt-10 font-kit text-2xl font-semibold uppercase text-muted">Próximas</h2>
          <ListaPartidas partidas={futuras} clube={clube} />
        </>
      )}
    </>
  );
}

function ListaPartidas({ partidas, clube }) {
  if (partidas.length === 0) return <p className="text-muted">Nenhuma partida nesta temporada.</p>;
  return (
    <ul className="divide-y divide-pitch-800">
      {partidas.map((p) => (
        <li
          key={p.id}
          className={`grid grid-cols-[4.5rem_1fr_auto_1fr] items-center gap-3 border-l-4 py-2.5 pl-3 sm:grid-cols-[6rem_1fr_auto_1fr] ${
            p.disputada ? BORDA_RESULTADO[resultado(p, clube)] : "border-transparent"
          }`}
        >
          <span className="text-sm text-muted">{dataBR(p.data)}</span>
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
        </li>
      ))}
    </ul>
  );
}

function Lendas({ id }) {
  const { dados: l, erro } = useDados(() => api.lendas(id), [id]);
  if (erro) return <Erro mensagem={erro} />;
  if (!l) return null;
  const rankings = [
    ["Artilheiros", "gols", "gols", l.artilheiros],
    ["Garçons", "assistencias", "assistências", l.garcons],
    ["Mais jogos", "jogos", "jogos", l.mais_jogos],
  ];
  return (
    <div className="grid gap-5 md:grid-cols-3">
      {rankings.map(([titulo, campo, unidade, lista]) => (
        <section key={titulo} className="rounded-md bg-pitch-900 p-5">
          <h2 className="mb-4 font-kit text-2xl font-semibold uppercase">{titulo}</h2>
          {lista[0] ? (
            <Camisa nome={lista[0].nome} numero={lista[0][campo]} unidade={unidade} />
          ) : (
            <p className="text-muted">Ninguém ainda.</p>
          )}
          <ol className="mt-5 space-y-1.5 text-sm">
            {lista.slice(1).map((j, i) => (
              <li key={j.player_id} className="flex items-baseline justify-between gap-3">
                <span className="truncate">
                  <span className="mr-1 font-kit text-muted">{i + 2}.</span> {j.nome}
                </span>
                <span className="font-kit text-lg">{j[campo]}</span>
              </li>
            ))}
          </ol>
        </section>
      ))}
    </div>
  );
}

// O líder de cada ranking vira a camisa vista de costas: nome em cima, recorde como número.
function Camisa({ nome, numero, unidade }) {
  const sobrenome = nome.split(" ").at(-1);
  return (
    <figure className="flex flex-col items-center">
      <svg viewBox="0 0 100 100" className="h-36 w-36" role="img" aria-label={`${nome}: ${numero} ${unidade}`}>
        <path
          d="M30 8 L42 4 Q50 9 58 4 L70 8 L94 22 L84 42 L74 36 L74 96 L26 96 L26 36 L16 42 L6 22 Z"
          className="fill-pitch-700 stroke-gold"
          strokeWidth="1.5"
          strokeLinejoin="round"
        />
        <text x="50" y="33" textAnchor="middle" className="fill-gold font-kit" fontSize="9" fontWeight="700" letterSpacing="0.5">
          {sobrenome.toUpperCase()}
        </text>
        <text x="50" y="78" textAnchor="middle" className="fill-gold font-kit" fontSize="40" fontWeight="800">
          {numero}
        </text>
      </svg>
      <figcaption className="mt-1 text-center font-kit text-xl font-semibold uppercase text-gold">{nome}</figcaption>
    </figure>
  );
}
