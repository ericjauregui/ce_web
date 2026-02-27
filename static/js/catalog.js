async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload || {}),
  });
  return response.json();
}

const CARD_INTERACTIVE_SELECTOR = ".add-to-cart-btn, .product-qty-control, .product-qty-input, .product-detail-link";

function isCardInteractiveTarget(target) {
  return !!target.closest(CARD_INTERACTIVE_SELECTOR);
}

function updateCartBadge(totalItems) {
  const badge = document.getElementById("cartCountBadge");
  if (!badge) return;
  badge.textContent = totalItems || 0;
  badge.style.display = (totalItems || 0) > 0 ? "inline-block" : "none";
}

function setAddButtonLabel(card, cardQty) {
  const button = card.querySelector(".add-to-cart-btn");
  if (!button) return;
  if ((cardQty || 0) <= 0) {
    button.textContent = "Add to Order";
    return;
  }
  const noun = cardQty === 1 ? "item" : "items";
  button.textContent = `${cardQty} ${noun} in order`;
}

function setCardQty(card, qty) {
  const control = card.querySelector(".product-qty-control");
  const input = card.querySelector(".product-qty-input");
  if (!control || !input) return;

  const safeQty = Math.max(0, Math.min(999, Number(qty) || 0));
  card.dataset.qty = String(safeQty);
  input.value = String(safeQty);
  control.classList.toggle("d-none", safeQty <= 0);
  card.classList.toggle("is-in-cart", safeQty > 0);
}

function syncDrawerHeight(card) {
  const drawer = card.querySelector(".product-drawer");
  if (!drawer) return;
  card.style.setProperty("--drawer-height", `${drawer.scrollHeight}px`);
}

function setCardExpanded(card, expanded) {
  const drawer = card.querySelector(".product-drawer");
  if (!drawer) return;

  syncDrawerHeight(card);
  card.classList.toggle("is-open", expanded);
  card.setAttribute("aria-expanded", expanded ? "true" : "false");
  drawer.setAttribute("aria-hidden", expanded ? "false" : "true");
}

function scrollToCatalogStart() {
  const firstAnchor = document.querySelector(".section-anchor");
  if (!firstAnchor) return;

  const styles = getComputedStyle(document.documentElement);
  const navActual = parseFloat(styles.getPropertyValue("--nav-actual-height")) || 0;
  const navFallback = parseFloat(styles.getPropertyValue("--nav-height")) || 50;
  const topOffset = navActual || navFallback;
  const targetTop = Math.max(0, firstAnchor.getBoundingClientRect().top + window.scrollY - topOffset);

  window.scrollTo({ top: targetTop, behavior: "smooth" });

  window.setTimeout(() => {
    const remaining = Math.abs(window.scrollY - targetTop);
    if (remaining > 24) {
      window.scrollTo({ top: targetTop, behavior: "auto" });
    }
  }, 420);
}

function scrollSectionToTop(target, behavior = "smooth", updateHash = false) {
  if (!target) return;

  const styles = getComputedStyle(document.documentElement);
  const navActual = parseFloat(styles.getPropertyValue("--nav-actual-height")) || 0;
  const navFallback = parseFloat(styles.getPropertyValue("--nav-height")) || 50;
  const topOffset = navActual || navFallback;
  const targetTop = Math.max(0, target.getBoundingClientRect().top + window.scrollY - topOffset);

  window.scrollTo({ top: targetTop, behavior });

  if (updateHash && target.id) {
    window.history.replaceState(null, "", `#${target.id}`);
  }

  window.setTimeout(() => {
    const remaining = Math.abs(window.scrollY - targetTop);
    if (remaining > 24) {
      window.scrollTo({ top: targetTop, behavior: "auto" });
    }
  }, 420);
}

function isReloadNavigation() {
  const navigationEntry = performance.getEntriesByType("navigation")[0];
  if (navigationEntry && navigationEntry.type) {
    return navigationEntry.type === "reload";
  }

  if (performance.navigation) {
    return performance.navigation.type === 1;
  }

  return false;
}

async function setCardQtyOnServer(card, nextQty) {
  const code =
    card.querySelector(".product-qty-control")?.getAttribute("data-code") ||
    card.querySelector(".add-to-cart-btn")?.getAttribute("data-code");
  if (!code) return;

  const response = await postJson("/api/cart/set", { code, qty: nextQty });
  const safeQty = Math.max(0, Math.min(999, Number(nextQty) || 0));

  updateCartBadge(response.total_items || 0);
  setCardQty(card, safeQty);
  setAddButtonLabel(card, safeQty);

  if (safeQty <= 0) {
    setCardExpanded(card, false);
  }
}

document.addEventListener("click", (event) => {
  const card = event.target.closest(".product-card");
  if (!card) return;
  if (card.dataset.longPressFired === "true") {
    card.dataset.longPressFired = "false";
    event.preventDefault();
    return;
  }
  if (isCardInteractiveTarget(event.target)) return;
  setCardExpanded(card, !card.classList.contains("is-open"));
});

document.addEventListener("keydown", (event) => {
  const card = event.target.closest(".product-card");
  if (!card) return;
  if (event.key !== "Enter" && event.key !== " ") return;
  if (isCardInteractiveTarget(event.target)) return;
  event.preventDefault();
  setCardExpanded(card, !card.classList.contains("is-open"));
});

const LONG_PRESS_MS = 520;
const LONG_PRESS_MOVE_TOLERANCE = 12;
let longPressTimerId = 0;
let longPressCard = null;
let longPressPointerId = null;
let longPressStartX = 0;
let longPressStartY = 0;

function clearLongPressState() {
  if (longPressTimerId) {
    window.clearTimeout(longPressTimerId);
    longPressTimerId = 0;
  }
  longPressCard = null;
  longPressPointerId = null;
}

document.addEventListener("pointerdown", (event) => {
  const card = event.target.closest(".product-card");
  if (!card) return;
  if (event.pointerType === "mouse") return;
  if (!card.classList.contains("is-open")) return;
  if (isCardInteractiveTarget(event.target)) return;

  const detailUrl = card.getAttribute("data-detail-url");
  if (!detailUrl) return;

  clearLongPressState();
  longPressCard = card;
  longPressPointerId = event.pointerId;
  longPressStartX = event.clientX;
  longPressStartY = event.clientY;

  longPressTimerId = window.setTimeout(() => {
    if (!longPressCard) return;
    longPressCard.dataset.longPressFired = "true";
    window.location.assign(detailUrl);
  }, LONG_PRESS_MS);
});

document.addEventListener("pointermove", (event) => {
  if (!longPressCard || longPressPointerId !== event.pointerId) return;
  const deltaX = Math.abs(event.clientX - longPressStartX);
  const deltaY = Math.abs(event.clientY - longPressStartY);
  if (deltaX > LONG_PRESS_MOVE_TOLERANCE || deltaY > LONG_PRESS_MOVE_TOLERANCE) {
    clearLongPressState();
  }
});

document.addEventListener("pointerup", clearLongPressState);
document.addEventListener("pointercancel", clearLongPressState);
window.addEventListener("scroll", clearLongPressState, { passive: true });

let resizeRafId = 0;

window.addEventListener("resize", () => {
  if (resizeRafId) return;
  resizeRafId = window.requestAnimationFrame(() => {
    resizeRafId = 0;
    document.querySelectorAll(".product-card.is-open").forEach(syncDrawerHeight);
  });
}, { passive: true });

function initializeCatalogCards(root = document) {
  root.querySelectorAll(".product-card").forEach((card) => {
    syncDrawerHeight(card);
    setCardExpanded(card, false);
    setCardQty(card, 0);
    setAddButtonLabel(card, 0);
  });
}

document.addEventListener("DOMContentLoaded", () => {
  initializeCatalogCards();

  const currentPath = window.location.pathname;
  const hash = (window.location.hash || "").trim();
  const params = new URLSearchParams(window.location.search);
  const query = (params.get("q") || "").trim();
  const shouldResetToLanding =
    currentPath === "/" &&
    isReloadNavigation() &&
    (query !== "" || hash.startsWith("#section-"));

  if (shouldResetToLanding) {
    window.history.replaceState(null, "", currentPath);
    window.scrollTo({ top: 0, behavior: "auto" });
    return;
  }

  if (query) {
    window.requestAnimationFrame(() => {
      scrollToCatalogStart();
    });
    return;
  }

  if (hash.startsWith("#section-")) {
    const target = document.querySelector(hash);
    if (!target) return;
    window.requestAnimationFrame(() => {
      scrollSectionToTop(target, "auto", false);
    });
  }
});

document.addEventListener("ce:content-replaced", () => {
  initializeCatalogCards();
});

document.addEventListener("click", async (event) => {
  const button = event.target.closest(".add-to-cart-btn");
  if (!button) return;

  event.preventDefault();
  event.stopPropagation();

  const card = button.closest(".product-card");
  if (!card) return;

  const code = button.getAttribute("data-code");
  const currentQty = Number(card.dataset.qty || 0);
  const nextQty = currentQty + 1;
  const response = await postJson("/api/cart/add", { code, qty: 1 });

  updateCartBadge(response.total_items || 0);
  setCardQty(card, nextQty);
  setAddButtonLabel(card, nextQty);
});

document.addEventListener("click", async (event) => {
  const adjustButton = event.target.closest(".qty-adjust-btn");
  if (!adjustButton) return;

  event.preventDefault();
  event.stopPropagation();

  const card = adjustButton.closest(".product-card");
  if (!card) return;

  const delta = Number(adjustButton.getAttribute("data-delta") || 0);
  const currentQty = Number(card.dataset.qty || 0);
  const nextQty = Math.max(0, Math.min(999, currentQty + delta));
  await setCardQtyOnServer(card, nextQty);
});

document.addEventListener("click", async (event) => {
  const clearButton = event.target.closest(".qty-clear-btn");
  if (!clearButton) return;

  event.preventDefault();
  event.stopPropagation();

  const card = clearButton.closest(".product-card");
  if (!card) return;

  await setCardQtyOnServer(card, 0);
});

document.addEventListener("click", (event) => {
  const qtyInput = event.target.closest(".product-qty-input");
  if (!qtyInput) return;
  event.stopPropagation();
  qtyInput.select();
});

document.addEventListener("keydown", async (event) => {
  const qtyInput = event.target.closest(".product-qty-input");
  if (!qtyInput || event.key !== "Enter") return;

  event.preventDefault();
  event.stopPropagation();

  const card = qtyInput.closest(".product-card");
  if (!card) return;

  const nextQty = Math.max(0, Math.min(999, Number(qtyInput.value) || 0));
  await setCardQtyOnServer(card, nextQty);
  qtyInput.blur();
});

document.addEventListener("change", async (event) => {
  const qtyInput = event.target.closest(".product-qty-input");
  if (!qtyInput) return;

  event.stopPropagation();

  const card = qtyInput.closest(".product-card");
  if (!card) return;

  const nextQty = Math.max(0, Math.min(999, Number(qtyInput.value) || 0));
  await setCardQtyOnServer(card, nextQty);
});

document.addEventListener("click", (event) => {
  const button = event.target.closest(".section-chip-btn[data-target]");
  if (!button) return;

  const targetId = button.getAttribute("data-target");
  const target = targetId ? document.getElementById(targetId) : null;
  if (!target) return;

  event.preventDefault();
  scrollSectionToTop(target, "smooth", true);
  button.blur();
});

document.addEventListener("click", (event) => {
  const link = event.target.closest('a[href="#top"]');
  if (!link) return;

  event.preventDefault();
  window.scrollTo({ top: 0, behavior: "smooth" });
  window.history.replaceState(null, "", window.location.pathname + window.location.search);
});
