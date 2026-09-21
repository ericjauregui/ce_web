(() => {
  // Native lazy loading can fetch several screens ahead, competing with the hero.
  // Keep the complete catalog and full-quality candidates; bound the look-ahead.
  const images = document.querySelectorAll('img[data-catalog-src]');
  function load(image) {
    if (!image.dataset.catalogSrc) return;
    if (image.dataset.catalogSrcset) {
      image.srcset = image.dataset.catalogSrcset;
      delete image.dataset.catalogSrcset;
    }
    image.src = image.dataset.catalogSrc;
    delete image.dataset.catalogSrc;
  }
  const preload = Array.from(document.querySelectorAll('link[rel="preload"][as="image"]'))
    .find(link => link.href.includes('hero_bg') && (!link.media || matchMedia(link.media).matches));
  window.catalogHeroReady = new Promise(resolve => {
    if (!preload) return resolve();
    const hero = new Image();
    hero.fetchPriority = 'high';
    hero.onload = hero.onerror = resolve;
    hero.src = preload.href; // Reuses the existing preload, including in-flight requests.
  });
  if (!('IntersectionObserver' in window)) {
    images.forEach(load);
    return;
  }
  let observer;
  function observe(margin) {
    if (observer) observer.disconnect();
    observer = new IntersectionObserver(entries => {
      entries.forEach(({ target, isIntersecting }) => {
        if (!isIntersecting) return;
        load(target);
        observer.unobserve(target);
      });
    }, { rootMargin: margin });
    images.forEach(image => {
      if (image.dataset.catalogSrc) observer.observe(image);
    });
  }
  // Visible images always load, including early scrolling and direct category links.
  observe('0px');
  let aheadEnabled = false;
  function enableLookAhead() {
    if (aheadEnabled) return;
    aheadEnabled = true;
    observe('400px 0px');
    window.removeEventListener('scroll', enableLookAhead);
  }
  // Browsing intent takes precedence over an unfinished hero download.
  window.addEventListener('scroll', enableLookAhead, { passive: true });
  document.addEventListener('click', event => {
    const link = event.target.closest('a[href]');
    if (!link) return;
    const url = new URL(link.href, location.href);
    if (url.origin !== location.origin || url.pathname !== location.pathname || !url.hash) return;
    let target;
    try { target = document.getElementById(decodeURIComponent(url.hash.slice(1))); }
    catch (_) { return; }
    if (!target) return;
    enableLookAhead();
    // Prepare the first two mobile rows while the existing anchor scroll runs.
    Array.from(target.querySelectorAll('img[data-catalog-src]')).slice(0, 4).forEach(load);
  });
  window.catalogHeroReady.then(enableLookAhead);
})();
