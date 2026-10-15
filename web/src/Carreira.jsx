import { useEffect, useRef, useState } from "react";
import { api, dataBR } from "./api.js";
import Escudo from "./Escudo.jsx";
import Rosto from "./Rosto.jsx";

const ABAS = ["Visão geral", "Elenco", "Partidas", "Campeonatos", "Transferências", "Adversários", "Lendas", "Pelo mundo"];
// Abas que olham a carreira inteira e não usam o seletor de temporada
// (Campeonatos tem o próprio seletor de edição, porque temporada de liga europeia atravessa o ano)
const DA_CARREIRA = new Set(["Campeonatos", "Transferências", "Adversários", "Lendas"]);

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
    <div style={estiloDoClube(carreira.cores)}>
      {voltar}
      {carreira.cores?.length > 0 && <div aria-hidden="true" className="cachecol mb-8" />}
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
        {!DA_CARREIRA.has(aba) && ano !== null && (
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
              a === aba ? "border-destaque text-chalk" : "border-transparent text-muted hover:text-chalk"
            }`}
          >
            {a}
          </button>
        ))}
      </nav>

      <div role="tabpanel" aria-label={aba}>
        {ano === null && !DA_CARREIRA.has(aba) ? (
          <p className="text-muted">Nenhuma partida do clube registrada ainda. Jogue uma partida, salve e sincronize.</p>
        ) : (
          <>
            {aba === "Visão geral" && (
              <VisaoGeral id={id} ano={ano} clube={carreira.clube_idx} orcamento={carreira.orcamento} dataJogo={carreira.data_jogo} />
            )}
            {aba === "Elenco" && <Elenco id={id} ano={ano} dataJogo={carreira.data_jogo} />}
            {aba === "Partidas" && <Partidas id={id} ano={ano} clube={carreira.clube_idx} />}
            {aba === "Campeonatos" && <Campeonatos id={id} clube={carreira.clube_idx} />}
            {aba === "Transferências" && <Transferencias id={id} />}
            {aba === "Adversários" && <Adversarios id={id} clube={carreira.clube_idx} />}
            {aba === "Lendas" && <Lendas id={id} clube={carreira.clube_idx} />}
            {aba === "Pelo mundo" && <PeloMundo id={id} ano={ano} clube={carreira.clube_idx} />}
          </>
        )}
      </div>
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

function VisaoGeral({ id, ano, clube, orcamento, dataJogo }) {
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
      <section className="mb-10 grid grid-cols-1 gap-8 md:grid-cols-[auto_1fr] md:items-end">
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

      {orcamento != null && (
        <p className="-mt-4 mb-10 flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span className="font-kit text-sm uppercase tracking-[0.2em] text-muted">Orçamento de transferências</span>
          <Dinheiro valor={orcamento} className="font-kit text-3xl font-bold text-gold" />
          <span className="text-sm text-muted">em {dataBR(dataJogo)}</span>
        </p>
      )}

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

// [chave, rótulo, valor para ordenar, ordem crescente?, só a partir do sm (no celular, idade e contrato vão para baixo do nome)]
const COLUNAS = [
  ["posicao", "Pos.", (l) => l.posicao ?? 99, true, true],
  ["nome", "Jogador", (l) => l.nome, true],
  ["idade", "Idade", (l) => l.idade ?? 99, true, true],
  ["jogos", "Jogos", (l) => l.jogos],
  ["gols", "Gols", (l) => l.gols],
  ["assistencias", "Assist.", (l) => l.assistencias],
  ["salario", "Salário/sem.", (l) => l.contrato?.salario_semanal ?? -1, false, true],
  ["multa", "Multa", (l) => l.contrato?.multa ?? -1, false, true],
  ["fim", "Contrato até", (l) => l.contrato?.fim ?? "9999", true, true],
];

const CURTOS = { jogos: "J", gols: "G", assistencias: "A" };

const comparar = (x, y) => (typeof x === "string" ? x.localeCompare(y, "pt-BR") : x - y);

function Elenco({ id, ano, dataJogo }) {
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
                    <span className="block">
                      {l.nome}
                      {!l.no_elenco && <span className="ml-2 font-kit text-sm uppercase tracking-wide">saiu</span>}
                    </span>
                    <span className={`flex items-center gap-2 text-sm sm:hidden ${vencendo(c) ? "text-gold" : "text-muted"}`}>
                      <Posicao codigo={l.posicao} className="w-9 py-0 text-xs" />
                      {/* no celular só idade e mês/ano do fim do contrato; salário e multa ficam nas colunas do desktop */}
                      {[l.idade && `${l.idade} anos`, c && `até ${dataBR(c.fim).slice(3)}`].filter(Boolean).join(" · ")}
                    </span>
                  </span>
                </div>
              </td>
              <td className="hidden text-right font-kit text-xl sm:table-cell">{l.idade}</td>
              <td className="text-right font-kit text-xl">{l.jogos}</td>
              <td className="text-right font-kit text-xl">{l.gols}</td>
              <td className="text-right font-kit text-xl">{l.assistencias}</td>
              <td className="hidden text-right font-kit text-xl sm:table-cell">{c && <Dinheiro valor={c.salario_semanal} />}</td>
              <td className="hidden text-right font-kit text-xl sm:table-cell">
                {c && (c.multa ? <Dinheiro valor={c.multa} /> : <span className="text-base text-muted">sem multa</span>)}
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
          <ListaPartidas id={id} partidas={futuras} clube={clube} />
        </>
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

function Campeonatos({ id, clube }) {
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
      <Edicao key={atual} id={id} chave={atual} clube={clube} />
    </>
  );
}

function Edicao({ id, chave, clube }) {
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

      {e.fases.map((f, i) =>
        f.tipo === "jogos" && f.titulo !== "Fase preliminar" && e.chaveamento.length > 0 ? null : f.tipo === "tabela" ? (
          <section key={i} className="mb-12">
            <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
              <h3 className="font-kit text-2xl font-semibold uppercase">{f.titulo}</h3>
              <p className="text-sm text-muted">
                {f.rodadas_jogadas} de {plural(f.rodadas_total, "rodada", "rodadas")} jogadas
              </p>
            </div>
            <div className={f.grupos.length > 1 ? "grid grid-cols-1 gap-x-8 gap-y-10 lg:grid-cols-2" : ""}>
              {f.grupos.map((g, k) => (
                <Classificacao key={k} titulo={g.titulo} linhas={g.linhas} clube={clube} compacta={f.grupos.length > 1} />
              ))}
            </div>
            <p className="mt-3 text-xs text-muted">
              Ordem: pontos, vitórias, saldo de gols, gols pró e confronto direto. Empatados em tudo dividem a posição.
            </p>
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

      {e.chaveamento.length > 0 && <Chaveamento id={id} colunas={e.chaveamento} clube={clube} />}

      {temTabela && e.partidas_clube.length > 0 && (
        <section>
          <h3 className="mb-3 font-kit text-2xl font-semibold uppercase">Seus jogos</h3>
          <ListaPartidas id={id} partidas={e.partidas_clube} clube={clube} />
        </section>
      )}
    </>
  );
}

// Assinatura do mata-mata: a chave riscada a giz. As linhas só aparecem quando os times da fase seguinte vêm mesmo
// do par (o banco confere); com dado faltando ou trocado no save, os cards ficam soltos para não ligar times errados.
function Chaveamento({ id, colunas, clube }) {
  const [aberta, setAberta] = useState(null);
  const liga = (i) => colunas[i].encaixa;
  return (
    <section className="mb-12" aria-label="Chaveamento">
      <h3 className="mb-4 font-kit text-2xl font-semibold uppercase">Mata-mata</h3>
      <div className="relative -mx-4 overflow-x-auto px-4 pb-4 sm:mx-0 sm:px-0">
        {/* colunas flexíveis: no desktop a chave inteira cabe; só rola de lado quando falta espaço */}
        <div className="grid auto-cols-[minmax(11rem,1fr)] grid-flow-col gap-8" style={{ maxWidth: `${colunas.length * 18}rem` }}>
          {colunas.map((col, i) => {
            const pares = liga(i)
              ? col.confrontos.filter((_, k) => k % 2 === 0).map((c, k) => [c, col.confrontos[2 * k + 1]])
              : col.confrontos.map((c) => [c]);
            const recebe = i > 0 && liga(i - 1);
            return (
              <div key={col.titulo} className="flex min-w-0 flex-col">
                <h4 className="mb-3 font-kit text-lg font-semibold uppercase text-muted">
                  {col.titulo} <span className="font-normal">· {col.confrontos.length}</span>
                </h4>
                <div className="flex flex-1 flex-col justify-around gap-4">
                  {pares.map((par, k) => (
                    <div key={k} className={`flex flex-1 flex-col justify-around gap-4 ${par.length === 2 ? "chave-par" : ""}`}>
                      {par.map((c, j) => (
                        <Confronto key={j} c={c} clube={clube} recebe={recebe} onAbrir={setAberta} />
                      ))}
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </div>
      {aberta !== null && <Sumula id={id} pid={aberta} onFechar={() => setAberta(null)} />}
    </section>
  );
}

function Confronto({ c, clube, recebe, onAbrir }) {
  const decidido = c.times.some((t) => t.vencedor);
  return (
    <div className={`rounded-md bg-pitch-900 ${recebe ? "chave-entrada" : ""}`}>
      <ul className="px-3 pt-2.5">
        {c.times.map((t) => (
          <li
            key={t.idx}
            className={`flex items-center gap-2 py-0.5 ${decidido && !t.vencedor ? "text-muted" : ""} ${t.vencedor ? "font-semibold" : ""}`}
          >
            <Escudo id={t.escudo} nome={t.nome ?? "?"} className={`size-5 ${decidido && !t.vencedor ? "opacity-50" : ""}`} />
            <span className={`min-w-0 flex-1 truncate ${t.idx === clube ? "text-destaque" : ""}`}>{t.nome}</span>
            {t.vencedor && <span className="sr-only">(passou)</span>}
            <span className="font-kit text-xl font-bold">{t.gols ?? "–"}</span>
            {t.penaltis !== null && <span className="w-6 font-kit text-sm text-muted">({t.penaltis})</span>}
          </li>
        ))}
      </ul>
      <div className="mt-1.5 flex gap-1 border-t border-pitch-800 px-2 py-1.5">
        {c.jogos.map((j, k) => {
          const rotulo = c.jogos.length === 1 ? "Jogo único" : k === 0 ? "Ida" : "Volta";
          return j.disputada ? (
            <button
              key={j.id}
              onClick={() => onAbrir(j.id)}
              aria-haspopup="dialog"
              className="rounded-sm px-2 py-0.5 font-kit text-sm uppercase tracking-wide text-muted hover:bg-pitch-800 hover:text-chalk"
            >
              {rotulo} {j.placar.replace("-", "–")}
            </button>
          ) : (
            <span key={j.id} className="px-2 py-0.5 font-kit text-sm uppercase tracking-wide text-muted/70">
              {rotulo} {dataBR(j.data).slice(0, 5)}
            </span>
          );
        })}
      </div>
    </div>
  );
}

// Colunas que somem no celular (e nas tabelas de grupo, que dividem a largura)
const DETALHE = "hidden sm:table-cell";

function Classificacao({ titulo, linhas, clube, compacta }) {
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
          <th className="w-8 py-2 text-right font-semibold">
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
        </tr>
      </thead>
      <tbody>
        {linhas.map((l) => {
          const nosso = l.idx === clube;
          const saldo = l.gols_pro - l.gols_contra;
          return (
            <tr key={l.idx} aria-current={nosso ? "true" : undefined} className={`border-b border-pitch-800 ${nosso ? "linha-do-clube" : ""}`}>
              <td className="py-2 text-right font-kit text-lg text-muted">{l.posicao}</td>
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
              <td className={`text-right font-kit text-lg ${saldo > 0 ? "text-neon" : saldo < 0 ? "text-cartao" : "text-muted"}`}>
                {saldo > 0 ? `+${saldo}` : saldo}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
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

function Transferencias({ id }) {
  const { dados: t, erro } = useDados(() => api.transferencias(id), [id]);
  if (erro) return <Erro mensagem={erro} />;
  if (!t) return null;
  if (t.janelas.length === 0) {
    return (
      <p className="max-w-xl text-muted">
        Nenhuma mudança no elenco{t.primeira && ` desde ${dataBR(t.primeira)}`}. Depois da próxima janela de
        transferências no jogo, salve e sincronize: quem chegou e quem saiu aparece aqui, com clube e valor.
      </p>
    );
  }
  return (
    <>
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
  const rankings = [
    ["Artilheiros", "gols", "gols", l.artilheiros],
    ["Garçons", "assistencias", "assistências", l.garcons],
    ["Mais jogos", "jogos", "jogos", l.mais_jogos],
  ];
  return (
    <>
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
      <p className="mb-8 max-w-2xl text-muted">
        As {m.partidas.toLocaleString("pt-BR")} partidas do mundo em {ano} que o Vestiário guardou, com todas as
        competições somadas. O time é o do último jogo de cada jogador.
      </p>
      <div className="grid grid-cols-1 gap-10 md:grid-cols-2">
        <RankingMundo titulo="Artilheiros" campo="gols" lista={m.artilheiros} clube={clube} />
        <RankingMundo titulo="Garçons" campo="assistencias" lista={m.garcons} clube={clube} />
      </div>
    </>
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
