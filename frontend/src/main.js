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
 * Regola tentativi: 2 tentativi sbagliati, poi mostra la soluzione e va avanti.
 */

import { Chess } from 'chess.js';
import { Chessground } from 'chessground';

// Stili di chessground (scacchiera e pezzi).
import 'chessground/assets/chessground.base.css';
import 'chessground/assets/chessground.brown.css';
import 'chessground/assets/chessground.cburnett.css';
import './style.css';

const BACKEND = 'http://localhost:8000';
const MAX_TENTATIVI = 2;

// Stato corrente del puzzle in gioco.
let chess = null;          // istanza chess.js con la posizione corrente
let soluzione = [];        // mosse-soluzione rimaste da giocare (UCI)
let board = null;          // istanza chessground
let tentativi = 0;         // tentativi sbagliati sul puzzle corrente
let esitoInviato = false;  // per non inviare due volte l'esito dello stesso puzzle
let puzzleCorrente = null; // dati del puzzle dal server

// Elementi della pagina.
const elBoard = document.getElementById('board');
const elInfo = document.getElementById('info');
const elStato = document.getElementById('stato');
const elProssimo = document.getElementById('prossimo');
const elStats = document.getElementById('stats');

// Converte una stringa UCI ("e2e4") in {from, to, promotion}.
function uciToMove(uci) {
  return { from: uci.slice(0, 2), to: uci.slice(2, 4), promotion: 'q' };
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

// Aggiorna la scacchiera con la posizione corrente di chess.js.
function aggiornaBoard() {
  const colore = chess.turn() === 'w' ? 'white' : 'black';
  board.set({
    fen: chess.fen(),
    turnColor: colore,
    movable: {
      color: colore,
      dests: mosseLegali(),
      free: false,
    },
  });
}

// Chiede un nuovo puzzle al backend e lo imposta.
async function caricaProssimoPuzzle() {
  elInfo.textContent = 'Carico il prossimo puzzle...';
  tentativi = 0;
  esitoInviato = false;
  try {
    const risposta = await fetch(`${BACKEND}/prossimo-puzzle`);
    const dati = await risposta.json();

    if (dati.fine) {
      elInfo.textContent = '🎉 Hai completato tutti i puzzle del piano!';
      return;
    }

    puzzleCorrente = dati.puzzle;
    const mosse = puzzleCorrente.moves.split(' ');

    // Carico la posizione e applico la PRIMA mossa (avversario).
    chess = new Chess(puzzleCorrente.fen);
    chess.move(uciToMove(mosse[0]));

    // Le mosse rimanenti sono la soluzione che il giocatore deve trovare.
    soluzione = mosse.slice(1);

    // Oriento la scacchiera dal lato di chi deve muovere.
    const orient = chess.turn() === 'w' ? 'white' : 'black';

    if (!board) {
      board = Chessground(elBoard, {
        fen: chess.fen(),
        orientation: orient,
        movable: { color: orient, dests: mosseLegali(), free: false },
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
    elInfo.textContent = `Tocca a ${orient === 'white' ? 'Bianco' : 'Nero'}. Trova la mossa migliore!`;
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
  } catch (err) {
    console.error('Errore invio esito:', err);
  }
}

// Mostra le statistiche di sessione nella pagina.
function mostraStatistiche(stats) {
  if (!elStats) return;
  elStats.textContent =
    `Sessione: ${stats.risolti_primo}/${stats.tentati} al primo colpo ` +
    `(${stats.percentuale_primo}%) · ${stats.falliti} soluzioni viste`;
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
    soluzione.shift();

    if (soluzione.length === 0) {
      // Puzzle risolto!
      elInfo.textContent = '✅ Corretto! Puzzle risolto.';
      aggiornaBoard();
      board.set({ movable: { color: undefined } });
      if (!esitoInviato) {
        // 0 errori = "primo", 1 errore = "secondo"
        inviaEsito(tentativi === 0 ? 'primo' : 'secondo');
        esitoInviato = true;
      }
      return;
    }

    // C'è ancora soluzione: l'avversario risponde con la mossa successiva.
    const rispostaAvv = soluzione.shift();
    chess.move(uciToMove(rispostaAvv));
    aggiornaBoard();
    elInfo.textContent = '✅ Bene! Continua...';
  } else {
    // Mossa sbagliata.
    tentativi += 1;
    if (tentativi >= MAX_TENTATIVI) {
      // Mostro la soluzione e fermo il puzzle.
      elInfo.textContent = `❌ La mossa giusta era ${soluzione[0]}. Passa al prossimo.`;
      // Riporto la posizione com'era (annullo la mossa sbagliata visivamente).
      aggiornaBoard();
      board.set({ movable: { color: undefined } });
      if (!esitoInviato) {
        inviaEsito('fallito');
        esitoInviato = true;
      }
    } else {
      elInfo.textContent = `❌ Non è giusta. Riprova (tentativo ${tentativi}/${MAX_TENTATIVI}).`;
      // Rimetto la posizione corretta (la mossa sbagliata non viene applicata).
      aggiornaBoard();
    }
  }
}

// Pulsante "prossimo puzzle".
elProssimo.addEventListener('click', caricaProssimoPuzzle);

// Avvio: carico il primo puzzle.
caricaProssimoPuzzle();
