import { useState } from 'react';
import { NavLink, Link } from 'react-router-dom';
import { useImpostazioni, AVATARS } from '../ImpostazioniContext.jsx';
import './TopNav.css';

// Navigazione principale. In alto a destra: avatar + nome utente, cliccabile per scegliere
// l'icona e aprire le Impostazioni.
const VOCI = [
  { to: '/', label: 'Home', end: true },
  { to: '/dati', label: 'I miei dati' },
  { to: '/allenamento', label: 'Allenamento' },
  { to: '/aperture', label: 'Aperture' },
  { to: '/sparring', label: 'Sparring' },
  { to: '/principi', label: 'Principi' },
  { to: '/progressi', label: 'Progressi' },
  { to: '/carenze', label: 'Le mie carenze' },
];

export default function TopNav() {
  const { imp, aggiorna } = useImpostazioni();
  const [apri, setApri] = useState(false);

  return (
    <header className="nav">
      <div className="nav-inner container">
        <NavLink to="/" className="nav-brand" end>
          <span className="nav-logo">♞</span> Chess-AI
        </NavLink>
        <nav className="nav-links">
          {VOCI.map((v) => (
            <NavLink
              key={v.to}
              to={v.to}
              end={v.end}
              className={({ isActive }) => 'nav-link' + (isActive ? ' is-active' : '')}
            >
              {v.label}
            </NavLink>
          ))}
        </nav>

        <div className="nav-utente">
          <button className="utente-btn" onClick={() => setApri((a) => !a)} aria-haspopup="true" aria-expanded={apri}>
            <span className="utente-avatar">{imp.avatar}</span>
            <span className="utente-nome">{imp.nomeUtente}</span>
            <span className="utente-freccia">▾</span>
          </button>
          {apri && (
            <>
              <div className="utente-backdrop" onClick={() => setApri(false)} />
              <div className="utente-menu">
                <div className="um-titolo">La tua icona</div>
                <div className="um-avatars">
                  {AVATARS.map((a) => (
                    <button
                      key={a}
                      className={'um-av' + (a === imp.avatar ? ' attivo' : '')}
                      onClick={() => aggiorna({ avatar: a })}
                    >
                      {a}
                    </button>
                  ))}
                </div>
                <Link to="/impostazioni" className="btn btn-ghost um-imp" onClick={() => setApri(false)}>
                  ⚙ Impostazioni
                </Link>
              </div>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
