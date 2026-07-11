import { Link } from 'react-router-dom';

export default function NotFound() {
  return (
    <div className="page-head">
      <h1>Pagina non trovata</h1>
      <p>La pagina che cerchi non esiste. <Link to="/">Torna alla Home</Link>.</p>
    </div>
  );
}
