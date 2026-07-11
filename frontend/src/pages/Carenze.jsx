import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Chart from 'chart.js/auto';
import { BACKEND } from '../config.js';
import { PRINCIPI } from '../data/principi.js';
import './Carenze.css';

// Colori leggibili su sfondo scuro (idempotente, come in Progressi).
Chart.defaults.color = '#9aa4b2';
Chart.defaults.borderColor = 'rgba(255,255,255,0.08)';
const COLORI_FASE = { apertura: '#5b9bf3', mediogioco: '#e0a53b', finale: '#46b17b' };
const COLORI_LINEA = ['#5b9bf3', '#46b17b', '#e0a53b', '#a78bfa'];
const etichettaData = (ts) => {
  if (!ts) return '';
  const d = new Date(ts);
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString('it-IT', { day: '2-digit', month: '2-digit' });
};

// Mappa ONESTA (euristica, non diagnosi puntuale) fase di gioco -> temi dei Principi utili.
const MAPPA_FASE = {
  apertura: ['sviluppo', 'centro', 're'],
  mediogioco: ['pezzi', 'spazio', 'case', 'piano', 'attacco', 'tattica', 'cambi'],
  finale: ['finali', 'struttura', 'pezzi', 'cambi'],
};
const NUCLEO_POSIZIONALE = ['piano', 'struttura', 'case'];

const FASI = ['apertura', 'mediogioco', 'finale'];
const QUALITA = ['best', 'excellent', 'good', 'inaccuracy', 'mistake', 'blunder'];
const TENDENZE = {
  migliorato: { freccia: '▼', classe: 'tend-migliorato', testo: 'in calo (meglio)' },
  peggiorato: { freccia: '▲', classe: 'tend-peggiorato', testo: 'in aumento (peggio)' },
  stabile: { freccia: '→', classe: 'tend-stabile', testo: 'stabile' },
};
const et = (n) => (n || '').replace(/_/g, ' ');
const pedoni = (cp) => { const v = (cp || 0) / 100; return `${v > 0 ? '+' : ''}${Number.isInteger(v) ? v : v.toFixed(1)}`; };
const etichettaPeso = (peso) => (peso >= 1 ? 'priorità massima' : `priorità ~${peso}× rispetto al tema dominante`);

export default function Carenze() {
  const navigate = useNavigate();
  const [profilo, setProfilo] = useState(null); // null | 'loading' | 'assente' | 'error' | obj
  const [conv, setConv] = useState(null);
  const [storico, setStorico] = useState(null); // null | 'loading' | { punti, ha_dati }
  const cFase = useRef(null);
  const cTipo = useRef(null);
  const grafici = useRef({});

  useEffect(() => {
    (async () => {
      setProfilo('loading');
      setStorico('loading');
      try {
        const r = await fetch(`${BACKEND}/profilo`);
        if (!r.ok) { setProfilo('assente'); return; }
        setProfilo(await r.json());
      } catch { setProfilo('error'); return; }
      try {
        const rc = await fetch(`${BACKEND}/diagnosi-conversione`);
        setConv(rc.ok ? await rc.json() : null);
      } catch { setConv(null); }
      try {
        const rs = await fetch(`${BACKEND}/storico-profili`);
        setStorico(rs.ok ? await rs.json() : null);
      } catch { setStorico(null); }
    })();
    return () => Object.values(grafici.current).forEach((c) => c?.destroy());
  }, []);

  // Disegna i grafici dell'evoluzione quando arrivano storico e profilo.
  useEffect(() => {
    if (!storico || typeof storico !== 'object' || !storico.ha_dati) return;
    if (typeof profilo !== 'object' || profilo === null) return;
    if (!cFase.current || !cTipo.current) return;
    Object.values(grafici.current).forEach((c) => c?.destroy());
    grafici.current = {};

    const punti = storico.punti || [];
    const labels = punti.map((p) => etichettaData(p.timestamp));
    const raggi = punti.map((p) => (p.affidabile ? 4 : 2));
    const opzioni = (titolo) => ({
      responsive: true,
      interaction: { mode: 'index', intersect: false },
      scales: { y: { beginAtZero: true, title: { display: true, text: "% d'errore" } },
        x: { title: { display: true, text: 'periodo (partite nuove)' } } },
      plugins: {
        title: { display: true, text: titolo },
        subtitle: { display: true, color: '#8a93a3', font: { size: 11 }, padding: { bottom: 8 },
          text: ['Più in basso = meglio. Ogni punto = solo le partite nuove di quel momento; i punti piccoli sono da poche partite (indicativi).'] },
      },
    });

    // 1) Tasso d'errore per fase nel tempo.
    grafici.current.fase = new Chart(cFase.current, {
      type: 'line',
      data: {
        labels,
        datasets: ['apertura', 'mediogioco', 'finale'].map((f) => ({
          label: f, data: punti.map((p) => (p.tasso_fase?.[f] ?? null)),
          borderColor: COLORI_FASE[f], backgroundColor: 'transparent',
          tension: 0.2, spanGaps: true, pointRadius: raggi, pointHoverRadius: 5,
        })),
      },
      options: opzioni("Errori per fase di gioco nel tempo"),
    });

    // 2) Posizionale (non tattico) + i tipi tattici RILEVANTI per questo giocatore.
    const rilevanti = new Set(profilo.temi_rilevanti || []);
    const ultimo = punti[punti.length - 1]?.tasso_tipo || {};
    const tipi = Object.keys(ultimo)
      .filter((t) => t !== 'non_tattico' && rilevanti.has(t))
      .sort((a, b) => (ultimo[b] || 0) - (ultimo[a] || 0))
      .slice(0, 3);
    const dsTipo = [{
      label: 'posizionale (non tattico)',
      data: punti.map((p) => (p.tasso_tipo?.non_tattico ?? null)),
      borderColor: '#e5678a', backgroundColor: 'transparent', borderWidth: 2.5,
      tension: 0.2, spanGaps: true, pointRadius: raggi, pointHoverRadius: 5,
    }];
    tipi.forEach((t, i) => dsTipo.push({
      label: t.replace(/_/g, ' '),
      data: punti.map((p) => (p.tasso_tipo?.[t] ?? null)),
      borderColor: COLORI_LINEA[i % COLORI_LINEA.length], backgroundColor: 'transparent',
      tension: 0.2, spanGaps: true, pointRadius: raggi, pointHoverRadius: 5,
    }));
    grafici.current.tipo = new Chart(cTipo.current, {
      type: 'line',
      data: { labels, datasets: dsTipo },
      options: opzioni("Errori per tipo nel tempo (posizionale e tattici rilevanti)"),
    });
  }, [storico, profilo]);

  const allena = (tema) => navigate(`/allenamento?tema=${encodeURIComponent(tema)}`);

  if (profilo === 'loading' || profilo === null) return <div className="page-head"><h1>Le mie carenze</h1><p className="muted">Carico il profilo…</p></div>;
  if (profilo === 'error') return <div className="page-head"><h1>Le mie carenze</h1><p className="dati-esito errore">⚠️ Errore nel contattare il server (localhost:8000).</p></div>;
  if (profilo === 'assente') return (
    <div className="page-head"><h1>Le mie carenze</h1>
      <p className="muted">Profilo non ancora disponibile: importa e analizza prima le tue partite
        (vai su <a href="/dati">I miei dati</a>).</p>
    </div>
  );

  const p = profilo;
  const tassi = p.tasso_su_mosse_per_tipo || {};
  const ogni = p.ogni_quante_mosse_per_tipo || {};
  const conteggi = p.conteggio_tattico || {};
  const tassiOcc = p.tasso_su_occasioni_per_tipo || {};
  const occN = p.occasioni_per_tipo || {};
  const rilevanti = new Set(p.temi_rilevanti || []);
  const tipi = Object.keys(tassi).filter((t) => t !== 'non_tattico').sort((a, b) => (tassi[b] || 0) - (tassi[a] || 0));
  const tassoFase = p.tasso_errore_per_fase || {};
  const grav = p.conteggio_gravita || {};
  const totGrav = QUALITA.reduce((s, g) => s + (grav[g] || 0), 0);
  const piano = p.piano_studio;
  const sf = p.studio_fasi;
  const confronto = p.confronto;

  // Principi da ripassare: dai tuoi errori posizionali (fase dove sbagli di più + quota non-tattica).
  const faseDeb = p.debolezza_principale;
  const nonTatt = (p.percentuali_tattico || {}).non_tattico || 0;
  const idsPrincipi = (() => {
    const s = new Set(MAPPA_FASE[faseDeb] || []);
    if (nonTatt >= 25) NUCLEO_POSIZIONALE.forEach((t) => s.add(t));
    if (s.size === 0) ['piano', 'struttura', 'pezzi'].forEach((t) => s.add(t));
    return [...s];
  })();
  const temiPrincipi = idsPrincipi.map((id) => PRINCIPI.find((t) => t.id === id)).filter(Boolean);

  return (
    <div className="carenze">
      <div className="page-head">
        <h1>Le mie carenze</h1>
        <p>Diagnosi onesta delle tue debolezze, ricavata dalle partite analizzate — non da un test
          generico. Da qui nasce il tuo piano.</p>
      </div>

      {p.sintesi && <div className="card carenza-sintesi">{p.sintesi}</div>}

      {/* COME sbagli */}
      <div className="card">
        <h3>Come sbagli</h3>
        <ul className="carenza-lista">
          {tipi.map((t) => {
            const nonRil = !rilevanti.has(t);
            const to = tassiOcc[t];
            return (
              <li key={t} className={'carenza-item' + (nonRil ? ' non-rilevante' : '')}>
                <span className="carenza-nome">{et(t)}</span>
                <span className="carenza-num">
                  {conteggi[t] || 0} errori · {tassi[t]}% delle mosse
                  {to != null && <> · <strong>{to}% delle occasioni</strong> ({occN[t] || 0} volte era la mossa giusta)</>}
                  {' · '}{ogni[t] ? `una ogni ~${ogni[t]} mosse` : 'mai osservato'}
                </span>
                {nonRil && <span className="carenza-tag">non è un problema per te</span>}
              </li>
            );
          })}
          <li className="carenza-item non-tattico">
            <span className="carenza-nome">errori posizionali</span>
            <span className="carenza-num">{(p.percentuali_tattico || {}).non_tattico || 0}% degli errori gravi · {tassi.non_tattico || 0}% delle mosse</span>
            <span className="carenza-tag">non coperti dai puzzle tattici</span>
          </li>
        </ul>
        <p className="carenza-nota-piccola"><strong>% delle mosse</strong> = su tutte le tue mosse;{' '}
          <strong>% delle occasioni</strong> = solo quando quella tattica era la mossa giusta
          (denominatore più vero: "quanto spesso l'ho mancata").</p>
      </div>

      {/* PRINCIPI DA RIPASSARE: collegamento carenze -> teoria posizionale */}
      {temiPrincipi.length > 0 && (
        <div className="card pr-consigliati">
          <h3>📚 Principi da ripassare</h3>
          <p className="muted">
            Gli errori <strong>posizionali</strong> (non tattici) non si allenano coi puzzle: si studiano.
            {faseDeb ? <> I tuoi si concentrano nella fase di <strong>{faseDeb}</strong>, quindi</> : ' Perciò'}{' '}
            questi temi teorici sono i più utili da ripassare. È un suggerimento basato sulla fase dove
            sbagli di più, non una diagnosi puntuale.
          </p>
          <div className="pr-consigliati-lista">
            {temiPrincipi.map((t) => (
              <button key={t.id} className="btn btn-ghost pr-cons-btn" onClick={() => navigate(`/principi?tema=${t.id}`)}>
                {t.icona} {t.titolo} →
              </button>
            ))}
          </div>
        </div>
      )}

      {/* DOVE sbagli */}
      <div className="card">
        <h3>Dove sbagli</h3>
        <ul className="carenza-lista">
          {FASI.map((f) => {
            const principale = f === p.debolezza_principale;
            return (
              <li key={f} className={'carenza-item' + (principale ? ' carenza-principale' : '')}>
                <span className="carenza-nome">{f}</span>
                <span className="carenza-num">{tassoFase[f] != null ? `${tassoFase[f]}%` : '—'} di errori{principale ? ' · debolezza principale' : ''}</span>
              </li>
            );
          })}
        </ul>
        {p.fasi_divario_piccolo && <p className="carenza-nota-piccola">I tassi delle tre fasi sono vicini: nessuna fase è drammaticamente peggiore.</p>}
      </div>

      {/* QUANTO: qualità mosse */}
      <div className="card">
        <h3>Quanto · qualità delle mosse</h3>
        <ul className="qualita-lista">
          {QUALITA.map((g) => {
            const n = grav[g] || 0;
            const perc = totGrav ? Math.round((100 * n) / totGrav) : 0;
            return (
              <li key={g} className="qualita-riga">
                <span className="qualita-nome">{g}</span>
                <span className="qualita-barra"><span className={'qualita-fill qualita-' + g} style={{ width: perc + '%' }} /></span>
                <span className="qualita-num">{n} ({perc}%)</span>
              </li>
            );
          })}
        </ul>
      </div>

      {/* PIANO DI STUDIO */}
      {piano && (
        <div className="card">
          <h3>📋 Il tuo piano di studio</h3>
          {(piano.voci || []).length === 0 ? (
            <p className="muted">{piano.nota_posizionale || 'Nessun tema tattico rilevante al momento.'}</p>
          ) : (
            <>
              <p className="muted">In base a dove sbagli più spesso, ecco su quali temi liberi concentrarti.</p>
              {piano.ricalibrato_recente && (
                <p className="piano-ricalibrato">📊 Piano <strong>ricalibrato sulle tue ultime {piano.partite_recenti} partite</strong>: i pesi riflettono il tuo livello di adesso.</p>
              )}
              <ol className="piano-lista">
                {piano.voci.map((v, i) => {
                  const t = v.tendenza && TENDENZE[v.tendenza];
                  return (
                    <li key={i} className="piano-voce">
                      <div className="piano-voce-testa">
                        <span className="piano-tema">{et(v.tema)}</span>
                        {t && <span className={'piano-tendenza ' + t.classe} title={`nelle ultime ${confronto?.partite_nuove || 0} partite: ${t.testo}`}>{t.freccia}</span>}
                        <span className={'piano-priorita priorita-' + v.priorita}>{v.priorita}</span>
                      </div>
                      <span className="piano-dato">{v.ogni_quante_mosse ? `una ogni ~${v.ogni_quante_mosse} mosse` : 'raro'} · {v.tasso_su_mosse}% delle tue mosse · {etichettaPeso(v.peso_relativo)}</span>
                      {v.tema_libero && <button className="btn btn-ghost piano-allena" onClick={() => allena(v.tema_libero)}>allenati su questo tema</button>}
                    </li>
                  );
                })}
              </ol>
              {piano.progressione && <p className="muted">{piano.progressione}</p>}
              {piano.nota_posizionale && <p className="muted">{piano.nota_posizionale}</p>}
            </>
          )}
        </div>
      )}

      {/* STUDIO PER FASI (finali) — denominatore proprio */}
      {sf && sf.disponibile && sf.tassi?.length > 0 && (() => {
        const maxT = Math.max(...sf.tassi.map((t) => t.tasso || 0));
        const scala = maxT > 0 ? maxT * 1.15 : 1;
        return (
          <div className="card">
            <h3>🎯 Studio per fasi di gioco — Finali</h3>
            {sf.denominatore && <p className="fasi-denominatore">{sf.denominatore}.</p>}
            <ul className="qualita-lista">
              {sf.tassi.map((t, i) => {
                const largh = Math.round((100 * (t.tasso || 0)) / scala);
                const evid = t.peggiore && !t.fragile;
                return (
                  <li key={i} className={'qualita-riga' + (evid ? ' fasi-peggiore' : '') + (t.fragile ? ' fasi-fragile' : '')}>
                    <span className="qualita-nome">{et(t.etichetta)}</span>
                    <span className="qualita-barra"><span className={'qualita-fill' + (evid ? ' fasi-fill-peggiore' : '')} style={{ width: largh + '%' }} /></span>
                    <span className="qualita-num">{t.tasso}% · {t.mosse} mosse {t.fragile ? <span className="carenza-tag">pochi dati</span> : (evid && <span className="carenza-tag">da allenare</span>)}</span>
                  </li>
                );
              })}
            </ul>
            {sf.raccomandazione && <p className="fasi-raccomandazione">{sf.raccomandazione}</p>}
            <div className="fasi-bottoni">
              {sf.tassi.flatMap((t) => (t.temi || []).map((tm) => (
                <button key={tm.it} className="btn btn-ghost piano-allena" onClick={() => allena(tm.it)}>allena {tm.label}</button>
              )))}
            </div>
          </div>
        );
      })()}

      {/* CONFRONTO nel tempo */}
      <div className="card">
        <h3>📈 Stai migliorando? <small className="muted">(partite recenti vs storico)</small></h3>
        {!confronto ? (
          <p className="muted">Nessun confronto ancora: carica nuove partite dopo esserti allenato e qui vedrai se stai migliorando davvero — sulle partite vere, non sui puzzle.</p>
        ) : (
          <>
            <p className="muted">Basato sulle tue ultime <strong>{confronto.partite_nuove}</strong> partite, confrontate con lo storico precedente.</p>
            {!confronto.affidabile && confronto.avvertenza && <p className="conv-avviso">⚠️ {confronto.avvertenza}</p>}
            <ul className="confronto-lista">
              {(confronto.voci || []).map((v, i) => {
                const t = TENDENZE[v.tendenza] || TENDENZE.stabile;
                return (
                  <li key={i} className="confronto-voce">
                    <span className="confronto-nome">{et(v.tema || v.fase)} <em className="faint">{v.tema ? 'tema' : 'fase'}</em></span>
                    <span className="confronto-tassi">{v.tasso_storico}% <span className={'confronto-arrow ' + t.classe}>{t.freccia}</span> {v.tasso_recente}% <span className={'confronto-delta ' + t.classe}>({v.delta > 0 ? '+' : ''}{v.delta})</span></span>
                  </li>
                );
              })}
            </ul>
          </>
        )}
      </div>

      {/* EVOLUZIONE NEL TEMPO: serie storica dei tassi d'errore (periodo per periodo) */}
      <div className="card">
        <h3>📈 Evoluzione nel tempo</h3>
        {storico === 'loading' || storico === null ? (
          <p className="muted">Carico lo storico…</p>
        ) : !storico.ha_dati ? (
          <div className="stato-box">
            <span className="stato-ic">📈</span>
            <p><strong>Non c'è ancora abbastanza storico</strong></p>
            <p className="muted">Serve aver analizzato le partite in <strong>almeno due momenti diversi</strong>:
              importa nuove partite dopo esserti allenato e qui vedrai come i tuoi tassi d'errore
              cambiano nel tempo — sulle partite vere, periodo per periodo, senza la diluizione del totale storico.</p>
          </div>
        ) : (
          <>
            <p className="muted">Ogni punto è un <strong>periodo</strong> (solo le partite nuove di quel momento),
              non il totale cumulativo: così un calo è un miglioramento vero. <strong>Più in basso = meglio.</strong>{' '}
              I punti da poche partite (cerchio piccolo) sono indicativi.</p>
            <div className="grafico-box"><canvas ref={cFase} /></div>
            <div className="grafico-box grafico-secondo"><canvas ref={cTipo} /></div>
          </>
        )}
      </div>

      {/* CONVERSIONE DEL VANTAGGIO */}
      <div className="card">
        <h3>🎯 Conversione del vantaggio</h3>
        {!conv || !conv.partite_con_vantaggio ? (
          <p className="muted">Non ci sono ancora abbastanza partite analizzate per misurare come converti i vantaggi.</p>
        ) : (
          <>
            <p className="conv-sintesi">
              Considero i vantaggi decisivi ma non banali, tra <strong>{pedoni(conv.picco_min)}</strong> e <strong>{pedoni(conv.picco_max)}</strong> —
              quelli che richiedono tecnica: li raggiungi in <strong>{conv.partite_con_vantaggio}</strong> partite
              {conv.escludi_bullet && <span className="faint"> (escluse le bullet, dove si perde a tempo)</span>};
              non li converti in <strong>{conv.non_convertite}</strong> ({conv.tasso_non_conversione}%). Di queste,{' '}
              <strong>{conv.crollo.n}</strong> sono <em>crolli</em> (un errore singolo, già coperti dall'allenamento errori) e{' '}
              <strong>{conv.erosione.n}</strong> sono <em>erosioni</em>: vantaggio sciolto gradualmente, senza un errore singolo. È il pattern che gli altri strumenti non vedono.
            </p>
            <div className="conv-evidenza">
              <span className="conv-evidenza-num">{conv.erosione.n}</span>
              <span className="conv-evidenza-eti">erosioni ({conv.erosione.perc}% delle non-conversioni)</span>
            </div>
            <p className="muted">L'erosione è <strong>tecnica di conversione</strong> (semplificare, non rischiare, migliorare i pezzi): non si allena coi puzzle tattici — è consapevolezza.</p>
            {!conv.affidabile && <p className="conv-avviso">⚠️ Campione piccolo ({conv.erosione.n} erosioni): indicativo, non ancora un pattern solido.</p>}
            {(conv.partite_erosione || []).length > 0 && (
              <>
                <p className="muted">Le erosioni più grosse, da rivedere su Chess.com:</p>
                <ul className="conv-lista">
                  {(conv.partite_erosione || []).slice(0, 15).map((pp, i) => {
                    const esito = pp.risultato === 'patta' ? 'patta' : 'sconfitta';
                    return <li key={i} className="conv-voce"><span className="conv-vantaggio">da {pedoni(pp.picco_vantaggio)}</span> → <span>{esito}</span> <span className="faint">{pp.fonte_file}</span></li>;
                  })}
                </ul>
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}
