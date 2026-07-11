import { useEffect, useRef, useState } from 'react';
import { Chess } from 'chess.js';
import { Chessground } from 'chessground';
import { BACKEND } from '../config.js';
import { suonaMossa, suonaCattura, suonaSuccesso, suonaErrore } from '../suoni.js';

const sanDaUci = (fen, uci) => {
  try {
    const c = new Chess(fen);
    const m = c.move({ from: uci.slice(0, 2), to: uci.slice(2, 4), promotion: 'q' });
    if (m && m.san) return m.san;
  } catch { /* fallback UCI */ }
  return uci;
};

// Vista di studio di UNA apertura (riusata da "Tutte" e "Guidate"). Due colonne come chessreps:
// scacchiera a sinistra, a destra il Coach (in alto) + toggle Linee/Puzzle e il menu delle varianti.
// LO STUDIO PARTE SEMPRE DALLA MOSSA 1: si costruisce l'apertura da zero (fase "guidata"), poi,
// raggiunta la posizione, si esplorano le varianti ECO libere. Montare con key={apertura.nome}.
export default function StudioApertura({ apertura, onIndietro }) {
  const boardEl = useRef(null);
  const cg = useRef(null);
  const chessStudio = useRef(null);
  const mosseStudio = useRef([]);            // mosse applicate finora (parte da [])
  const mosseGuida = useRef(apertura.mosse.slice()); // linea che DEFINISCE l'apertura (da costruire)
  const mossaAvanti = useRef(null);          // la prossima mossa di "Avanti" (guidata o da libro)
  const puzzleSetup = useRef([]);
  const onMoveRef = useRef(() => {});

  const [modo, setModo] = useState('linee');
  const [msg, setMsg] = useState('');
  const [continuazioni, setContinuazioni] = useState([]);
  const [lineeAperte, setLineeAperte] = useState(false);
  const [avantiOff, setAvantiOff] = useState(true);
  const [indietroOff, setIndietroOff] = useState(true);
  const [pz, setPz] = useState({ attivo: false, aperto: false, stato: '', indice: 0, totale: 0 });

  const ricostruisci = () => {
    chessStudio.current = new Chess();
    for (const u of mosseStudio.current) chessStudio.current.move({ from: u.slice(0, 2), to: u.slice(2, 4), promotion: 'q' });
  };
  const destsStudio = () => {
    const d = new Map();
    chessStudio.current.moves({ verbose: true }).forEach((m) => {
      if (!d.has(m.from)) d.set(m.from, []);
      d.get(m.from).push(m.to);
    });
    return d;
  };
  const coloreCg = () => (chessStudio.current.turn() === 'w' ? 'white' : 'black');
  const ultimaCoppia = () => {
    const a = mosseStudio.current;
    return a.length ? [a[a.length - 1].slice(0, 2), a[a.length - 1].slice(2, 4)] : undefined;
  };

  // Se esiste una spiegazione pre-generata per la posizione, la mostro nel coach (altrimenti
  // resta il messaggio-guida). Lookup puro: niente attesa di generazione a runtime.
  const aggiornaCoach = (seq) => {
    fetch(`${BACKEND}/aperture/coach?mosse=${seq.join(',')}`)
      .then((r) => r.json())
      .then((c) => { if (c.disponibile && c.testo) setMsg(c.testo); })
      .catch(() => { /* coach non disponibile: tengo la guida */ });
  };

  const aggiorna = async () => {
    const fen = chessStudio.current.fen();
    cg.current.set({ fen, lastMove: ultimaCoppia(), movable: { color: undefined } });
    const n = mosseStudio.current.length;
    setIndietroOff(n === 0);

    // FASE GUIDATA: stiamo ancora costruendo la linea che definisce l'apertura.
    if (n < mosseGuida.current.length) {
      const prossima = mosseGuida.current[n];
      const san = sanDaUci(fen, prossima);
      mossaAvanti.current = prossima;
      setAvantiOff(false);
      setContinuazioni([{ uci: prossima, san, linee: null, nome: null, guidata: true }]);
      setMsg(`Costruiamo la <strong>${apertura.nome}</strong> dall'inizio — siamo alla mossa ${n}. `
        + `Prossima: <strong>${san}</strong>. Premi <em>Avanti</em> (o clicca la mossa) per proseguire.`);
      if (n > 0) aggiornaCoach(mosseStudio.current.slice());
      return;
    }

    // FASE LIBERA: raggiunta la posizione dell'apertura, esploriamo le varianti ECO.
    setMsg('Carico…');
    try {
      const d = await fetch(`${BACKEND}/aperture/esplora?mosse=${mosseStudio.current.join(',')}`).then((r) => r.json());
      mossaAvanti.current = d.mossa_da_libro || null;
      const ap = d.apertura ? `${d.apertura.eco} — ${d.apertura.nome}` : '(fuori dalle aperture nominate)';
      const guida = (d.continuazioni || []).length
        ? "Apri <em>Vedi le linee</em> per scegliere una variante, oppure passa ai <em>Puzzle</em>."
        : "Sei fuori dal libro: torna <em>Indietro</em> o <em>Da capo</em>.";
      setMsg(`Hai raggiunto la <strong>${ap}</strong> (${n} mosse).<br/>${guida}`);
      setAvantiOff(!mossaAvanti.current);
      setContinuazioni((d.continuazioni || []).slice(0, 12).map((c) => ({
        uci: c.uci, linee: c.linee, nome: c.nome, san: sanDaUci(fen, c.uci),
      })));
      aggiornaCoach(mosseStudio.current.slice());
    } catch { setMsg('⚠️ Errore nel contattare il server.'); setContinuazioni([]); }
  };

  const applicaMossa = (uci) => {
    let m;
    try { m = chessStudio.current.move({ from: uci.slice(0, 2), to: uci.slice(2, 4), promotion: 'q' }); }
    catch { return; }
    if (!m) return;
    mosseStudio.current.push(uci);
    (m.captured ? suonaCattura : suonaMossa)();
    aggiorna();
  };
  const indietro = () => {
    if (!mosseStudio.current.length) return;
    mosseStudio.current.pop();
    ricostruisci();
    aggiorna();
  };
  const daCapo = () => { mosseStudio.current = []; ricostruisci(); aggiorna(); };

  // ---- puzzle (ancorati alla linea COMPLETA dell'apertura) ----
  const abilitaMossaPuzzle = () => {
    cg.current.set({
      fen: chessStudio.current.fen(), lastMove: ultimaCoppia(), turnColor: coloreCg(),
      movable: { color: coloreCg(), dests: destsStudio(), free: false, events: { after: (o, d) => onMoveRef.current(o, d) } },
    });
  };
  const avviaPuzzle = async (indice) => {
    setPz((p) => ({ ...p, aperto: true, stato: 'Preparo un puzzle…' }));
    try {
      const d = await fetch(`${BACKEND}/aperture/puzzle?mosse=${mosseGuida.current.join(',')}&indice=${indice}`).then((r) => r.json());
      if (!d.disponibile) { setPz((p) => ({ ...p, attivo: false, stato: 'ℹ️ ' + (d.motivo || 'Nessun puzzle per questa apertura.') })); return; }
      puzzleSetup.current = d.setup.slice();
      mosseStudio.current = d.setup.slice();
      ricostruisci();
      setPz({ attivo: true, aperto: true, indice: d.indice, totale: d.totale,
        stato: `Muove il ${d.lato}. Trova la mossa principale (mossa ${d.numero_mossa}). Puzzle ${d.indice + 1}/${d.totale}.` });
      abilitaMossaPuzzle();
    } catch { setPz((p) => ({ ...p, stato: '⚠️ Errore nel contattare il server.' })); }
  };
  const onMossaPuzzle = async (orig, dest) => {
    const uci = orig + dest;
    const fenPrima = chessStudio.current.fen();
    cg.current.set({ movable: { color: undefined } });
    try {
      const d = await fetch(`${BACKEND}/aperture/puzzle/verifica?setup=${puzzleSetup.current.join(',')}&mossa=${uci}`).then((r) => r.json());
      if (d.corretto) {
        chessStudio.current.move({ from: d.attesa.slice(0, 2), to: d.attesa.slice(2, 4), promotion: 'q' });
        mosseStudio.current.push(d.attesa);
        suonaSuccesso();
        cg.current.set({ fen: chessStudio.current.fen(), lastMove: [d.attesa.slice(0, 2), d.attesa.slice(2, 4)], turnColor: coloreCg(), movable: { color: undefined } });
        setPz((p) => ({ ...p, attivo: false, stato: `✅ Esatto: ${sanDaUci(fenPrima, d.attesa)}${d.apertura_dopo ? ' → ' + d.apertura_dopo.nome : ''}. "Altro puzzle" per continuare.` }));
      } else {
        suonaErrore();
        ricostruisci();
        abilitaMossaPuzzle();
        setPz((p) => ({ ...p, stato: `❌ Non è la principale: la mossa da libro era ${sanDaUci(fenPrima, d.attesa)}. Riprova o prova un altro puzzle.` }));
      }
    } catch { setPz((p) => ({ ...p, stato: '⚠️ Errore nel contattare il server.' })); }
  };
  onMoveRef.current = onMossaPuzzle;

  const vaiLinee = () => {
    setModo('linee');
    setPz({ attivo: false, aperto: false, stato: '', indice: 0, totale: 0 });
    mosseStudio.current = [];
    ricostruisci();
    aggiorna();
  };
  const vaiPuzzle = () => { setModo('puzzle'); setLineeAperte(false); avviaPuzzle(0); };

  useEffect(() => {
    mosseGuida.current = apertura.mosse.slice();
    mosseStudio.current = [];                 // si parte dalla posizione iniziale
    ricostruisci();
    cg.current = Chessground(boardEl.current, {
      fen: chessStudio.current.fen(), orientation: 'white',
      movable: { color: undefined }, drawable: { enabled: false }, highlight: { lastMove: true },
    });
    aggiorna();
    return () => { if (cg.current) { cg.current.destroy(); cg.current = null; } };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const coachTesto = modo === 'puzzle' ? (pz.stato || 'Preparo un puzzle…') : msg;

  return (
    <div className="card studio">
      <div className="studio-testa">
        <button className="btn btn-ghost" onClick={onIndietro}>← Tutte</button>
        <h3>{apertura.nome}</h3>
      </div>

      <div className="studio-layout">
        {/* Sinistra: scacchiera + controlli */}
        <div className="studio-board">
          <div className="board-frame"><div ref={boardEl} className="board" /></div>
          {modo === 'linee' && (
            <div className="ap-controlli">
              <button className="btn btn-ghost" disabled={indietroOff} onClick={indietro}>◀ Indietro</button>
              <button className="btn btn-ghost" disabled={avantiOff} onClick={() => mossaAvanti.current && applicaMossa(mossaAvanti.current)}>▶ Avanti</button>
              <button className="btn btn-ghost" disabled={indietroOff} onClick={daCapo}>↺ Da capo</button>
            </div>
          )}
        </div>

        {/* Destra: coach in alto + toggle + menu varianti */}
        <div className="studio-pannello">
          <div className="coach">
            <div className="coach-head">🎓 Coach · {apertura.nome}</div>
            <div className="coach-bubble" dangerouslySetInnerHTML={{ __html: coachTesto }} />
            <div className="coach-nota">Le spiegazioni sono pre-generate in locale (Ollama/Qwen); dove non ancora prodotte compare la guida.</div>
          </div>

          <div className="studio-modi">
            <button className={'temi-tab' + (modo === 'linee' ? ' attivo' : '')} onClick={vaiLinee}>📖 Linee</button>
            <button className={'temi-tab' + (modo === 'puzzle' ? ' attivo' : '')} onClick={vaiPuzzle}>🧩 Puzzle</button>
          </div>

          {modo === 'linee' && (
            <>
              <button className="vedi-linee" onClick={() => setLineeAperte((v) => !v)}>
                {lineeAperte ? '▾' : '▸'} Vedi le linee ({continuazioni.length})
              </button>
              {lineeAperte && (
                <div className="linee-menu">
                  {continuazioni.length ? continuazioni.map((c) => (
                    <button key={c.uci} className="linee-voce" onClick={() => applicaMossa(c.uci)}>
                      <span className="lv-san">{c.san}</span>
                      {c.linee != null && <span className="ap-cont-n">[{c.linee}]</span>}
                      {c.guidata && <span className="lv-nome muted">mossa dell'apertura</span>}
                      {c.nome && <span className="lv-nome muted">{c.nome}</span>}
                    </button>
                  )) : <p className="muted">Nessuna linea nota: sei fuori dal libro.</p>}
                </div>
              )}
            </>
          )}

          {modo === 'puzzle' && (
            <button className="btn btn-ghost" onClick={() => avviaPuzzle(pz.totale ? (pz.indice + 1) % pz.totale : 0)}>Altro puzzle</button>
          )}
        </div>
      </div>
    </div>
  );
}
