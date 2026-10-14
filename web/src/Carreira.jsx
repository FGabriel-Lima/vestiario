import { useEffect, useState } from "react";
import { api, dataBR } from "./api.js";

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
    <button onClick={onVoltar} className="mb-4 text-muted hover:text-chalk">
      <span className="icone">arrow_back</span> Carreiras
    </button>
  );

  if (erro) return (<>{voltar}<Erro mensagem={erro} /></>);
  if (!carreira) return <p className="text-muted">Carregando…</p>;

  return (
    <>
      {voltar}
      <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-kit text-5xl font-bold uppercase">{carreira.clube_nome}</h1>
          <p className="text-muted">No jogo: {dataBR(carreira.data_jogo)}</p>
        </div>
        {aba !== "Lendas" && ano !== null && (
          <select
            value={ano}
            onChange={(e) => setAno(Number(e.target.value))}
            className="rounded-lg bg-pitch-800 px-3 py-2"
          >
            {carreira.temporadas.map((t) => (
              <option key={t} value={t}>
                Temporada {t}
              </option>
            ))}
          </select>
        )}
      </header>

      <nav className="mb-6 flex gap-1 border-b border-pitch-700">
        {ABAS.map((a) => (
          <button
            key={a}
            onClick={() => setAba(a)}
            className={`px-4 py-2 ${a === aba ? "border-b-2 border-neon text-chalk" : "text-muted hover:text-chalk"}`}
          >
            {a}
          </button>
        ))}
      </nav>

      {ano === null && aba !== "Lendas" ? (
        <p className="text-muted">Nenhuma partida do clube registrada ainda.</p>
      ) : (
        <>
          {aba === "Visão geral" && <VisaoGeral id={id} ano={ano} clube={carreira.clube_idx} />}
          {aba === "Elenco" && <Elenco id={id} ano={ano} />}
          {aba === "Partidas" && <Partidas id={id} ano={ano} clube={carreira.clube_idx} />}
          {aba === "Lendas" && <Lendas id={id} />}
        </>
      )}
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
  return <p className="rounded-lg bg-red-900/60 p-3">{mensagem}</p>;
}

function VisaoGeral({ id, ano, clube }) {
  const { dados: r, erro } = useDados(() => api.resumo(id, ano), [id, ano]);
  if (erro) return <Erro mensagem={erro} />;
  if (!r) return null;
  const numeros = [
    ["Jogos", r.jogos],
    ["Vitórias", r.vitorias],
    ["Empates", r.empates],
    ["Derrotas", r.derrotas],
    ["Gols pró", r.gols_pro],
    ["Gols contra", r.gols_contra],
  ];
  return (
    <>
      <div className="mb-8 grid grid-cols-3 gap-3 sm:grid-cols-6">
        {numeros.map(([rotulo, valor]) => (
          <div key={rotulo} className="rounded-xl bg-pitch-800 p-4 text-center">
            <p className="font-kit text-4xl font-bold">{valor}</p>
            <p className="text-xs uppercase text-muted">{rotulo}</p>
          </div>
        ))}
      </div>
      <h2 className="mb-2 font-kit text-2xl uppercase">Últimos resultados</h2>
      <ListaPartidas partidas={r.ultimas} clube={clube} />
    </>
  );
}

function Elenco({ id, ano }) {
  const { dados: linhas, erro } = useDados(() => api.elenco(id, ano), [id, ano]);
  const [ordem, setOrdem] = useState("jogos");
  if (erro) return <Erro mensagem={erro} />;
  if (!linhas) return null;
  const ordenadas = [...linhas].sort((a, b) => (ordem === "nome" ? a.nome.localeCompare(b.nome) : b[ordem] - a[ordem]));
  const colunas = [
    ["nome", "Jogador"],
    ["jogos", "J"],
    ["gols", "G"],
    ["assistencias", "A"],
  ];
  return (
    <table className="w-full text-left">
      <thead>
        <tr className="text-muted">
          {colunas.map(([k, rotulo]) => (
            <th key={k} className={`py-2 ${k !== "nome" ? "w-16 text-right" : ""}`}>
              <button onClick={() => setOrdem(k)} className={ordem === k ? "text-neon" : ""}>
                {rotulo}
              </button>
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {ordenadas.map((l) => (
          <tr key={l.player_id} className={`border-t border-pitch-800 ${l.no_elenco ? "" : "text-muted"}`}>
            <td className="py-2">
              {l.nome} {!l.no_elenco && <span className="ml-2 text-xs uppercase">saiu</span>}
            </td>
            <td className="text-right">{l.jogos}</td>
            <td className="text-right">{l.gols}</td>
            <td className="text-right">{l.assistencias}</td>
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
      <h2 className="mb-2 font-kit text-2xl uppercase">Disputadas</h2>
      <ListaPartidas partidas={ps.filter((p) => p.disputada)} clube={clube} />
      {futuras.length > 0 && (
        <>
          <h2 className="mb-2 mt-8 font-kit text-2xl uppercase">Próximas</h2>
          <ListaPartidas partidas={futuras} clube={clube} />
        </>
      )}
    </>
  );
}

function ListaPartidas({ partidas, clube }) {
  if (partidas.length === 0) return <p className="text-muted">Nenhuma partida.</p>;
  return (
    <ul className="divide-y divide-pitch-800">
      {partidas.map((p) => (
        <li key={p.id} className="grid grid-cols-[6rem_1fr_auto_1fr] items-center gap-3 py-2">
          <span className="text-sm text-muted">{dataBR(p.data)}</span>
          <span className={`text-right ${p.mandante_idx === clube ? "font-semibold" : ""}`}>{p.mandante}</span>
          <span className="min-w-16 rounded bg-pitch-800 px-2 text-center font-kit text-xl">
            {p.disputada ? `${p.gols_mandante} x ${p.gols_visitante}` : "x"}
            {p.penaltis_mandante + p.penaltis_visitante > 0 && (
              <span className="block text-xs text-muted">
                pên. {p.penaltis_mandante}-{p.penaltis_visitante}
              </span>
            )}
          </span>
          <span className={p.visitante_idx === clube ? "font-semibold" : ""}>{p.visitante}</span>
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
    ["Artilheiros", "gols", l.artilheiros],
    ["Garçons", "assistencias", l.garcons],
    ["Mais jogos", "jogos", l.mais_jogos],
  ];
  return (
    <div className="grid gap-4 md:grid-cols-3">
      {rankings.map(([titulo, campo, lista]) => (
        <section key={titulo} className="rounded-xl bg-pitch-900 p-4">
          <h2 className="mb-3 font-kit text-2xl uppercase">{titulo}</h2>
          {lista[0] && <Camisa nome={lista[0].nome} numero={lista[0][campo]} />}
          <ol className="mt-3 space-y-1 text-sm">
            {lista.slice(1).map((j, i) => (
              <li key={j.player_id} className="flex justify-between">
                <span>
                  <span className="text-muted">{i + 2}.</span> {j.nome}
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

// O líder de cada ranking vira uma camisa com o recorde como número.
function Camisa({ nome, numero }) {
  return (
    <div className="flex flex-col items-center">
      <svg viewBox="0 0 100 100" className="h-28 w-28">
        <path
          d="M30 8 L42 4 Q50 12 58 4 L70 8 L94 22 L84 42 L74 36 L74 96 L26 96 L26 36 L16 42 L6 22 Z"
          className="fill-pitch-700 stroke-gold"
          strokeWidth="2"
        />
        <text x="50" y="74" textAnchor="middle" className="fill-gold font-kit" fontSize="38" fontWeight="700">
          {numero}
        </text>
      </svg>
      <p className="font-kit text-xl uppercase text-gold">{nome}</p>
    </div>
  );
}
