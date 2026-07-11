import { useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Chess } from 'chess.js';
import { Chessground } from 'chessground';
import { BACKEND } from '../config.js';
import { suonaMossa, suonaCattura, suonaSuccesso, suonaErrore } from '../suoni.js';
import TrainingDisclaimer from '../components/TrainingDisclaimer.jsx';
import './Allenamento.css';

const MAX_TENTATIVI = 3;
const RITARDO_AVANZAMENTO = 800;
const FLUSSI_INFO = {
  piano: { etichetta: '📋 Piano (debolezze)', breve: 'Piano' },
  temi: { etichetta: '🎯 Temi liberi', breve: 'Temi' },
  errori: { etichetta: '🛠️ Dai miei errori', breve: 'Errori' },
};

const uciToMove = (u) => ({ from: u.slice(0, 2), to: u.slice(2, 4), promotion: 'q' });
const uciCaselle = (u) => [u.slice(0, 2), u.slice(2, 4)];

export default function Allenamento() {
  const boardEl = useRef(null);
  const cg = useRef(null);
  const chess = useRef(null);
  const onMoveRef = useRef(() => {});
  // Stato mutabile del puzzle corrente (fuori da React: non deve causare re-render).
  const S = useRef({
    tentativi: 0, esitoInviato: false, soluzione: [], puzzle: null,
    ultimaMossa: null, ultimaSbagliata: null, replay: [], replayIdx: 0, mosseGiocate: [],
  });

  const [stato, setStato] = useState('Caricamento...');
  const [info, setInfo] = useState('');
  const [statsText, setStatsText] = useState('');
  const [flussi, setFlussi] = useState(null);
  const [flussoAttivo, setFlussoAttivo] = useState('piano');
  const [temiCat, setTemiCat] = useState(null);
  const [temaAttivo, setTemaAttivo] = useState(null);
  const [badge, setBadge] = useState(null);
  const [replay, setReplay] = useState({ visible: false, disabled: false });
  const [vista, setVista] = useState('menu');     // 'menu' | 'piano' | 'temi' | 'errori'
  const [catAperta, setCatAperta] = useState(null); // categoria temi aperta (Tattiche/Matti/Finali)
  const [searchParams] = useSearchParams();       // ?tema= dai pulsanti "allena" delle Carenze

  // ---- helper sulla scacchiera (usano i ref, quindi stabili tutta la sessione) ----
  const mosseLegali = () => {
    const d = new Map();
    chess.current.moves({ verbose: true }).forEach((m) => {
      if (!d.has(m.from)) d.set(m.from, []);
      d.get(m.from).push(m.to);
    });
    return d;
  };
  const coloreInScacco = () =>
    chess.current.inCheck?.() ? (chess.current.turn() === 'w' ? 'white' : 'black') : false;
  const uciToSan = (uci) => {
    try {
      const tmp = new Chess(chess.current.fen());
      const m = tmp.move({ from: uci.slice(0, 2), to: uci.slice(2, 4), promotion: 'q' });
      if (m && m.san) return m.san;
    } catch { /* fallback UCI */ }
    return uci;
  };
  const aggiornaBoard = () => {
    const colore = chess.current.turn() === 'w' ? 'white' : 'black';
    cg.current.set({
      fen: chess.current.fen(), turnColor: colore, check: coloreInScacco(),
      lastMove: S.current.ultimaMossa,
      movable: { color: colore, dests: mosseLegali(), free: false },
    });
  };

  // ---- rete ----
  const inviaEsito = async (risultato) => {
    try {
      const r = await fetch(`${BACKEND}/esito`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ puzzle_id: S.current.puzzle.id, risultato, mosse_giocate: S.current.mosseGiocate }),
      });
      const stats = await r.json();
      mostraStatistiche(stats);
      if (stats.fascia_cambiata) {
        const verso = stats.fascia_cambiata === 'alzata' ? '📈 salita' : '📉 scesa';
        setInfo((p) => p + `  ·  Difficoltà ${verso}! Nuova fascia Elo ${stats.elo_min}-${stats.elo_max}`);
      }
    } catch (e) { console.error('Errore invio esito:', e); }
  };

  const mostraStatistiche = (stats) => {
    if (!stats || !stats.flusso) return;
    const breve = FLUSSI_INFO[stats.flusso]?.breve || stats.flusso;
    const tema = stats.tema_libero ? ` (${stats.tema_libero.replace(/_/g, ' ')})` : '';
    let t = `Flusso ${breve}${tema}: ${stats.risolti_primo}/${stats.tentati} al primo colpo `
      + `(${stats.percentuale_primo}%) · ${stats.falliti} soluzioni viste`
      + (stats.elo_min ? `  ·  fascia ${stats.elo_min}-${stats.elo_max}` : '');
    if (stats.complessivo) t += `  ·  totale su tutti i flussi: ${stats.complessivo.tentati_totali} puzzle`;
    setStatsText(t);
  };

  const aggiornaStatisticheDaServer = async () => {
    try { mostraStatistiche(await fetch(`${BACKEND}/statistiche`).then((r) => r.json())); }
    catch (e) { console.error(e); }
  };

  const mostraBadge = (puzzle, flusso) => {
    if (flusso !== 'errori') { setBadge(null); return; }
    if ((puzzle.origine || 'lichess') === 'errore') {
      const n = puzzle.lunghezza_soluzione || 1;
      setBadge({ cls: 'badge-errore', text: n > 1 ? `📍 Tuo errore · 🧩 Combinazione (${n} mosse)` : '📍 Tuo errore' });
    } else {
      setBadge({ cls: 'badge-lichess', text: '♟ Rinforzo Lichess' });
    }
  };

  const caricaProssimoPuzzle = async () => {
    setInfo('Carico il prossimo puzzle...');
    Object.assign(S.current, {
      tentativi: 0, esitoInviato: false, ultimaMossa: null, ultimaSbagliata: null,
      replay: [], replayIdx: 0, mosseGiocate: [],
    });
    setReplay({ visible: false, disabled: false });
    setBadge(null);
    if (cg.current) cg.current.setShapes([]);
    try {
      const dati = await fetch(`${BACKEND}/prossimo-puzzle`).then((r) => r.json());
      if (dati.fine) { setInfo(dati.messaggio || '🎉 Hai completato tutti i puzzle disponibili!'); return; }
      S.current.puzzle = dati.puzzle;
      mostraBadge(dati.puzzle, dati.flusso);
      const mosse = dati.puzzle.moves.split(' ');
      chess.current = new Chess(dati.puzzle.fen);
      chess.current.move(uciToMove(mosse[0]));
      S.current.ultimaMossa = uciCaselle(mosse[0]);
      S.current.soluzione = mosse.slice(1);
      const orient = chess.current.turn() === 'w' ? 'white' : 'black';
      if (!cg.current) {
        cg.current = Chessground(boardEl.current, {
          fen: chess.current.fen(), orientation: orient, turnColor: orient,
          check: coloreInScacco(), lastMove: S.current.ultimaMossa,
          animation: { enabled: true, duration: 250 },
          highlight: { lastMove: true, check: true },
          movable: { color: orient, dests: mosseLegali(), free: false },
          drawable: { enabled: true, brushes: {} },
          events: { move: (o, d) => onMoveRef.current(o, d) },
        });
      } else {
        cg.current.set({ orientation: orient });
        aggiornaBoard();
      }
      setStato(`Puzzle ${dati.numero}/${dati.totale} · tema: ${dati.puzzle.motivo_allenamento} `
        + `(${dati.puzzle.fase_allenamento}) · Elo ${dati.puzzle.rating}`);
      const latoIt = orient === 'white' ? 'Bianco' : 'Nero';
      setInfo(`<span class="turno">Tocca a te (${latoIt})</span> — trova la mossa migliore!`);
    } catch (e) {
      setInfo('⚠️ Errore nel contattare il server. È avviato su localhost:8000?');
      console.error(e);
    }
  };

  const onMossaGiocatore = (orig, dest) => {
    const mossaUci = orig + dest;
    const attesa = S.current.soluzione[0];
    const giusta = mossaUci === attesa || (attesa && attesa.slice(0, 4) === mossaUci);
    if (giusta) {
      const mUser = chess.current.move(uciToMove(attesa));
      (mUser && mUser.captured ? suonaCattura : suonaMossa)();
      S.current.ultimaMossa = uciCaselle(attesa);
      S.current.mosseGiocate.push(mossaUci);
      S.current.soluzione.shift();
      if (S.current.soluzione.length === 0) {
        suonaSuccesso();
        setInfo('<span class="ok">✅ Corretto! Puzzle risolto.</span>');
        aggiornaBoard();
        cg.current.set({ movable: { color: undefined } });
        if (!S.current.esitoInviato) { inviaEsito(S.current.tentativi === 0 ? 'primo' : 'secondo'); S.current.esitoInviato = true; }
        setTimeout(caricaProssimoPuzzle, RITARDO_AVANZAMENTO);
        return;
      }
      const rispostaAvv = S.current.soluzione.shift();
      const mAvv = chess.current.move(uciToMove(rispostaAvv));
      (mAvv && mAvv.captured ? suonaCattura : suonaMossa)();
      S.current.ultimaMossa = uciCaselle(rispostaAvv);
      aggiornaBoard();
      setInfo('<span class="ok">✅ Bene! Continua...</span>');
    } else {
      suonaErrore();
      S.current.tentativi += 1;
      S.current.ultimaSbagliata = [orig, dest];
      if (S.current.tentativi >= MAX_TENTATIVI) {
        const sol = S.current.soluzione[0];
        const san = uciToSan(sol);
        aggiornaBoard();
        const [o, d] = uciCaselle(sol);
        const shapes = [];
        if (S.current.ultimaSbagliata) shapes.push({ orig: S.current.ultimaSbagliata[0], dest: S.current.ultimaSbagliata[1], brush: 'red' });
        shapes.push({ orig: o, dest: d, brush: 'green' });
        cg.current.setShapes(shapes);
        cg.current.set({ movable: { color: undefined } });
        S.current.replay = S.current.soluzione.slice();
        S.current.replayIdx = 0;
        if (S.current.replay.length > 1) {
          setInfo(`<span class="ko">❌ La mossa giusta era ${san}. È una combinazione: ripercorrila col pulsante ▶.</span>`);
          setReplay({ visible: true, disabled: false });
        } else {
          setInfo(`<span class="ko">❌ La mossa giusta era ${san}. Guarda la freccia. Passa al prossimo.</span>`);
        }
        if (!S.current.esitoInviato) { inviaEsito('fallito'); S.current.esitoInviato = true; }
      } else {
        setInfo(`<span class="ko">❌ Non è giusta. Riprova (tentativo ${S.current.tentativi}/${MAX_TENTATIVI}).</span>`);
        aggiornaBoard();
      }
    }
  };
  onMoveRef.current = onMossaGiocatore;

  const avanzaReplay = () => {
    if (S.current.replayIdx >= S.current.replay.length) return;
    const uci = S.current.replay[S.current.replayIdx];
    const san = uciToSan(uci);
    const [orig, dest] = uciCaselle(uci);
    const mia = S.current.replayIdx % 2 === 0;
    chess.current.move(uciToMove(uci));
    S.current.ultimaMossa = [orig, dest];
    aggiornaBoard();
    cg.current.set({ movable: { color: undefined } });
    cg.current.setShapes([{ orig, dest, brush: mia ? 'green' : 'blue' }]);
    S.current.replayIdx += 1;
    const etichetta = mia ? 'La tua mossa' : 'Risposta avversaria';
    if (S.current.replayIdx >= S.current.replay.length) {
      setInfo(`<span class="ko">${etichetta}: ${san}. Fine della combinazione — passa al prossimo.</span>`);
      setReplay((r) => ({ ...r, disabled: true }));
    } else {
      setInfo(`<span class="ko">${etichetta}: ${san}. Premi ▶ per la prossima.</span>`);
    }
  };

  // ---- flussi & temi ----
  const caricaFlussi = async () => {
    try {
      const r = await fetch(`${BACKEND}/flussi`).then((x) => x.json());
      setFlussoAttivo(r.flusso_attivo);
      setFlussi(r);
    } catch (e) { console.error(e); }
  };
  const cambiaFlusso = async (nome) => {
    try {
      const resp = await fetch(`${BACKEND}/flusso/${nome}`, { method: 'POST' });
      if (!resp.ok) { const e = await resp.json().catch(() => ({})); setInfo(e.errore || 'Questo flusso non è disponibile.'); return; }
      setFlussoAttivo(nome);
      if (nome !== 'temi') setTemaAttivo(null);
      await caricaFlussi();
      await caricaProssimoPuzzle();
      aggiornaStatisticheDaServer();
    } catch (e) { console.error(e); }
  };
  const caricaTemi = async () => {
    try {
      const dati = await fetch(`${BACKEND}/temi`).then((r) => r.json());
      const cats = dati.categorie || { Temi: dati.temi };
      setTemiCat(cats);
      return cats;
    } catch (e) { console.error(e); return {}; }
  };
  const scegliTema = async (tema) => {
    try {
      await fetch(`${BACKEND}/scegli-tema/${tema}`, { method: 'POST' });
      setFlussoAttivo('temi');
      setTemaAttivo(tema);
      await caricaFlussi();
      await caricaProssimoPuzzle();
      aggiornaStatisticheDaServer();
    } catch (e) { console.error(e); }
  };

  // Entrare/uscire da un flusso. In "menu" NON c'e' scacchiera (per non confondere):
  // compare solo quando si entra in un flusso.
  const apriFlusso = async (nome) => {
    setVista(nome);
    if (nome === 'temi') { setCatAperta(null); setTemaAttivo(null); return; }
    await cambiaFlusso(nome);
  };
  const tornaAlMenu = () => {
    setVista('menu');
    setCatAperta(null);
    setTemaAttivo(null);
    if (cg.current) { cg.current.destroy(); cg.current = null; }
    setStato('Caricamento...');
    setInfo('');
  };

  // Avvio: stato flussi e temi. Se arrivo con ?tema=... (dai pulsanti delle Carenze),
  // entro direttamente nel flusso Temi e avvio quel tema.
  useEffect(() => {
    caricaFlussi();
    (async () => {
      const cats = await caricaTemi();
      const tema = searchParams.get('tema');
      if (tema) {
        const cat = Object.keys(cats).find((c) => (cats[c] || []).includes(tema));
        setVista('temi');
        setCatAperta(cat || null);
        scegliTema(tema);
      }
    })();
    return () => { if (cg.current) { cg.current.destroy(); cg.current = null; } };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const boardVisibile = vista === 'piano' || vista === 'errori' || (vista === 'temi' && temaAttivo);
  const erroriPronto = flussi?.flussi?.errori?.implementato ?? false;

  return (
    <div className="allenamento">
      <TrainingDisclaimer />
      <div className="page-head">
        <h1>Allenamento</h1>
        <p>Puzzle costruiti sulle tue partite. Scegli un flusso; la scacchiera è condivisa.</p>
      </div>

      {vista === 'menu' ? (
        <div className="flussi-menu">
          <button className="flusso-card" onClick={() => apriFlusso('piano')}>
            <span className="fc-ic">📋</span>
            <span className="fc-tit">Piano (debolezze)</span>
            <span className="fc-sub">Esercizi scelti automaticamente su dove sbagli di più.</span>
          </button>
          <button className="flusso-card" onClick={() => apriFlusso('temi')}>
            <span className="fc-ic">🎯</span>
            <span className="fc-tit">Temi liberi</span>
            <span className="fc-sub">Scegli tu su cosa allenarti: tattiche, matti, finali.</span>
          </button>
          <button
            className={'flusso-card' + (erroriPronto ? '' : ' disabilitato')}
            disabled={!erroriPronto}
            onClick={() => erroriPronto && apriFlusso('errori')}
          >
            <span className="fc-ic">🛠️</span>
            <span className="fc-tit">Dai miei errori{erroriPronto ? '' : ' (presto)'}</span>
            <span className="fc-sub">Rivedi le posizioni dove hai sbagliato.</span>
          </button>
        </div>
      ) : (
        <>
          <button className="btn btn-ghost torna" onClick={tornaAlMenu}>← Tutti i flussi</button>

          {vista === 'piano' && (
            <p className="pannello-intestazione">📋 <strong>Piano (dalle tue debolezze)</strong> — esercizi
              scelti su dove sbagli di più. Dettaglio in <Link to="/carenze">Le mie carenze</Link>.</p>
          )}
          {vista === 'errori' && (
            <p className="pannello-intestazione">🛠️ <strong>Dai miei errori</strong> — rivedi le posizioni dove hai sbagliato.</p>
          )}
          {vista === 'temi' && (
            <div className="temi">
              <div className="temi-tabs">
                {temiCat && Object.keys(temiCat).map((cat) => (
                  <button
                    key={cat}
                    className={'temi-tab' + (cat === catAperta ? ' attivo' : '')}
                    onClick={() => setCatAperta(cat === catAperta ? null : cat)}
                  >
                    {cat}
                  </button>
                ))}
              </div>
              {catAperta && temiCat?.[catAperta] && (
                <div className="tema-menu">
                  {temiCat[catAperta].map((t) => (
                    <button
                      key={t}
                      className={'tema-voce' + (t === temaAttivo ? ' attivo' : '')}
                      onClick={() => scegliTema(t)}
                    >
                      {t.replace(/_/g, ' ')}
                    </button>
                  ))}
                </div>
              )}
              {!temaAttivo && (
                <p className="temi-hint muted">Scegli una categoria, poi un tema: la scacchiera comparirà qui sotto.</p>
              )}
            </div>
          )}

          {boardVisibile && (
            <div className="zona-scacchiera card">
              <div className="stato">{stato}</div>
              {badge && <div className={'badge-origine ' + badge.cls}>{badge.text}</div>}
              <div className="board-frame">
                <div ref={boardEl} className="board" />
              </div>
              {/* Messaggi generati dal sistema (no input utente): innerHTML controllato. */}
              <div className="info" dangerouslySetInnerHTML={{ __html: info }} />
              {replay.visible && (
                <button className="btn btn-ghost replay" disabled={replay.disabled} onClick={avanzaReplay}>
                  ▶ Rivedi la sequenza
                </button>
              )}
              <div className="stats">{statsText}</div>
              <button className="btn btn-primary" onClick={caricaProssimoPuzzle}>Prossimo puzzle</button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
