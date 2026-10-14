import { useState } from "react";
import Carreira from "./Carreira.jsx";
import Inicio from "./Inicio.jsx";

export default function App() {
  const [carreiraId, setCarreiraId] = useState(null);
  return (
    <main className="mx-auto max-w-6xl px-4 py-10 sm:px-8">
      {carreiraId === null ? (
        <Inicio onAbrir={setCarreiraId} />
      ) : (
        <Carreira id={carreiraId} onVoltar={() => setCarreiraId(null)} />
      )}
    </main>
  );
}
