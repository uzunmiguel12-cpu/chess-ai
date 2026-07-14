import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  useImpostazioni, TEMI_BOARD, AVATARS, PEZZI, DIMENSIONI_TESTO,
  VELOCITA_ANIM, MAX_TENTATIVI_OPZIONI,
} from '../ImpostazioniContext.jsx';
import { provaSuoni } from '../suoni.js';
import { BACKEND, BACKEND_DEFAULT, APP_VERSION, APP_CANALE } from '../config.js';
import MiniBoard from '../components/MiniBoard.jsx';
import './Impostazioni.css';

const SEZIONI = [
  { id: 'profilo', icona: '👤', nome: 'Profilo giocatore' },
  { id: 'scacchiera', icona: '♟️', nome: 'Scacchiera e pezzi' },
  { id: 'allenamento', icona: '🎯', nome: 'Preferenze allenamento' },
  { id: 'accessibilita', icona: '♿', nome: 'Accessibilità' },
  { id: 'dati', icona: '🗄️', nome: 'Dati e privacy' },
  { id: 'sistema', icona: '🖥️', nome: 'Sistema e connessione' },
  { id: 'abbonamenti', icona: '💳', nome: 'Abbonamenti' },
  { id: 'account', icona: '🔒', nome: 'Account' },
  { id: 'info', icona: 'ℹ️', nome: 'Info e note legali' },
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

// Ping al backend con misura di latenza (Sistema e connessione).
function StatoConnessione() {
  const [stato, setStato] = useState('prova'); // prova | ok | ko
  const [ms, setMs] = useState(null);
  const prova = async () => {
    setStato('prova'); setMs(null);
    const t0 = performance.now();
    try {
      const r = await fetch(`${BACKEND}/`, { method: 'GET' });
      if (!r.ok) throw new Error('http ' + r.status);
      await r.json().catch(() => ({}));
      setMs(Math.round(performance.now() - t0));
      setStato('ok');
    } catch {
      setStato('ko');
    }
  };
  useEffect(() => { prova(); /* al montaggio */ }, []);
  const testo = stato === 'prova' ? 'verifico…' : stato === 'ok' ? `connesso · ${ms} ms` : 'non raggiungibile';
  return (
    <div className="stato-conn-riga">
      <span className={'stato-conn stato-conn-' + stato}>{stato === 'ok' ? '● ' : stato === 'ko' ? '● ' : '◌ '}{testo}</span>
      <button className="btn btn-ghost imp-mini-btn" onClick={prova} disabled={stato === 'prova'}>↻ Riprova</button>
    </div>
  );
}

export default function Impostazioni() {
  const { imp, aggiorna, ripristina, sostituisci } = useImpostazioni();
  const [sezione, setSezione] = useState('scacchiera');
  const [msgDati, setMsgDati] = useState('');
  const fileRef = useRef(null);

  // --- Dati e privacy ---
  const esporta = () => {
    const blob = new Blob([JSON.stringify(imp, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = 'chess-ai-impostazioni.json';
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
    setMsgDati('✅ Impostazioni esportate.');
  };
  const importa = (e) => {
    const f = e.target.files && e.target.files[0];
    if (!f) return;
    const r = new FileReader();
    r.onload = () => {
      try { sostituisci(JSON.parse(String(r.result))); setMsgDati('✅ Impostazioni importate dal file.'); }
      catch { setMsgDati('⚠️ File non valido: dev\'essere un JSON di impostazioni esportato da qui.'); }
    };
    r.readAsText(f);
    e.target.value = '';
  };
  const azzera = () => {
    if (window.confirm('Ripristinare tutte le impostazioni ai valori di fabbrica?')) {
      ripristina(); setMsgDati('✅ Impostazioni ripristinate ai valori di fabbrica.');
    }
  };
  const cancella = () => {
    if (window.confirm('Cancellare TUTTI i dati locali del sito (impostazioni comprese)? L\'operazione non è reversibile.')) {
      try { localStorage.clear(); } catch { /* quota */ }
      window.location.reload();
    }
  };

  // Spazio occupato in localStorage (diagnostica).
  const storageKB = (() => {
    try {
      let n = 0;
      for (let i = 0; i < localStorage.length; i++) {
        const k = localStorage.key(i);
        n += k.length + (localStorage.getItem(k) || '').length;
      }
      return (n / 1024).toFixed(1);
    } catch { return '—'; }
  })();

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

          {sezione === 'allenamento' && (
            <>
              <h2>Preferenze allenamento</h2>
              <p className="muted">Impostazioni tecniche della scacchiera durante gli esercizi. Si applicano dal prossimo puzzle.</p>

              <div className="imp-campo"><span>Velocità animazioni scacchiera</span>
                <div className="seg-row">
                  {VELOCITA_ANIM.map((v) => (
                    <button key={v.id} className={'temi-tab' + (v.id === imp.velocitaAnimazioni ? ' attivo' : '')} onClick={() => aggiorna({ velocitaAnimazioni: v.id })}>{v.nome}</button>
                  ))}
                </div>
              </div>

              <Interruttore on={imp.mostraMossePossibili} onChange={(v) => aggiorna({ mostraMossePossibili: v })} label="Mostra le mosse possibili" nota="i puntini sulle case dove il pezzo selezionato può andare" />

              <div className="imp-campo"><span>Tentativi prima di rivelare la soluzione</span>
                <div className="seg-row">
                  {MAX_TENTATIVI_OPZIONI.map((n) => (
                    <button key={n} className={'temi-tab' + (n === imp.maxTentativi ? ' attivo' : '')} onClick={() => aggiorna({ maxTentativi: n })}>{n}</button>
                  ))}
                </div>
                <p className="faint">Dopo questi tentativi errati il puzzle mostra la mossa giusta e si passa oltre.</p>
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
            </>
          )}

          {sezione === 'dati' && (
            <>
              <h2>Dati e privacy</h2>
              <p className="muted">Le tue impostazioni sono salvate <strong>solo su questo dispositivo</strong> (localStorage del browser): non vengono inviate a nessun server. Anche il backend di analisi gira in locale sul tuo computer.</p>

              <div className="imp-campo"><span>Le tue impostazioni</span>
                <div className="imp-azioni">
                  <button className="btn btn-ghost" onClick={esporta}>⬇️ Esporta (JSON)</button>
                  <button className="btn btn-ghost" onClick={() => fileRef.current && fileRef.current.click()}>⬆️ Importa da file</button>
                  <input ref={fileRef} type="file" accept="application/json,.json" hidden onChange={importa} />
                </div>
              </div>

              <div className="imp-campo"><span>Ripristino e cancellazione</span>
                <div className="imp-azioni">
                  <button className="btn btn-ghost" onClick={azzera}>↺ Azzera impostazioni</button>
                  <button className="btn btn-ghost imp-pericolo" onClick={cancella}>🗑️ Cancella tutti i dati locali</button>
                </div>
              </div>

              {msgDati && <p className="imp-esito">{msgDati}</p>}
              <p className="faint">«Cancella tutti i dati locali» svuota il localStorage del sito e ricarica la pagina: tornerai ai valori di fabbrica. I dati delle partite (backend) si gestiscono da <Link to="/dati">I miei dati</Link>.</p>
            </>
          )}

          {sezione === 'sistema' && (
            <>
              <h2>Sistema e connessione</h2>

              <div className="imp-campo"><span>Stato del backend</span>
                <StatoConnessione />
              </div>

              <label className="imp-campo"><span>URL del backend</span>
                <input type="text" value={imp.backendUrl} placeholder={BACKEND_DEFAULT} onChange={(e) => aggiorna({ backendUrl: e.target.value })} />
              </label>
              <p className="faint">Vuoto = default (<code>{BACKEND_DEFAULT}</code>). In uso ora: <code>{BACKEND}</code>. Se cambi l'URL, <strong>ricarica la pagina</strong> per applicarlo.</p>

              <div className="imp-diag">
                <h3>Diagnostica</h3>
                <table className="imp-diag-tab"><tbody>
                  <tr><th>Versione app</th><td>{APP_VERSION} · {APP_CANALE}</td></tr>
                  <tr><th>Backend in uso</th><td><code>{BACKEND}</code></td></tr>
                  <tr><th>Connessione rete</th><td>{typeof navigator !== 'undefined' && navigator.onLine ? 'online' : 'offline'}</td></tr>
                  <tr><th>Finestra</th><td>{window.innerWidth}×{window.innerHeight} px</td></tr>
                  <tr><th>Spazio impostazioni</th><td>{storageKB} KB</td></tr>
                  <tr><th>Browser</th><td className="imp-ua">{typeof navigator !== 'undefined' ? navigator.userAgent : '—'}</td></tr>
                </tbody></table>
              </div>
            </>
          )}

          {sezione === 'abbonamenti' && (
            <>
              <h2>Abbonamenti</h2>
              <div className="stub">
                Chess-AI è in <strong>anteprima gratuita</strong> e a utente singolo: nessun piano a pagamento
                è attivo e non è richiesto alcun metodo di pagamento. Piani, fatturazione e gestione
                dell'abbonamento arriveranno con il prodotto pubblico (Fase 5, multi-utente).
              </div>
              <p className="faint">Nessun dato di pagamento viene raccolto o trattato in questa versione.</p>
            </>
          )}

          {sezione === 'account' && (
            <>
              <h2>Account</h2>
              <div className="stub">
                Oggi l'app lavora a <strong>utente singolo, in locale</strong>: non esiste ancora un account
                online, quindi non ci sono credenziali da gestire. Con la Fase 5 (multi-utente) qui troverai:
              </div>
              <ul className="imp-elenco">
                <li>e-mail e password, con reimpostazione della password;</li>
                <li>autenticazione a due fattori (2FA) e gestione delle sessioni attive;</li>
                <li>esportazione e cancellazione dell'account (diritto all'oblio);</li>
                <li>collegamento del profilo Chess.com al tuo account.</li>
              </ul>
              <p className="muted">Intanto, l'identità locale (nome e icona) si imposta in <button className="imp-inline-link" onClick={() => setSezione('profilo')}>Profilo giocatore</button>, e i dati delle partite in <Link to="/dati">I miei dati</Link>.</p>
            </>
          )}

          {sezione === 'info' && (
            <>
              <h2>Info e note legali</h2>
              <p className="muted"><strong>Chess-AI</strong> — versione {APP_VERSION} ({APP_CANALE}). Strumento personale di allenamento scacchistico costruito sulle tue partite reali.</p>

              <h3>Tecnologie e licenze</h3>
              <p className="muted">Il sito è costruito su librerie open-source, di cui riconosce autori e licenze:</p>
              <table className="imp-lic">
                <thead><tr><th>Componente</th><th>Uso</th><th>Licenza</th></tr></thead>
                <tbody>
                  <tr><td>React / React-DOM</td><td>interfaccia</td><td>MIT</td></tr>
                  <tr><td>Vite</td><td>build e dev server</td><td>MIT</td></tr>
                  <tr><td>React Router</td><td>navigazione</td><td>MIT</td></tr>
                  <tr><td>chessground</td><td>scacchiera</td><td>GPL-3.0</td></tr>
                  <tr><td>chess.js</td><td>regole del gioco</td><td>BSD-2-Clause</td></tr>
                  <tr><td>Chart.js</td><td>grafici dei progressi</td><td>MIT</td></tr>
                  <tr><td>Stockfish</td><td>motore di analisi (backend)</td><td>GPL-3.0</td></tr>
                </tbody>
              </table>
              <p className="faint">chessground e Stockfish sono rilasciati sotto GPL-3.0: il loro uso comporta gli obblighi della licenza copyleft.</p>

              <h3>Termini e privacy</h3>
              <p className="muted">Versione anteprima per uso personale. Le impostazioni restano sul tuo dispositivo e le partite vengono analizzate in locale. L'unico dato esterno richiesto è il tuo nome utente Chess.com, usato solo per scaricare le tue partite pubbliche tramite l'API ufficiale.</p>
              <p className="faint">Termini di servizio e informativa privacy completi arriveranno con il prodotto pubblico (Fase 5).</p>

              <h3>Crediti</h3>
              <p className="muted">Puzzle tattici dal database pubblico Lichess; classificazione delle aperture secondo il codice ECO. Grazie alle community open-source dietro questi strumenti.</p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
