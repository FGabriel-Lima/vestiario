import { useEffect, useState } from "react";
import { api, dataBR } from "./api.js";

export default function Inicio({ onAbrir }) {
  const [carreiras, setCarreiras] = useState([]);
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
      <header className="mb-8 flex items-center justify-between">
        <h1 className="font-kit text-5xl font-bold uppercase tracking-wide">Vestiário</h1>
        <button
          onClick={sincronizar}
          disabled={sincronizando}
          className="flex items-center gap-2 rounded-lg bg-neon px-4 py-2 font-semibold text-pitch-950 disabled:opacity-50"
        >
          <span className={`icone ${sincronizando ? "animate-spin" : ""}`}>sync</span>
          {sincronizando ? "Sincronizando…" : "Sincronizar"}
        </button>
      </header>

      {erro && <p className="mb-4 rounded-lg bg-red-900/60 p-3">{erro}</p>}
      {resultado && <ResultadoSync resultado={resultado} />}

      {carreiras.length === 0 ? (
        <p className="text-muted">Nenhuma carreira ainda. Salve no PES e clique em Sincronizar.</p>
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2">
          {carreiras.map((c) => (
            <li key={c.id}>
              <button
                onClick={() => onAbrir(c.id)}
                className="w-full rounded-xl bg-pitch-800 p-5 text-left hover:bg-pitch-700"
              >
                <p className="font-kit text-3xl font-bold uppercase">{c.clube_nome}</p>
                <p className="text-muted">
                  {c.nome} · {c.slot} · no jogo: {dataBR(c.data_jogo)}
                </p>
                <p className="mt-2 text-xs text-muted">Sincronizado em {c.em.replace("T", " ")}</p>
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
    <section className="mb-6 rounded-xl bg-pitch-900 p-4 text-sm">
      {resultado.avisos.map((a) => (
        <p key={a} className="text-gold">
          <span className="icone">warning</span> {a}
        </p>
      ))}
      <ul>
        {resultado.arquivos.map((a) => (
          <li key={a.arquivo}>
            <span className="font-semibold">{a.arquivo}</span>{" "}
            {a.status === "ok" && `${a.carreira} (${a.clube}): ${a.novas} partidas novas, ${a.atualizadas} atualizadas`}
            {a.status === "sem mudanças" && <span className="text-muted">sem mudanças</span>}
            {a.status === "erro" && <span className="text-red-400">{a.mensagem}</span>}
          </li>
        ))}
      </ul>
    </section>
  );
}
