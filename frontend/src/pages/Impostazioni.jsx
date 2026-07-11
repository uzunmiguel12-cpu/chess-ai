import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useImpostazioni, TEMI_BOARD, AVATARS, PEZZI, DIMENSIONI_TESTO } from '../ImpostazioniContext.jsx';
import { provaSuoni } from '../suoni.js';
import MiniBoard from '../components/MiniBoard.jsx';
import './Impostazioni.css';

const SEZIONI = [
  { id: 'profilo', icona: '👤', nome: 'Profilo giocatore' },
  { id: 'scacchiera', icona: '♟️', nome: 'Scacchiera e pezzi' },
  { id: 'accessibilita', icona: '♿', nome: 'Accessibilità' },
  { id: 'abbonamenti', icona: '💳', nome: 'Abbonamenti' },
  { id: 'account', icona: '🔒', nome: 'Account' },
];

// Posizione d'esempio per l'anteprima del tema scacchiera.
const FEN_ANTEPRIMA = 'r2qk2r/pp3ppp/2n1bn2/2ppp3/3PP3/2N1BN2/PPP2PPP/R2QK2R w - -';

function Interruttore({ on, onChange, label, nota }) {
  return (
    <label className="imp-switch-riga">
      <span className={'imp-switch' + (on ? ' on' : '')} onClick={() => onChange(!on)} role="switch" aria-checked={on}>
        <span className="imp-switch-pallina" />
      </span>
      <span className="imp-switch-testo"><strong>{label}</strong>{nota && <span className="muted"> — {nota}</span>}</span>
    </label>
  );
}

export default function Impostazioni() {
  const { imp, aggiorna } = useImpostazioni();
  const [sezione, setSezione] = useState('scacchiera');

  return (
    <div className="impostazioni">
      <div className="page-head"><h1>⚙️ Impostazioni</h1></div>
      <div className="imp-layout">
        <nav className="imp-sidebar">
          {SEZIONI.map((s) => (
            <button key={s.id} className={'imp-voce' + (s.id === sezione ? ' attiva' : '')} onClick={() => setSezione(s.id)}>
              <span className="imp-voce-ic">{s.icona}</span> {s.nome}
            </button>
          ))}
        </nav>

        <div className="imp-contenuto card">
          {sezione === 'profilo' && (
            <>
              <h2>Profilo giocatore</h2>
              <label className="imp-campo"><span>Nome utente</span>
                <input type="text" value={imp.nomeUtente} maxLength={24} onChange={(e) => aggiorna({ nomeUtente: e.target.value })} />
              </label>
              <div className="imp-campo"><span>La tua icona</span>
                <div className="imp-avatars">
                  {AVATARS.map((a) => (
                    <button key={a} className={'imp-av' + (a === imp.avatar ? ' attivo' : '')} onClick={() => aggiorna({ avatar: a })}>{a}</button>
                  ))}
                </div>
              </div>
              <p className="muted">Il tuo profilo chess.com (per l'analisi delle partite) si imposta in <Link to="/dati">I miei dati</Link>.</p>
              <p className="faint">Un profilo pubblico con statistiche condivisibili arriverà con la Fase 5 (multi-utente).</p>
            </>
          )}

          {sezione === 'scacchiera' && (
            <>
              <h2>Scacchiera e pezzi</h2>
              <p className="muted">Scegli il tema dei colori della scacchiera. L'anteprima si aggiorna subito.</p>
              <div className="imp-scac">
                <div className="imp-temi">
                  {TEMI_BOARD.map((t) => (
                    <button key={t.id} className={'imp-tema' + (t.id === imp.boardTheme ? ' attivo' : '')} onClick={() => aggiorna({ boardTheme: t.id })}>
                      <span className="imp-tema-sw" style={{ background: `linear-gradient(135deg, ${t.light} 0 50%, ${t.dark} 50% 100%)` }} />
                      <span className="imp-tema-nome">{t.nome}</span>
                    </button>
                  ))}
                </div>
                <div className="imp-anteprima">
                  <div className="board-frame"><MiniBoard fen={FEN_ANTEPRIMA} /></div>
                  <p className="faint">Anteprima</p>
                </div>
              </div>

              <div className="imp-campo imp-campo-largo"><span>Set di pezzi</span>
                <div className="imp-pezzi">
                  {PEZZI.map((p) => (
                    <button key={p.id} className={'imp-pezzo' + (p.id === imp.pezzi ? ' attivo' : '')} onClick={() => aggiorna({ pezzi: p.id })}>
                      <span className="imp-pezzo-camp">{p.campione}</span>
                      <span className="imp-pezzo-nome">{p.nome}</span>
                    </button>
                  ))}
                </div>
                <p className="faint">L'anteprima qui sopra si aggiorna subito col set scelto.</p>
              </div>
            </>
          )}

          {sezione === 'accessibilita' && (
            <>
              <h2>Accessibilità</h2>

              <div className="imp-campo"><span>Dimensione testo</span>
                <div className="seg-row">
                  {DIMENSIONI_TESTO.map((d) => (
                    <button key={d.id} className={'temi-tab' + (d.id === imp.dimensioneTesto ? ' attivo' : '')} onClick={() => aggiorna({ dimensioneTesto: d.id })}>{d.nome}</button>
                  ))}
                </div>
              </div>

              <Interruttore on={imp.contrastoAlto} onChange={(v) => aggiorna({ contrastoAlto: v })} label="Contrasto elevato" nota="testo più chiaro e bordi più marcati" />
              <Interruttore on={imp.riduciAnimazioni} onChange={(v) => aggiorna({ riduciAnimazioni: v })} label="Riduci animazioni" nota="disattiva transizioni ed effetti di movimento" />

              <Interruttore on={imp.suoni} onChange={(v) => aggiorna({ suoni: v })} label="Suoni" nota="effetti audio per mosse, catture ed esiti" />
              <button className="btn btn-ghost imp-prova-suoni" onClick={provaSuoni}>🔊 Prova i suoni</button>

              <label className="imp-campo" style={{ marginTop: 'var(--sp-5)' }}><span>Lingua</span>
                <select value={imp.lingua} onChange={(e) => aggiorna({ lingua: e.target.value })}>
                  <option value="it">Italiano</option>
                </select>
              </label>
              <p className="faint">Il supporto multilingua è in arrivo: per ora l'interfaccia è in italiano.</p>

              <div className="imp-campo"><span>Aspetto della scacchiera</span>
                <button className="btn btn-ghost" onClick={() => setSezione('scacchiera')}>Cambia tema e pezzi →</button>
              </div>
            </>
          )}

          {sezione === 'abbonamenti' && (
            <>
              <h2>Abbonamenti</h2>
              <div className="stub">
                Chess-AI è gratuito e in versione preview. Piani e abbonamenti (per funzioni avanzate del
                prodotto pubblico) arriveranno con la Fase 5. Nessun pagamento richiesto ora.
              </div>
            </>
          )}

          {sezione === 'account' && (
            <>
              <h2>Account</h2>
              <div className="stub">
                Oggi l'app lavora a utente singolo, in locale: non c'è ancora un account online. Con la
                Fase 5 (multi-utente) qui gestirai i tuoi dati, la password, la sicurezza e l'assistenza.
              </div>
              <p className="muted">Intanto, i dati delle partite si gestiscono da <Link to="/dati">I miei dati</Link>.</p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
