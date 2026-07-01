/*
 * Scacchiera giocabile per l'allenamento puzzle (Fase 4 / frontend).
 *
 * Chiede un puzzle al backend (localhost:8000), lo mostra sulla scacchiera,
 * applica la prima mossa dell'avversario, e lascia che il giocatore trovi la
 * soluzione trascinando i pezzi.
 *
 * - chess.js gestisce le regole (mosse legali, posizione)
 * - chessground disegna la scacchiera e il drag&drop
 *
 * Regola tentativi: 3 tentativi sbagliati, poi mostra la soluzione e va avanti.
 * IMPORTANTE: conta come "successo" (per adattivita' e statistiche) SOLO il
 * puzzle risolto al PRIMO tentativo. Il 2o e 3o tentativo sono margine didattico.
 *
 * Flussi: l'allenamento e' diviso in tre flussi indipendenti (piano / temi /
 * errori), ciascuno con coda, fascia Elo e statistiche proprie. L'utente sceglie
 * il flusso dal selettore in alto; statistiche e grafici si riferiscono al flusso
 * attivo. Ogni puzzle porta un campo "origine" ("errore" per i miei errori,
 * "lichess" per i puzzle del DB); nel flusso "errori" lo mostriamo come badge.
 */

import { Chess } from 'chess.js';
import { Chessground } from 'chessground';
import Chart from 'chart.js/auto';

// Stili di chessground (scacchiera e pezzi).
import 'chessground/assets/chessground.base.css';
import 'chessground/assets/chessground.brown.css';
import 'chessground/assets/chessground.cburnett.css';
import './style.css';

const BACKEND = 'http://localhost:8000';
const MAX_TENTATIVI = 3;
const RITARDO_AVANZAMENTO = 800;  // ms di pausa dopo un puzzle risolto, poi avanza da solo

// Metadati di presentazione dei tre flussi (etichetta lunga + breve).
const FLUSSI_INFO = {
  piano: { etichetta: '📋 Piano (debolezze)', breve: 'Piano' },
  temi: { etichetta: '🎯 Temi liberi', breve: 'Temi' },
  errori: { etichetta: '🛠️ Dai miei errori', breve: 'Errori' },
};

let flussoAttivo = 'piano';  // quale flusso e' attivo (sincronizzato col backend)

// Stato corrente del puzzle in gioco.
let chess = null;          // istanza chess.js con la posizione corrente
let soluzione = [];        // mosse-soluzione rimaste da giocare (UCI)
let board = null;          // istanza chessground
let tentativi = 0;         // tentativi sbagliati sul puzzle corrente
let esitoInviato = false;  // per non inviare due volte l'esito dello stesso puzzle
let puzzleCorrente = null; // dati del puzzle dal server
let ultimaMossa = null;    // [from, to] dell'ultima mossa, per evidenziarla
let ultimaMossaSbagliata = null; // [from, to] dell'ultimo tentativo fallito, per la freccia rossa

// Elementi della pagina.
const elBoard = document.getElementById('board');
const elInfo = document.getElementById('info');
const elStato = document.getElementById('stato');
const elBadgeOrigine = document.getElementById('badge-origine');
const elProssimo = document.getElementById('prossimo');
const elStats = document.getElementById('stats');
const elTemi = document.getElementById('temi');
const elFlussi = document.getElementById('flussi');
// Pannelli-schermata dei tre flussi (Tappa 1a di R4): solo quello del flusso
// attivo e' visibile; la scacchiera resta unica e condivisa sotto di esso.
const elPannelli = {
  piano: document.getElementById('pannello-piano'),
  temi: document.getElementById('pannello-temi'),
  errori: document.getElementById('pannello-errori'),
};
const elProgressi = document.getElementById('progressi');
const elToggleCarenze = document.getElementById('toggle-carenze');
const elCarenze = document.getElementById('carenze');
const elPianoEstratto = document.getElementById('piano-estratto-carenze');
const elCarenzeSintesi = document.getElementById('carenze-sintesi');
const elCarenzeCome = document.getElementById('carenze-come');
const elCarenzeDove = document.getElementById('carenze-dove');
const elCarenzeQuanto = document.getElementById('carenze-quanto');
const elCarenzePiano = document.getElementById('carenze-piano');
const elCarenzeFasi = document.getElementById('carenze-fasi');
const elCarenzeConfronto = document.getElementById('carenze-confronto');
const elCarenzeConversione = document.getElementById('carenze-conversione');
const elEvoluzioneVuoto = document.getElementById('evoluzione-vuoto');
const elEvoluzioneGrafici = document.getElementById('evoluzione-grafici');
const elProgressiVuoto = document.getElementById('progressi-vuoto');
const elIndicatoreTendenza = document.getElementById('indicatore-tendenza');
const elRiepilogoBox = document.getElementById('riepilogo-box');
const elProgressiFlusso = document.getElementById('progressi-flusso');

// Converte una stringa UCI ("e2e4") in {from, to, promotion}.
function uciToMove(uci) {
  return { from: uci.slice(0, 2), to: uci.slice(2, 4), promotion: 'q' };
}

// Spezza una mossa UCI in [from, to] per l'evidenziazione.
function uciCaselle(uci) {
  return [uci.slice(0, 2), uci.slice(2, 4)];
}

// Converte una mossa UCI nella notazione SAN leggibile, partendo dalla
// posizione corrente. Lavora su una copia (Chess(fen)) per non sporcare lo
// stato del puzzle. Se il SAN non si ottiene, ripiega sull'UCI grezzo.
function uciToSan(uci) {
  try {
    const tmp = new Chess(chess.fen());
    const m = tmp.move({ from: uci.slice(0, 2), to: uci.slice(2, 4), promotion: 'q' });
    if (m && m.san) return m.san;
  } catch (e) {
    // posizione/mossa non valida: uso il fallback UCI sotto.
  }
  return uci;
}

// Calcola le mosse legali per chessground (mappa casa -> case raggiungibili).
function mosseLegali() {
  const dests = new Map();
  chess.moves({ verbose: true }).forEach((m) => {
    if (!dests.has(m.from)) dests.set(m.from, []);
    dests.get(m.from).push(m.to);
  });
  return dests;
}

// Restituisce il colore in scacco ('white'/'black') o false.
function coloreInScacco() {
  if (chess.inCheck && chess.inCheck()) {
    return chess.turn() === 'w' ? 'white' : 'black';
  }
  return false;
}

// Aggiorna la scacchiera con la posizione corrente di chess.js.
function aggiornaBoard() {
  const colore = chess.turn() === 'w' ? 'white' : 'black';
  board.set({
    fen: chess.fen(),
    turnColor: colore,
    check: coloreInScacco(),
    lastMove: ultimaMossa,
    movable: {
      color: colore,
      dests: mosseLegali(),
      free: false,
    },
  });
}

// Mostra un badge sull'origine del puzzle. Nel flusso "errori" distingue i miei
// errori (📍) dai rinforzi Lichess (♟); negli altri flussi resta nascosto (i loro
// puzzle sono tutti "lichess" e il badge non aggiunge nulla).
function mostraBadgeOrigine(puzzle, flusso) {
  if (!elBadgeOrigine) return;
  if (flusso !== 'errori') {
    elBadgeOrigine.hidden = true;
    return;
  }
  const origine = puzzle.origine || 'lichess';
  if (origine === 'errore') {
    // I puzzle estesi richiedono piu' mosse: lo segnaliamo accanto al badge cosi'
    // l'utente sa che non basta una singola mossa. lunghezza_soluzione == 1 -> base.
    const lunghezza = puzzle.lunghezza_soluzione || 1;
    elBadgeOrigine.textContent = lunghezza > 1
      ? `📍 Tuo errore · 🧩 Combinazione (${lunghezza} mosse)`
      : '📍 Tuo errore';
    elBadgeOrigine.className = 'badge-origine badge-errore';
  } else {
    elBadgeOrigine.textContent = '♟ Rinforzo Lichess';
    elBadgeOrigine.className = 'badge-origine badge-lichess';
  }
  elBadgeOrigine.hidden = false;
}

// Chiede un nuovo puzzle al backend e lo imposta.
async function caricaProssimoPuzzle() {
  elInfo.textContent = 'Carico il prossimo puzzle...';
  tentativi = 0;
  esitoInviato = false;
  ultimaMossa = null;  // azzero: non deve restare l'evidenziazione del puzzle precedente
  ultimaMossaSbagliata = null;  // azzero: la freccia rossa non deve passare al puzzle successivo
  if (board) board.setShapes([]);  // pulisco eventuali frecce-soluzione del puzzle precedente
  if (elBadgeOrigine) elBadgeOrigine.hidden = true;
  try {
    const risposta = await fetch(`${BACKEND}/prossimo-puzzle`);
    const dati = await risposta.json();

    if (dati.fine) {
      elInfo.textContent = dati.messaggio || '🎉 Hai completato tutti i puzzle disponibili!';
      return;
    }

    puzzleCorrente = dati.puzzle;
    mostraBadgeOrigine(puzzleCorrente, dati.flusso);
    const mosse = puzzleCorrente.moves.split(' ');

    // Carico la posizione e applico la PRIMA mossa (avversario).
    chess = new Chess(puzzleCorrente.fen);
    chess.move(uciToMove(mosse[0]));
    ultimaMossa = uciCaselle(mosse[0]);

    // Le mosse rimanenti sono la soluzione che il giocatore deve trovare.
    soluzione = mosse.slice(1);

    // Oriento la scacchiera dal lato di chi deve muovere.
    const orient = chess.turn() === 'w' ? 'white' : 'black';

    if (!board) {
      board = Chessground(elBoard, {
        fen: chess.fen(),
        orientation: orient,
        turnColor: orient,
        check: coloreInScacco(),
        lastMove: ultimaMossa,
        animation: { enabled: true, duration: 250 },
        highlight: { lastMove: true, check: true },
        movable: { color: orient, dests: mosseLegali(), free: false },
        // Abilito il sistema "drawable" nativo: lo usiamo per disegnare la
        // freccia-soluzione sull'errore (brush di default: green/red/blue/yellow).
        drawable: { enabled: true, brushes: {} },
        events: { move: onMossaGiocatore },
      });
    } else {
      board.set({ orientation: orient });
      aggiornaBoard();
    }

    elStato.textContent =
      `Puzzle ${dati.numero}/${dati.totale} - ` +
      `tema: ${puzzleCorrente.motivo_allenamento} (${puzzleCorrente.fase_allenamento}) - ` +
      `Elo ${puzzleCorrente.rating}`;
    const latoIt = orient === 'white' ? 'Bianco' : 'Nero';
    elInfo.innerHTML = `<span class="turno">Tocca a te (${latoIt})</span> — trova la mossa migliore!`;
  } catch (err) {
    elInfo.textContent = '⚠️ Errore nel contattare il server. È avviato su localhost:8000?';
    console.error(err);
  }
}

// Invia l'esito del puzzle corrente al backend e aggiorna le statistiche a video.
async function inviaEsito(risultato) {
  try {
    const risposta = await fetch(`${BACKEND}/esito`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ puzzle_id: puzzleCorrente.id, risultato }),
    });
    const stats = await risposta.json();
    mostraStatistiche(stats);
    // Se la sezione progressi e' aperta, tengo i grafici aggiornati.
    if (elProgressi && !elProgressi.hidden) aggiornaProgressi();
    if (stats.fascia_cambiata) {
      const verso = stats.fascia_cambiata === 'alzata' ? '📈 salita' : '📉 scesa';
      elInfo.innerHTML +=
        `  ·  Difficoltà ${verso}! Nuova fascia Elo ${stats.elo_min}-${stats.elo_max}`;
    }
  } catch (err) {
    console.error('Errore invio esito:', err);
  }
}

// Mostra le statistiche del FLUSSO ATTIVO nella pagina (+ totale complessivo).
function mostraStatistiche(stats) {
  if (!elStats) return;
  const breve = (FLUSSI_INFO[stats.flusso] && FLUSSI_INFO[stats.flusso].breve) || stats.flusso;
  const tema = stats.tema_libero ? ` (${stats.tema_libero.replace(/_/g, ' ')})` : '';
  let testo =
    `Flusso ${breve}${tema}: ${stats.risolti_primo}/${stats.tentati} al primo colpo ` +
    `(${stats.percentuale_primo}%) · ${stats.falliti} soluzioni viste` +
    (stats.elo_min ? `  ·  fascia ${stats.elo_min}-${stats.elo_max}` : '');
  if (stats.complessivo) {
    testo += `  ·  totale su tutti i flussi: ${stats.complessivo.tentati_totali} puzzle`;
  }
  elStats.textContent = testo;
}

// Scarica e mostra le statistiche correnti del flusso attivo (senza un esito).
async function aggiornaStatisticheDaServer() {
  try {
    const s = await fetch(`${BACKEND}/statistiche`).then((r) => r.json());
    mostraStatistiche(s);
  } catch (err) {
    console.error('Errore caricamento statistiche:', err);
  }
}

// Chiamata quando il giocatore trascina un pezzo.
function onMossaGiocatore(orig, dest) {
  const mossaUci = orig + dest;
  const attesa = soluzione[0];

  // Confronto (gestisco anche promozioni: confronto i primi 4 caratteri).
  const giusta = (mossaUci === attesa) || (attesa && attesa.slice(0, 4) === mossaUci);

  if (giusta) {
    // Mossa corretta: la applico davvero.
    chess.move(uciToMove(attesa));
    ultimaMossa = uciCaselle(attesa);
    soluzione.shift();

    if (soluzione.length === 0) {
      // Puzzle risolto!
      elInfo.innerHTML = '<span class="ok">✅ Corretto! Puzzle risolto.</span>';
      aggiornaBoard();
      board.set({ movable: { color: undefined } });
      if (!esitoInviato) {
        // SOLO 0 errori = "primo" (= successo per adattivita'/statistiche);
        // 1 o 2 errori = "secondo" (risolto ma non conta come successo).
        inviaEsito(tentativi === 0 ? 'primo' : 'secondo');
        esitoInviato = true;
      }
      // Avanzamento automatico: dopo un successo, passa da solo al prossimo.
      setTimeout(caricaProssimoPuzzle, RITARDO_AVANZAMENTO);
      return;
    }

    // C'è ancora soluzione: l'avversario risponde con la mossa successiva.
    const rispostaAvv = soluzione.shift();
    chess.move(uciToMove(rispostaAvv));
    ultimaMossa = uciCaselle(rispostaAvv);
    aggiornaBoard();
    elInfo.innerHTML = '<span class="ok">✅ Bene! Continua...</span>';
  } else {
    // Mossa sbagliata.
    tentativi += 1;
    ultimaMossaSbagliata = [orig, dest]; // la mossa appena giocata (per la freccia rossa alla rivelazione)
    if (tentativi >= MAX_TENTATIVI) {
      // Mostro la soluzione e fermo il puzzle. Mostro SOLO la prima mossa
      // (soluzione[0]) anche per i puzzle multi-mossa: è chiaro e sufficiente.
      const sol = soluzione[0];
      const san = uciToSan(sol);  // SAN leggibile (fallback su UCI grezzo).
      elInfo.innerHTML = `<span class="ko">❌ La mossa giusta era ${san}. Guarda la freccia. Passa al prossimo.</span>`;
      aggiornaBoard();
      // Disegno le frecce con il sistema nativo di chessground: la ROSSA dell'ultima
      // mia mossa sbagliata (se c'è) e la VERDE della soluzione. La verde è spinta DOPO
      // nell'array: se le due frecce si sovrappongono, la soluzione resta visibile sopra.
      const [orig, dest] = uciCaselle(sol);
      const shapes = [];
      if (ultimaMossaSbagliata) {
        shapes.push({ orig: ultimaMossaSbagliata[0], dest: ultimaMossaSbagliata[1], brush: 'red' });
      }
      shapes.push({ orig, dest, brush: 'green' });
      board.setShapes(shapes);
      board.set({ movable: { color: undefined } });
      if (!esitoInviato) {
        inviaEsito('fallito');
        esitoInviato = true;
      }
    } else {
      elInfo.innerHTML = `<span class="ko">❌ Non è giusta. Riprova (tentativo ${tentativi}/${MAX_TENTATIVI}).</span>`;
      // Rimetto la posizione corretta (la mossa sbagliata non viene applicata).
      aggiornaBoard();
    }
  }
}


// --- Selettore dei flussi (piano / temi / errori) ---

// Sposta l'UNICA sezione progressi dentro il pannello del flusso indicato.
// La sezione (e i suoi canvas) esiste una sola volta nel DOM: niente id
// duplicati, stessa aggiornaProgressi — cambia solo il pannello che la ospita.
function agganciaProgressiAlPannello(nome) {
  const pannello = elPannelli[nome];
  if (pannello && elProgressi && elProgressi.parentElement !== pannello) {
    pannello.appendChild(elProgressi);
  }
}

// Mostra SOLO il pannello-schermata del flusso indicato e nasconde gli altri
// due. I controlli specifici di un flusso (es. i pulsanti dei temi) vivono
// dentro il rispettivo pannello, quindi compaiono/spariscono di conseguenza.
function mostraSchermataFlusso(nome) {
  Object.entries(elPannelli).forEach(([n, el]) => {
    if (el) el.hidden = n !== nome;
  });
  // La sezione progressi segue il pannello attivo, cosi' se e' aperta resta
  // visibile anche dopo il cambio flusso (i dati li aggiorna chi cambia flusso).
  agganciaProgressiAlPannello(nome);
}

// Azzera COMPLETAMENTE lo stato visivo e logico della scacchiera, come a
// inizio di un nuovo puzzle: niente frecce-soluzione, niente evidenziazioni,
// niente contatori residui. Va chiamata al cambio flusso, PRIMA di caricare
// il puzzle del nuovo flusso: la schermata non deve ereditare NULLA.
function pulisciScacchiera() {
  tentativi = 0;
  esitoInviato = false;
  soluzione = [];
  puzzleCorrente = null;
  ultimaMossa = null;
  ultimaMossaSbagliata = null;
  if (board) {
    board.setShapes([]);  // via le frecce (verde soluzione + rossa errore)
    board.set({ lastMove: undefined, selected: undefined, movable: { color: undefined } });
  }
  if (elBadgeOrigine) elBadgeOrigine.hidden = true;
}

// Scarica lo stato dei flussi e (ri)disegna il selettore.
async function caricaFlussi() {
  try {
    const r = await fetch(`${BACKEND}/flussi`).then((x) => x.json());
    flussoAttivo = r.flusso_attivo;
    renderFlussi(r);
  } catch (err) {
    console.error('Errore caricamento flussi:', err);
  }
}

// Disegna i pulsanti dei flussi, evidenzia l'attivo e mostra il totale complessivo.
function renderFlussi(r) {
  elFlussi.innerHTML = '<span class="flussi-label">Flusso di allenamento:</span>';
  Object.entries(r.flussi).forEach(([nome, info]) => {
    const btn = document.createElement('button');
    btn.className = 'flusso-btn';
    btn.classList.toggle('attivo', nome === r.flusso_attivo);
    const meta = FLUSSI_INFO[nome] || { etichetta: nome };
    btn.textContent = info.implementato ? meta.etichetta : `${meta.etichetta} (presto)`;
    btn.dataset.flusso = nome;
    if (info.implementato) {
      btn.addEventListener('click', () => cambiaFlusso(nome));
    } else {
      btn.classList.add('disabilitato');
      btn.disabled = true;
      btn.title = 'Flusso non ancora implementato (arriverà col punto 6 della visione).';
    }
    elFlussi.appendChild(btn);
  });
  // Riepilogo complessivo: totale puzzle fatti sommando i flussi.
  const c = r.complessivo;
  if (c) {
    const tot = document.createElement('span');
    tot.className = 'flussi-totale';
    tot.textContent = `Totale (tutti i flussi): ${c.tentati_totali} puzzle`;
    elFlussi.appendChild(tot);
  }
  // Schermata coerente col flusso attivo: solo il suo pannello e' visibile
  // (i pulsanti dei temi vivono dentro #pannello-temi e seguono il pannello).
  mostraSchermataFlusso(r.flusso_attivo);
}

// Cambia il flusso attivo, poi ricarica puzzle, statistiche ed eventuali grafici.
async function cambiaFlusso(nome) {
  try {
    const resp = await fetch(`${BACKEND}/flusso/${nome}`, { method: 'POST' });
    if (!resp.ok) {
      const e = await resp.json().catch(() => ({}));
      elInfo.textContent = e.errore || 'Questo flusso non è disponibile.';
      return;
    }
    flussoAttivo = nome;
    mostraSchermataFlusso(nome);  // schermata subito coerente col nuovo flusso
    pulisciScacchiera();          // niente stato residuo dal flusso precedente
    await caricaFlussi();
    await caricaProssimoPuzzle();
    aggiornaStatisticheDaServer();
    // Entrando nel flusso piano, riallineo l'estratto delle carenze.
    if (nome === 'piano') aggiornaEstrattoCarenze();
    if (elProgressi && !elProgressi.hidden) aggiornaProgressi();
  } catch (err) {
    console.error('Errore cambio flusso:', err);
  }
}

// Carica i temi disponibili dal backend e crea i pulsanti, raggruppati per
// categoria (Tattiche / Matti / Finali).
async function caricaTemi() {
  try {
    const risposta = await fetch(`${BACKEND}/temi`);
    const dati = await risposta.json();
    elTemi.innerHTML = '<span class="temi-label">Allenati su un tema:</span>';
    // Fallback: se il backend non manda le categorie, uso la lista piatta.
    const categorie = dati.categorie || { Temi: dati.temi };
    Object.entries(categorie).forEach(([categoria, temi]) => {
      const gruppo = document.createElement('div');
      gruppo.className = 'tema-gruppo';
      const titolo = document.createElement('span');
      titolo.className = 'tema-categoria';
      titolo.textContent = categoria;
      gruppo.appendChild(titolo);
      temi.forEach((tema) => {
        const btn = document.createElement('button');
        btn.className = 'tema-btn';
        btn.textContent = tema.replace(/_/g, ' ');
        btn.dataset.tema = tema;  // valore vero, indipendente dal testo mostrato
        btn.addEventListener('click', () => scegliTema(tema));
        gruppo.appendChild(btn);
      });
      elTemi.appendChild(gruppo);
    });
  } catch (err) {
    console.error('Errore caricamento temi:', err);
  }
}

// Avvia l'allenamento focalizzato su un tema scelto (attiva il flusso "temi").
async function scegliTema(tema) {
  try {
    await fetch(`${BACKEND}/scegli-tema/${tema}`, { method: 'POST' });
    flussoAttivo = 'temi';  // il backend porta il flusso attivo su "temi"
    mostraSchermataFlusso('temi');  // schermata del flusso temi
    pulisciScacchiera();            // niente stato residuo dal flusso precedente
    // Evidenzio il tema attivo tra i pulsanti (confronto sul valore vero).
    document.querySelectorAll('.tema-btn').forEach((b) => {
      b.classList.toggle('attivo', b.dataset.tema === tema);
    });
    await caricaFlussi();  // riallinea il selettore (e mostra i pulsanti tema)
    await caricaProssimoPuzzle();
    aggiornaStatisticheDaServer();
    if (elProgressi && !elProgressi.hidden) aggiornaProgressi();
  } catch (err) {
    console.error('Errore scelta tema:', err);
  }
}

// --- Estratto carenze nel pannello Piano (Tappa 2 di R4) ---
// Il collegamento debolezza -> esercizio: poche righe che spiegano PERCHE' il
// flusso piano propone certi esercizi. NON e' il report completo (quello resta
// nella sezione globale "Le mie carenze"): solo le 1-2 debolezze principali.

// Scarica il profilo (stesso endpoint GET /profilo del report) e disegna l'estratto.
async function aggiornaEstrattoCarenze() {
  if (!elPianoEstratto) return;
  try {
    const r = await fetch(`${BACKEND}/profilo`);
    if (!r.ok) {
      // Profilo non ancora disponibile: messaggio neutro, il pannello resta usabile.
      elPianoEstratto.innerHTML =
        `<p class="estratto-vuoto">Analizza le tue partite per vedere qui le
          debolezze su cui lavora il Piano.</p>`;
      return;
    }
    renderEstrattoCarenze(await r.json());
  } catch (err) {
    console.error('Errore caricamento estratto carenze:', err);
    elPianoEstratto.innerHTML = '';
  }
}

// Disegna l'estratto compatto: le 1-2 debolezze tattiche principali (temi
// rilevanti ordinati per tasso) + link che apre il report completo.
function renderEstrattoCarenze(p) {
  const rilevanti = p.temi_rilevanti || [];
  const tassi = p.tasso_su_mosse_per_tipo || {};
  const percErrori = p.percentuali_tattico || {};
  const principali = [...rilevanti]
    .sort((a, b) => (tassi[b] || 0) - (tassi[a] || 0))
    .slice(0, 2);

  if (principali.length === 0) {
    elPianoEstratto.innerHTML =
      `<p class="estratto-vuoto">Nessuna debolezza tattica rilevante al momento:
        il Piano propone esercizi generali.</p>`;
    return;
  }

  const voci = principali.map((t) => {
    // Preferisco la quota sugli errori ("45% degli errori"): e' il dato che
    // giustifica meglio la scelta degli esercizi; ripiego sul tasso-mosse.
    const perc = percErrori[t];
    const dato = (perc != null) ? `${perc}% degli errori` : `${tassi[t] || 0}% delle mosse`;
    return `<li class="estratto-voce">
        <span class="estratto-tema">${etichettaCarenza(t)}</span>
        <span class="estratto-dato">${dato}</span>
      </li>`;
  }).join('');

  elPianoEstratto.innerHTML =
    `<div class="piano-estratto">
       <p class="estratto-intro">Il Piano allena le tue debolezze principali:</p>
       <ul class="estratto-lista">${voci}</ul>
       <button class="estratto-link">Vedi tutte le carenze →</button>
     </div>`;

  // Il link apre la sezione globale "Le mie carenze" (stessa logica del toggle).
  elPianoEstratto.querySelector('.estratto-link').addEventListener('click', () => {
    elCarenze.hidden = false;
    aggiornaCarenze();
    elCarenze.scrollIntoView({ behavior: 'smooth' });
  });
}

// --- Sezione "I miei progressi" (grafici Chart.js) ---

let graficoElo = null;
let graficoTemi = null;
let graficoPrimoColpo = null;

// Scarica i dati e ridisegna grafici, indicatore di tendenza e tabella.
async function aggiornaProgressi() {
  try {
    const [rFasce, rTemi, rProg] = await Promise.all([
      fetch(`${BACKEND}/storico-fasce`).then((r) => r.json()),
      fetch(`${BACKEND}/statistiche-temi`).then((r) => r.json()),
      fetch(`${BACKEND}/progressi`).then((r) => r.json()),
    ]);
    const snapshot = rProg.snapshot || [];
    // Etichetto la sezione col flusso a cui si riferiscono i dati.
    if (elProgressiFlusso) {
      const breve = (FLUSSI_INFO[rProg.flusso] && FLUSSI_INFO[rProg.flusso].breve) || rProg.flusso;
      elProgressiFlusso.textContent = breve ? `— flusso ${breve}` : '';
    }
    // Indicatore "stai migliorando?" e tabella riassuntiva (sempre visibili).
    mostraIndicatoreTendenza(rProg.tendenza);
    mostraRiepilogo(rProg.riepilogo);
    // Grafico 1: % al primo colpo nel tempo (dagli snapshot periodici).
    disegnaGraficoPrimoColpo(snapshot);
    disegnaGraficoElo(rFasce);
    disegnaGraficoTemi(rTemi.temi || {});
    // Avviso "pochi dati" se non c'e' ancora nulla di significativo.
    const niente = (rFasce.storico_fasce || []).length === 0 &&
                   snapshot.length === 0 &&
                   Object.keys(rTemi.temi || {}).length === 0;
    elProgressiVuoto.hidden = !niente;
  } catch (err) {
    console.error('Errore caricamento progressi:', err);
  }
}

// Indicatore onesto "stai migliorando?": freccia + etichetta dalla tendenza Elo.
function mostraIndicatoreTendenza(tendenza) {
  if (!elIndicatoreTendenza || !tendenza) return;
  const classe = `tendenza-${tendenza.direzione}`;  // su | stabile | giu
  elIndicatoreTendenza.className = `indicatore-tendenza ${classe}`;
  elIndicatoreTendenza.innerHTML =
    `<span class="tendenza-freccia">${tendenza.freccia}</span>` +
    `<span class="tendenza-testo">Stai migliorando? <strong>${tendenza.etichetta}</strong></span>`;
}

// Tabella riassuntiva dei progressi.
function mostraRiepilogo(r) {
  if (!elRiepilogoBox || !r) return;
  const iniz = r.elo_iniziale;
  const att = r.elo_attuale;
  const segno = r.guadagno >= 0 ? '+' : '';
  const tema = (t) => (t ? `${t.tema.replace(/_/g, ' ')} (${t.percentuale_primo}%)` : '—');
  elRiepilogoBox.innerHTML = `
    <table class="riepilogo-tabella">
      <tbody>
        <tr><th>Puzzle totali tentati</th><td>${r.tentati_totali}</td></tr>
        <tr><th>% al primo colpo (storica)</th><td>${r.percentuale_primo_storica}%</td></tr>
        <tr><th>Fascia Elo iniziale</th><td>${iniz[0]}–${iniz[1]}</td></tr>
        <tr><th>Fascia Elo attuale</th><td>${att[0]}–${att[1]}</td></tr>
        <tr><th>Guadagno</th><td>${segno}${r.guadagno} punti</td></tr>
        <tr><th>Tema migliore</th><td>${tema(r.tema_migliore)}</td></tr>
        <tr><th>Tema peggiore</th><td>${tema(r.tema_peggiore)}</td></tr>
      </tbody>
    </table>`;
}

// Grafico 1: percentuale di successo al primo colpo nel tempo (serie snapshot).
function disegnaGraficoPrimoColpo(snapshot) {
  // Etichetta ogni snapshot col numero di puzzle tentati a quel momento.
  const etichette = snapshot.map((s) => `${s.tentati}`);
  const valori = snapshot.map((s) => s.percentuale_primo_colpo);
  const canvas = document.getElementById('grafico-primo-colpo');
  if (graficoPrimoColpo) graficoPrimoColpo.destroy();
  graficoPrimoColpo = new Chart(canvas, {
    type: 'line',
    data: {
      labels: etichette,
      datasets: [
        {
          label: 'performance reale (% al primo colpo)',
          data: valori,
          borderColor: '#3a6ea5',
          backgroundColor: 'rgba(58,110,165,0.2)',
          tension: 0.2,
          fill: true,
        },
        {
          // Linea di riferimento orizzontale: il "bersaglio" verso cui la
          // difficolta' adattiva spinge sempre la percentuale (~85%).
          label: 'bersaglio adattivo (85%)',
          data: valori.map(() => 85),
          borderColor: '#999',
          borderDash: [5, 5],
          borderWidth: 1,
          pointRadius: 0,
          tension: 0,
          fill: false,
        },
      ],
    },
    options: {
      responsive: true,
      scales: {
        y: { beginAtZero: true, max: 100, title: { display: true, text: '%' } },
        x: { title: { display: true, text: 'puzzle tentati' } },
      },
      plugins: {
        title: { display: true, text: '% di successo al primo colpo nel tempo' },
        // Sottotitolo onesto: una linea piatta qui e' NORMALE e non indica
        // mancanza di progresso (la difficolta' si adatta). Per la crescita
        // reale si guarda la "Fascia Elo nel tempo".
        subtitle: {
          display: true,
          color: '#666',
          font: { size: 11 },
          padding: { bottom: 8 },
          text: [
            "Tende all'85% perche' la difficolta' si adatta. Una linea piatta e' NORMALE, non significa che non",
            "migliori — per il miglioramento guarda la 'Fascia Elo nel tempo'.",
          ],
        },
        legend: { display: true },
      },
    },
  });
}

// (a) Fascia Elo nel tempo: ricostruita dallo storico dei cambi di fascia.
function disegnaGraficoElo(dati) {
  const storico = dati.storico_fasce || [];
  const etichette = [];
  const valori = [];  // punto medio della fascia, piu' leggibile di due linee
  if (storico.length > 0) {
    const partenza = storico[0].da;  // fascia prima del primo cambio
    etichette.push('inizio');
    valori.push((partenza[0] + partenza[1]) / 2);
    storico.forEach((s, i) => {
      etichette.push(`cambio ${i + 1}`);
      valori.push((s.a[0] + s.a[1]) / 2);
    });
  } else {
    // Nessun cambio ancora: mostro solo la fascia attuale come singolo punto.
    etichette.push('ora');
    valori.push((dati.elo_min + dati.elo_max) / 2);
  }
  const canvas = document.getElementById('grafico-elo');
  if (graficoElo) graficoElo.destroy();
  graficoElo = new Chart(canvas, {
    type: 'line',
    data: {
      labels: etichette,
      datasets: [{
        label: 'Fascia Elo (punto medio)',
        data: valori,
        borderColor: '#4a7',
        backgroundColor: 'rgba(68,170,119,0.2)',
        tension: 0.2,
        fill: true,
      }],
    },
    options: {
      responsive: true,
      scales: {
        // NIENTE beginAtZero: un asse Elo da 0 schiaccia le variazioni che
        // contano. Lascio autoscalare Chart.js con un po' di respiro (grace).
        y: {
          grace: '10%',
          title: { display: true, text: 'Elo (punto medio fascia)' },
        },
        x: { title: { display: true, text: 'tappa' } },
      },
      plugins: {
        title: { display: true, text: 'Fascia Elo nel tempo' },
        // Sottotitolo onesto: QUESTO e' il vero indicatore di crescita.
        subtitle: {
          display: true,
          color: '#666',
          font: { size: 11 },
          padding: { bottom: 8 },
          text: [
            'Questo e\' il vero indicatore di crescita: se la fascia sale, stai migliorando davvero',
            '(i puzzle si fanno piu\' difficili a parita\' di % di successo).',
          ],
        },
      },
    },
  });
}

// (b) Percentuale di successo al primo colpo per tema.
function disegnaGraficoTemi(temi) {
  const chiavi = Object.keys(temi);
  const etichette = chiavi.map((t) => t.replace(/_/g, ' '));
  const valori = chiavi.map((t) => temi[t].percentuale_primo);
  const canvas = document.getElementById('grafico-temi');
  if (graficoTemi) graficoTemi.destroy();
  graficoTemi = new Chart(canvas, {
    type: 'bar',
    data: {
      labels: etichette,
      datasets: [{
        label: '% risolti al primo colpo',
        data: valori,
        backgroundColor: '#4a7',
      }],
    },
    options: {
      responsive: true,
      scales: {
        y: { beginAtZero: true, max: 100, title: { display: true, text: '%' } },
        x: { title: { display: true, text: 'tema' } },
      },
      plugins: { title: { display: true, text: 'Successo per tema (%)' } },
    },
  });
}

// --- Sezione "Le mie carenze" (REPORT DELLE CARENZE, punto 2) ---
// Diagnosi onesta dal profilo: NON e' legata al flusso attivo, e' il quadro
// complessivo di come e dove sbaglia il giocatore (dalle partite analizzate).

const FASI_CARENZE = ['apertura', 'mediogioco', 'finale'];
// Ordine "stile Chess.com" della qualita' delle mosse (best -> blunder).
const QUALITA_ORDINE = ['best', 'excellent', 'good', 'inaccuracy', 'mistake', 'blunder'];

// Scarica il profilo arricchito e ridisegna la sezione carenze.
async function aggiornaCarenze() {
  try {
    const r = await fetch(`${BACKEND}/profilo`);
    if (!r.ok) {
      elCarenzeSintesi.textContent =
        'Profilo non ancora disponibile: analizza e arricchisci prima le partite.';
      elCarenzeCome.innerHTML = '';
      elCarenzeDove.innerHTML = '';
      elCarenzeQuanto.innerHTML = '';
      elCarenzePiano.innerHTML = '';
      elCarenzeConfronto.innerHTML = '';
      return;
    }
    const p = await r.json();
    renderCarenze(p);
  } catch (err) {
    elCarenzeSintesi.textContent = '⚠️ Errore nel contattare il server (localhost:8000).';
    console.error('Errore caricamento carenze:', err);
  }
}

// Etichetta leggibile per un tipo tattico/fase (underscore -> spazio).
function etichettaCarenza(nome) {
  return (nome || '').replace(/_/g, ' ');
}

// Disegna le quattro parti: sintesi, COME, DOVE, QUANTO.
function renderCarenze(p) {
  // 1. Sintesi in evidenza (la frase-diagnosi).
  elCarenzeSintesi.textContent = p.sintesi || '';

  // 2. COME sbagli: tipi tattici per tasso sulle mosse, decrescente.
  const tassi = p.tasso_su_mosse_per_tipo || {};
  const ogni = p.ogni_quante_mosse_per_tipo || {};
  const conteggi = p.conteggio_tattico || {};
  const rilevanti = new Set(p.temi_rilevanti || []);
  const tipi = Object.keys(tassi)
    .filter((t) => t !== 'non_tattico')
    .sort((a, b) => (tassi[b] || 0) - (tassi[a] || 0));
  let righeCome = tipi.map((t) => {
    const nonRil = !rilevanti.has(t);
    const n = conteggi[t] || 0;
    const o = ogni[t];
    const quanto = o ? `una ogni ~${o} mosse` : 'mai osservato';
    const tag = nonRil
      ? '<span class="carenza-tag">non è un problema per te</span>' : '';
    return `<li class="carenza-item${nonRil ? ' non-rilevante' : ''}">
        <span class="carenza-nome">${etichettaCarenza(t)}</span>
        <span class="carenza-num">${n} errori · ${tassi[t]}% delle mosse · ${quanto}</span>
        ${tag}
      </li>`;
  }).join('');
  // Quota non_tattico: errori posizionali non coperti dai puzzle tattici.
  const percNonTatt = (p.percentuali_tattico || {}).non_tattico || 0;
  const tassoNonTatt = tassi.non_tattico || 0;
  righeCome += `<li class="carenza-item non-tattico">
      <span class="carenza-nome">errori posizionali</span>
      <span class="carenza-num">${percNonTatt}% degli errori gravi · ${tassoNonTatt}% delle mosse</span>
      <span class="carenza-tag">non coperti dai puzzle tattici</span>
    </li>`;
  elCarenzeCome.innerHTML =
    `<h3>Come sbagli</h3><ul class="carenza-lista">${righeCome}</ul>`;

  // 3. DOVE sbagli: le tre fasi, evidenziando la debolezza principale.
  const tassoFase = p.tasso_errore_per_fase || {};
  const dom = p.debolezza_principale;
  const righeDove = FASI_CARENZE.map((f) => {
    const principale = f === dom;
    const tasso = (tassoFase[f] != null) ? `${tassoFase[f]}%` : '—';
    const nota = principale ? ' · debolezza principale' : '';
    return `<li class="carenza-item${principale ? ' carenza-principale' : ''}">
        <span class="carenza-nome">${f}</span>
        <span class="carenza-num">${tasso} di errori${nota}</span>
      </li>`;
  }).join('');
  const notaDivario = p.fasi_divario_piccolo
    ? '<p class="carenza-nota-piccola">I tassi delle tre fasi sono vicini tra loro: '
      + 'nessuna fase è drammaticamente peggiore delle altre.</p>'
    : '';
  elCarenzeDove.innerHTML =
    `<h3>Dove sbagli</h3><ul class="carenza-lista">${righeDove}</ul>${notaDivario}`;

  // 4. QUANTO: distribuzione della qualita' delle mosse (best -> blunder), compatta.
  const grav = p.conteggio_gravita || {};
  const totGrav = QUALITA_ORDINE.reduce((s, g) => s + (grav[g] || 0), 0);
  const barre = QUALITA_ORDINE.map((g) => {
    const n = grav[g] || 0;
    const perc = totGrav ? Math.round((100 * n) / totGrav) : 0;
    return `<li class="qualita-riga">
        <span class="qualita-nome">${g}</span>
        <span class="qualita-barra"><span class="qualita-fill qualita-${g}" style="width:${perc}%"></span></span>
        <span class="qualita-num">${n} (${perc}%)</span>
      </li>`;
  }).join('');
  elCarenzeQuanto.innerHTML =
    `<h3>Quanto · qualità delle mosse</h3><ul class="qualita-lista">${barre}</ul>`;

  // 5. PIANO DI STUDIO: la parte azionabile, sotto il report.
  renderPianoStudio(p.piano_studio, p.confronto);

  // 5-bis. FASI DI GIOCO: sezione separata, sotto il piano tattico, col SUO
  //         denominatore (mosse in finale, non mosse totali). Onesta': scala distinta.
  renderStudioFasi(p.studio_fasi);

  // 6. CONFRONTO nel tempo: stai migliorando davvero? (partite recenti vs storico).
  renderConfronto(p.confronto);

  // 7. EVOLUZIONE nel tempo: grafico dei tassi DEL PERIODO (raffinamento punto 4).
  //    Usa gli stessi temi rilevanti del report, cosi' le linee combaciano col resto.
  aggiornaEvoluzione(p.temi_rilevanti || []);

  // 8. CONVERSIONE DEL VANTAGGIO: diagnosi "non converti" (punto 5). Indipendente
  //    dal profilo: ha la sua fonte dati (GET /diagnosi-conversione).
  aggiornaConversione();
}

// --- Conversione del vantaggio (prima diagnosi del punto 5) ---
// SOLO consapevolezza: mostra il pattern "non converti il vantaggio", separando i
// CROLLI (gia' coperti dall'allenamento errori) dalle EROSIONI (vantaggio sciolto
// gradualmente, il pattern che gli altri strumenti non vedono). Niente puzzle:
// l'erosione non ha una mossa-soluzione da allenare, e' solo da capire.

// Centipawn -> stringa pedoni con segno ("+2", "+15.4", "-3.3").
function centipawnPedoni(cp) {
  const v = (cp || 0) / 100;
  const segno = v > 0 ? '+' : '';
  // Interi netti senza decimali (+2), il resto con un decimale (+2.5).
  return `${segno}${Number.isInteger(v) ? v : v.toFixed(1)}`;
}

// Scarica la diagnosi di conversione e ridisegna il blocco.
async function aggiornaConversione() {
  try {
    const r = await fetch(`${BACKEND}/diagnosi-conversione`);
    if (!r.ok) { elCarenzeConversione.innerHTML = ''; return; }
    renderConversione(await r.json());
  } catch (err) {
    console.error('Errore caricamento conversione:', err);
    elCarenzeConversione.innerHTML = '';
  }
}

// Disegna il blocco "🎯 Conversione del vantaggio".
function renderConversione(d) {
  const titolo = '<h3>🎯 Conversione del vantaggio</h3>';

  // Nessun vantaggio misurato: stato vuoto onesto invece di numeri finti.
  if (!d || !d.partite_con_vantaggio) {
    elCarenzeConversione.innerHTML =
      `${titolo}<p class="conv-vuoto">Non ci sono ancora abbastanza partite
        analizzate per misurare come converti i vantaggi.</p>`;
    return;
  }

  const minPedoni = centipawnPedoni(d.picco_min);            // es. "+2"
  const maxPedoni = centipawnPedoni(d.picco_max);            // es. "+6"
  const N = d.partite_con_vantaggio;
  const M = d.non_convertite;
  const X = d.tasso_non_conversione;
  const K = d.crollo.n;
  const E = d.erosione.n;
  const T = d.erosioni_sopra_tetto_escluse || 0;

  // Frase di sintesi ONESTA, generata dai numeri. La nota sul bullet appare solo
  // se l'esclusione e' attiva (e' il default del backend).
  const notaBullet = d.escludi_bullet
    ? ' <span class="conv-bullet-nota">(escluse le partite bullet, dove si perde a tempo)</span>' : '';
  // Nota sul TETTO AL PICCO: appare solo se davvero abbiamo escluso erosioni oltre +6.
  const notaTetto = T
    ? ` <span class="conv-tetto-nota">(escluse anche ${T} erosioni da vantaggi oltre
        ${maxPedoni}: lì è matto facile, non tecnica di conversione)</span>` : '';
  // Considero solo i vantaggi DECISIVI ma da convertire con tecnica (tra +2 e +6):
  // sotto non è "vantaggio chiaro", sopra è già vinto in modo banale / matto imminente.
  const sintesi =
    `Considero i vantaggi decisivi ma non banali, tra <strong>${minPedoni}</strong> e
     <strong>${maxPedoni}</strong> — quelli che richiedono tecnica per convertire
     (sotto non è vantaggio chiaro, sopra è già vinto): li raggiungi in
     <strong>${N}</strong> partite${notaBullet}${notaTetto};
     non li converti in <strong>${M}</strong> (${X}%). Di queste,
     <strong>${K}</strong> sono <em>crolli</em> (un singolo errore — già coperti
     dall'allenamento errori) e <strong>${E}</strong> sono <em>erosioni</em>:
     vantaggio sciolto gradualmente, <strong>senza</strong> un errore singolo.
     Le erosioni sono il pattern che gli altri strumenti non vedono.`;

  // Numero EROSIONE in evidenza: e' il dato chiave (il valore aggiunto).
  const evidenza =
    `<div class="conv-evidenza">
       <span class="conv-evidenza-num">${E}</span>
       <span class="conv-evidenza-eti">erosioni (${d.erosione.perc}% delle non-conversioni)</span>
     </div>`;

  // Riga di metodo: l'erosione e' tecnica di conversione, non un esercizio tattico.
  const nota =
    `<p class="conv-nota">L'erosione è <strong>tecnica di conversione</strong>
       (semplificare, non rischiare, migliorare i pezzi): non si allena coi puzzle
       tattici — è consapevolezza, non un esercizio.</p>`;

  // Banner onesto se il campione di erosioni è piccolo.
  const avviso = !d.affidabile
    ? `<p class="conv-avviso">⚠️ Campione piccolo (${E} erosioni): indicativo,
        non ancora un pattern solido.</p>`
    : '';

  // Lista delle prime erosioni da rivedere su Chess.com (da che vantaggio a che esito).
  const erosioni = (d.partite_erosione || []).slice(0, 15);
  const righe = erosioni.map((p) => {
    const picco = centipawnPedoni(p.picco_vantaggio);
    const esito = p.risultato === 'patta' ? 'patta' : 'sconfitta';
    return `<li class="conv-voce conv-${esito}">
        <span class="conv-vantaggio">da ${picco}</span>
        <span class="conv-arrow">→</span>
        <span class="conv-esito">${esito}</span>
        <span class="conv-file">${p.fonte_file}</span>
      </li>`;
  }).join('');
  const lista = righe
    ? `<p class="conv-lista-intro">Le erosioni più grosse, da rivedere
         (cerca queste partite su Chess.com):</p>
       <ul class="conv-lista">${righe}</ul>`
    : '';

  elCarenzeConversione.innerHTML =
    `${titolo}
     <p class="conv-sintesi">${sintesi}</p>
     ${evidenza}${nota}${avviso}${lista}`;
}

// Etichetta leggibile del peso relativo di una voce rispetto al tema dominante.
// Onesto: NON finge minuti, esprime solo "quante volte piu' urgente del secondo".
function etichettaPeso(peso) {
  if (peso >= 1) return 'priorità massima';        // il tema dominante (peso 1.0)
  // Es. peso 0.5 -> "circa metà del tema dominante"; 0.8 -> "~0.8× del dominante".
  return `priorità ~${peso}× rispetto al tema dominante`;
}

// Presentazione di una tendenza: il tasso d'ERRORE che scende = miglioramento, quindi
// "migliorato" e' una freccia in giu' verde; "peggiorato" in su rossa; "stabile" grigia.
const TENDENZE = {
  migliorato: { freccia: '▼', classe: 'tend-migliorato', testo: 'in calo (meglio)' },
  peggiorato: { freccia: '▲', classe: 'tend-peggiorato', testo: 'in aumento (peggio)' },
  stabile: { freccia: '→', classe: 'tend-stabile', testo: 'stabile' },
};

// Disegna il blocco "📋 Il tuo piano di studio" dalle voci del piano (statico).
// `confronto` (Tappa D) e' opzionale: se presente, ogni voce mostra una freccetta
// di tendenza rispetto allo storico nelle ultime N partite.
function renderPianoStudio(piano, confronto) {
  if (!piano) { elCarenzePiano.innerHTML = ''; return; }
  const voci = piano.voci || [];

  // Caso limite: nessun tema rilevante -> solo la nota onesta, niente elenco.
  if (voci.length === 0) {
    elCarenzePiano.innerHTML =
      `<h3>📋 Il tuo piano di studio</h3>
       <p class="piano-nota">${piano.nota_posizionale || ''}</p>`;
    return;
  }

  const partiteNuove = (confronto && confronto.partite_nuove) || 0;
  const righe = voci.map((v) => {
    const ogni = v.ogni_quante_mosse
      ? `una ogni ~${v.ogni_quante_mosse} mosse` : 'raro';
    // Pulsante "allenati su questo tema": riusa scegliTema (flusso temi).
    const bottone = v.tema_libero
      ? `<button class="piano-allena" data-tema="${v.tema_libero}">allenati su questo tema</button>`
      : '';
    // Freccetta di tendenza (se il confronto esiste e copre questo tema).
    const t = v.tendenza && TENDENZE[v.tendenza];
    const tendenza = t
      ? `<span class="piano-tendenza ${t.classe}"
            title="rispetto al tuo storico, nelle ultime ${partiteNuove} partite: ${t.testo}">${t.freccia}</span>`
      : '';
    return `<li class="piano-voce">
        <div class="piano-voce-testa">
          <span class="piano-tema">${etichettaCarenza(v.tema)}</span>
          ${tendenza}
          <span class="piano-priorita priorita-${v.priorita}">${v.priorita}</span>
        </div>
        <span class="piano-dato">${ogni} · ${v.tasso_su_mosse}% delle tue mosse · ${etichettaPeso(v.peso_relativo)}</span>
        ${bottone}
      </li>`;
  }).join('');

  const progressione = piano.progressione
    ? `<p class="piano-progressione">${piano.progressione}</p>` : '';
  const nota = piano.nota_posizionale
    ? `<p class="piano-nota">${piano.nota_posizionale}</p>` : '';

  elCarenzePiano.innerHTML =
    `<h3>📋 Il tuo piano di studio</h3>
     <p class="piano-intro">In base a dove sbagli più spesso, ecco su quali temi
       liberi concentrarti.</p>
     <ol class="piano-lista">${righe}</ol>
     ${progressione}${nota}`;

  // Aggancio i pulsanti "allenati" al flusso temi (stesso meccanismo dei temi liberi).
  elCarenzePiano.querySelectorAll('.piano-allena').forEach((b) => {
    b.addEventListener('click', () => scegliTema(b.dataset.tema));
  });
}

// Disegna il blocco "🎯 Studio per fasi di gioco — Finali" (studio_fasi): sezione
// SEPARATA dal piano tattico, col SUO denominatore (mosse giocate in finale, non le
// mosse totali). ONESTA': i tassi qui NON sono confrontabili con quelli tattici, per
// questo stanno in una sezione a parte con la frase-denominatore dichiarata in chiaro
// e una scala di barre tutta sua. La raccomandazione rimanda a un tema del flusso Temi
// (se esiste), attivabile con un click riusando scegliTema (come il piano tattico).
function renderStudioFasi(sf) {
  // Non disponibile o senza tassi: niente sezione (nessun numero finto).
  if (!sf || !sf.disponibile || !(sf.tassi && sf.tassi.length)) {
    elCarenzeFasi.innerHTML = '';
    return;
  }

  // Scala delle barre: da 0 al tasso massimo + margine (niente zero forzato
  // ingannevole, coerente con R3). Le barre partono comunque da 0.
  const maxTasso = Math.max(...sf.tassi.map((t) => t.tasso || 0));
  const scala = maxTasso > 0 ? maxTasso * 1.15 : 1;

  const righe = sf.tassi.map((t) => {
    const largh = Math.round((100 * (t.tasso || 0)) / scala);
    // Evidenzio SOLO il peggiore reale, mai un tipo "fragile" (pochi dati).
    const evidenzia = t.peggiore && !t.fragile;
    // Tag onesto: "pochi dati" per i fragili, "da allenare" per il peggiore reale.
    const tag = t.fragile
      ? '<span class="carenza-tag">pochi dati</span>'
      : (evidenzia ? '<span class="carenza-tag">da allenare</span>' : '');
    return `<li class="qualita-riga fasi-riga${evidenzia ? ' fasi-peggiore' : ''}${t.fragile ? ' fasi-fragile' : ''}">
        <span class="qualita-nome fasi-nome">${etichettaCarenza(t.etichetta)}</span>
        <span class="qualita-barra"><span class="qualita-fill${evidenzia ? ' fasi-fill-peggiore' : ''}" style="width:${largh}%"></span></span>
        <span class="qualita-num">${t.tasso}% · ${t.mosse} mosse ${tag}</span>
      </li>`;
  }).join('');

  // Frase-DENOMINATORE ben visibile: e' cio' che impedisce di confondere questi tassi
  // con quelli tattici. NON va omessa.
  const denom = sf.denominatore
    ? `<p class="fasi-denominatore">${sf.denominatore}.</p>` : '';

  // Raccomandazione in evidenza + pulsante che attiva il tema nel flusso Temi (se
  // c'e' un tema dedicato), riusando lo stesso meccanismo del piano tattico.
  const racc = sf.raccomandazione
    ? `<p class="fasi-raccomandazione">${sf.raccomandazione}</p>` : '';
  const bottone = sf.tema_libero
    ? `<button class="piano-allena fasi-allena" data-tema="${sf.tema_libero}">allenati su questo finale</button>`
    : '';

  elCarenzeFasi.innerHTML =
    `<h3>🎯 Studio per fasi di gioco — Finali</h3>
     ${denom}
     <ul class="qualita-lista fasi-lista">${righe}</ul>
     ${racc}${bottone}`;

  // Aggancio il pulsante al flusso temi (stesso meccanismo del piano tattico).
  elCarenzeFasi.querySelectorAll('.piano-allena').forEach((b) => {
    b.addEventListener('click', () => scegliTema(b.dataset.tema));
  });
}

// Disegna il blocco "📈 Stai migliorando?" (Tappa D): confronto onesto tra le partite
// recenti e lo storico. Se non c'e' ancora un confronto, spiega come ottenerlo.
function renderConfronto(confronto) {
  const titolo = '<h3>📈 Stai migliorando? <small>(partite recenti vs storico)</small></h3>';

  // Nessun confronto disponibile: messaggio onesto su come sbloccarlo.
  if (!confronto) {
    elCarenzeConfronto.innerHTML =
      `${titolo}
       <p class="confronto-vuoto">Nessun confronto ancora: carica nuove partite dopo
         esserti allenato e qui vedrai se stai migliorando davvero — sulle partite
         vere, non sui puzzle.</p>`;
    return;
  }

  // Banner discreto quando il confronto è poco affidabile (poche partite nuove).
  const avviso = !confronto.affidabile && confronto.avvertenza
    ? `<p class="confronto-avviso">⚠️ ${confronto.avvertenza}</p>` : '';

  const righe = (confronto.voci || []).map((v) => {
    const nome = etichettaCarenza(v.tema || v.fase);
    const genere = v.tema ? 'tema' : 'fase';
    const t = TENDENZE[v.tendenza] || TENDENZE.stabile;
    const segno = v.delta > 0 ? '+' : '';   // il delta porta già il segno meno
    return `<li class="confronto-voce">
        <span class="confronto-nome">${nome} <em class="confronto-genere">${genere}</em></span>
        <span class="confronto-tassi">
          ${v.tasso_storico}% <span class="confronto-arrow ${t.classe}">${t.freccia}</span> ${v.tasso_recente}%
          <span class="confronto-delta ${t.classe}">(${segno}${v.delta})</span>
        </span>
      </li>`;
  }).join('');

  elCarenzeConfronto.innerHTML =
    `${titolo}
     <p class="confronto-base">Basato sulle tue ultime
       <strong>${confronto.partite_nuove}</strong> partite, confrontate con lo storico
       precedente.</p>
     ${avviso}
     <ul class="confronto-lista">${righe}</ul>`;
}

// --- Evoluzione nel tempo (grafico anti-diluizione, raffinamento del punto 4) ---
// Linee dei tassi d'errore DEL PERIODO (sole partite nuove di ogni snapshot), NON
// cumulativi: e' cosi' che si vede il miglioramento vero. Un grafico per i temi
// tattici rilevanti, uno per le fasi. I punti di periodi con poche partite
// (affidabile=false) sono resi con punto vuoto: indicativi, non conclusivi.

let graficoEvolTemi = null;
let graficoEvolFasi = null;

// Palette stabile per le linee (riusata tra temi e fasi).
const COLORI_EVOLUZIONE = ['#3a6ea5', '#c0504d', '#4a7', '#e0a800', '#7e57c2', '#00897b'];

// "2026-06-11T14:30:00" -> "11/06 14:30" (etichetta X compatta e leggibile).
function formattaTimestamp(ts) {
  if (!ts) return '';
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  const due = (n) => String(n).padStart(2, '0');
  return `${due(d.getDate())}/${due(d.getMonth() + 1)} ${due(d.getHours())}:${due(d.getMinutes())}`;
}

// Scarica la serie temporale e disegna i due grafici (o lo stato vuoto onesto).
async function aggiornaEvoluzione(temiRilevanti) {
  try {
    const r = await fetch(`${BACKEND}/storico-profili`).then((x) => x.json());
    // STATO VUOTO ONESTO: con < 2 snapshot (nessun punto-periodo) niente grafico.
    if (!r.ha_dati || !(r.punti && r.punti.length)) {
      if (elEvoluzioneGrafici) elEvoluzioneGrafici.hidden = true;
      if (elEvoluzioneVuoto) elEvoluzioneVuoto.hidden = false;
      if (graficoEvolTemi) { graficoEvolTemi.destroy(); graficoEvolTemi = null; }
      if (graficoEvolFasi) { graficoEvolFasi.destroy(); graficoEvolFasi = null; }
      return;
    }
    if (elEvoluzioneVuoto) elEvoluzioneVuoto.hidden = true;
    if (elEvoluzioneGrafici) elEvoluzioneGrafici.hidden = false;

    const punti = r.punti;
    const etichette = punti.map((p) => formattaTimestamp(p.timestamp));

    // Temi da tracciare: i rilevanti del report; in mancanza, quelli che hanno
    // almeno un valore > 0 nella serie (cosi' il grafico non resta vuoto).
    let temi = (temiRilevanti || []).filter(
      (t) => punti.some((p) => (p.tasso_tipo || {})[t] > 0));
    if (temi.length === 0) {
      const visti = new Set();
      punti.forEach((p) => Object.entries(p.tasso_tipo || {}).forEach(([t, v]) => {
        if (v > 0) visti.add(t);
      }));
      temi = [...visti];
    }

    disegnaGraficoEvoluzione(
      'grafico-evoluzione-temi',
      (g) => { graficoEvolTemi = g; },
      graficoEvolTemi,
      etichette, punti, temi, (p, k) => (p.tasso_tipo || {})[k],
      "Evoluzione dei temi tattici (tasso delle partite nuove di ogni periodo)");

    const fasi = ['apertura', 'mediogioco', 'finale'];
    disegnaGraficoEvoluzione(
      'grafico-evoluzione-fasi',
      (g) => { graficoEvolFasi = g; },
      graficoEvolFasi,
      etichette, punti, fasi, (p, k) => (p.tasso_fase || {})[k],
      "Evoluzione per fase (tasso delle partite nuove di ogni periodo)");
  } catch (err) {
    console.error('Errore caricamento evoluzione:', err);
  }
}

// Disegna un grafico a linee dell'evoluzione: una linea per `chiave`, asse X = tempo,
// asse Y = tasso (%). I punti di periodi non affidabili sono resi vuoti (bordo colore
// pieno, riempimento bianco). `valore(p, k)` estrae il tasso del punto p per la chiave k.
function disegnaGraficoEvoluzione(canvasId, salva, vecchio, etichette, punti, chiavi,
                                  valore, titolo) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  if (vecchio) vecchio.destroy();
  const datasets = chiavi.map((k, i) => {
    const colore = COLORI_EVOLUZIONE[i % COLORI_EVOLUZIONE.length];
    // Per-punto: pieno se affidabile, vuoto (bianco) se poche partite.
    const sfondoPunti = punti.map((p) => (p.affidabile ? colore : '#fff'));
    return {
      label: k.replace(/_/g, ' '),
      data: punti.map((p) => {
        const v = valore(p, k);
        return (v == null) ? null : v;  // null -> Chart.js salta il punto
      }),
      borderColor: colore,
      backgroundColor: colore,
      pointBackgroundColor: sfondoPunti,
      pointBorderColor: colore,
      pointRadius: 4,
      pointHoverRadius: 5,
      tension: 0.2,
      spanGaps: true,
      fill: false,
    };
  });
  const g = new Chart(canvas, {
    type: 'line',
    data: { labels: etichette, datasets },
    options: {
      responsive: true,
      scales: {
        y: { beginAtZero: true, title: { display: true, text: '% delle mosse' } },
        x: { title: { display: true, text: 'periodo (data)' } },
      },
      plugins: {
        title: { display: true, text: titolo },
        // Nota onesta in legenda: i periodi con poche partite sono indicativi.
        subtitle: {
          display: true,
          text: 'I punti vuoti sono periodi con poche partite: indicativi.',
          font: { style: 'italic', size: 11 },
          padding: { bottom: 6 },
        },
      },
    },
  });
  salva(g);
}

// Mostra/nasconde la sezione progressi (unica, condivisa): un toggle per
// pannello-flusso, tutti agiscono sulla stessa sezione. Quando la apro, la
// aggancio al pannello attivo e aggiorno i grafici (gia' riferiti al flusso attivo).
document.querySelectorAll('.toggle-progressi').forEach((btn) => {
  btn.addEventListener('click', () => {
    elProgressi.hidden = !elProgressi.hidden;
    if (!elProgressi.hidden) {
      agganciaProgressiAlPannello(flussoAttivo);
      aggiornaProgressi();
    }
  });
});

// Mostra/nasconde la sezione carenze; quando la apro, scarico il profilo.
elToggleCarenze.addEventListener('click', () => {
  elCarenze.hidden = !elCarenze.hidden;
  if (!elCarenze.hidden) aggiornaCarenze();
});

// --- Schermata "La scienza dietro il sistema" ---
// Tab informativa: spiega il principio (regola dell'85%) e come il sistema lo
// applica. Sezioni 1-2 sono grafici teorici/illustrativi (statici); la sezione 4
// legge /profilo e /storico-profili come il resto della pagina.

const elScienza = document.getElementById('scienza');
const elToggleScienza = document.getElementById('toggle-scienza');
const elScienzaDatiVuoto = document.getElementById('scienza-dati-vuoto');
const elScienzaDatiGrafici = document.getElementById('scienza-dati-grafici');
const elScienzaEvolVuoto = document.getElementById('scienza-evoluzione-vuoto');
const elScienzaEvolGrafico = document.getElementById('scienza-evoluzione-grafico');

let graficoScienzaCurva = null;
let graficoScienzaConvergenza = null;
let graficoScienzaFasi = null;
let graficoScienzaTemi = null;
let graficoScienzaEvol = null;

// SEZIONE 1 — curva teorica "velocità di apprendimento vs tasso di successo".
// Forma asimmetrica: sale, picco intorno all'85%, poi cala PIU' ripida verso il 100%.
// Asse Y qualitativo (niente numeri, come nel paper). Linea di riferimento verticale
// sull'85% disegnata A MANO con un secondo dataset + borderDash (stesso metodo della
// linea 85% in disegnaGraficoPrimoColpo: NON introduco chartjs-plugin-annotation).
function disegnaCurvaApprendimento() {
  const canvas = document.getElementById('grafico-scienza-curva');
  if (!canvas) return;
  if (graficoScienzaCurva) graficoScienzaCurva.destroy();
  // Punti di controllo illustrativi della FORMA (non dati misurati). La salita
  // 0->85 e' graduale, la discesa 85->100 e' piu' ripida: curva asimmetrica.
  const curva = [
    { x: 0, y: 0.12 }, { x: 20, y: 0.28 }, { x: 40, y: 0.48 },
    { x: 60, y: 0.70 }, { x: 75, y: 0.88 }, { x: 85, y: 1.0 },
    { x: 91, y: 0.78 }, { x: 96, y: 0.5 }, { x: 100, y: 0.18 },
  ];
  graficoScienzaCurva = new Chart(canvas, {
    type: 'line',
    data: {
      datasets: [
        {
          label: 'velocità di apprendimento',
          data: curva,
          borderColor: '#3a6ea5',
          backgroundColor: 'rgba(58,110,165,0.2)',
          tension: 0.4,
          fill: true,
          pointRadius: 0,
        },
        {
          // Linea di riferimento VERTICALE sull'85%: due punti sulla stessa x,
          // tratteggiata. Stesso approccio "a mano" della linea 85% di R3.
          label: 'zona ottimale ~85%',
          data: [{ x: 85, y: 0 }, { x: 85, y: 1.05 }],
          borderColor: '#c0392b',
          borderDash: [6, 4],
          borderWidth: 2,
          pointRadius: 0,
          fill: false,
        },
      ],
    },
    options: {
      responsive: true,
      scales: {
        x: {
          type: 'linear',
          min: 0,
          max: 100,
          title: { display: true, text: 'tasso di successo (%)' },
        },
        y: {
          min: 0,
          max: 1.1,
          // Asse qualitativo: niente numeri (come nel paper), solo il titolo.
          ticks: { display: false },
          title: { display: true, text: 'velocità di apprendimento (unità relative)' },
        },
      },
      plugins: {
        title: { display: true, text: 'Dove si impara di più' },
        legend: { display: true },
      },
    },
  });
}

// SEZIONE 2 — convergenza: SOLO 2 barre quantitative (Wilson 85%, Rosenshine ~80%).
// Vygotskij NON e' una barra (sarebbe un falso quantitativo): vive come banda
// qualitativa nell'HTML. Scala 70-90 per non drammatizzare.
function disegnaConvergenza() {
  const canvas = document.getElementById('grafico-scienza-convergenza');
  if (!canvas) return;
  if (graficoScienzaConvergenza) graficoScienzaConvergenza.destroy();
  graficoScienzaConvergenza = new Chart(canvas, {
    type: 'bar',
    data: {
      labels: ['Wilson et al. (2019)', 'Rosenshine (~2012)'],
      datasets: [{
        label: 'tasso di successo ottimale (%)',
        data: [85, 80],
        backgroundColor: ['#3a6ea5', '#4a7'],
      }],
    },
    options: {
      responsive: true,
      scales: {
        y: {
          min: 70,
          max: 90,
          title: { display: true, text: 'tasso di successo ottimale (%)' },
        },
      },
      plugins: {
        title: { display: true, text: 'Due risultati quantitativi a confronto' },
        legend: { display: false },
      },
    },
  });
}

// SEZIONE 4 — tasso d'errore per fase (apertura/mediogioco/finale): dati reali da /profilo.
function disegnaScienzaFasi(tassoFase) {
  const canvas = document.getElementById('grafico-scienza-fasi');
  if (!canvas) return;
  const chiavi = FASI_CARENZE.filter((f) => tassoFase[f] != null);
  if (graficoScienzaFasi) graficoScienzaFasi.destroy();
  graficoScienzaFasi = new Chart(canvas, {
    type: 'bar',
    data: {
      labels: chiavi,
      datasets: [{
        label: "% delle tue mosse con errore",
        data: chiavi.map((f) => tassoFase[f]),
        backgroundColor: '#b5651d',
      }],
    },
    options: {
      responsive: true,
      scales: {
        y: { beginAtZero: true, title: { display: true, text: '% delle mosse' } },
        x: { title: { display: true, text: 'fase' } },
      },
      plugins: {
        title: { display: true, text: "Il tuo tasso d'errore per fase" },
        legend: { display: false },
      },
    },
  });
}

// SEZIONE 4 — tasso d'errore per tema tattico (pezzo_in_presa, forchetta...): da /profilo.
function disegnaScienzaTemi(tassoTipo) {
  const canvas = document.getElementById('grafico-scienza-temi');
  if (!canvas) return;
  // Tutti i tipi tranne "non_tattico", ordinati per tasso decrescente.
  const chiavi = Object.keys(tassoTipo)
    .filter((t) => t !== 'non_tattico')
    .sort((a, b) => (tassoTipo[b] || 0) - (tassoTipo[a] || 0));
  if (graficoScienzaTemi) graficoScienzaTemi.destroy();
  graficoScienzaTemi = new Chart(canvas, {
    type: 'bar',
    data: {
      labels: chiavi.map((t) => t.replace(/_/g, ' ')),
      datasets: [{
        label: '% delle tue mosse con errore',
        data: chiavi.map((t) => tassoTipo[t]),
        backgroundColor: '#3a6ea5',
      }],
    },
    options: {
      responsive: true,
      scales: {
        y: { beginAtZero: true, title: { display: true, text: '% delle mosse' } },
        x: { title: { display: true, text: 'tema tattico' } },
      },
      plugins: {
        title: { display: true, text: "Il tuo tasso d'errore per tema" },
        legend: { display: false },
      },
    },
  });
}

// SEZIONE 4 — carica i dati reali e li disegna; gestisce gli stati-vuoto onesti.
async function aggiornaScienzaDati() {
  // Profilo: tassi per fase e per tema.
  try {
    const r = await fetch(`${BACKEND}/profilo`);
    if (!r.ok) {
      if (elScienzaDatiVuoto) elScienzaDatiVuoto.hidden = false;
      if (elScienzaDatiGrafici) elScienzaDatiGrafici.hidden = true;
    } else {
      const p = await r.json();
      if (elScienzaDatiVuoto) elScienzaDatiVuoto.hidden = true;
      if (elScienzaDatiGrafici) elScienzaDatiGrafici.hidden = false;
      disegnaScienzaFasi(p.tasso_errore_per_fase || {});
      disegnaScienzaTemi(p.tasso_su_mosse_per_tipo || {});
    }
  } catch (err) {
    console.error('Errore caricamento dati scienza:', err);
    if (elScienzaDatiVuoto) elScienzaDatiVuoto.hidden = false;
    if (elScienzaDatiGrafici) elScienzaDatiGrafici.hidden = true;
  }

  // Evoluzione: con < 2 rilevazioni mostro il MESSAGGIO onesto, mai un grafico finto.
  try {
    const r = await fetch(`${BACKEND}/storico-profili`).then((x) => x.json());
    if (!r.ha_dati || !(r.punti && r.punti.length)) {
      if (elScienzaEvolVuoto) elScienzaEvolVuoto.hidden = false;
      if (elScienzaEvolGrafico) elScienzaEvolGrafico.hidden = true;
      if (graficoScienzaEvol) { graficoScienzaEvol.destroy(); graficoScienzaEvol = null; }
    } else {
      // Ci sono almeno due rilevazioni: grafico VERO, riusando l'helper esistente.
      if (elScienzaEvolVuoto) elScienzaEvolVuoto.hidden = true;
      if (elScienzaEvolGrafico) elScienzaEvolGrafico.hidden = false;
      const punti = r.punti;
      const etichette = punti.map((p) => formattaTimestamp(p.timestamp));
      const fasi = ['apertura', 'mediogioco', 'finale'];
      disegnaGraficoEvoluzione(
        'grafico-scienza-evoluzione',
        (g) => { graficoScienzaEvol = g; },
        graficoScienzaEvol,
        etichette, punti, fasi, (p, k) => (p.tasso_fase || {})[k],
        "La tua evoluzione per fase (tasso delle partite nuove di ogni periodo)");
    }
  } catch (err) {
    console.error('Errore caricamento evoluzione scienza:', err);
    if (elScienzaEvolVuoto) elScienzaEvolVuoto.hidden = false;
    if (elScienzaEvolGrafico) elScienzaEvolGrafico.hidden = true;
  }
}

// Mostra/nasconde la schermata scienza; quando la apro, disegno i grafici teorici
// (statici) e carico i dati reali della sezione 4.
elToggleScienza.addEventListener('click', () => {
  elScienza.hidden = !elScienza.hidden;
  if (!elScienza.hidden) {
    disegnaCurvaApprendimento();
    disegnaConvergenza();
    aggiornaScienzaDati();
  }
});

// Pulsante "prossimo puzzle".
elProssimo.addEventListener('click', caricaProssimoPuzzle);

// Avvio: carico i temi, lo stato dei flussi, le statistiche, l'estratto delle
// carenze (pannello piano) e il primo puzzle.
caricaTemi();
caricaFlussi();
aggiornaStatisticheDaServer();
aggiornaEstrattoCarenze();
caricaProssimoPuzzle();
