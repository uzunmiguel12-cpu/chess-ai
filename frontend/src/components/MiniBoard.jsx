import { useEffect, useRef } from 'react';
import { Chess } from 'chess.js';
import { Chessground } from 'chessground';

// Mini scacchiera SOLO visiva (niente interazione). Mostra un `fen` diretto (per i diagrammi
// dei Principi) oppure la posizione raggiunta dopo `mosse` (array UCI, per le card aperture).
export default function MiniBoard({ mosse = [], fen = null, orientation = 'white' }) {
  const el = useRef(null);
  const cg = useRef(null);
  useEffect(() => {
    let posizione = fen;
    if (!posizione) {
      const chess = new Chess();
      for (const u of mosse) {
        try { chess.move({ from: u.slice(0, 2), to: u.slice(2, 4), promotion: 'q' }); } catch { /* ignora */ }
      }
      posizione = chess.fen();
    }
    cg.current = Chessground(el.current, {
      fen: posizione, orientation, viewOnly: true, coordinates: false,
      drawable: { enabled: false }, highlight: { lastMove: false },
    });
    return () => { if (cg.current) { cg.current.destroy(); cg.current = null; } };
  }, [mosse, fen, orientation]);
  return <div ref={el} className="mini-board" />;
}
