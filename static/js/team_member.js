(() => {
  'use strict';
  const shareButton = document.getElementById('shareCard');
  const fallback = document.getElementById('shareFallback');
  const linkInput = document.getElementById('shareLink');
  const copyButton = document.getElementById('copyCardLink');
  const status = document.getElementById('shareStatus');
  if (shareButton && fallback && linkInput && copyButton && status) {
    shareButton.hidden = false;
    const url = document.querySelector('link[rel="canonical"]')?.href || window.location.href;
    linkInput.value = url;
    const revealFallback = () => {
      fallback.hidden = false;
      linkInput.focus();
      linkInput.select();
    };
    shareButton.addEventListener('click', async () => {
      status.textContent = '';
      if (typeof navigator.share !== 'function') {
        revealFallback();
        return;
      }
      shareButton.disabled = true;
      try {
        await navigator.share({ title: shareButton.dataset.shareTitle, text: shareButton.dataset.shareText, url });
      } catch (error) {
        // Dismissing the system share sheet is an intentional cancellation.
        if (error.name !== 'AbortError') revealFallback();
      } finally {
        shareButton.disabled = false;
      }
    });
    copyButton.addEventListener('click', async () => {
      try {
        if (!navigator.clipboard?.writeText) throw new Error('Clipboard unavailable');
        await navigator.clipboard.writeText(url);
        status.textContent = 'Card link copied.';
      } catch (_) {
        linkInput.focus();
        linkInput.select();
        status.textContent = 'Select and copy the link above to share this card.';
      }
    });
  }

  const qr = document.getElementById('contactQr');
  if (qr) {
    const desktop = window.matchMedia('(min-width: 768px)');
    const summary = qr.querySelector('summary');
    const syncQr = () => {
      qr.open = desktop.matches;
      // The desktop QR is always visible; only mobile needs a disclosure control.
      summary.tabIndex = desktop.matches ? -1 : 0;
      if (desktop.matches) summary.setAttribute('aria-disabled', 'true');
      else summary.removeAttribute('aria-disabled');
    };
    summary.addEventListener('click', (event) => {
      if (desktop.matches) event.preventDefault();
    });
    desktop.addEventListener('change', syncQr);
    syncQr();
  }
})();
