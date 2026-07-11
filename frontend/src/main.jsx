import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App.jsx';
import { ImpostazioniProvider } from './ImpostazioniContext.jsx';

// Design system + stili della scacchiera (chessground) globali.
import './styles/theme.css';
import 'chessground/assets/chessground.base.css';
import 'chessground/assets/chessground.brown.css';
import 'chessground/assets/chessground.cburnett.css';
import './styles/pezzi.css';

createRoot(document.getElementById('root')).render(
  <ImpostazioniProvider>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </ImpostazioniProvider>,
);
