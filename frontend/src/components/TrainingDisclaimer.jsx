import { useState } from 'react';
import './TrainingDisclaimer.css';

// Disclaimer una-tantum (onesta' del sistema). Flag in localStorage: appare solo la prima volta.
export default function TrainingDisclaimer() {
  const [visto, setVisto] = useState(() => localStorage.getItem('disclaimer_visto') === '1');
  if (visto) return null;
  const chiudi = () => { localStorage.setItem('disclaimer_visto', '1'); setVisto(true); };
  return (
    <div className="disclaimer-overlay" role="dialog" aria-modal="true">
      <div className="disclaimer-box card">
        <h2>Come funziona questo allenamento</h2>
        <p>Il sistema analizza le <strong>tue partite reali</strong> con un motore (Stockfish) e
          costruisce un profilo delle tue debolezze: i puzzle che ti propone vengono da lì.</p>
        <p>La difficoltà si <strong>adatta</strong> a come rispondi (regola dell'85%): per questo la
          percentuale di successo tende all'85% e non è, da sola, un segno di miglioramento. Il vero
          indicatore di crescita è la <strong>fascia Elo</strong> che sale nel tempo.</p>
        <p>Conta solo il <strong>primo tentativo</strong> di ogni puzzle; i successivi sono margine
          didattico per capire la soluzione, non contano come successo.</p>
        <p className="muted">Nota: queste statistiche servono a spiegarti onestamente cosa stai
          vedendo — non sono un segreto tecnico protetto.</p>
        <button className="btn btn-primary" onClick={chiudi}>Ho capito</button>
      </div>
    </div>
  );
}
