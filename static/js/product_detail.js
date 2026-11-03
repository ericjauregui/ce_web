function clampQty(qty) {
  return Math.max(0, Math.min(999, Math.trunc(Number(qty) || 0)));
}

function updateCartBadge(totalItems) {
  const badge = document.getElementById("cartCountBadge");
  if (!badge) return;
  badge.textContent = totalItems || 0;
  badge.style.display = (totalItems || 0) > 0 ? "inline-block" : "none";
}

function setAddButtonLabels(code, qty) {
  const buttons = document.querySelectorAll(
    `.add-to-cart-btn[data-code="${code}"]`,
  );
  if (!buttons.length) return;

  let label = "Add to Order";
  if (qty > 0) {
    const noun = qty === 1 ? "item" : "items";
    label = `${qty} ${noun} in order`;
  }

  buttons.forEach((button) => {
    button.textContent = label;
  });
}

function setDetailQty(card, qty) {
  const safeQty = clampQty(qty);
  const control = card.querySelector(".product-qty-control");
  const input = card.querySelector(".product-qty-input");
  if (!control || !input) return;

  card.dataset.qty = String(safeQty);
  control.classList.toggle("d-none", safeQty <= 0);
  input.value = String(safeQty > 0 ? safeQty : 1);
  const code = card.getAttribute("data-code") || "";
  if (code) {
    setAddButtonLabels(code, safeQty);
  }
}

async function setQtyOnServer(card, nextQty) {
  const code = card.getAttribute("data-code");
  if (!code) return;

  const safeQty = clampQty(nextQty);
  const restore = () => setDetailQty(card, card.dataset.qty || 0);
  return CEOrder.run(async () => {
    const response = await CEOrder.post("/api/cart/set", {code, qty: safeQty});
    updateCartBadge(response.total_items);
    setDetailQty(card, response.qty);
  }, restore);

}

document.addEventListener("DOMContentLoaded", () => {
  const card = document.querySelector(".product-detail-meta-card[data-code]");
  if (!card) return;

  const code = card.getAttribute("data-code");
  if (!code) return;

  const initialQty = clampQty(card.getAttribute("data-initial-qty") || 0);
  setDetailQty(card, initialQty);

  const shareButton = document.querySelector(
    ".product-share-btn[data-share-url]",
  );
  if (shareButton) {
    shareButton.addEventListener("click", async () => {
      const shareUrl =
        shareButton.getAttribute("data-share-url") || window.location.href;
      const shareTitle =
        shareButton.getAttribute("data-share-title") || document.title;

      if (navigator.share) {
        try {
          await navigator.share({ title: shareTitle, url: shareUrl });
          return;
        } catch (error) {
          if (
            error &&
            (error.name === "AbortError" || error.name === "NotAllowedError")
          ) {
            return;
          }
        }
      }

      if (navigator.clipboard && navigator.clipboard.writeText) {
        try {
          await navigator.clipboard.writeText(shareUrl);
          const originalLabel = shareButton.textContent;
          shareButton.textContent = "Link copied";
          window.setTimeout(() => {
            shareButton.textContent = originalLabel || "Share";
          }, 1300);
          return;
        } catch (_err) {}
      }

      window.prompt("Copy this product link", shareUrl);
    });
  }

  document.addEventListener("click", async (event) => {
    const addButton = event.target.closest(".add-to-cart-btn");
    if (!addButton || addButton.getAttribute("data-code") !== code) return;

    event.preventDefault();

    await CEOrder.run(async () => {
      const response = await CEOrder.post("/api/cart/add", {code, qty: 1});
      updateCartBadge(response.total_items);
      setDetailQty(card, response.qty);
    });
  });

  document.addEventListener("click", async (event) => {
    const adjustButton = event.target.closest(".qty-adjust-btn");
    if (!adjustButton || !card.contains(adjustButton)) return;

    event.preventDefault();

    const delta = Number(adjustButton.getAttribute("data-delta") || 0);
    const currentQty = clampQty(card.dataset.qty || 0);
    await setQtyOnServer(card, currentQty + delta);
  });

  document.addEventListener("click", async (event) => {
    const clearButton = event.target.closest(".qty-clear-btn");
    if (!clearButton || !card.contains(clearButton)) return;

    event.preventDefault();
    await setQtyOnServer(card, 0);
  });

  document.addEventListener("change", async (event) => {
    const qtyInput = event.target.closest(".product-qty-input");
    if (!qtyInput || !card.contains(qtyInput)) return;

    await setQtyOnServer(card, qtyInput.value);
  });

  document.addEventListener("keydown", async (event) => {
    const qtyInput = event.target.closest(".product-qty-input");
    if (!qtyInput || !card.contains(qtyInput) || event.key !== "Enter") return;

    event.preventDefault();
    qtyInput.blur();
  });
});

// The existing original image is reused only when opened; no second eager download.
document.addEventListener('DOMContentLoaded', () => {
  const trigger = document.querySelector('.product-image-open');
  const dialog = document.getElementById('productImageDialog');
  if (!trigger || !dialog || typeof dialog.showModal !== 'function') return;
  const viewport = dialog.querySelector('.product-image-viewport');
  const image = viewport.querySelector('img');
  const zoomIn = dialog.querySelector('[data-image-zoom="in"]');
  const zoomOut = dialog.querySelector('[data-image-zoom="out"]');
  const fit = dialog.querySelector('[data-image-fit]');
  const status = dialog.querySelector('[data-image-status]');
  let scale = 1;
  let drag = null;

  function render(reset = false) {
    if (!dialog.open || !image.naturalWidth) return;
    const oldWidth = image.width || 1;
    // A fitted image may be smaller than its viewport; preserve its center,
    // not the whitespace around it, when crossing into scrollable zoom.
    const centerX = oldWidth <= viewport.clientWidth ? .5 : (viewport.scrollLeft + viewport.clientWidth / 2) / oldWidth;
    const centerY = image.height <= viewport.clientHeight ? .5 : (viewport.scrollTop + viewport.clientHeight / 2) / (image.height || 1);
    const fitWidth = Math.min(viewport.clientWidth, viewport.clientHeight * image.naturalWidth / image.naturalHeight);
    image.style.width = `${fitWidth * scale}px`;
    image.style.height = `${fitWidth * scale * image.naturalHeight / image.naturalWidth}px`;
    viewport.scrollLeft = reset ? 0 : centerX * image.width - viewport.clientWidth / 2;
    viewport.scrollTop = reset ? 0 : centerY * image.height - viewport.clientHeight / 2;
    zoomIn.disabled = scale >= 4;
    zoomOut.disabled = scale <= 1;
    fit.disabled = false;
    viewport.classList.toggle('is-zoomed', scale > 1);
    status.textContent = `${Math.round(scale * 100)}%`;
  }
  function zoom(delta) {
    scale = Math.max(1, Math.min(4, scale + delta));
    render(scale === 1);
  }
  trigger.addEventListener('click', (event) => {
    event.preventDefault();
    if (dialog.open) return;
    scale = 1;
    dialog.showModal();
    if (!image.getAttribute('src') || (image.complete && !image.naturalWidth)) {
      status.textContent = 'Loading image…';
      image.src = trigger.href;
    }
    render(true);
  });
  image.addEventListener('load', () => render(true));
  image.addEventListener('error', () => { status.textContent = 'Image unavailable. Close and try again.'; });
  dialog.querySelector('[data-image-close]').addEventListener('click', () => dialog.close());
  dialog.addEventListener('close', () => {
    drag = null;
    viewport.classList.remove('is-dragging');
    trigger.focus({preventScroll: true});
  });
  dialog.addEventListener('click', (event) => {
    if (event.target !== dialog) return;
    const bounds = dialog.getBoundingClientRect();
    if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) dialog.close();
  });
  zoomIn.addEventListener('click', () => zoom(.5));
  zoomOut.addEventListener('click', () => zoom(-.5));
  fit.addEventListener('click', () => { scale = 1; render(true); });
  dialog.addEventListener('keydown', (event) => {
    if (event.key === '+' || event.key === '=') { event.preventDefault(); zoom(.5); }
    if (event.key === '-') { event.preventDefault(); zoom(-.5); }
  });
  viewport.addEventListener('dblclick', () => { scale = scale === 1 ? 2 : 1; render(scale === 1); });
  viewport.addEventListener('pointerdown', (event) => {
    if (event.pointerType !== 'mouse' || event.button !== 0 || scale <= 1) return;
    drag = {id: event.pointerId, x: event.clientX, y: event.clientY, left: viewport.scrollLeft, top: viewport.scrollTop};
    viewport.setPointerCapture(event.pointerId);
    viewport.classList.add('is-dragging');
    event.preventDefault();
  });
  viewport.addEventListener('pointermove', (event) => {
    if (!drag || drag.id !== event.pointerId) return;
    viewport.scrollLeft = drag.left - (event.clientX - drag.x);
    viewport.scrollTop = drag.top - (event.clientY - drag.y);
  });
  function endDrag() { drag = null; viewport.classList.remove('is-dragging'); }
  viewport.addEventListener('pointerup', endDrag);
  viewport.addEventListener('pointercancel', endDrag);
  viewport.addEventListener('lostpointercapture', endDrag);
  window.addEventListener('resize', () => render());
});
