/* Serialize cart writes: Flask stores the cart in the session cookie. */
(() => {
  let queue = Promise.resolve(true);
  let pending = 0;
  let locked = [];
  const feedback = () => (document.body.classList.contains('has-cart-drawer') && document.querySelector('#cartDrawer [data-order-feedback]')) || document.getElementById('orderFeedback');
  function showError(message) {
    const element = feedback();
    if (element) { element.hidden = false; element.textContent = message; }
  }
  function lock() {
    locked = [...document.querySelectorAll('.add-to-cart-btn, .qty-adjust-btn, .qty-clear-btn, .qty-remove, .cart-undo-btn, #clearOrderBtn, .product-qty-input')]
      .filter(element => !element.closest('[inert]'))
      .map(element => ({element, disabled: element.disabled, readOnly: element.readOnly}));
    locked.forEach(({element}) => {
      if (element.tagName === 'INPUT') element.readOnly = true;
      else element.disabled = true;
    });
  }
  async function post(url, payload) {
    let response;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    try {
      response = await fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload || {}), signal: controller.signal});
    } catch (_) {
      throw new Error('We couldn’t confirm your update. Check your connection and review your order before trying again.');
    } finally {
      clearTimeout(timeout);
    }
    if (!response.ok) {
      const error = new Error(response.status === 410
        ? 'The 30-second Undo window has ended.'
        : response.status === 429
        ? 'Please wait a moment, then try again. Your update was not saved.'
        : 'We couldn’t save your update. Please try again.');
      error.status = response.status;
      throw error;
    }
    let data;
    try { data = await response.json(); } catch (_) {
      throw new Error('We couldn’t confirm your update. Review your order before trying again.');
    }
    if (!data || data.ok !== true) throw new Error('We couldn’t save your update. Please try again.');
    const valid = url.endsWith('/note')
      ? typeof data.note === 'string'
      : Number.isInteger(data.total_items) && Number.isInteger(data.distinct_items) &&
        (!/\/(add|set)$/.test(url) || Number.isInteger(data.qty));
    if (!valid) throw new Error('We couldn’t confirm your update. Review your order before trying again.');
    if (url.endsWith('/undo') && (typeof data.rows_html !== 'string' || !Number.isFinite(data.undo_seconds))) {
      throw new Error('We couldn’t confirm your update. Review your order before trying again.');
    }
    return data;
  }
  function run(action, rollback = () => {}, message = 'Order updated.') {
    if (pending++ === 0) {
      lock();
      const status = document.getElementById('orderStatus');
      if (status) status.textContent = 'Saving changes…';
    }
    const result = queue.then(async () => {
      try {
        await action();
        if (feedback()) feedback().hidden = true;
        const status = document.getElementById('orderStatus');
        if (status) status.textContent = message;
        return true;
      } catch (error) {
        rollback(error);
        showError(error.message || 'We couldn’t save your update. Please try again.');
        return false;
      } finally {
        if (--pending === 0) {
          locked.forEach(({element, disabled, readOnly}) => {
            element.disabled = disabled || Boolean(element.closest('tr[inert]'));
            if (element.tagName === 'INPUT') element.readOnly = readOnly;
          });
          locked = [];
        }
      }
    });
    queue = result;
    return result;
  }
  document.addEventListener('click', async event => {
    const link = event.target.closest('a[href]');
    if ((!pending && !window.CEOrder.flush) || !link || event.ctrlKey || event.metaKey || link.target === '_blank') return;
    if (link.origin !== location.origin || (link.pathname === location.pathname && link.search === location.search && link.hash)) return;
    event.preventDefault();
    const wasPending = pending > 0;
    const flushed = window.CEOrder.flush ? await window.CEOrder.flush() : true;
    const saved = await queue;
    if (flushed && (!wasPending || saved)) location.assign(link.href);
  }, true);
  window.CEOrder = {post, run, showError, whenIdle: () => queue};
})();
