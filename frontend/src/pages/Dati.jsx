import { useState } from 'react';
import { BACKEND } from '../config.js';
import './Dati.css';

// Estrazione dati del giocatore: inserisce lo username chess.com e il sistema scarica/analizza
// le partite. Anticipa il multi-utente (ognuno i propri dati). L'endpoint di import lato server
// e' una feature a parte: qui la pagina e' pronta e mostra con onesta' lo stato del collegamento.
export default function Dati() {
  const [username, setUsername] = useState('');
  const [mesi, setMesi] = useState('3');
  const [stato, setStato] = useState(null); // { tipo: 'ok'|'errore'|'info', testo }
  const [inCorso, setInCorso] = useState(false);

  const estrai = async (e) => {
    e.preventDefault();
    if (!username.trim()) { setStato({ tipo: 'errore', testo: 'Inserisci il tuo username chess.com.' }); return; }
    setInCorso(true);
    setStato({ tipo: 'info', testo: 'Avvio estrazione…' });
    try {
      const r = await fetch(`${BACKEND}/importa-chesscom`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: username.trim(), mesi: Number(mesi) }),
      });
      if (r.status === 404) {
        setStato({ tipo: 'info', testo: 'La pagina è pronta, ma il backend di estrazione non è ancora collegato. '
          + 'È il prossimo passo: scaricare le partite da chess.com e lanciare l’analisi.' });
        return;
      }
      const d = await r.json();
      if (!r.ok) { setStato({ tipo: 'errore', testo: d.errore || 'Estrazione non riuscita.' }); return; }
      setStato({ tipo: 'ok', testo: d.messaggio || `Estrazione avviata per ${username}.` });
    } catch {
      setStato({ tipo: 'info', testo: 'Backend non raggiungibile (o estrazione non ancora collegata). '
        + 'Assicurati che il server sia avviato; il collegamento dell’import è il prossimo passo.' });
    } finally {
      setInCorso(false);
    }
  };

  return (
    <div className="dati">
      <div className="page-head">
        <h1>I miei dati</h1>
        <p>Collega il tuo profilo chess.com: il sistema scarica le tue partite recenti, le analizza
          con il motore e costruisce il profilo delle tue debolezze. Da lì nascono puzzle, piano e
          diagnosi. I tuoi dati restano la base di tutto: nessun test generico.</p>
      </div>

      <form className="card dati-form" onSubmit={estrai}>
        <label className="campo">
          <span>Username chess.com</span>
          <input
            type="text" value={username} placeholder="es. MigueL_uz"
            onChange={(e) => setUsername(e.target.value)} autoComplete="off"
          />
        </label>
        <label className="campo">
          <span>Periodo da importare</span>
          <select value={mesi} onChange={(e) => setMesi(e.target.value)}>
            <option value="1">Ultimo mese</option>
            <option value="3">Ultimi 3 mesi</option>
            <option value="6">Ultimi 6 mesi</option>
            <option value="12">Ultimo anno</option>
          </select>
        </label>
        <button className="btn btn-primary" type="submit" disabled={inCorso}>
          {inCorso ? 'Estrazione…' : 'Estrai e analizza'}
        </button>
      </form>

      {stato && <div className={'dati-esito ' + stato.tipo}>{stato.testo}</div>}

      <div className="card dati-note">
        <h3>Come funziona</h3>
        <p className="muted">Scarichiamo le partite pubbliche dal tuo profilo chess.com, le
          analizziamo con Stockfish e ne ricaviamo dove sbagli più spesso. L’analisi richiede un
          po’ di tempo: è il prezzo dell’onestà, i numeri vengono da partite vere.</p>
        <p className="muted">Nota (multi-utente, Fase 5): oggi l’app lavora su un solo profilo; qui
          nasce il punto d’ingresso in cui, in futuro, ogni giocatore inserirà i propri dati.</p>
      </div>
    </div>
  );
}
