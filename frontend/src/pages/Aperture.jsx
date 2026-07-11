import { useEffect, useState } from 'react';
import { BACKEND } from '../config.js';
import MiniBoard from '../components/MiniBoard.jsx';
import StudioApertura from '../components/StudioApertura.jsx';
import './Aperture.css';

const FASCE = [
  { v: '625', l: 'Principiante alle prime armi (500-750)' },
  { v: '875', l: 'Principiante base (750-1000)' },
  { v: '1125', l: 'Principiante avanzato (1000-1250)' },
  { v: '1375', l: 'Intermedio base (1250-1500)' },
  { v: '1625', l: 'Intermedio avanzato (1500-1750)' },
  { v: '1875', l: 'Avanzato (1750-2000)' },
  { v: '2100', l: 'Avanzato+ (2000+)' },
];

export default function Aperture() {
  const [sezione, setSezione] = useState(null);       // null | 'tutte' | 'guidate'
  const [catalogo, setCatalogo] = useState(null);     // null | 'loading' | 'error' | array
  const [selezione, setSelezione] = useState(null);   // { nome, mosse:[] } | null

  const [elo, setElo] = useState('1125');
  const [obiettivo, setObiettivo] = useState('migliorare');
  const [minuti, setMinuti] = useState('30');
  const [colore, setColore] = useState('entrambi');
  const [consigli, setConsigli] = useState(null);     // null | 'loading' | 'error' | obj

  // Carico il catalogo la prima volta che entro in "Tutte le aperture".
  useEffect(() => {
    if (sezione === 'tutte' && catalogo === null) {
      setCatalogo('loading');
      fetch(`${BACKEND}/aperture/catalogo`)
        .then(async (r) => {
          if (!r.ok) throw new Error('http ' + r.status);
          const d = await r.json();
          if (!Array.isArray(d.aperture)) throw new Error('formato inatteso');
          setCatalogo(d.aperture);
        })
        .catch(() => setCatalogo('error'));
    }
  }, [sezione, catalogo]);

  const caricaConsigli = async () => {
    setConsigli('loading');
    try {
      const r = await fetch(`${BACKEND}/aperture/consiglio?fascia_elo=${elo}&obiettivo=${obiettivo}&minuti=${minuti}&colore=${colore}`);
      setConsigli(await r.json());
    } catch { setConsigli('error'); }
  };

  const studia = (nome, mosseStr) => setSelezione({ nome, mosse: mosseStr.split(' ') });

  // Opening view (riusata da entrambe le sezioni).
  if (selezione) {
    return (
      <div className="aperture">
        <StudioApertura key={selezione.nome} apertura={selezione} onIndietro={() => setSelezione(null)} />
      </div>
    );
  }

  // Landing: due opzioni.
  if (!sezione) {
    return (
      <div className="aperture">
        <div className="page-head">
          <h1>Aperture</h1>
          <p>Impara le aperture con dati veri: nomi e mosse vengono dall'albero ECO, niente teoria inventata.</p>
        </div>
        <div className="ap-scelta">
          <button className="ap-scelta-card" onClick={() => setSezione('tutte')}>
            <span className="asc-ic">📚</span>
            <span className="asc-tit">Tutte le aperture</span>
            <span className="asc-sub">Sfoglia il catalogo: scegli un'apertura, esplora le linee e allenati coi puzzle.</span>
          </button>
          <button className="ap-scelta-card" onClick={() => setSezione('guidate')}>
            <span className="asc-ic">🎯</span>
            <span className="asc-tit">Aperture guidate per livello</span>
            <span className="asc-sub">Rispondi a quattro domande: ti consiglio da quali aperture partire, calibrate sul tuo Elo.</span>
          </button>
        </div>
      </div>
    );
  }

  // Sezione "Tutte le aperture": galleria.
  if (sezione === 'tutte') {
    return (
      <div className="aperture">
        <button className="btn btn-ghost torna" onClick={() => setSezione(null)}>← Aperture</button>
        <div className="page-head"><h1>Tutte le aperture</h1><p>{Array.isArray(catalogo) ? `${catalogo.length} aperture` : ''} — clicca per studiarne una.</p></div>
        {catalogo === 'loading' && <p className="muted">Carico il catalogo…</p>}
        {catalogo === 'error' && <p className="dati-esito errore">⚠️ Catalogo non disponibile: assicurati che il backend sia <strong>avviato e riavviato</strong> dopo gli ultimi aggiornamenti (il nuovo endpoint /aperture/catalogo richiede il riavvio).</p>}
        {Array.isArray(catalogo) && (
          <div className="galleria">
            {catalogo.map((a) => {
              const mosse = a.mosse.split(' ');
              return (
                <button key={a.nome} className="galleria-card" onClick={() => studia(a.nome, a.mosse)}>
                  <MiniBoard mosse={mosse} orientation={a.colore === 'nero' ? 'black' : 'white'} />
                  <div className="gc-corpo">
                    <div className="gc-testa"><strong>{a.nome}</strong> <span className="badge">{a.colore}</span></div>
                    <p className="gc-desc muted">{a.descrizione}</p>
                    <div className="gc-piede"><span className="faint">{a.linee} linee</span><span className="gc-cta">Studia →</span></div>
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </div>
    );
  }

  // Sezione "Aperture guidate": questionario + consigli a menu.
  return (
    <div className="aperture">
      <button className="btn btn-ghost torna" onClick={() => setSezione(null)}>← Aperture</button>
      <div className="page-head"><h1>Aperture guidate per livello</h1><p>Consiglio calibrato sul tuo livello; scegli un'apertura per studiarla.</p></div>

      <form className="card questionario" onSubmit={(e) => { e.preventDefault(); caricaConsigli(); }}>
        <label className="campo"><span>Fascia Elo</span>
          <select value={elo} onChange={(e) => setElo(e.target.value)}>
            {FASCE.map((f) => <option key={f.v} value={f.v}>{f.l}</option>)}
          </select>
        </label>
        <label className="campo"><span>Obiettivo</span>
          <select value={obiettivo} onChange={(e) => setObiettivo(e.target.value)}>
            <option value="divertimento">Divertimento</option>
            <option value="migliorare">Migliorare</option>
            <option value="competere">Competere</option>
          </select>
        </label>
        <label className="campo"><span>Minuti/giorno</span>
          <input type="number" min="5" max="240" value={minuti} onChange={(e) => setMinuti(e.target.value)} />
        </label>
        <label className="campo"><span>Colore</span>
          <select value={colore} onChange={(e) => setColore(e.target.value)}>
            <option value="entrambi">Entrambi</option>
            <option value="bianco">Bianco</option>
            <option value="nero">Nero</option>
          </select>
        </label>
        <button className="btn btn-primary" type="submit">Consigliami le aperture</button>
      </form>

      {consigli === 'loading' && <p className="muted">Calcolo i consigli…</p>}
      {consigli === 'error' && <p className="dati-esito errore">⚠️ Errore nel contattare il server.</p>}
      {consigli && typeof consigli === 'object' && (
        <div className="consigli card">
          {consigli.nota_tempo && <p className="muted">{consigli.nota_tempo}</p>}
          <div className="consigli-menu">
            {(consigli.consigli || []).map((c, i) => (
              <button key={c.nome + i} className="consiglio-voce" onClick={() => studia(c.nome, c.mosse)}>
                <div className="cv-testa"><strong>{c.nome}</strong> <span className="badge">{c.colore} · liv {c.livello} · {c.complessita} varianti</span></div>
                <div className="cv-desc muted">{c.perche}</div>
                <span className="gc-cta">Studia →</span>
              </button>
            ))}
          </div>
          {consigli.nota && <p className="faint">{consigli.nota}</p>}
        </div>
      )}
    </div>
  );
}
