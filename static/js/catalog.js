async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload || {}),
  });
  return response.json();
}

const CARD_INTERACTIVE_SELECTOR = ".add-to-cart-btn, .product-qty-control, .product-qty-input, .product-detail-link";
const PRODUCT_GRID_SELECTOR = "[data-density-grid]";
const CATALOG_DENSITY_MIN = 1;
const CATALOG_DENSITY_MAX = 20;
const DEFAULT_CATALOG_DENSITY = 6;
const CATALOG_DENSITY_CURVE = 1.7;
const CATALOG_DENSITY_GAP_CURVE = 0.92;
const CATALOG_DENSITY_RESPONSIVE_BREAKPOINTS = [
  { minWidth: 1680, minColumns: 2, maxColumns: 19, defaultColumns: 6, minGapRem: 0.34, maxGapRem: 1.08, minCardWidth: 140 },
  { minWidth: 1400, minColumns: 2, maxColumns: 16, defaultColumns: 5, minGapRem: 0.38, maxGapRem: 1.04, minCardWidth: 148 },
  { minWidth: 1200, minColumns: 2, maxColumns: 13, defaultColumns: 4, minGapRem: 0.42, maxGapRem: 1.02, minCardWidth: 160 },
  { minWidth: 992, minColumns: 2, maxColumns: 11, defaultColumns: 4, minGapRem: 0.46, maxGapRem: 1, minCardWidth: 168 },
  { minWidth: 768, minColumns: 2, maxColumns: 8, defaultColumns: 4, minGapRem: 0.5, maxGapRem: 0.98, minCardWidth: 188 },
  { minWidth: 576, minColumns: 2, maxColumns: 6, defaultColumns: 3, minGapRem: 0.58, maxGapRem: 1.02, minCardWidth: 172 },
  { minWidth: 0, minColumns: 2, maxColumns: 4, defaultColumns: 2, minGapRem: 0.68, maxGapRem: 1.08, minCardWidth: 132 },
];

let catalogDensityValue = DEFAULT_CATALOG_DENSITY;
let catalogDensityControlsBound = false;
let catalogDensityInitialized = false;
let catalogDensityActiveMaxValue = CATALOG_DENSITY_MAX;
let densityResyncRafId = 0;
let densityResyncTimeoutId = 0;
let densityWheelCooldownId = 0;
let activeDensityPointerId = null;
let densityVisibilityRafId = 0;

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
    syncCatalogDensityState();
    document.querySelectorAll(".product-card.is-open").forEach(syncDrawerHeight);
  });
}, { passive: true });

function normalizeCatalogDensity(value, maxValue = CATALOG_DENSITY_MAX) {
  const numericValue = Number.parseInt(String(value), 10);
  if (!Number.isFinite(numericValue)) {
    return clampNumber(DEFAULT_CATALOG_DENSITY, CATALOG_DENSITY_MIN, maxValue);
  }

  return Math.max(CATALOG_DENSITY_MIN, Math.min(maxValue, numericValue));
}

function clampNumber(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function getCatalogDensityNormalizedProgress(value, maxValue = CATALOG_DENSITY_MAX) {
  if (maxValue === CATALOG_DENSITY_MIN) {
    return 0;
  }

  return (normalizeCatalogDensity(value, maxValue) - CATALOG_DENSITY_MIN) / (maxValue - CATALOG_DENSITY_MIN);
}

function getCatalogDensityResponsiveProfile(viewportWidth) {
  return CATALOG_DENSITY_RESPONSIVE_BREAKPOINTS.find((profile) => viewportWidth >= profile.minWidth)
    || CATALOG_DENSITY_RESPONSIVE_BREAKPOINTS[CATALOG_DENSITY_RESPONSIVE_BREAKPOINTS.length - 1];
}

function getCatalogDensityViewportWidth() {
  return window.innerWidth || document.documentElement.clientWidth || 0;
}

function getCatalogDensityAvailableWidth(grid, viewportWidth = getCatalogDensityViewportWidth()) {
  const measuredWidth = grid?.getBoundingClientRect?.().width || grid?.clientWidth || grid?.parentElement?.clientWidth || 0;
  return Math.max(0, measuredWidth || viewportWidth);
}

function getCatalogDensityEffectiveMaxColumns(profile, availableWidth) {
  const rootFontSize = parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
  const minGapPixels = profile.minGapRem * rootFontSize;

  for (let columnCount = profile.maxColumns; columnCount >= profile.minColumns; columnCount -= 1) {
    const totalGapWidth = Math.max(0, columnCount - 1) * minGapPixels;
    const cardWidth = (availableWidth - totalGapWidth) / columnCount;

    if (cardWidth >= profile.minCardWidth) {
      return columnCount;
    }
  }

  return profile.minColumns;
}

function getCatalogDensityProfileMetrics(grid) {
  const viewportWidth = getCatalogDensityViewportWidth();
  const profile = getCatalogDensityResponsiveProfile(viewportWidth);
  const availableWidth = getCatalogDensityAvailableWidth(grid, viewportWidth);
  const effectiveMaxColumns = getCatalogDensityEffectiveMaxColumns(profile, availableWidth);

  return { profile, effectiveMaxColumns };
}

function getCatalogDensityCompactTier(columnCount) {
  if (columnCount >= 10) return 3;
  if (columnCount >= 7) return 2;
  if (columnCount >= 5) return 1;
  return 0;
}

function getCatalogDensityColumnCountForValue(value, profile, effectiveMaxColumns) {
  const densityProgress = getCatalogDensityNormalizedProgress(value);
  const columnProgress = densityProgress ** CATALOG_DENSITY_CURVE;
  const rawColumnCount = profile.minColumns + ((effectiveMaxColumns - profile.minColumns) * columnProgress);

  return clampNumber(Math.round(rawColumnCount), profile.minColumns, effectiveMaxColumns);
}

function getCatalogDensityActiveMaxValue(profile, effectiveMaxColumns) {
  for (let value = CATALOG_DENSITY_MIN; value <= CATALOG_DENSITY_MAX; value += 1) {
    const columnCount = getCatalogDensityColumnCountForValue(value, profile, effectiveMaxColumns);
    if (columnCount >= effectiveMaxColumns) {
      return value;
    }
  }

  return CATALOG_DENSITY_MAX;
}

function getDefaultCatalogDensityValueForRange({ profile, effectiveMaxColumns, activeMaxValue }) {
  const targetColumns = clampNumber(profile.defaultColumns, profile.minColumns, effectiveMaxColumns);
  let bestValue = DEFAULT_CATALOG_DENSITY;
  let bestDistance = Number.POSITIVE_INFINITY;

  for (let value = CATALOG_DENSITY_MIN; value <= activeMaxValue; value += 1) {
    const columnCount = getCatalogDensityColumnCountForValue(value, profile, effectiveMaxColumns);
    const distance = Math.abs(columnCount - targetColumns);
    const isBetterMatch = distance < bestDistance;
    const isCloserToBaseline = distance === bestDistance
      && Math.abs(value - DEFAULT_CATALOG_DENSITY) < Math.abs(bestValue - DEFAULT_CATALOG_DENSITY);

    if (isBetterMatch || isCloserToBaseline) {
      bestValue = value;
      bestDistance = distance;
    }
  }

  return bestValue;
}

function getCatalogDensityRangeState(grid = getCatalogDensityGrids()[0]) {
  const { profile, effectiveMaxColumns } = getCatalogDensityProfileMetrics(grid);
  const activeMaxValue = getCatalogDensityActiveMaxValue(profile, effectiveMaxColumns);

  return {
    profile,
    effectiveMaxColumns,
    activeMaxValue,
    defaultValue: getDefaultCatalogDensityValueForRange({ profile, effectiveMaxColumns, activeMaxValue }),
  };
}

function getCatalogDensityGridMetrics(grid, value) {
  const { profile, effectiveMaxColumns } = getCatalogDensityProfileMetrics(grid);
  const densityProgress = getCatalogDensityNormalizedProgress(value);
  const gapProgress = densityProgress ** CATALOG_DENSITY_GAP_CURVE;
  const columnCount = getCatalogDensityColumnCountForValue(value, profile, effectiveMaxColumns);
  const gapRem = profile.maxGapRem - ((profile.maxGapRem - profile.minGapRem) * gapProgress);

  return {
    columnCount,
    compactTier: getCatalogDensityCompactTier(columnCount),
    gapRem: `${gapRem.toFixed(3)}rem`,
  };
}

function syncCatalogDensityGridLayout() {
  getCatalogDensityGrids().forEach((grid) => {
    const metrics = getCatalogDensityGridMetrics(grid, catalogDensityValue);
    grid.style.setProperty("--product-grid-columns", String(metrics.columnCount));
    grid.style.setProperty("--product-grid-gap", metrics.gapRem);
    grid.dataset.density = String(catalogDensityValue);
    grid.dataset.densityTier = String(metrics.compactTier);
  });
}

function getCatalogDensityGrids(root = document) {
  return Array.from(root.querySelectorAll(PRODUCT_GRID_SELECTOR));
}

function syncOpenCardHeights() {
  document.querySelectorAll(".product-card.is-open").forEach(syncDrawerHeight);
}

function queueCatalogDensityResync() {
  if (!densityResyncRafId) {
    densityResyncRafId = window.requestAnimationFrame(() => {
      densityResyncRafId = 0;
      syncOpenCardHeights();
    });
  }

  if (densityResyncTimeoutId) {
    window.clearTimeout(densityResyncTimeoutId);
  }

  densityResyncTimeoutId = window.setTimeout(() => {
    densityResyncTimeoutId = 0;
    syncOpenCardHeights();
  }, 180);
}

function getCatalogDensityRailElements() {
  const rail = document.querySelector("[data-density-rail]");
  if (!rail) return null;

  return {
    rail,
    zoomInButton: rail.querySelector('[data-density-action="zoom-in"]'),
    zoomOutButton: rail.querySelector('[data-density-action="zoom-out"]'),
    track: rail.querySelector("[data-density-track]"),
    thumb: rail.querySelector("[data-density-thumb]"),
  };
}

function getCatalogDensityProgress(value, maxValue = catalogDensityActiveMaxValue) {
  return getCatalogDensityNormalizedProgress(value, maxValue) * 100;
}

function getCatalogDensityVisibilityTarget() {
  const stickyHeaders = Array.from(document.querySelectorAll(".sticky-section-header"));
  return stickyHeaders[1] || stickyHeaders[0] || document.querySelector(".section-header-row");
}

function getCatalogDensityVisibilityThreshold(target) {
  const styles = getComputedStyle(document.documentElement);
  const navActual = parseFloat(styles.getPropertyValue("--nav-actual-height")) || 0;
  const navFallback = parseFloat(styles.getPropertyValue("--nav-height")) || 50;
  const navOffset = navActual || navFallback;

  return target.getBoundingClientRect().top <= navOffset;
}

function syncCatalogDensityVisibility() {
  const elements = getCatalogDensityRailElements();
  if (!elements?.rail) return;

  const target = getCatalogDensityVisibilityTarget();
  const isVisible = target ? getCatalogDensityVisibilityThreshold(target) : false;

  elements.rail.classList.toggle("is-visible", isVisible);
  elements.rail.setAttribute("aria-hidden", isVisible ? "false" : "true");
}

function queueCatalogDensityVisibilitySync() {
  if (densityVisibilityRafId) return;

  densityVisibilityRafId = window.requestAnimationFrame(() => {
    densityVisibilityRafId = 0;
    syncCatalogDensityVisibility();
  });
}

function updateCatalogDensityRail() {
  const elements = getCatalogDensityRailElements();
  if (!elements) return;

  const { rail, zoomInButton, zoomOutButton, thumb } = elements;
  rail.dataset.density = String(catalogDensityValue);
  rail.dataset.densityMax = String(catalogDensityActiveMaxValue);
  rail.setAttribute("title", "Catalog zoom controls. Plus zooms in to fewer columns, minus zooms out to more columns. Drag the thumb or hold Ctrl or Cmd and use the mouse wheel to adjust.");

  if (thumb) {
    thumb.style.setProperty("--catalog-density-progress", `${getCatalogDensityProgress(catalogDensityValue, catalogDensityActiveMaxValue)}%`);
    thumb.setAttribute("aria-valuemax", String(catalogDensityActiveMaxValue));
    thumb.setAttribute("aria-valuenow", String(catalogDensityValue));
    thumb.setAttribute("aria-valuetext", `Catalog zoom level ${catalogDensityValue}`);
  }

  if (zoomInButton) {
    zoomInButton.disabled = catalogDensityValue <= CATALOG_DENSITY_MIN;
  }

  if (zoomOutButton) {
    zoomOutButton.disabled = catalogDensityValue >= catalogDensityActiveMaxValue;
  }
}

function syncCatalogDensityState(options = {}) {
  const { resetToDefault = false } = options;
  const rangeState = getCatalogDensityRangeState();

  catalogDensityActiveMaxValue = rangeState.activeMaxValue;
  catalogDensityValue = resetToDefault
    ? rangeState.defaultValue
    : normalizeCatalogDensity(catalogDensityValue, catalogDensityActiveMaxValue);
  syncCatalogDensityGridLayout();
  updateCatalogDensityRail();

  queueCatalogDensityResync();
}

function applyCatalogDensity(value) {
  catalogDensityValue = normalizeCatalogDensity(value, catalogDensityActiveMaxValue);
  syncCatalogDensityGridLayout();
  updateCatalogDensityRail();
  queueCatalogDensityResync();
}

function nudgeCatalogDensity(step) {
  const nextValue = normalizeCatalogDensity(catalogDensityValue + step, catalogDensityActiveMaxValue);
  if (nextValue === catalogDensityValue) {
    updateCatalogDensityRail();
    return;
  }

  applyCatalogDensity(nextValue);
}

function getCatalogDensityFromPointer(clientY, track) {
  const rect = track.getBoundingClientRect();
  if (!rect.height) return catalogDensityValue;

  const relativeY = Math.min(rect.height, Math.max(0, clientY - rect.top));
  const ratio = relativeY / rect.height;
  const nextValue = CATALOG_DENSITY_MIN + Math.round(ratio * (catalogDensityActiveMaxValue - CATALOG_DENSITY_MIN));
  return normalizeCatalogDensity(nextValue, catalogDensityActiveMaxValue);
}

function handleCatalogDensityPointerMove(event) {
  const elements = getCatalogDensityRailElements();
  if (!elements?.track || activeDensityPointerId !== event.pointerId) return;

  event.preventDefault();
  applyCatalogDensity(getCatalogDensityFromPointer(event.clientY, elements.track));
}

function releaseCatalogDensityPointer(event) {
  if (event.pointerId !== activeDensityPointerId) return;
  activeDensityPointerId = null;
  window.removeEventListener("pointermove", handleCatalogDensityPointerMove);
  window.removeEventListener("pointerup", releaseCatalogDensityPointer);
  window.removeEventListener("pointercancel", releaseCatalogDensityPointer);
}

function bindCatalogDensityControls() {
  if (catalogDensityControlsBound) return;

  const elements = getCatalogDensityRailElements();
  if (!elements) return;

  const { rail, zoomInButton, zoomOutButton, track, thumb } = elements;

  zoomInButton?.addEventListener("click", () => {
    nudgeCatalogDensity(-1);
  });

  zoomOutButton?.addEventListener("click", () => {
    nudgeCatalogDensity(1);
  });

  const startDensityPointer = (event) => {
    if (!track) return;
    activeDensityPointerId = event.pointerId;
    thumb?.setPointerCapture?.(event.pointerId);
    applyCatalogDensity(getCatalogDensityFromPointer(event.clientY, track));
    window.addEventListener("pointermove", handleCatalogDensityPointerMove, { passive: false });
    window.addEventListener("pointerup", releaseCatalogDensityPointer);
    window.addEventListener("pointercancel", releaseCatalogDensityPointer);
  };

  track?.addEventListener("pointerdown", (event) => {
    event.preventDefault();
    startDensityPointer(event);
  });

  thumb?.addEventListener("pointerdown", (event) => {
    event.preventDefault();
    event.stopPropagation();
    startDensityPointer(event);
  });

  thumb?.addEventListener("keydown", (event) => {
    if (event.key === "ArrowUp" || event.key === "ArrowRight" || event.key === "PageUp") {
      event.preventDefault();
      nudgeCatalogDensity(-1);
      return;
    }

    if (event.key === "ArrowDown" || event.key === "ArrowLeft" || event.key === "PageDown") {
      event.preventDefault();
      nudgeCatalogDensity(1);
      return;
    }

    if (event.key === "Home") {
      event.preventDefault();
      applyCatalogDensity(CATALOG_DENSITY_MIN);
      return;
    }

    if (event.key === "End") {
      event.preventDefault();
      applyCatalogDensity(catalogDensityActiveMaxValue);
    }
  });

  rail.addEventListener("keydown", (event) => {
    if (event.target !== rail) return;
    if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
    event.preventDefault();
    nudgeCatalogDensity(event.key === "ArrowUp" ? -1 : 1);
  });

  document.addEventListener("wheel", (event) => {
    if (!(event.ctrlKey || event.metaKey)) return;
    if (!getCatalogDensityGrids().length) return;

    if (event.target instanceof Element) {
      const blockedTarget = event.target.closest("input, textarea, select, [contenteditable='true']");
      if (blockedTarget) return;
    }

    if (Math.abs(event.deltaY) < Math.max(6, Math.abs(event.deltaX))) return;

    event.preventDefault();
    if (densityWheelCooldownId) return;

    nudgeCatalogDensity(event.deltaY < 0 ? -1 : 1);
    densityWheelCooldownId = window.setTimeout(() => {
      densityWheelCooldownId = 0;
    }, 140);
  }, { passive: false });

  window.addEventListener("scroll", queueCatalogDensityVisibilitySync, { passive: true });
  window.addEventListener("resize", queueCatalogDensityVisibilitySync, { passive: true });

  catalogDensityControlsBound = true;
}

function initializeCatalogDensity() {
  if (!getCatalogDensityGrids().length) return;

  bindCatalogDensityControls();

  if (!catalogDensityInitialized) {
    syncCatalogDensityState({ resetToDefault: true });
    catalogDensityInitialized = true;
  } else {
    syncCatalogDensityState();
  }

  queueCatalogDensityVisibilitySync();
}

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
  initializeCatalogDensity();

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
  initializeCatalogDensity();
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
