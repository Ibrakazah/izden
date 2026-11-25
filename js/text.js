// Rendering of unit texts + evidence anchors. Sentence rule is shared with scripts/check.py:
// split a paragraph after . ! ? … followed by whitespace; numbering from 1.

// Written without regex lookbehind so that old Safari / Android WebView can parse the module.
export function splitSentences(text) {
  const s = String(text).trim();
  const out = [];
  let cur = '';
  for (let i = 0; i < s.length; i++) {
    const ch = s[i];
    if (/\s/.test(ch) && cur && /[.!?…]$/.test(cur)) {
      out.push(cur);
      cur = '';
      while (i + 1 < s.length && /\s/.test(s[i + 1])) i++;
      continue;
    }
    cur += ch;
  }
  if (cur) out.push(cur);
  return out;
}

export function esc(s) {
  return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

// Reading-order numbers for every evidence target (used on paper: "evidence No. 7").
export function evidenceNumbers(unit) {
  const m = new Map();
  let n = 0;
  for (const b of unit.blocks) {
    if (b.type === 'p') splitSentences(b.text).forEach((_, i) => m.set(`${b.id}:s${i + 1}`, ++n));
    else if (b.type === 'list') b.items.forEach((_, i) => m.set(`${b.id}:i${i + 1}`, ++n));
    else if (b.type === 'table') b.rows.slice(1).forEach((_, i) => m.set(`${b.id}:r${i + 1}`, ++n));
    else if (b.type === 'chart') b.rows.forEach((_, i) => m.set(`${b.id}:r${i + 1}`, ++n));
  }
  return m;
}

// Is the tapped target (e.g. "b2:r3") valid evidence for refs (e.g. ["b2:r3","b2:r4"] or ["b2"])?
export function evidenceMatches(tap, refs) {
  if (!tap) return false;
  return refs.some(r => r === tap || (!r.includes(':') && tap.split(':')[0] === r));
}

// Each evidence target gets data-ev="b2" / "b2:r3" / "b3:s2" / "b5:i1"; targets with ":" are tappable (.tap)
export function renderBlocks(unit, { compact = false, numbers = false } = {}) {
  const nums = numbers ? evidenceNumbers(unit) : null;
  const num = ref => (nums ? `<sup class="evn">${nums.get(ref)}</sup>` : '');
  const out = [];
  for (const b of unit.blocks) {
    if (b.type === 'h') {
      out.push(`<h3 class="blk-h" data-ev="${b.id}">${esc(b.text)}</h3>`);
    } else if (b.type === 'p') {
      const ss = splitSentences(b.text).map((s, i) => `<span class="sent tap" data-ev="${b.id}:s${i + 1}">${num(`${b.id}:s${i + 1}`)}${esc(s)}</span>`);
      out.push(`<p class="blk-p" data-ev="${b.id}">${ss.join(' ')}</p>`);
    } else if (b.type === 'list') {
      const li = b.items.map((s, i) => `<li class="tap" data-ev="${b.id}:i${i + 1}">${num(`${b.id}:i${i + 1}`)}${esc(s)}</li>`).join('');
      out.push(`<ul class="blk-list" data-ev="${b.id}">${li}</ul>`);
    } else if (b.type === 'table') {
      const [head, ...rows] = b.rows;
      const th = head.map(c => `<th scope="col">${esc(c)}</th>`).join('');
      const tr = rows.map((r, i) => `<tr class="tap" data-ev="${b.id}:r${i + 1}">${r.map((c, j) => `<td>${j === 0 ? num(`${b.id}:r${i + 1}`) : ''}${esc(c)}</td>`).join('')}</tr>`).join('');
      out.push(`<figure class="blk-table" data-ev="${b.id}">${b.caption ? `<figcaption>${esc(b.caption)}</figcaption>` : ''}`
        + `<div class="table-scroll" tabindex="0"><table><thead><tr>${th}</tr></thead><tbody>${tr}</tbody></table></div></figure>`);
    } else if (b.type === 'chart') {
      const max = Math.max(...b.rows.map(r => r[1]), 0) || 1;
      const bars = b.rows.map((r, i) => {
        const w = Math.max(0, (r[1] / max) * 100);
        return `<div class="bar-row tap" data-ev="${b.id}:r${i + 1}"><span class="bar-label">${num(`${b.id}:r${i + 1}`)}${esc(r[0])}</span>`
          + `<span class="bar-track"><span class="bar" style="width:${w.toFixed(1)}%"></span></span>`
          + `<span class="bar-val">${esc(fmtNum(r[1]))}</span></div>`;
      }).join('');
      out.push(`<figure class="blk-chart" data-ev="${b.id}"><figcaption>${esc(b.caption)}${b.unit ? ` <span class="unit">(${esc(b.unit)})</span>` : ''}</figcaption>`
        + `<div class="bars" role="img" aria-label="${esc(b.caption)}">${bars}</div></figure>`);
    }
  }
  const cls = `unit-text fmt-${unit.format}${compact ? ' compact' : ''}`;
  return `<article class="${cls}"><h2 class="unit-title">${esc(unit.title)}</h2>${out.join('')}</article>`;
}

function fmtNum(n) {
  return String(n).replace('.', ',');
}

export function clearEvidence(root) {
  root.querySelectorAll('.ev-on').forEach(el => el.classList.remove('ev-on'));
}

// For block-level refs ("b2") highlight the whole block.

// Highlight evidence; returns first highlighted element.
export function showEvidence(root, refs) {
  clearEvidence(root);
  let first = null;
  for (const ref of refs) {
    const el = root.querySelector(`[data-ev="${CSS.escape(ref)}"]`);
    if (el) {
      el.classList.add('ev-on');
      if (!first) first = el;
    }
  }
  return first;
}
