async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload || {}),
  });
  return response.json();
}

function clampQty(qty) {
  return Math.max(0, Math.min(999, Number(qty) || 0));
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
  const response = await postJson("/api/cart/set", { code, qty: safeQty });

  updateCartBadge(response.total_items || 0);
  setDetailQty(card, safeQty);
}

document.addEventListener("DOMContentLoaded", async () => {
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

  try {
    const countData = await fetch("/api/cart/count").then((r) => r.json());
    updateCartBadge(countData.total_items || 0);
  } catch (_err) {}

  document.addEventListener("click", async (event) => {
    const addButton = event.target.closest(".add-to-cart-btn");
    if (!addButton || addButton.getAttribute("data-code") !== code) return;

    event.preventDefault();

    const currentQty = clampQty(card.dataset.qty || 0);
    const nextQty = currentQty + 1;
    const response = await postJson("/api/cart/add", { code, qty: 1 });
    updateCartBadge(response.total_items || 0);
    setDetailQty(card, nextQty);
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
    await setQtyOnServer(card, qtyInput.value);
    qtyInput.blur();
  });
});
