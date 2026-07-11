import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { PRINCIPI } from '../data/principi.js';
import MiniBoard from '../components/MiniBoard.jsx';
import PrincipioDettaglio from '../components/PrincipioDettaglio.jsx';
import './Principi.css';

// Indice: tutti i principi come card (con diagramma), raggruppati per tema. Click -> dettaglio.
export default function Principi() {
  const [sel, setSel] = useState(null); // principio selezionato | null
  const [params] = useSearchParams();   // ?tema= dai consigli delle Carenze

  // Se arrivo con ?tema=..., scorro fino a quel tema e lo evidenzio un istante.
  useEffect(() => {
    const t = params.get('tema');
    if (!t || sel) return;
    const el = document.getElementById('tema-' + t);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
      el.classList.add('pr-evidenzia');
      const timer = setTimeout(() => el.classList.remove('pr-evidenzia'), 2200);
      return () => clearTimeout(timer);
    }
    return undefined;
  }, [params, sel]);

  if (sel) return <PrincipioDettaglio principio={sel} onIndietro={() => setSel(null)} />;

  return (
    <div className="principi">
      <div className="page-head">
        <h1>Principi</h1>
        <p>La teoria posizionale per capire <em>come</em> affrontare una posizione — ciò che i puzzle
          tattici non allenano. Scegli un principio: dentro trovi spiegazione, esempi giocabili e un quiz.</p>
      </div>

      {PRINCIPI.map((tema) => (
        <section key={tema.id} id={'tema-' + tema.id} className="pr-tema-sezione">
          <h2 className="pr-tema-h">{tema.icona} {tema.titolo}</h2>
          <div className="pr-cards">
            {tema.principi.map((p, i) => (
              <button key={tema.id + i} className="pr-card" onClick={() => setSel(p)}>
                {p.fen && <div className="pr-card-ill"><MiniBoard fen={p.fen} /></div>}
                <div className="pr-card-corpo">
                  <strong className="pr-card-tit">{p.titolo}</strong>
                  <span className="pr-card-desc muted">{p.testo}</span>
                  <span className="pr-card-cta">Studia →</span>
                </div>
              </button>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
