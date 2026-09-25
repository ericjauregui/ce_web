(() => {
  const page = document.querySelector('.connect-page');
  if (!page) return;

  const tradeShowKey = page.dataset.tradeShow || '';

  function track(action) {
    const body = JSON.stringify({ action, trade_show_key: tradeShowKey });
    const endpoint = '/api/connect/event';
    try {
      if (navigator.sendBeacon && navigator.sendBeacon(
        endpoint, new Blob([body], { type: 'application/json' })
      )) return;
    } catch (_) { /* The contact action should proceed even if tracking fails. */ }
    fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body,
      keepalive: true,
      credentials: 'omit',
    }).catch(() => {});
  }

  const navToggle = document.querySelector('.navbar-toggler[data-bs-target="#nav"]');
  const nav = document.querySelector('#nav');
  if (navToggle && nav) {
    function setNavigationOpen(open) {
      nav.classList.toggle('show', open);
      navToggle.setAttribute('aria-expanded', String(open));
    }
    navToggle.addEventListener('click', () => setNavigationOpen(!nav.classList.contains('show')));
    nav.addEventListener('click', event => {
      if (event.target.closest('a')) setNavigationOpen(false);
    });
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && nav.classList.contains('show')) {
        setNavigationOpen(false);
        navToggle.focus();
      }
    });
  }

  track('visit');
  page.querySelectorAll('[data-destination]').forEach(link => {
    link.addEventListener('click', () => track(link.dataset.destination));
  });
})();
