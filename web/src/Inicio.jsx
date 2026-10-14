import { useEffect, useState } from "react";
import { api, dataBR, dataHoraBR } from "./api.js";
import Escudo from "./Escudo.jsx";

export default function Inicio({ onAbrir }) {
  const [carreiras, setCarreiras] = useState(null);
  const [sincronizando, setSincronizando] = useState(false);
  const [resultado, setResultado] = useState(null);
  const [erro, setErro] = useState(null);

  const carregar = () => api.carreiras().then(setCarreiras).catch((e) => setErro(e.message));
  useEffect(() => {
    carregar();
  }, []);

  async function sincronizar() {
    setSincronizando(true);
    setErro(null);
    try {
      setResultado(await api.sincronizar());
      await carregar();
    } catch (e) {
      setErro(e.message);
    } finally {
      setSincronizando(false);
    }
  }

  return (
    <>
      <header className="mb-10 flex flex-wrap items-end justify-between gap-6">
        <div>
          <h1 className="font-kit text-6xl font-extrabold uppercase leading-none tracking-tight sm:text-7xl">
            Vestiário
          </h1>
          <p className="mt-2 text-muted">Suas carreiras da Master League, direto do save do PES.</p>
        </div>
        <button
          onClick={sincronizar}
          disabled={sincronizando}
          className="flex items-center gap-2 rounded-md bg-neon px-5 py-3 font-kit text-xl font-bold uppercase tracking-wide text-pitch-950 hover:brightness-110 disabled:opacity-60"
        >
          <span className={`icone ${sincronizando ? "animate-spin motion-reduce:animate-none" : ""}`}>sync</span>
          {sincronizando ? "Lendo os saves…" : "Sincronizar"}
        </button>
      </header>

      {erro && <p className="mb-6 rounded-md border-l-4 border-cartao bg-pitch-900 p-4">{erro}</p>}
      {resultado && <ResultadoSync resultado={resultado} />}

      {carreiras?.length === 0 && (
        <p className="max-w-md text-muted">
          Nenhuma carreira ainda. Salve a Master League no PES e clique em <strong className="text-chalk">Sincronizar</strong>.
        </p>
      )}
      {carreiras?.length > 0 && (
        <ul className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {carreiras.map((c, i) => (
            <li key={c.id}>
              <button
                onClick={() => onAbrir(c.id)}
                className="armario w-full rounded-md border border-pitch-700 bg-pitch-800 px-6 pb-6 text-left"
              >
                <Escudo id={c.escudo} nome={c.clube_nome} className="mb-4 block size-16 drop-shadow-lg" />
                <span className="fita text-2xl" style={{ "--giro": `${i % 2 ? 1.5 : -2}deg` }}>
                  {c.clube_nome}
                </span>
                <span className="mt-5 block font-kit text-lg font-semibold uppercase tracking-wide text-muted">
                  {c.nome} · {c.slot}
                </span>
                <span className="mt-1 block">No jogo: {dataBR(c.data_jogo)}</span>
                <span className="mt-4 block text-xs text-muted">Sincronizado em {dataHoraBR(c.em)}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

function ResultadoSync({ resultado }) {
  return (
    <section aria-live="polite" className="mb-8 rounded-md bg-pitch-900 p-4 text-sm">
      {resultado.avisos.map((a, i) => (
        <p key={i} className="mb-2 text-gold">
          <span className="icone">warning</span> {a}
        </p>
      ))}
      <ul className="space-y-1">
        {resultado.arquivos.map((a) => (
          <li key={a.arquivo} className="flex flex-wrap gap-x-2">
            <span className="font-semibold">{a.arquivo}</span>
            {a.status === "ok" && (
              <span>
                {a.carreira} ({a.clube}): {a.novas} partidas novas, {a.atualizadas} atualizadas
              </span>
            )}
            {a.status === "sem mudanças" && <span className="text-muted">sem mudanças</span>}
            {a.status === "erro" && <span className="text-cartao">{a.mensagem}</span>}
          </li>
        ))}
      </ul>
    </section>
  );
}
