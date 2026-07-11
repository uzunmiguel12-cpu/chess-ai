import { useEffect, useRef, useState } from 'react';
import { Chess } from 'chess.js';
import { Chessground } from 'chessground';
import { suonaMossa, suonaCattura } from '../suoni.js';

// Esempio giocabile di un principio: parte da `fen`, si scorre con Avanti/Indietro lungo `mosse`
// (array UCI). A ogni passo mostra il commento del coach `commenti[idx]` (idx 0 = posizione iniziale,
// idx k = dopo la k-esima mossa). Solo visiva: l'utente scorre, non muove.
export default function EsempioInterattivo({ fen, mosse = [], commenti = [] }) {
  const el = useRef(null);
  const cg = useRef(null);
  const [idx, setIdx] = useState(0);

  const posizioneA = (n) => {
    const c = new Chess(fen);
    for (let i = 0; i < n; i++) {
      const u = mosse[i];
      try { c.move({ from: u.slice(0, 2), to: u.slice(2, 4), promotion: 'q' }); } catch { /* ignora */ }
    }
    return c;
  };
  const ultima = () => (idx > 0 ? [mosse[idx - 1].slice(0, 2), mosse[idx - 1].slice(2, 4)] : undefined);

  // "Avanti": suona in base a se la mossa che sto per giocare è una cattura.
  const avanti = () => {
    if (idx >= mosse.length) return;
    let cattura = false;
    try {
      const c = posizioneA(idx);
      const m = c.move({ from: mosse[idx].slice(0, 2), to: mosse[idx].slice(2, 4), promotion: 'q' });
      cattura = !!(m && m.captured);
    } catch { /* ignora */ }
    (cattura ? suonaCattura : suonaMossa)();
    setIdx((i) => Math.min(mosse.length, i + 1));
  };

  useEffect(() => {
    const c = posizioneA(idx);
    if (!cg.current) {
      cg.current = Chessground(el.current, {
        fen: c.fen(), viewOnly: true, coordinates: false,
        drawable: { enabled: false }, highlight: { lastMove: true }, lastMove: ultima(),
      });
    } else {
      cg.current.set({ fen: c.fen(), lastMove: ultima() });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idx]);
  useEffect(() => () => { if (cg.current) { cg.current.destroy(); cg.current = null; } }, []);

  return (
    <div className="esempio">
      <div className="board-frame esempio-board"><div ref={el} className="board" /></div>
      <div className="esempio-lato">
        <div className="coach">
          <div className="coach-head">🎓 Coach</div>
          <div className="coach-bubble">{commenti[idx] || ''}</div>
        </div>
        <div className="ap-controlli">
          <button className="btn btn-ghost" disabled={idx === 0} onClick={() => setIdx((i) => Math.max(0, i - 1))}>◀ Indietro</button>
          <button className="btn btn-ghost" disabled={idx >= mosse.length} onClick={avanti}>▶ Avanti</button>
          <button className="btn btn-ghost" disabled={idx === 0} onClick={() => setIdx(0)}>↺ Da capo</button>
        </div>
        <p className="faint">Mossa {idx}/{mosse.length}</p>
      </div>
    </div>
  );
}
