async function pedir(caminho, opcoes) {
  const r = await fetch(`/api${caminho}`, opcoes);
  const corpo = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(corpo.detail ?? `Erro ${r.status}`);
  return corpo;
}

export const api = {
  carreiras: () => pedir("/carreiras"),
  sincronizar: () => pedir("/sincronizar", { method: "POST" }),
  carreira: (id) => pedir(`/carreiras/${id}`),
  resumo: (id, ano) => pedir(`/carreiras/${id}/resumo?ano=${ano}`),
  elenco: (id, ano) => pedir(`/carreiras/${id}/elenco?ano=${ano}`),
  partidas: (id, ano) => pedir(`/carreiras/${id}/partidas?ano=${ano}`),
  lendas: (id) => pedir(`/carreiras/${id}/lendas`),
  partida: (id, pid) => pedir(`/carreiras/${id}/partidas/${pid}`),
  confrontos: (id) => pedir(`/carreiras/${id}/confrontos`),
  transferencias: (id) => pedir(`/carreiras/${id}/transferencias`),
  mundo: (id, ano) => pedir(`/carreiras/${id}/mundo?ano=${ano}`),
  campeonatos: (id) => pedir(`/carreiras/${id}/campeonatos`),
  titulos: (id) => pedir(`/carreiras/${id}/titulos`),
  feed: (id) => pedir(`/carreiras/${id}/feed`),
  contatos: (id) => pedir(`/carreiras/${id}/conversas`),
  conversa: (id, contato) => pedir(`/carreiras/${id}/conversas/${contato}`),
  enviar: (id, contato, texto) =>
    pedir(`/carreiras/${id}/conversas/${contato}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ texto }),
    }),
  atualizarFeed: (id) => pedir(`/carreiras/${id}/feed`, { method: "POST" }),
  abrirColetiva: (id) => pedir(`/carreiras/${id}/coletiva`, { method: "POST" }),
  responderColetiva: (id, respostas) =>
    pedir(`/carreiras/${id}/coletiva/respostas`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ respostas }),
    }),
  parecer: (id, p) =>
    pedir(`/carreiras/${id}/propostas/parecer`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ player_id: p.player_id, clube_idx: p.clube.idx, valor: p.valor_bruto }),
    }),
  campeonato: (id, chave) => pedir(`/carreiras/${id}/campeonato?chave=${encodeURIComponent(chave)}`),
};

export const dataBR = (iso) => iso.slice(0, 10).split("-").reverse().join("/");

export const dataHoraBR = (iso) => `${dataBR(iso)} às ${iso.slice(11, 16)}`;
