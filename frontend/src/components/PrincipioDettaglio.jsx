import { useState } from 'react';
import MiniBoard from './MiniBoard.jsx';
import EsempioInterattivo from './EsempioInterattivo.jsx';
import QuizPrincipio from './QuizPrincipio.jsx';

// Vista completa di UN principio: illustrazione, spiegazione approfondita, come riconoscerlo,
// come sfruttarlo/difendersi, esempi giocabili (con "Esempio successivo") e quiz. Le sezioni
// ricche sono opzionali: un principio ancora "breve" mostra solo cio' che ha.
export default function PrincipioDettaglio({ principio, onIndietro }) {
  const p = principio;
  const esempi = p.esempi || [];
  const [esIdx, setEsIdx] = useState(0);
  const es = esempi[esIdx];

  return (
    <div className="principi">
      <button className="btn btn-ghost torna" onClick={onIndietro}>← Principi</button>
      <div className="pr-dett-testa">
        {p.fen && <div className="pr-dett-ill"><MiniBoard fen={p.fen} /></div>}
        <div>
          <h1>{p.titolo}</h1>
          <p className="muted">{p.descrizione || p.testo}</p>
        </div>
      </div>

      {p.riconoscere && (
        <div className="card pr-sez">
          <h3>Come riconoscerlo</h3>
          <p className="muted">{p.riconoscere}</p>
        </div>
      )}

      {(p.sfruttare || p.difendersi) && (
        <div className="pr-due">
          {p.sfruttare && <div className="card pr-sez"><h3>Come sfruttarlo</h3><p className="muted">{p.sfruttare}</p></div>}
          {p.difendersi && <div className="card pr-sez"><h3>Come difendersi</h3><p className="muted">{p.difendersi}</p></div>}
        </div>
      )}

      {es && (
        <div className="card pr-sez">
          <div className="pr-esempi-testa">
            <h3>Esempio giocabile{esempi.length > 1 ? ` (${esIdx + 1}/${esempi.length})` : ''}</h3>
            {es.titolo && <span className="pr-esempio-tit">{es.titolo}</span>}
          </div>
          <EsempioInterattivo key={esIdx} fen={es.fen} mosse={es.mosse} commenti={es.commenti} />
          {esempi.length > 1 && (
            <button className="btn btn-ghost pr-es-succ" onClick={() => setEsIdx((i) => (i + 1) % esempi.length)}>
              Esempio successivo →
            </button>
          )}
        </div>
      )}

      {p.quiz && <QuizPrincipio quiz={p.quiz} />}

      {!p.descrizione && !esempi.length && !p.quiz && (
        <p className="faint">Approfondimento in arrivo per questo principio.</p>
      )}
    </div>
  );
}
