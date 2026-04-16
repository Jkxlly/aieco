// ── Prompt page token counter ─────────────────────────
const promptArea = document.getElementById('p-text');
const tokenEl    = document.getElementById('p-tokCount');
const tokenBar   = document.getElementById('p-tokBar');
const tokenCtx   = document.getElementById('p-tokCtx');
const modelSel   = document.getElementById('p-model');

if (promptArea) {
  promptArea.addEventListener('input', updateTokens);
  if (modelSel) modelSel.addEventListener('change', updateTokens);
}

function updateTokens() {
  const text  = promptArea ? promptArea.value.trim() : '';
  const words = text ? text.split(/\s+/).length : 0;
  const toks  = Math.round(words * 1.33);
  if (tokenEl) tokenEl.textContent = toks.toLocaleString();
  // Get context window from selected model option
  if (modelSel && tokenBar && tokenCtx) {
    const ctx = parseInt(modelSel.options[modelSel.selectedIndex]?.dataset?.ctx || 128000);
    const pct = Math.min(100, (toks / ctx) * 100);
    tokenBar.style.width = pct + '%';
    tokenBar.style.background = pct > 80 ? '#f07070' : pct > 50 ? '#e3a043' : '#3fb884';
    tokenCtx.textContent = toks.toLocaleString() + ' / ' + (ctx >= 1e6 ? ctx/1e6+'M' : ctx/1e3+'k');
  }
}

// ── Auto-dismiss alerts ───────────────────────────────
document.querySelectorAll('.msg-banner').forEach(el => {
  setTimeout(() => { if (el.parentNode) el.remove(); }, 4000);
});
