import { useState } from "react";

const SIGLAS = new Set(["FC", "SC", "EC", "CF", "AC", "CR", "SE", "AFC", "CD", "CA", "FK", "SK", "SV", "AS", "SS", "US", "RC", "CLUB", "CLUBE", "DE", "DA", "DO", "DEL"]);

function iniciais(nome) {
  const palavras = nome.split(/[\s.-]+/).filter((p) => p && !SIGLAS.has(p.toUpperCase()));
  return (palavras.length ? palavras : [nome]).slice(0, 3).map((p) => p[0].toUpperCase()).join("");
}

// Escudo do time vindo do patch; sem escudo, um escudo neutro com as iniciais.
export default function Escudo({ id, nome, className = "size-6" }) {
  const [falhou, setFalhou] = useState(false);
  if (id != null && !falhou) {
    return (
      <img
        src={`/api/escudos/${id}`}
        alt=""
        loading="lazy"
        onError={() => setFalhou(true)}
        className={`shrink-0 object-contain ${className}`}
      />
    );
  }
  return (
    <svg viewBox="0 0 40 46" aria-hidden="true" className={`shrink-0 ${className}`}>
      <path d="M20 1 L38 7 V22 C38 34 30 41 20 45 C10 41 2 34 2 22 V7 Z" className="fill-pitch-700 stroke-muted" strokeWidth="1.5" />
      <text x="20" y="28" textAnchor="middle" className="fill-chalk font-kit" fontSize="15" fontWeight="700">
        {iniciais(nome)}
      </text>
    </svg>
  );
}
