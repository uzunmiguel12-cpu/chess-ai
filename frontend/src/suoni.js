// Motore audio minimale sintetizzato con Web Audio: nessun file da scaricare.
// Suoni: mossa, cattura, successo, errore. Gestito da un flag globale (abilitaSuoni),
// impostato dal context in base all'impostazione "Suoni". L'AudioContext si crea al
// primo suono (dentro un gesto utente, quindi consentito dal browser).

let ctx = null;
let abilitati = true;

function ac() {
  if (ctx === null) {
    try { ctx = new (window.AudioContext || window.webkitAudioContext)(); }
    catch { ctx = false; }
  }
  if (ctx && ctx.state === 'suspended') { ctx.resume().catch(() => {}); }
  return ctx || null;
}

// Un tono con inviluppo rapido (attacco 5ms, decadimento esponenziale).
function tono({ freq, dur = 0.08, tipo = 'sine', vol = 0.16, glideTo = null, quando = 0 }) {
  const c = ac();
  if (!c) return;
  const t0 = c.currentTime + quando;
  const osc = c.createOscillator();
  const g = c.createGain();
  osc.type = tipo;
  osc.frequency.setValueAtTime(freq, t0);
  if (glideTo) osc.frequency.exponentialRampToValueAtTime(glideTo, t0 + dur);
  g.gain.setValueAtTime(0.0001, t0);
  g.gain.exponentialRampToValueAtTime(vol, t0 + 0.005);
  g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
  osc.connect(g);
  g.connect(c.destination);
  osc.start(t0);
  osc.stop(t0 + dur + 0.02);
}

// Breve burst di rumore filtrato: dà "corpo" alla cattura (legno/impatto).
function rumore({ dur = 0.09, vol = 0.18, taglio = 900 }) {
  const c = ac();
  if (!c) return;
  const t0 = c.currentTime;
  const n = Math.floor(c.sampleRate * dur);
  const buf = c.createBuffer(1, n, c.sampleRate);
  const data = buf.getChannelData(0);
  for (let i = 0; i < n; i++) data[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / n, 2);
  const src = c.createBufferSource();
  src.buffer = buf;
  const lp = c.createBiquadFilter();
  lp.type = 'lowpass';
  lp.frequency.value = taglio;
  const g = c.createGain();
  g.gain.value = vol;
  src.connect(lp);
  lp.connect(g);
  g.connect(c.destination);
  src.start(t0);
}

export function abilitaSuoni(v) { abilitati = !!v; }

export function suonaMossa() {
  if (!abilitati) return;
  tono({ freq: 300, glideTo: 210, dur: 0.05, tipo: 'triangle', vol: 0.13 });
}
export function suonaCattura() {
  if (!abilitati) return;
  rumore({ dur: 0.1, vol: 0.2, taglio: 1100 });
  tono({ freq: 190, glideTo: 130, dur: 0.09, tipo: 'sine', vol: 0.14 });
}
export function suonaSuccesso() {
  if (!abilitati) return;
  tono({ freq: 660, dur: 0.1, tipo: 'sine', vol: 0.15 });
  tono({ freq: 880, dur: 0.14, tipo: 'sine', vol: 0.15, quando: 0.11 });
}
export function suonaErrore() {
  if (!abilitati) return;
  tono({ freq: 200, glideTo: 150, dur: 0.22, tipo: 'square', vol: 0.12 });
}

// Anteprima per il pulsante "Prova": suona SEMPRE (anche col toggle spento), per far
// sentire com'è prima di attivarlo.
export function provaSuoni() {
  const salva = abilitati;
  abilitati = true;
  suonaMossa();
  setTimeout(suonaCattura, 150);
  setTimeout(suonaSuccesso, 320);
  setTimeout(() => { abilitati = salva; }, 700);
}
