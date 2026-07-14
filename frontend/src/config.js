// Punto unico di configurazione del frontend.

// URL di default del backend (FastAPI in locale).
export const BACKEND_DEFAULT = 'http://localhost:8000';

// Override configurabile da Impostazioni → Sistema e connessione (salvato in localStorage).
// Letto una volta all'avvio: cambiando l'URL serve ricaricare la pagina.
function _backendConfigurato() {
  try {
    const s = JSON.parse(localStorage.getItem('impostazioni') || '{}');
    const u = (s.backendUrl || '').trim().replace(/\/+$/, '');
    return u || BACKEND_DEFAULT;
  } catch {
    return BACKEND_DEFAULT;
  }
}

export const BACKEND = _backendConfigurato();

// Metadati applicazione (mostrati in Impostazioni → Info e note legali / Sistema).
export const APP_VERSION = '0.5.0';
export const APP_CANALE = 'anteprima locale (single-user)';
