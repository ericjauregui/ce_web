(() => {
  const drawer = document.getElementById('cartDrawer');
  if (!drawer || !window.bootstrap || !window.CECart) return;
  const overlay = bootstrap.Offcanvas.getOrCreateInstance(drawer);
  const body = drawer.querySelector('.cart-drawer__body');
  const loading = drawer.querySelector('.cart-drawer__loading');
  const retry = drawer.querySelector('[data-cart-drawer-retry]');
  const triggers = [...document.querySelectorAll('[data-cart-drawer-open]')];
  let opener;
  let loadingOrder = false;
  let closing = false;
  let allowClose = false;
  let scrollPosition;
  let background = [];

  function lockBackground() {
    let current = drawer;
    background = [];
    while (current.parentElement && current !== document.body) {
      for (const sibling of current.parentElement.children) {
        if (sibling === current || sibling.matches('script, style, #orderStatus, #orderFeedback, .offcanvas-backdrop')) continue;
        background.push({element: sibling, inert: sibling.inert});
        sibling.inert = true;
      }
      current = current.parentElement;
    }
  }

  async function loadOrder() {
    if (loadingOrder) return;
    loadingOrder = true;
    body.hidden = true;
    loading.hidden = false;
    loading.querySelector('span').hidden = false;
    retry.hidden = true;
    drawer.setAttribute('aria-busy', 'true');
    const loaded = await CECart.refresh();
    loadingOrder = false;
    drawer.removeAttribute('aria-busy');
    body.hidden = !loaded;
    loading.hidden = loaded;
    if (!loaded) {
      loading.querySelector('span').hidden = true;
      retry.hidden = false;
      if (drawer.classList.contains('show')) retry.focus();
    }
  }

  triggers.forEach(trigger => trigger.addEventListener('click', () => {
    opener = trigger;
    overlay.show(trigger);
  }));
  retry.addEventListener('click', loadOrder);
  drawer.addEventListener('keydown', event => {
    if (event.key !== 'Tab') return;
    const controls = [...drawer.querySelectorAll('a[href], button:not(:disabled), input:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])')]
      .filter(element => !element.closest('[inert]') && element.getClientRects().length > 0);
    const first = controls[0];
    const last = controls[controls.length - 1];
    if (event.shiftKey && (document.activeElement === first || document.activeElement === drawer)) {
      event.preventDefault();
      last?.focus({preventScroll: true});
    } else if (!event.shiftKey && (document.activeElement === last || document.activeElement === drawer)) {
      event.preventDefault();
      first?.focus({preventScroll: true});
    }
  });
  drawer.addEventListener('show.bs.offcanvas', () => {
    scrollPosition = {top: window.scrollY, left: window.scrollX, behavior: 'instant'};
    lockBackground();
    document.body.classList.add('has-cart-drawer');
    triggers.forEach(trigger => trigger.setAttribute('aria-expanded', 'true'));
    loadOrder();
  });
  // A close also saves notes and waits for queued quantity writes.
  drawer.addEventListener('hide.bs.offcanvas', event => {
    if (allowClose) return;
    event.preventDefault();
    if (closing) return;
    closing = true;
    (async () => {
      const flushed = await CEOrder.flush();
      await CEOrder.whenIdle();
      if (flushed) {
        allowClose = true;
        overlay.hide();
      }
      closing = false;
    })();
  });
  drawer.addEventListener('hidden.bs.offcanvas', () => {
    allowClose = false;
    document.body.classList.remove('has-cart-drawer');
    background.forEach(({element, inert}) => { element.inert = inert; });
    background = [];
    window.scrollTo(scrollPosition);
    triggers.forEach(trigger => trigger.setAttribute('aria-expanded', 'false'));
    if (opener && !opener.closest('[hidden]')) opener.focus({preventScroll: true});
    else document.getElementById('cartLink')?.focus({preventScroll: true});
  });
})();
