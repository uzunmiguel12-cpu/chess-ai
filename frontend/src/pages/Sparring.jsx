import { useEffect, useRef, useState } from 'react';
import { Chess } from 'chess.js';
import { Chessground } from 'chessground';
import { BACKEND } from '../config.js';
import { suonaMossa, suonaCattura, suonaSuccesso, suonaErrore } from '../suoni.js';
import './Sparring.css';

// SPARRING: partita contro un bot a livelli (Skill Level Stockfish) con il coach
// posizionale a fianco. Dopo OGNI tua mossa il backend risponde con:
//   - cp_loss e tipo (ok | teoria | tattico | posizionale)  [DATO, engine]
//   - le feature posizionali peggiorate (spiegazione)        [DATO, deterministico]
//   - il rischio stimato dal modello ML                      [STIMA, dichiarata]
// Qui si mettono in pratica le aperture studiate in /aperture: nelle prime mosse
// il pannello mostra il nome dell'apertura raggiunta (teoria), poi inizia la diagnosi.

const ETICHETTE = {
  ok:          { testo: 'Buona mossa',        classe: 'sp-ok' },
  teoria:      { testo: 'Teoria d’apertura', classe: 'sp-teoria' },
  tattico:     { testo: 'Errore tattico',     classe: 'sp-tattico' },
  posizionale: { testo: 'Errore posizionale', classe: 'sp-posizionale' },
};

export default function Sparring() {
  const boardEl = useRef(null);
  const cg = useRef(null);
  const chessRef = useRef(null);
  const onMoveRef = useRef(() => {});

  const [livelli, setLivelli] = useState([]);
  const [livello, setLivello] = useState('medio');
  const [colore, setColore] = useState('white');
  const [inCorso, setInCorso] = useState(false);
  const [attesa, setAttesa] = useState(false);
  const [stato, setStato] = useState('');
  const [analisi, setAnalisi] = useState(null);      // ultima risposta del backend
  const [storia, setStoria] = useState([]);          // diagnosi della partita
  const [apertura, setApertura] = useState('');

  // ---- scacchiera -----------------------------------------------------------
  const dests = () => {
    const d = new Map();
    chessRef.current.moves({ verbose: true }).forEach((m) => {
      if (!d.has(m.from)) d.set(m.from, []);
      d.get(m.from).push(m.to);
    });
    return d;
  };

  const abilitaUtente = () => {
    cg.current.set({
      fen: chessRef.current.fen(),
      turnColor: chessRef.current.turn() === 'w' ? 'white' : 'black',
      movable: {
        color: colore, dests: dests(), free: false,
        events: { after: (o, d) => onMoveRef.current(o, d) },
      },
    });
  };

  const blocca = (lastMove) => {
    cg.current.set({ fen: chessRef.current.fen(), lastMove, movable: { color: undefined } });
  };

  // ---- apertura raggiunta (riusa l'endpoint di /aperture) --------------------
  const aggiornaApertura = (mosse) => {
    if (mosse.length === 0 || mosse.length > 16) return;
    fetch(`${BACKEND}/aperture/esplora?mosse=${mosse.join(',')}`)
      .then((r) => r.json())
      .then((d) => { if (d.apertura) setApertura(`${d.apertura.eco} — ${d.apertura.nome}`); })
      .catch(() => {});
  };

  // ---- flusso di gioco --------------------------------------------------------
  const mosseGiocate = useRef([]);

  const nuovaPartita = async () => {
    chessRef.current = new Chess();
    mosseGiocate.current = [];
    setStoria([]); setAnalisi(null); setApertura('');
    setInCorso(true); setStato('');
    if (colore === 'black') {
      setAttesa(true);
      blocca();
      try {
        const d = await fetch(`${BACKEND}/sparring/mossa-bot`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ fen: chessRef.current.fen(), livello }),
        }).then((r) => r.json());
        chessRef.current.move({ from: d.mossa_bot.slice(0, 2), to: d.mossa_bot.slice(2, 4), promotion: 'q' });
        mosseGiocate.current.push(d.mossa_bot);
        suonaMossa();
      } catch { setStato('⚠️ Backend non raggiungibile.'); }
      setAttesa(false);
    }
    cg.current.set({ orientation: colore });
    abilitaUtente();
  };

  const fineSeServe = (statoPartita) => {
    if (statoPartita && statoPartita !== 'in_corso') {
      setInCorso(false);
      blocca();
      const testi = { scacco_matto: 'Scacco matto!', stallo: 'Stallo.', patta: 'Patta.' };
      setStato(`🏁 ${testi[statoPartita] || 'Partita finita.'}`);
      return true;
    }
    return false;
  };

  const onMossaUtente = async (orig, dest) => {
    const uci = orig + dest;
    const fenPrima = chessRef.current.fen();
    setAttesa(true);
    blocca([orig, dest]);
    try {
      const d = await fetch(`${BACKEND}/sparring/mossa`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ fen: fenPrima, mossa_uci: uci, livello }),
      }).then((r) => r.json());

      if (d.errore) {           // mossa rifiutata: ripristina
        chessRef.current.load(fenPrima);
        abilitaUtente();
        setAttesa(false);
        return;
      }

      // applica la mossa dell'utente
      const m = chessRef.current.move({ from: orig, to: dest, promotion: 'q' });
      mosseGiocate.current.push(uci);
      (m && m.captured ? suonaCattura : suonaMossa)();
      if (d.tipo === 'tattico' || d.tipo === 'posizionale') suonaErrore();

      // pannello di analisi + storia
      setAnalisi(d);
      setStoria((s) => [...s, {
        n: Math.ceil(mosseGiocate.current.length / 2),
        san: d.san, tipo: d.tipo, cp_loss: d.cp_loss,
        spiegazioni: d.spiegazioni || [], rischio: d.rischio_ml,
      }]);
      aggiornaApertura(mosseGiocate.current.slice());

      // mossa del bot
      if (d.bot) {
        chessRef.current.move({ from: d.bot.mossa_bot.slice(0, 2), to: d.bot.mossa_bot.slice(2, 4), promotion: 'q' });
        mosseGiocate.current.push(d.bot.mossa_bot);
        suonaMossa();
        blocca([d.bot.mossa_bot.slice(0, 2), d.bot.mossa_bot.slice(2, 4)]);
      }
      if (!fineSeServe(d.stato)) abilitaUtente();
    } catch {
      setStato('⚠️ Errore nel contattare il server.');
      chessRef.current.load(fenPrima);
      abilitaUtente();
    }
    setAttesa(false);
  };
  onMoveRef.current = onMossaUtente;

  // ---- montaggio ----------------------------------------------------------------
  useEffect(() => {
    chessRef.current = new Chess();
    cg.current = Chessground(boardEl.current, {
      fen: chessRef.current.fen(), orientation: 'white',
      movable: { color: undefined }, drawable: { enabled: false }, highlight: { lastMove: true },
    });
    fetch(`${BACKEND}/sparring/livelli`)
      .then((r) => r.json())
      .then((d) => setLivelli(d.livelli || []))
      .catch(() => setStato('⚠️ Backend non raggiungibile: avvia `uvicorn server:app` in api/.'));
    return () => { if (cg.current) { cg.current.destroy(); cg.current = null; } };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const errori = storia.filter((r) => r.tipo === 'tattico' || r.tipo === 'posizionale');
  const et = analisi ? (ETICHETTE[analisi.tipo] || ETICHETTE.ok) : null;

  return (
    <div className="sparring">
      <div className="sp-testa">
        <h2>Sparring</h2>
        <p className="sp-sotto">
          Gioca contro il bot e metti in pratica le aperture: il coach posizionale
          analizza ogni tua mossa e ti spiega <em>perché</em> una scelta è un errore posizionale.
        </p>
      </div>

      <div className="sp-griglia">
        {/* Sinistra: scacchiera + controlli */}
        <div className="card sp-board-card">
          <div className="sp-controlli">
            <label>
              Livello{' '}
              <select value={livello} disabled={inCorso}
                onChange={(e) => setLivello(e.target.value)}>
                {livelli.map((l) => <option key={l.id} value={l.id}>{l.nome}</option>)}
                {livelli.length === 0 && <option value="medio">Medio</option>}
              </select>
            </label>
            <label>
              Colore{' '}
              <select value={colore} disabled={inCorso}
                onChange={(e) => setColore(e.target.value)}>
                <option value="white">Bianco</option>
                <option value="black">Nero</option>
              </select>
            </label>
            <button className="btn" onClick={nuovaPartita} disabled={attesa}>
              {inCorso ? 'Ricomincia' : 'Nuova partita'}
            </button>
          </div>
          <div className="sp-board-wrap">
            <div ref={boardEl} className="sp-board" />
          </div>
          <div className="sp-stato">
            {attesa ? 'Il coach analizza…' : stato}
            {apertura && <span className="sp-apertura">📖 {apertura}</span>}
          </div>
        </div>

        {/* Destra: coach posizionale */}
        <div className="card sp-coach">
          <h3>Coach posizionale</h3>

          {!analisi && (
            <p className="sp-vuoto">
              Premi <strong>Nuova partita</strong> e gioca: dopo ogni tua mossa
              vedrai qui la valutazione. Le prime 5 mosse sono teoria d’apertura.
            </p>
          )}

          {analisi && (
            <div className={`sp-esito ${et.classe}`}>
              <div className="sp-esito-riga">
                <span className="sp-badge">{et.testo}</span>
                <span className="sp-mossa">{analisi.san}</span>
                {analisi.cp_loss > 0 && analisi.tipo !== 'teoria' && (
                  <span className="sp-cp">−{analisi.cp_loss} cp</span>
                )}
              </div>

              {analisi.tipo === 'posizionale' && (
                <div className="sp-spiega">
                  <p className="sp-spiega-titolo">Cosa è peggiorato [dato]:</p>
                  {analisi.spiegazioni.length > 0 ? (
                    <ul>
                      {analisi.spiegazioni.map((s) => (
                        <li key={s.feature}>{s.descrizione} <span className="sp-delta">({s.delta})</span></li>
                      ))}
                    </ul>
                  ) : (
                    <p>Peggioramento generale della posizione (attività dei pezzi).</p>
                  )}
                </div>
              )}

              {analisi.tipo === 'tattico' && (
                <p className="sp-spiega">C’è una confutazione forzata: questa è
                  tattica, non posizione — usa l’Allenamento puzzle per lavorarci.</p>
              )}

              {analisi.rischio_ml != null && analisi.tipo !== 'teoria' && (
                <p className="sp-rischio" title="Probabilità stimata dal modello ML allenato sulle tue partite. È una stima, non un dato.">
                  Rischio posizionale stimato dal modello: <strong>{Math.round(analisi.rischio_ml * 100)}%</strong> <span className="sp-stima">[stima]</span>
                </p>
              )}
            </div>
          )}

          {/* storico errori della partita */}
          {errori.length > 0 && (
            <div className="sp-storia">
              <h4>Errori di questa partita ({errori.length})</h4>
              <ul>
                {errori.map((r, i) => (
                  <li key={i}>
                    <span className="sp-storia-mossa">{r.n}. {r.san}</span>{' '}
                    <span className={`sp-tag ${ETICHETTE[r.tipo].classe}`}>{r.tipo}</span>{' '}
                    −{r.cp_loss} cp
                    {r.spiegazioni.length > 0 && (
                      <span className="sp-storia-perche"> — {r.spiegazioni.map((s) => s.descrizione).join('; ')}</span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
