async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload || {}),
  });
  return response.json();
}

const CARD_INTERACTIVE_SELECTOR =
  ".add-to-cart-btn, .product-qty-control, .product-qty-input, .product-detail-link";

function isCardInteractiveTarget(target) {
  return !!target.closest(CARD_INTERACTIVE_SELECTOR);
}

function setCatalogMiniCartExpanded(expanded) {
  const miniCart = document.getElementById("catalogMiniCart");
  if (!miniCart) return;

  const desktop = window.matchMedia("(min-width: 768px)").matches;
  const shouldExpand = desktop || expanded;
  miniCart.classList.toggle("is-expanded", shouldExpand);
  const actions = miniCart.querySelector(".catalog-mini-cart__actions");
  if (actions) actions.inert = !shouldExpand;
  document.body.classList.toggle(
    "is-mini-cart-expanded",
    !miniCart.hidden && shouldExpand,
  );
}

function updateCatalogMiniCart(totalItems, distinctItems, reveal = false) {
  const miniCart = document.getElementById("catalogMiniCart");
  if (!miniCart) return;

  const total = Math.max(0, Number(totalItems) || 0);
  const distinct = Math.max(0, Number(distinctItems) || 0);
  const wasHidden = miniCart.hidden;

  miniCart.dataset.totalItems = String(total);
  miniCart.dataset.distinctItems = String(distinct);
  miniCart.hidden = total <= 0;
  document.body.classList.toggle("has-catalog-mini-cart", total > 0);

  miniCart.querySelectorAll("[data-mini-cart-total]").forEach((element) => {
    element.textContent = String(total);
  });
  miniCart.querySelectorAll("[data-mini-cart-distinct]").forEach((element) => {
    element.textContent = String(distinct);
  });
  miniCart
    .querySelectorAll("[data-mini-cart-piece-label]")
    .forEach((element) => {
      element.textContent = total === 1 ? "piece" : "pieces";
    });
  miniCart
    .querySelectorAll("[data-mini-cart-style-label]")
    .forEach((element) => {
      element.textContent = distinct === 1 ? "style" : "styles";
    });

  const count = miniCart.querySelector(".catalog-mini-cart__count");
  if (count) count.textContent = String(total);

  if (total > 0 && (reveal || wasHidden)) {
    setCatalogMiniCartExpanded(true);
  } else {
    setCatalogMiniCartExpanded(miniCart.classList.contains("is-expanded"));
  }
}

function updateCartBadge(totalItems, distinctItems, revealMiniCart = false) {
  const badge = document.getElementById("cartCountBadge");
  if (badge) {
    badge.textContent = totalItems || 0;
    badge.style.display = (totalItems || 0) > 0 ? "inline-block" : "none";
  }
  updateCatalogMiniCart(totalItems, distinctItems, revealMiniCart);
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

  if (expanded) syncDrawerHeight(card);
  card.classList.toggle("is-open", expanded);
  card.setAttribute("aria-expanded", expanded ? "true" : "false");
  drawer.setAttribute("aria-hidden", expanded ? "false" : "true");
}

function scrollToCatalogStart() {
  const firstAnchor = document.querySelector(".section-anchor");
  if (!firstAnchor) return;

  const styles = getComputedStyle(document.documentElement);
  const navActual =
    parseFloat(styles.getPropertyValue("--nav-actual-height")) || 0;
  const navFallback = parseFloat(styles.getPropertyValue("--nav-height")) || 50;
  const topOffset = (navActual || navFallback) +
    (document.querySelector(".home-collections")?.getBoundingClientRect().height || 0);
  const targetTop = Math.max(
    0,
    firstAnchor.getBoundingClientRect().top + window.scrollY - topOffset,
  );

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
  const navActual =
    parseFloat(styles.getPropertyValue("--nav-actual-height")) || 0;
  const navFallback = parseFloat(styles.getPropertyValue("--nav-height")) || 50;
  const topOffset = (navActual || navFallback) +
    (document.querySelector(".home-collections")?.getBoundingClientRect().height || 0);
  const targetTop = Math.max(
    0,
    target.getBoundingClientRect().top + window.scrollY - topOffset,
  );

  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) behavior = "instant";
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

  updateCartBadge(response.total_items || 0, response.distinct_items || 0);
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
  if (
    deltaX > LONG_PRESS_MOVE_TOLERANCE ||
    deltaY > LONG_PRESS_MOVE_TOLERANCE
  ) {
    clearLongPressState();
  }
});

document.addEventListener("pointerup", clearLongPressState);
document.addEventListener("pointercancel", clearLongPressState);
window.addEventListener("scroll", clearLongPressState, { passive: true });

let resizeRafId = 0;

window.addEventListener(
  "resize",
  () => {
    if (resizeRafId) return;
    resizeRafId = window.requestAnimationFrame(() => {
      resizeRafId = 0;
      document
        .querySelectorAll(".product-card.is-open")
        .forEach(syncDrawerHeight);
    });
  },
  { passive: true },
);

function initializeCatalogCards(root = document) {
  root.querySelectorAll(".product-card").forEach((card) => {
    setCardExpanded(card, false);
    const initialQty = Math.max(
      0,
      Math.min(999, Number(card.dataset.qty) || 0),
    );
    setCardQty(card, initialQty);
    setAddButtonLabel(card, initialQty);
  });
}

function initializeCatalogScrollTracking() {
  const header = document.querySelector(".home-collections");
  if (!header) return;
  const toggle = header.querySelector(".home-collections-toggle");
  const navigation = header.querySelector(".home-collection-navigation");
  let nudged = false;
  let previousScrollY = window.scrollY;
  toggle.addEventListener("click", () => {
    const expanded = toggle.getAttribute("aria-expanded") !== "true";
    toggle.setAttribute("aria-expanded", String(expanded));
    toggle.setAttribute("aria-label", `${expanded ? "Collapse" : "Expand"} catalog collections`);
    navigation.hidden = !expanded;
    toggle.classList.remove("is-nudging");
    nudged = true;
    scheduleUpdate();
  });
  toggle.addEventListener("animationend", () => toggle.classList.remove("is-nudging"));
  const pinned = header.querySelector(".home-collection-current");
  const track = header.querySelector(".home-collection-track");
  const options = Array.from(track.querySelectorAll("[data-target]"));
  const sections = options.map((option) => document.getElementById(option.dataset.target));
  let activeIndex = -1;
  let frame = 0;

  function update() {
    frame = 0;
    const styles = getComputedStyle(document.documentElement);
    const navHeight = parseFloat(styles.getPropertyValue("--nav-actual-height")) ||
      parseFloat(styles.getPropertyValue("--nav-height")) || 50;
    if (!nudged && window.scrollY > previousScrollY + 4 &&
        header.getBoundingClientRect().top <= navHeight + 2) {
      toggle.classList.add("is-nudging");
      nudged = true;
    }
    previousScrollY = window.scrollY;
    const headerHeight = header.getBoundingClientRect().height;
    document.documentElement.style.setProperty("--catalog-header-height", `${headerHeight}px`);
    const readingLine = navHeight + headerHeight + 12;
    let nextIndex = 0;
    sections.forEach((section, index) => {
      if (section && section.getBoundingClientRect().top <= readingLine) nextIndex = index;
    });
    if (nextIndex === activeIndex) return;
    activeIndex = nextIndex;
    const focused = header.contains(document.activeElement) ? document.activeElement : null;
    options.forEach((option, index) => {
      if (index === activeIndex) {
        option.setAttribute("aria-current", "location");
        pinned.appendChild(option);
      } else {
        option.removeAttribute("aria-current");
        track.appendChild(option);
      }
    });
    if (focused) focused.focus({ preventScroll: true });
  }

  function scheduleUpdate() {
    if (!frame) frame = window.requestAnimationFrame(update);
  }
  window.addEventListener("scroll", scheduleUpdate, { passive: true });
  window.addEventListener("resize", scheduleUpdate, { passive: true });
  new ResizeObserver(scheduleUpdate).observe(header);
  update();
}

document.addEventListener("DOMContentLoaded", () => {
  initializeCatalogCards();
  initializeCatalogScrollTracking();

  const miniCart = document.getElementById("catalogMiniCart");
  if (miniCart) {
    updateCatalogMiniCart(
      miniCart.dataset.totalItems,
      miniCart.dataset.distinctItems,
    );
  }

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

  updateCartBadge(
    response.total_items || 0,
    response.distinct_items || 0,
    true,
  );
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

let miniCartLastScrollY = window.scrollY;
let miniCartScrollRafId = 0;

window.addEventListener(
  "scroll",
  () => {
    if (miniCartScrollRafId) return;
    miniCartScrollRafId = window.requestAnimationFrame(() => {
      miniCartScrollRafId = 0;
      const currentScrollY = window.scrollY;
      const scrollDelta = currentScrollY - miniCartLastScrollY;
      miniCartLastScrollY = currentScrollY;

      const miniCart = document.getElementById("catalogMiniCart");
      if (!miniCart || miniCart.hidden) return;
      if (window.matchMedia("(min-width: 768px)").matches) {
        setCatalogMiniCartExpanded(true);
        return;
      }
      if (currentScrollY < 80 || scrollDelta < -6) {
        setCatalogMiniCartExpanded(true);
      } else if (scrollDelta > 8) {
        setCatalogMiniCartExpanded(false);
      }
    });
  },
  { passive: true },
);

window.addEventListener(
  "resize",
  () => {
    if (window.matchMedia("(min-width: 768px)").matches) {
      setCatalogMiniCartExpanded(true);
    }
  },
  { passive: true },
);

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
  window.scrollTo({ top: 0, behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth" });
  window.history.replaceState(
    null,
    "",
    window.location.pathname + window.location.search,
  );
});
