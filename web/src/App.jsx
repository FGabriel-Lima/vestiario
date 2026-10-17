import { useState } from "react";
import Carreira from "./Carreira.jsx";
import Inicio from "./Inicio.jsx";

export default function App() {
  const [aberta, setAberta] = useState(null);
  return (
    <main className="mx-auto max-w-7xl px-4 py-10 sm:px-8">
      {aberta === null ? (
        <Inicio onAbrir={(id) => setAberta({ id })} />
      ) : (
        <Carreira key={aberta.id} id={aberta.id} abaInicial={aberta.aba} onVoltar={() => setAberta(null)} onTrocar={(id, aba) => setAberta({ id, aba })} />
      )}
    </main>
  );
}
