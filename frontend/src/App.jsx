import { Routes, Route } from 'react-router-dom';
import TopNav from './components/TopNav.jsx';
import Home from './pages/Home.jsx';
import Dati from './pages/Dati.jsx';
import Allenamento from './pages/Allenamento.jsx';
import Aperture from './pages/Aperture.jsx';
import Sparring from './pages/Sparring.jsx';
import Principi from './pages/Principi.jsx';
import Progressi from './pages/Progressi.jsx';
import Carenze from './pages/Carenze.jsx';
import Impostazioni from './pages/Impostazioni.jsx';
import NotFound from './pages/NotFound.jsx';

export default function App() {
  return (
    <>
      <TopNav />
      <main className="container page">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/dati" element={<Dati />} />
          <Route path="/allenamento" element={<Allenamento />} />
          <Route path="/aperture" element={<Aperture />} />
          <Route path="/sparring" element={<Sparring />} />
          <Route path="/principi" element={<Principi />} />
          <Route path="/progressi" element={<Progressi />} />
          <Route path="/carenze" element={<Carenze />} />
          <Route path="/impostazioni" element={<Impostazioni />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>
      <footer className="container" style={{ padding: '32px 16px', color: 'var(--text-faint)', borderTop: '1px solid var(--border)' }}>
        Chess-AI — allenamento costruito sulle tue partite reali. Sostanza, non apparenza.
      </footer>
    </>
  );
}
