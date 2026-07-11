import { createContext, useContext, useEffect, useState } from 'react';
import { abilitaSuoni } from './suoni.js';

// Impostazioni del sito, salvate in locale (localStorage). Niente account/backend per ora:
// il multi-utente arriverà con la Fase 5. Le preferenze visive si applicano globalmente via
// attributi data-* su <html> (vedi theme.css e pezzi.css).
const DEFAULTS = {
  boardTheme: 'legno', pezzi: 'classico', avatar: '♞', nomeUtente: 'Giocatore',
  suoni: true, lingua: 'it',
  // Accessibilità
  riduciAnimazioni: false, dimensioneTesto: 'normale', contrastoAlto: false,
};
const KEY = 'impostazioni';
const Ctx = createContext(null);

function carica() {
  try { return { ...DEFAULTS, ...JSON.parse(localStorage.getItem(KEY) || '{}') }; }
  catch { return { ...DEFAULTS }; }
}

export function ImpostazioniProvider({ children }) {
  const [imp, setImp] = useState(carica);
  useEffect(() => { try { localStorage.setItem(KEY, JSON.stringify(imp)); } catch { /* quota */ } }, [imp]);
  // Applico le preferenze visive come attributi su <html> (il CSS fa il resto).
  useEffect(() => {
    const d = document.documentElement.dataset;
    d.board = imp.boardTheme;
    d.pezzi = imp.pezzi;
    d.anim = imp.riduciAnimazioni ? 'ridotte' : 'normali';
    d.testo = imp.dimensioneTesto;
    d.contrasto = imp.contrastoAlto ? 'alto' : 'normale';
  }, [imp.boardTheme, imp.pezzi, imp.riduciAnimazioni, imp.dimensioneTesto, imp.contrastoAlto]);
  // Collego il toggle Suoni al motore audio (flag globale in suoni.js).
  useEffect(() => { abilitaSuoni(imp.suoni); }, [imp.suoni]);
  const aggiorna = (patch) => setImp((s) => ({ ...s, ...patch }));
  return <Ctx.Provider value={{ imp, aggiorna }}>{children}</Ctx.Provider>;
}

export function useImpostazioni() {
  return useContext(Ctx) || { imp: DEFAULTS, aggiorna: () => {} };
}

// Elenchi condivisi (usati dalla pagina Impostazioni e dal menu avatar).
export const TEMI_BOARD = [
  { id: 'legno', nome: 'Legno', light: '#f0d9b5', dark: '#b58863' },
  { id: 'verde', nome: 'Verde', light: '#ebecd0', dark: '#779556' },
  { id: 'blu', nome: 'Blu', light: '#dee3e6', dark: '#6f92b0' },
  { id: 'grigio', nome: 'Grigio', light: '#dcdcdc', dark: '#8f8f8f' },
  { id: 'notte', nome: 'Notte', light: '#6b7a8f', dark: '#3b4656' },
  { id: 'marmo', nome: 'Marmo', light: '#e8e2d8', dark: '#9b8f7e' },
];

export const AVATARS = ['♞', '♟️', '♚', '♛', '♜', '♝', '🦊', '🐯', '🦉', '🐺', '🦁', '🐧', '🐢', '⚡', '🔥', '🌟'];

// Set di pezzi disponibili. "classico" = cburnett (di serie). Gli altri sono definiti in
// pezzi.css e attivati da html[data-pezzi]. `campione` è un glifo per l'anteprima nel menu.
export const PEZZI = [
  { id: 'classico', nome: 'Classico', campione: '♘' },
  { id: 'pieno', nome: 'Pieno', campione: '♞' },
  { id: 'contorno', nome: 'Contorno', campione: '♞' },
];

// Opzioni dimensione testo (Accessibilità).
export const DIMENSIONI_TESTO = [
  { id: 'piccolo', nome: 'Piccolo' },
  { id: 'normale', nome: 'Normale' },
  { id: 'grande', nome: 'Grande' },
];
