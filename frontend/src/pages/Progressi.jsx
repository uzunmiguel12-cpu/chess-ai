import { useEffect, useRef, useState } from 'react';
import Chart from 'chart.js/auto';
import { BACKEND } from '../config.js';
import './Progressi.css';

// Colori leggibili su sfondo scuro (una volta sola).
Chart.defaults.color = '#9aa4b2';
Chart.defaults.borderColor = 'rgba(255,255,255,0.08)';

const FLUSSI = { piano: 'Piano', temi: 'Temi', errori: 'Errori' };

export default function Progressi() {
  const cPrimo = useRef(null);
  const cElo = useRef(null);
  const cTemi = useRef(null);
  const charts = useRef({});

  const [dati, setDati] = useState(null); // { fasce, temi, prog } | 'loading' | 'error'
  const [flussi, setFlussi] = useState(null);

  const carica = async () => {
    setDati('loading');
    try {
      const [fasce, temi, prog, fl] = await Promise.all([
        fetch(`${BACKEND}/storico-fasce`).then((r) => r.json()),
        fetch(`${BACKEND}/statistiche-temi`).then((r) => r.json()),
        fetch(`${BACKEND}/progressi`).then((r) => r.json()),
        fetch(`${BACKEND}/flussi`).then((r) => r.json()),
      ]);
      setFlussi(fl);
      setDati({ fasce, temi, prog });
    } catch { setDati('error'); }
  };

  const cambiaFlusso = async (nome) => {
    try { await fetch(`${BACKEND}/flusso/${nome}`, { method: 'POST' }); await carica(); }
    catch { /* noop */ }
  };

  useEffect(() => { carica(); return () => Object.values(charts.current).forEach((c) => c?.destroy()); }, []);

  // Disegna/aggiorna i grafici quando arrivano i dati.
  useEffect(() => {
    if (!dati || typeof dati !== 'object') return;
    Object.values(charts.current).forEach((c) => c?.destroy());
    charts.current = {};
    const { fasce, temi, prog } = dati;
    const snapshot = prog.snapshot || [];
    // Niente dati significativi: nessun grafico (i canvas non sono nemmeno montati).
    if ((fasce.storico_fasce || []).length === 0 && snapshot.length === 0 && Object.keys(temi.temi || {}).length === 0) return;

    // 1) % al primo colpo nel tempo + bersaglio 85%.
    const val = snapshot.map((s) => s.percentuale_primo_colpo);
    charts.current.primo = new Chart(cPrimo.current, {
      type: 'line',
      data: {
        labels: snapshot.map((s) => `${s.tentati}`),
        datasets: [
          { label: '% al primo colpo', data: val, borderColor: '#5b9bf3', backgroundColor: 'rgba(91,155,243,0.18)', tension: 0.2, fill: true },
          { label: 'bersaglio adattivo (85%)', data: val.map(() => 85), borderColor: '#8a93a3', borderDash: [5, 5], borderWidth: 1, pointRadius: 0, fill: false },
        ],
      },
      options: {
        responsive: true,
        scales: { y: { beginAtZero: true, max: 100, title: { display: true, text: '%' } }, x: { title: { display: true, text: 'puzzle tentati' } } },
        plugins: {
          title: { display: true, text: '% di successo al primo colpo nel tempo' },
          subtitle: { display: true, color: '#8a93a3', font: { size: 11 }, padding: { bottom: 8 },
            text: ["Tende all'85% perché la difficoltà si adatta: una linea piatta è NORMALE.", "Per la crescita reale guarda la 'Fascia Elo nel tempo'."] },
        },
      },
    });

    // 2) Fascia Elo nel tempo (punto medio).
    const storico = fasce.storico_fasce || [];
    const etE = []; const valE = [];
    if (storico.length) {
      const p = storico[0].da; etE.push('inizio'); valE.push((p[0] + p[1]) / 2);
      storico.forEach((s, i) => { etE.push(`cambio ${i + 1}`); valE.push((s.a[0] + s.a[1]) / 2); });
    } else { etE.push('ora'); valE.push((fasce.elo_min + fasce.elo_max) / 2); }
    charts.current.elo = new Chart(cElo.current, {
      type: 'line',
      data: { labels: etE, datasets: [{ label: 'Fascia Elo (punto medio)', data: valE, borderColor: '#46b17b', backgroundColor: 'rgba(70,177,123,0.18)', tension: 0.2, fill: true }] },
      options: {
        responsive: true,
        scales: { y: { grace: '10%', title: { display: true, text: 'Elo (punto medio)' } }, x: { title: { display: true, text: 'tappa' } } },
        plugins: {
          title: { display: true, text: 'Fascia Elo nel tempo' },
          subtitle: { display: true, color: '#8a93a3', font: { size: 11 }, padding: { bottom: 8 },
            text: ['Questo è il vero indicatore di crescita: se la fascia sale, stai migliorando davvero.'] },
        },
      },
    });

    // 3) Successo per tema.
    const chiavi = Object.keys(temi.temi || {});
    charts.current.temi = new Chart(cTemi.current, {
      type: 'bar',
      data: { labels: chiavi.map((t) => t.replace(/_/g, ' ')), datasets: [{ label: '% al primo colpo', data: chiavi.map((t) => temi.temi[t].percentuale_primo), backgroundColor: '#46b17b' }] },
      options: { responsive: true, scales: { y: { beginAtZero: true, max: 100, title: { display: true, text: '%' } } }, plugins: { title: { display: true, text: 'Successo per tema (%)' } } },
    });
  }, [dati]);

  const vuoto = dati && typeof dati === 'object'
    && (dati.fasce.storico_fasce || []).length === 0
    && (dati.prog.snapshot || []).length === 0
    && Object.keys(dati.temi.temi || {}).length === 0;
  const mostra = dati && typeof dati === 'object' && !vuoto;

  const prog = dati && typeof dati === 'object' ? dati.prog : null;
  const t = prog?.tendenza;
  const r = prog?.riepilogo;
  const tema = (x) => (x ? `${x.tema.replace(/_/g, ' ')} (${x.percentuale_primo}%)` : '—');

  return (
    <div className="progressi">
      <div className="page-head">
        <h1>Progressi</h1>
        <p>Andamento nel tempo, riferito al flusso selezionato. Il successo tende all'85% per la
          difficoltà adattiva: la crescita vera si legge nella fascia Elo.</p>
      </div>

      <div className="prog-flussi">
        <span className="muted">Flusso:</span>
        {flussi && Object.entries(flussi.flussi).map(([nome, meta]) => (
          <button
            key={nome}
            className={'flusso-btn' + (nome === flussi.flusso_attivo ? ' attivo' : '') + (meta.implementato ? '' : ' disabilitato')}
            disabled={!meta.implementato}
            onClick={() => cambiaFlusso(nome)}
          >
            {FLUSSI[nome] || nome}
          </button>
        ))}
      </div>

      {dati === 'loading' && (
        <div className="stato-box caricamento"><span className="stato-ic">⏳</span><p>Carico i progressi…</p></div>
      )}
      {dati === 'error' && (
        <div className="stato-box errore"><span className="stato-ic">⚠️</span><p>Impossibile contattare il server.</p><p className="muted">È avviato su localhost:8000?</p></div>
      )}
      {vuoto && (
        <div className="stato-box"><span className="stato-ic">📊</span><p><strong>Ancora pochi dati</strong></p>
          <p className="muted">Risolvi qualche puzzle nell'Allenamento: qui vedrai comparire i tuoi progressi nel tempo.</p></div>
      )}

      {mostra && (
        <>
          {t && (
            <div className={'indicatore-tendenza tendenza-' + t.direzione}>
              <span className="tendenza-freccia">{t.freccia}</span>
              <span>Stai migliorando? <strong>{t.etichetta}</strong></span>
            </div>
          )}
          {r && (
            <div className="card">
              <table className="riepilogo-tabella">
                <tbody>
                  <tr><th>Puzzle totali tentati</th><td>{r.tentati_totali}</td></tr>
                  <tr><th>% al primo colpo (storica)</th><td>{r.percentuale_primo_storica}%</td></tr>
                  <tr><th>Fascia Elo iniziale</th><td>{r.elo_iniziale[0]}–{r.elo_iniziale[1]}</td></tr>
                  <tr><th>Fascia Elo attuale</th><td>{r.elo_attuale[0]}–{r.elo_attuale[1]}</td></tr>
                  <tr><th>Guadagno</th><td>{r.guadagno >= 0 ? '+' : ''}{r.guadagno} punti</td></tr>
                  <tr><th>Tema migliore</th><td>{tema(r.tema_migliore)}</td></tr>
                  <tr><th>Tema peggiore</th><td>{tema(r.tema_peggiore)}</td></tr>
                </tbody>
              </table>
            </div>
          )}
          <div className="card grafico-box"><canvas ref={cPrimo} /></div>
          <div className="card grafico-box"><canvas ref={cElo} /></div>
          <div className="card grafico-box"><canvas ref={cTemi} /></div>
        </>
      )}
    </div>
  );
}
