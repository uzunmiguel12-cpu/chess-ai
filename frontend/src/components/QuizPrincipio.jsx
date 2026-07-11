import { useState, useRef, useEffect } from 'react';
import { Chess } from 'chess.js';
import { Chessground } from 'chessground';
import { suonaSuccesso, suonaErrore } from '../suoni.js';

// Una domanda di teoria: al click blocca, evidenzia giusto/sbagliato e mostra la spiegazione.
// Chiama onFine(corretto) una sola volta (per il punteggio + per abilitare "Prosegui").
function ItemTeoria({ item, onFine }) {
  const [scelta, setScelta] = useState(null);
  const scegli = (oi) => {
    if (scelta != null) return;
    setScelta(oi);
    (oi === item.corretta ? suonaSuccesso : suonaErrore)();
    onFine(oi === item.corretta);
  };
  return (
    <div className="quiz-item">
      <p className="quiz-domanda">{item.domanda}</p>
      <div className="quiz-opzioni">
        {item.opzioni.map((o, oi) => {
          let cls = 'quiz-opz';
          if (scelta != null) {
            if (oi === item.corretta) cls += ' giusta';
            else if (oi === scelta) cls += ' sbagliata';
          }
          return (
            <button key={oi} className={cls} disabled={scelta != null} onClick={() => scegli(oi)}>{o}</button>
          );
        })}
      </div>
      {scelta != null && (
        <p className={'quiz-spieg ' + (scelta === item.corretta ? 'ok' : 'ko')}>
          {scelta === item.corretta ? '✅ Giusto. ' : '❌ '} {item.spiegazione}
        </p>
      )}
    </div>
  );
}

// Un puzzle: l'utente trascina una mossa. onFine(corretto) è chiamato al PRIMO tentativo (per il
// punteggio); "Prosegui" si abilita solo quando risolve (mossa giusta), così deve completarlo.
function ItemPuzzle({ item, onFine }) {
  const el = useRef(null);
  const cg = useRef(null);
  const chess = useRef(null);
  const primo = useRef(true);
  const [esito, setEsito] = useState(null);

  const dests = () => {
    const m = new Map();
    chess.current.moves({ verbose: true }).forEach((x) => {
      if (!m.has(x.from)) m.set(x.from, []);
      m.get(x.from).push(x.to);
    });
    return m;
  };
  const movable = () => ({ color: chess.current.turn() === 'w' ? 'white' : 'black', dests: dests(), free: false, events: { after: onMove } });
  const onMove = (orig, dest) => {
    const uci = orig + dest;
    const ok = (item.soluzione[0] || '').slice(0, 4) === uci;
    cg.current.set({ movable: { color: undefined } });
    if (primo.current) { onFine(ok); primo.current = false; }
    if (ok) {
      suonaSuccesso();
      setEsito({ ok: true });
    } else {
      suonaErrore();
      setEsito({ ok: false });
      chess.current = new Chess(item.fen);
      setTimeout(() => {
        if (cg.current) cg.current.set({ fen: chess.current.fen(), turnColor: chess.current.turn() === 'w' ? 'white' : 'black', movable: movable() });
      }, 500);
    }
  };

  useEffect(() => {
    chess.current = new Chess(item.fen);
    const colore = chess.current.turn() === 'w' ? 'white' : 'black';
    cg.current = Chessground(el.current, {
      fen: chess.current.fen(), turnColor: colore, orientation: colore,
      movable: movable(), drawable: { enabled: true },
    });
    return () => { if (cg.current) { cg.current.destroy(); cg.current = null; } };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="quiz-item quiz-puzzle">
      <p className="quiz-domanda">{item.consegna}</p>
      <div className="board-frame esempio-board"><div ref={el} className="board" /></div>
      {esito && (
        <p className={'quiz-spieg ' + (esito.ok ? 'ok' : 'ko')}>
          {esito.ok ? '✅ Esatto! ' + item.spiegazione : '❌ Non è la mossa giusta: riprova.'}
        </p>
      )}
    </div>
  );
}

// Quiz interattivo: si apre con un pulsante, poi UN item alla volta con "Prosegui", infine il
// riepilogo. `puoiProseguire` diventa true quando l'item corrente è completato.
export default function QuizPrincipio({ quiz }) {
  const items = quiz?.items || [];
  const [avviato, setAvviato] = useState(false);
  const [idx, setIdx] = useState(0);
  const [puoiProseguire, setPuoiProseguire] = useState(false);
  const [punti, setPunti] = useState(0);
  const [fatto, setFatto] = useState(false);

  if (!items.length) return null;

  if (!avviato) {
    return (
      <div className="card quiz-card">
        <h3>🧩 Quiz interattivo</h3>
        <p className="muted">{items.length} tra domande di teoria e puzzle, per verificare tutto lo studio del principio.</p>
        <button className="btn btn-primary" onClick={() => setAvviato(true)}>▶ Inizia il quiz</button>
      </div>
    );
  }

  if (fatto) {
    const rifai = () => { setAvviato(false); setIdx(0); setPuoiProseguire(false); setPunti(0); setFatto(false); };
    return (
      <div className="card quiz-card">
        <h3>🧩 Quiz completato</h3>
        <p className="quiz-punteggio">Risolti al primo colpo: <strong>{punti}/{items.length}</strong>.</p>
        <button className="btn btn-ghost" onClick={rifai}>↺ Rifai il quiz</button>
      </div>
    );
  }

  const item = items[idx];
  const onFine = (ok) => { setPuoiProseguire(true); if (ok) setPunti((p) => p + 1); };
  const prosegui = () => {
    if (idx + 1 >= items.length) { setFatto(true); return; }
    setIdx(idx + 1);
    setPuoiProseguire(false);
  };

  return (
    <div className="card quiz-card">
      <div className="quiz-testa">
        <h3>🧩 Quiz interattivo</h3>
        <span className="quiz-avanz faint">{idx + 1}/{items.length}</span>
      </div>
      {item.tipo === 'puzzle'
        ? <ItemPuzzle key={idx} item={item} onFine={onFine} />
        : <ItemTeoria key={idx} item={item} onFine={onFine} />}
      {puoiProseguire && (
        <button className="btn btn-primary quiz-prosegui" onClick={prosegui}>
          {idx + 1 >= items.length ? 'Vedi risultato →' : 'Prosegui →'}
        </button>
      )}
    </div>
  );
}
