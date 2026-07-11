import { Link } from 'react-router-dom';
import './Home.css';

export default function Home() {
  return (
    <div className="home">
      <section className="hero">
        <div className="hero-text">
          <span className="badge badge-accent">Allenamento onesto</span>
          <h1>Migliora agli scacchi partendo dalle <em>tue</em> partite reali.</h1>
          <p className="muted">
            Chess-AI analizza le partite che hai davvero giocato con un motore (Stockfish),
            costruisce un profilo delle tue debolezze e ti allena esattamente dove sbagli di
            più. Niente numeri gonfiati: ti mostra con onestà cosa stai vedendo.
          </p>
          <div className="hero-cta">
            <Link to="/allenamento" className="btn btn-primary">Inizia l'allenamento</Link>
            <Link to="/aperture" className="btn btn-ghost">Studia le aperture</Link>
          </div>
        </div>
        <div className="hero-art" aria-hidden="true">
          <div className="hero-board" />
        </div>
      </section>

      <section className="features grid grid-3">
        <div className="card">
          <div className="feat-ic">🩺</div>
          <h3>Diagnosi dalle tue partite</h3>
          <p className="muted">
            Le tue debolezze ricavate dalle partite analizzate — non da un test generico. I
            puzzle nascono da lì.
          </p>
          <Link to="/carenze" className="feat-link">Vedi le mie carenze →</Link>
        </div>
        <div className="card">
          <div className="feat-ic">🎯</div>
          <h3>Puzzle adattivi e onesti</h3>
          <p className="muted">
            La difficoltà si adatta a te (regola dell'85%). Il vero segno di crescita è la
            fascia Elo che sale nel tempo, e te lo diciamo chiaramente.
          </p>
          <Link to="/progressi" className="feat-link">Guarda i progressi →</Link>
        </div>
        <div className="card">
          <div className="feat-ic">♟</div>
          <h3>Aperture con dati veri</h3>
          <p className="muted">
            Rosa curata calibrata sul tuo livello, studio passo-passo e puzzle: nomi e mosse
            vengono dai dati ECO reali, niente teoria inventata.
          </p>
          <Link to="/aperture" className="feat-link">Apri lo studio →</Link>
        </div>
      </section>

      <section className="card honesty">
        <h2>Sostanza, non apparenza</h2>
        <p className="muted">
          Ogni numero che vedi è etichettato per quello che è: un dato misurato o una stima.
          Le statistiche servono a spiegarti il tuo percorso, non a farti sentire più bravo di
          quanto tu sia. È così che si migliora davvero.
        </p>
      </section>
    </div>
  );
}
