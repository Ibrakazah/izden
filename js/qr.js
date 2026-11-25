// Offline student -> teacher transfer: compact "IZ1|…" string in a QR code, plus a short typed code.
// Uses vendor/qrcode.js (global `qrcode`, kazuhikoarase/qrcode-generator) and vendor/jsQR.js (global `jsQR`).
import { SKILLS, TRAPS, DIAGNOSES } from './engine.js';

const pct = p => Math.max(0, Math.min(100, Math.round(p * 100)));

function checksum(s) {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) % 1296;
  return h.toString(36).toUpperCase().padStart(2, '0');
}

function cleanName(name) {
  return String(name || '').replace(/[|\n\r]/g, ' ').trim().slice(0, 24) || '?';
}

// The QR carries initials plus a 2-character tag (so two students with equal initials stay distinct); the full name never leaves the device.
export function qrName(name) {
  const words = String(name || '').replace(/[|#\n\r]/g, ' ').trim().split(/\s+/).filter(Boolean);
  const ini = words.slice(0, 3).map(w => Array.from(w)[0].toUpperCase() + '.').join('');
  return `${ini || '?'}#${checksum(String(name || '').trim().toLowerCase())}`;
}

// IZ1|initials#tag|grade|lang|pL.pU.pE|nL.nU.nE|cL.cU.cE|t1..t6|d1..d4|units|yymmdd|e1..e6|CHK  (e = trap exposure)  (d = understood.guessed.found_wrong.not_found)
export function encodePayload(profile, state, date = new Date()) {
  const p = SKILLS.map(s => pct(state.skills[s].p)).join('.');
  const n = SKILLS.map(s => state.skills[s].n).join('.');
  const c = SKILLS.map(s => state.skills[s].c).join('.');
  const t = TRAPS.map(k => state.traps[k] || 0).join('.');
  const dg = DIAGNOSES.map(k => (state.diag && state.diag[k]) || 0).join('.');
  const ex = TRAPS.map(k => (state.exposure && state.exposure[k]) || 0).join('.');
  const units = Object.keys(state.done).length;
  const d = `${String(date.getFullYear()).slice(2)}${String(date.getMonth() + 1).padStart(2, '0')}${String(date.getDate()).padStart(2, '0')}`;
  const body = ['IZ1', qrName(profile.name), profile.grade, profile.lang, p, n, c, t, dg, units, d, ex].join('|');
  return `${body}|${checksum(body)}`;
}

export function decodePayload(str) {
  const s = String(str || '').trim();
  const parts = s.split('|');
  // 12 parts (v1, no exposure) or 13 parts (exposure appended before the checksum)
  if ((parts.length !== 12 && parts.length !== 13) || parts[0] !== 'IZ1') return null;
  const last = parts.length - 1;
  if (checksum(parts.slice(0, last).join('|')) !== parts[last]) return null;
  const nums = (x, k) => {
    const a = x.split('.').map(v => parseInt(v, 10));
    return a.length === k && a.every(v => Number.isFinite(v) && v >= 0) ? a : null;
  };
  const p = nums(parts[4], 3), n = nums(parts[5], 3), c = nums(parts[6], 3), t = nums(parts[7], 6), dg = nums(parts[8], 4);
  const ex = parts.length === 13 ? nums(parts[11], 6) : null;
  const grade = parseInt(parts[2], 10);
  if (!p || !n || !c || !t || !dg || ![7, 8, 9].includes(grade) || !['kk', 'ru'].includes(parts[3])) return null;
  return {
    name: parts[1], grade, lang: parts[3], p: p.map(v => Math.min(100, v)), n, c, traps: t, diag: dg, exposure: ex,
    units: parseInt(parts[9], 10) || 0, date: parts[10], source: 'qr',
  };
}

// ---- short code (typed by the teacher together with the student's name) ----
const B32 = '0123456789ABCDEFGHJKMNPQRSTVWXYZ';

// Luhn mod 32 check symbol: catches every single-symbol typo and adjacent swaps (a plain sum does not).
function luhn32(symbols) {
  let factor = 2, sum = 0;
  for (let i = symbols.length - 1; i >= 0; i--) {
    let add = factor * symbols[i];
    factor = factor === 2 ? 1 : 2;
    add = Math.floor(add / 32) + (add % 32);
    sum += add;
  }
  return (32 - (sum % 32)) % 32;
}

export function encodeShortCode(profile, state) {
  const p = SKILLS.map(s => pct(state.skills[s].p));
  const nTot = Math.min(255, SKILLS.reduce((a, s) => a + state.skills[s].n, 0));
  const cTot = Math.min(255, SKILLS.reduce((a, s) => a + state.skills[s].c, 0));
  let v = 0n;
  const put = (val, bits) => { v = (v << BigInt(bits)) | BigInt(val); };
  put(Math.max(0, Math.min(2, profile.grade - 7)), 2);
  put(profile.lang === 'ru' ? 1 : 0, 1);
  p.forEach(x => put(x, 7));
  put(nTot, 8);
  put(cTot, 8);
  TRAPS.forEach(k => put(Math.min(31, state.traps[k] || 0), 5));
  put(Math.min(31, (state.diag && state.diag.guessed) || 0), 5);
  const sym = [];
  for (let i = 0; i < 15; i++) { sym.unshift(Number(v & 31n)); v >>= 5n; } // 75 data bits = 15 symbols
  sym.push(luhn32(sym));
  return sym.map(i => B32[i]).join('').match(/.{4}/g).join('-');
}

export function decodeShortCode(code, name) {
  const s = String(code || '').toUpperCase().replace(/[\s-]/g, '').replace(/O/g, '0').replace(/[IL]/g, '1');
  if (!/^[0-9A-Z]{16}$/.test(s)) return null;
  const sym = [...s].map(ch => B32.indexOf(ch));
  if (sym.some(i => i < 0)) return null;
  if (luhn32(sym.slice(0, 15)) !== sym[15]) return null;
  let v = 0n;
  for (const i of sym.slice(0, 15)) v = (v << 5n) | BigInt(i);
  const take = bits => { const x = Number(v & ((1n << BigInt(bits)) - 1n)); v >>= BigInt(bits); return x; };
  const guessed = take(5);
  const traps = []; for (let i = 0; i < 6; i++) traps.unshift(take(5));
  const cTot = take(8), nTot = take(8);
  const p = []; for (let i = 0; i < 3; i++) p.unshift(take(7));
  const lang = take(1) ? 'ru' : 'kk';
  const g = take(2);
  // nothing answered (e.g. 0000-0000-…) or impossible values -> not a real student code
  if (v !== 0n || g > 2 || p.some(x => x > 100) || nTot === 0 || cTot > nTot) return null;
  return {
    name: cleanName(name), grade: g + 7, lang, p, n: [nTot, 0, 0], c: [cTot, 0, 0], nTotalOnly: true,
    traps, diag: [0, guessed, 0, 0], units: 0, date: '', source: 'code',
  };
}

// ---- QR image ----
export function qrSvg(text) {
  const q = window.qrcode;
  q.stringToBytes = q.stringToBytesFuncs['UTF-8'];
  const qr = q(0, 'M');
  qr.addData(text, 'Byte');
  qr.make();
  return qr.createSvgTag({ cellSize: 6, margin: 4, scalable: true, alt: 'QR' });
}

export function decodeImageData(imageData) {
  const res = window.jsQR(imageData.data, imageData.width, imageData.height, { inversionAttempts: 'attemptBoth' });
  if (!res) return null;
  try {
    return new TextDecoder('utf-8').decode(new Uint8Array(res.binaryData));
  } catch (e) {
    return res.data;
  }
}

export async function decodeFile(file) {
  const url = URL.createObjectURL(file);
  try {
    const img = await new Promise((ok, bad) => { const i = new Image(); i.onload = () => ok(i); i.onerror = bad; i.src = url; });
    const scale = Math.min(1, 1200 / Math.max(img.width, img.height));
    const c = document.createElement('canvas');
    c.width = Math.round(img.width * scale); c.height = Math.round(img.height * scale);
    const ctx = c.getContext('2d');
    ctx.drawImage(img, 0, 0, c.width, c.height);
    return decodeImageData(ctx.getImageData(0, 0, c.width, c.height));
  } finally {
    URL.revokeObjectURL(url);
  }
}

// Camera scanner. onText(text) is called for every decoded QR; returns stop().
export async function startScanner(video, onText) {
  const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' }, audio: false });
  video.srcObject = stream;
  video.setAttribute('playsinline', '');
  try {
    await video.play();
  } catch (e) {
    stream.getTracks().forEach(tr => tr.stop()); // do not leave the camera on
    video.srcObject = null;
    throw e;
  }
  const c = document.createElement('canvas');
  const ctx = c.getContext('2d', { willReadFrequently: true });
  let running = true;
  const tick = () => {
    if (!running) return;
    if (video.readyState >= 2 && video.videoWidth) {
      const scale = Math.min(1, 640 / Math.max(video.videoWidth, video.videoHeight));
      c.width = Math.round(video.videoWidth * scale); c.height = Math.round(video.videoHeight * scale);
      ctx.drawImage(video, 0, 0, c.width, c.height);
      const text = decodeImageData(ctx.getImageData(0, 0, c.width, c.height));
      if (text) onText(text);
    }
    setTimeout(() => requestAnimationFrame(tick), 120);
  };
  tick();
  return () => { running = false; stream.getTracks().forEach(tr => tr.stop()); video.srcObject = null; };
}
