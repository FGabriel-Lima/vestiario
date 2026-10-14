import { useState } from "react";

// Miniface do jogador vinda do patch; sem foto, uma silhueta neutra.
export default function Rosto({ id, className = "size-9" }) {
  const [falhou, setFalhou] = useState(false);
  const base = `shrink-0 rounded-full bg-pitch-800 ring-1 ring-pitch-700 ${className}`;
  if (!falhou) {
    return <img src={`/api/rostos/${id}`} alt="" loading="lazy" onError={() => setFalhou(true)} className={`object-cover object-top ${base}`} />;
  }
  return (
    <svg viewBox="0 0 40 40" aria-hidden="true" className={base}>
      <circle cx="20" cy="15" r="7" className="fill-muted" />
      <path d="M7 36 C8 27 13 24 20 24 C27 24 32 27 33 36 Z" className="fill-muted" />
    </svg>
  );
}
