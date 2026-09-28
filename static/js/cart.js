function autoResizeNoteInput(input) {
  if (!input) return;
  const minHeight = 36;
  const maxHeight = Math.min(180, Math.round(window.innerHeight * 0.42));
  const noteValue = (input.value || "").trim();

  const noteShell = input.closest(".item-note-shell");
  if (noteShell && noteShell.classList.contains("is-collapsed")) {
    input.style.height = `${minHeight}px`;
    input.style.overflowY = "hidden";
    return;
  }

  if (!noteValue) {
    input.style.height = `${minHeight}px`;
    input.style.overflowY = "hidden";
    return;
  }

  input.style.height = "auto";
  const nextHeight = Math.max(minHeight, input.scrollHeight);
  input.style.height = `${Math.min(nextHeight, maxHeight)}px`;
  input.style.overflowY = nextHeight > maxHeight ? "auto" : "hidden";
}

function syncCompactCartNoteInput(input) {
  if (!input) return;
  const shell = input.closest(".item-note-shell");
  if (!shell) return;

  const hasValue = Boolean((input.value || "").trim());
  const isFocused = document.activeElement === input;

  shell.classList.toggle("has-value", hasValue);
  shell.classList.toggle("is-expanded", isFocused);
  shell.classList.toggle("is-collapsed", !isFocused);
}


const undoStorageKey = 'ceCartUndoV1';
const undoEntries = new Map();
const noteTimers = new Map();
const cartBody = document.getElementById('cartTableBody');
let totalQuantity = Number(document.getElementById('cartTotalQty').textContent);
function clampQty(value) { return Math.max(0, Math.min(999, parseInt(value, 10) || 0)); }
function rowCode(row) { return row.dataset.code || row.querySelector('.qty-control')?.dataset.code; }
function initializeRows() {
  for (const row of cartBody.querySelectorAll('tr:not(.is-removed)')) {
    row.dataset.code = rowCode(row);
    const input = row.querySelector('.item-note-input');
    input.dataset.savedNote = input.value.trim();
    syncCompactCartNoteInput(input);
    autoResizeNoteInput(input);
  }
}
function persistUndo() {
  try {
    sessionStorage.setItem(undoStorageKey, JSON.stringify([...undoEntries.values()].map(({id, token, expiresAt, kind}) => ({id, token, expiresAt, kind}))));
  } catch (_) { /* Undo still works on this page when storage is unavailable. */ }
}
function renderCartState() {
  const hasRows = cartBody.children.length > 0;
  document.getElementById('cartTableWrap').hidden = !hasRows;
  document.getElementById('cartEmptyState').hidden = hasRows;
  document.getElementById('cartIntroCard').hidden = !hasRows;
  document.getElementById('cartSummaryBar').hidden = totalQuantity === 0;
  const reels = document.getElementById('cartEmptyReelsSection');
  if (reels) reels.hidden = hasRows;
}
function updateTotals(data) {
  totalQuantity = data.total_items;
  const badge = document.getElementById('cartCountBadge');
  badge.textContent = data.total_items;
  badge.style.display = data.total_items > 0 ? 'inline-block' : 'none';
  document.getElementById('cartTotalQty').textContent = data.total_items;
  document.getElementById('cartLineItemCount').textContent = data.distinct_items;
  renderCartState();
}
function undoControl(entry, label, accessibleName) {
  const control = document.createElement('div');
  control.className = 'cart-undo-control';
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'btn btn-outline-gold cart-undo-btn';
  button.dataset.undoId = entry.id;
  button.textContent = label;
  button.setAttribute('aria-label', accessibleName);
  const timer = document.createElement('span');
  timer.className = 'cart-undo-timer';
  timer.dataset.undoId = entry.id;
  timer.setAttribute('aria-hidden', 'true');
  timer.innerHTML = '<svg viewBox="0 0 36 36" focusable="false"><circle class="cart-undo-ring-track" cx="18" cy="18" r="15"/><circle class="cart-undo-ring-progress" cx="18" cy="18" r="15" pathLength="100" stroke-dasharray="100" stroke-dashoffset="0"/></svg><span class="cart-undo-seconds">60s</span>';
  control.append(button, timer);
  return control;
}
function markRemoved(entry, rows) {
  for (const row of rows) {
    const code = rowCode(row);
    row.dataset.code = code;
    row.dataset.undoId = entry.id;
    const note = row.querySelector('.item-note-input');
    clearTimeout(noteTimers.get(note));
    noteTimers.delete(note);
    row.classList.add('is-removed');
    if (entry.kind === 'clear') {
      row.classList.add('is-clear-removal');
      row.inert = true;
    } else {
      row.classList.add('cart-undo-item');
      for (const cell of row.querySelectorAll('.cell-item, .cell-code')) cell.inert = true;
      for (const cell of row.querySelectorAll('.cell-qty, .cell-notes, .cell-remove')) cell.remove();
      const cell = document.createElement('td');
      cell.colSpan = 3;
      cell.className = 'cart-undo-cell';
      const message = document.createElement('span');
      message.className = 'cart-removed-label';
      message.textContent = 'Removed';
      const control = undoControl(entry, 'Undo', `Undo removal of ${code}`);
      control.prepend(message);
      cell.append(control);
      row.append(cell);
    }
  }
  if (entry.kind === 'clear' && rows.length) {
    const banner = document.createElement('div');
    banner.className = 'cart-undo-clear';
    banner.dataset.undoId = entry.id;
    const text = document.createElement('span');
    text.textContent = 'Order cleared';
    banner.append(text, undoControl(entry, 'Undo Clear', 'Undo clear order'));
    document.getElementById('cartUndoClear').append(banner);
  }
  tickUndo();
}
function rememberRemoval(data, rows, kind) {
  if (!data.undo_token) { rows.forEach(row => row.remove()); return; }
  const entry = {id: crypto.randomUUID(), token: data.undo_token, expiresAt: Date.now() + data.undo_seconds * 1000, kind};
  undoEntries.set(entry.id, entry);
  markRemoved(entry, rows);
  persistUndo();
  document.querySelector(`.cart-undo-btn[data-undo-id="${entry.id}"]`)?.focus({preventScroll: true});
}
function forgetUndo(entry, fade = false) {
  undoEntries.delete(entry.id);
  const nodes = [...document.querySelectorAll(`[data-undo-id="${entry.id}"]`)]
    .filter(node => node.matches('tr, .cart-undo-clear'));
  const finish = () => { nodes.forEach(node => node.remove()); renderCartState(); };
  if (fade) { nodes.forEach(node => node.classList.add('is-expiring')); setTimeout(finish, 240); }
  else finish();
  persistUndo();
}
function tickUndo() {
  for (const entry of undoEntries.values()) {
    const remaining = Math.max(0, entry.expiresAt - Date.now());
    const seconds = Math.ceil(remaining / 1000);
    if (!seconds && !entry.busy) { forgetUndo(entry, true); continue; }
    for (const timer of document.querySelectorAll(`.cart-undo-timer[data-undo-id="${entry.id}"]`)) {
      timer.querySelector('.cart-undo-seconds').textContent = `${seconds}s`;
      const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      const progress = Math.min(1, (reducedMotion ? seconds * 1000 : remaining) / 60000);
      timer.querySelector('.cart-undo-ring-progress').setAttribute('stroke-dashoffset', String(100 * (1 - progress)));
    }
  }
}
// The HTML is rendered by the same escaped Jinja row partial as the cart page.
function serverRows(html) {
  const table = document.createElement('table');
  table.innerHTML = `<tbody>${html}</tbody>`;
  return [...table.tBodies[0].rows];
}
async function restore(entry) {
  if (entry.busy) return;
  if (Date.now() >= entry.expiresAt) { forgetUndo(entry, true); return; }
  entry.busy = true;
  const restoredCode = [...cartBody.rows].find(row => row.dataset.undoId === entry.id)?.dataset.code;
  await CEOrder.run(async () => {
    const data = await CEOrder.post('/api/cart/undo', {token: entry.token});
    const fresh = new Map(serverRows(data.rows_html).map(row => [rowCode(row), row]));
    for (const oldRow of [...cartBody.rows]) {
      const code = rowCode(oldRow);
      if (fresh.has(code)) { oldRow.replaceWith(fresh.get(code)); fresh.delete(code); }
      else if (oldRow.dataset.undoId === entry.id || !oldRow.classList.contains('is-removed')) oldRow.remove();
    }
    for (const row of fresh.values()) cartBody.append(row);
    forgetUndo(entry);
    for (const other of [...undoEntries.values()]) {
      if (![...cartBody.rows].some(row => row.dataset.undoId === other.id)) forgetUndo(other);
    }
    initializeRows();
    updateTotals(data);
    const focusRow = [...cartBody.rows].find(row => rowCode(row) === restoredCode);
    (entry.kind === 'clear' ? document.getElementById('clearOrderBtn') : focusRow?.querySelector('.qty-remove'))?.focus({preventScroll: true});
  }, error => { if (error.status === 410 || error.status === 403) forgetUndo(entry, true); }, 'Order restored.');
  entry.busy = false;
  tickUndo();
}
function saveNote(input) {
  clearTimeout(noteTimers.get(input));
  noteTimers.delete(input);
  const note = input.value.trim().slice(0, 500);
  return CEOrder.run(async () => {
    if (!input.isConnected || input.closest('.is-removed') || note === input.dataset.savedNote) return;
    const data = await CEOrder.post('/api/cart/note', {code: input.dataset.code, note});
    input.dataset.savedNote = data.note;
  }, () => {}, 'Item note saved.');
}
CEOrder.flush = async () => {
  const results = await Promise.all([...document.querySelectorAll('tr:not(.is-removed) .item-note-input')]
    .filter(input => input.value.trim() !== input.dataset.savedNote).map(saveNote));
  return results.every(Boolean);
};
initializeRows();
renderCartState();
async function hydrateUndo() {
  let saved;
  try { saved = JSON.parse(sessionStorage.getItem(undoStorageKey) || '[]'); } catch (_) { saved = []; }
  if (!Array.isArray(saved)) return;
  for (const entry of saved) {
    if (!entry || !/^[a-z0-9-]+$/i.test(entry.id) || typeof entry.token !== 'string' || !['item', 'clear'].includes(entry.kind) || entry.expiresAt <= Date.now()) continue;
    undoEntries.set(entry.id, entry);
    await CEOrder.run(async () => {
      let data;
      try { data = await CEOrder.post('/api/cart/undo', {token: entry.token, preview: true}); }
      catch (error) {
        if ([400, 403, 410].includes(error.status)) { undoEntries.delete(entry.id); return; }
        throw error;
      }
      const rows = serverRows(data.rows_html);
      if (!rows.length) { undoEntries.delete(entry.id); return; }
      entry.expiresAt = Math.min(entry.expiresAt, Date.now() + data.undo_seconds * 1000);
      rows.forEach(row => cartBody.append(row));
      markRemoved(entry, rows);
      renderCartState();
    }, error => { if ([400, 403, 410].includes(error.status)) undoEntries.delete(entry.id); });
  }
  persistUndo();
}
hydrateUndo();
setInterval(tickUndo, 250);
document.addEventListener('visibilitychange', tickUndo);
document.addEventListener('click', async event => {
  const undo = event.target.closest('.cart-undo-btn');
  if (undo) { const entry = undoEntries.get(undo.dataset.undoId); if (entry) await restore(entry); return; }
  const clear = event.target.closest('#clearOrderBtn');
  if (clear) {
    if (!await CEOrder.flush()) return;
    await CEOrder.run(async () => {
      const rows = [...cartBody.querySelectorAll('tr:not(.is-removed)')];
      const data = await CEOrder.post('/api/cart/clear', {allow_undo: true});
      rememberRemoval(data, rows, 'clear');
      updateTotals(data);
    }, () => {}, 'Order cleared. Undo is available for 60 seconds.');
    return;
  }
  const remove = event.target.closest('.qty-remove');
  const adjust = event.target.closest('.qty-adjust-btn');
  if (!remove && !adjust) return;
  const row = event.target.closest('tr');
  if (row.classList.contains('is-removed')) return;
  const wrap = row.querySelector('.qty-control');
  const next = remove ? 0 : clampQty(Number(wrap.dataset.qty) + (adjust.classList.contains('qty-minus') ? -1 : 1));
  await changeQuantity(wrap, next);
});
async function changeQuantity(wrap, next) {
  const input = wrap.querySelector('.qty-input');
  const rollback = () => { input.value = wrap.dataset.qty; };
  if (next === 0 && !await CEOrder.flush()) { rollback(); return; }
  return CEOrder.run(async () => {
    const data = await CEOrder.post('/api/cart/set', {code: wrap.dataset.code, qty: next, allow_undo: next === 0});
    if (data.qty === 0) rememberRemoval(data, [wrap.closest('tr')], 'item');
    else { wrap.dataset.qty = String(data.qty); input.value = data.qty; }
    updateTotals(data);
  }, rollback, next === 0 ? 'Item removed. Undo is available for 60 seconds.' : 'Order updated.');
}
document.addEventListener('change', event => {
  const input = event.target.closest('.qty-input');
  if (input && !input.closest('.is-removed')) changeQuantity(input.closest('.qty-control'), clampQty(input.value));
});
document.addEventListener('input', event => {
  const input = event.target.closest('.item-note-input');
  if (!input || input.closest('.is-removed')) return;
  syncCompactCartNoteInput(input); autoResizeNoteInput(input);
  clearTimeout(noteTimers.get(input));
  noteTimers.set(input, setTimeout(() => saveNote(input), 350));
});
document.addEventListener('focusin', event => {
  const input = event.target.closest('.item-note-input');
  if (input) { syncCompactCartNoteInput(input); autoResizeNoteInput(input); }
});
document.addEventListener('blur', event => {
  const input = event.target.closest('.item-note-input');
  if (!input || input.closest('.is-removed')) return;
  syncCompactCartNoteInput(input); autoResizeNoteInput(input);
  if (input.value.trim() !== input.dataset.savedNote) saveNote(input);
}, true);
document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && event.target.matches('.item-note-input')) event.target.blur();
});
window.addEventListener('beforeunload', event => {
  const unsaved = [...document.querySelectorAll('tr:not(.is-removed) .item-note-input')]
    .some(input => input.value.trim() !== input.dataset.savedNote);
  if (unsaved) { event.preventDefault(); event.returnValue = ''; }
});
