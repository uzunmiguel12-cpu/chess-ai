// Segnaposto per le pagine non ancora portate al nuovo design. Rende visibile
// lo scheletro del sito prima di migrare la logica pagina per pagina.
export default function Stub({ title, sottotitolo, children }) {
  return (
    <div>
      <div className="page-head">
        <h1>{title}</h1>
        {sottotitolo && <p>{sottotitolo}</p>}
      </div>
      <div className="stub">
        {children || 'In costruzione: questa sezione verrà portata al nuovo design nel prossimo passo del refactor.'}
      </div>
    </div>
  );
}
