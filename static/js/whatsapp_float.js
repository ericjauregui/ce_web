(() => {
  const bubble = document.querySelector(".whatsapp-float");
  if (!bubble || typeof window.PointerEvent !== "function") {
    return;
  }

  const STORAGE_KEY = "ce-whatsapp-float-position";
  const HOLD_DELAY_MS = 170;
  const MOVE_THRESHOLD_PX = 8;
  let dragPointerId = null;
  let holdTimer = 0;
  let suppressClick = false;
  let dragReady = false;
  let dragging = false;
  let pointerStartX = 0;
  let pointerStartY = 0;
  let bubbleWidth = 0;
  let bubbleHeight = 0;
  let pointerOffsetX = 0;
  let pointerOffsetY = 0;
  let pendingPosition = null;

  function clearHoldTimer() {
    if (!holdTimer) {
      return;
    }

    window.clearTimeout(holdTimer);
    holdTimer = 0;
  }

  function getViewportBounds() {
    return {
      maxLeft: Math.max(0, window.innerWidth - bubbleWidth),
      maxTop: Math.max(0, window.innerHeight - bubbleHeight),
    };
  }

  function clampPosition(left, top) {
    const bounds = getViewportBounds();
    return {
      left: Math.min(bounds.maxLeft, Math.max(0, left)),
      top: Math.min(bounds.maxTop, Math.max(0, top)),
    };
  }

  function applyPosition(left, top) {
    const clamped = clampPosition(left, top);
    bubble.style.left = `${clamped.left}px`;
    bubble.style.top = `${clamped.top}px`;
    bubble.style.right = "auto";
    bubble.style.bottom = "auto";
    pendingPosition = clamped;
    return clamped;
  }

  function persistPosition(position) {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(position));
    } catch (_err) {
      // Ignore storage failures.
    }
  }

  function syncBubbleMetrics() {
    const rect = bubble.getBoundingClientRect();
    bubbleWidth = rect.width;
    bubbleHeight = rect.height;
    return rect;
  }

  function loadSavedPosition() {
    try {
      const rawValue = window.localStorage.getItem(STORAGE_KEY);
      if (!rawValue) {
        return false;
      }

      const parsed = JSON.parse(rawValue);
      if (
        !parsed ||
        !Number.isFinite(parsed.left) ||
        !Number.isFinite(parsed.top)
      ) {
        return false;
      }

      applyPosition(parsed.left, parsed.top);
      return true;
    } catch (_err) {
      return false;
    }
  }

  function normalizeInitialPosition() {
    const rect = syncBubbleMetrics();
    if (loadSavedPosition()) {
      return;
    }

    applyPosition(rect.left, rect.top);
  }

  function beginDrag(event) {
    if (dragging) {
      return;
    }

    const rect = syncBubbleMetrics();
    dragging = true;
    dragReady = false;
    suppressClick = true;
    bubble.classList.add("is-dragging");
    pointerOffsetX = event.clientX - rect.left;
    pointerOffsetY = event.clientY - rect.top;
    bubble.setPointerCapture(event.pointerId);
    applyPosition(
      event.clientX - pointerOffsetX,
      event.clientY - pointerOffsetY,
    );
  }

  function finishDrag() {
    if (!dragging) {
      return;
    }

    dragging = false;
    bubble.classList.remove("is-dragging");
    if (pendingPosition) {
      persistPosition(pendingPosition);
    }
  }

  bubble.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) {
      return;
    }

    dragPointerId = event.pointerId;
    dragReady = false;
    dragging = false;
    suppressClick = false;
    pointerStartX = event.clientX;
    pointerStartY = event.clientY;

    clearHoldTimer();
    holdTimer = window.setTimeout(() => {
      holdTimer = 0;
      dragReady = true;
    }, HOLD_DELAY_MS);
  });

  bubble.addEventListener("pointermove", (event) => {
    if (event.pointerId !== dragPointerId) {
      return;
    }

    const deltaX = event.clientX - pointerStartX;
    const deltaY = event.clientY - pointerStartY;
    const movedEnough = Math.hypot(deltaX, deltaY) >= MOVE_THRESHOLD_PX;
    if (!dragging && movedEnough) {
      dragReady = true;
    }

    if (!dragReady && !dragging) {
      return;
    }

    event.preventDefault();
    clearHoldTimer();
    if (!dragging) {
      beginDrag(event);
      return;
    }

    applyPosition(
      event.clientX - pointerOffsetX,
      event.clientY - pointerOffsetY,
    );
  });

  function resetPointerState() {
    clearHoldTimer();
    dragPointerId = null;
    dragReady = false;
  }

  bubble.addEventListener("pointerup", (event) => {
    if (event.pointerId !== dragPointerId) {
      return;
    }

    if (dragging) {
      event.preventDefault();
      finishDrag();
    }

    resetPointerState();
  });

  bubble.addEventListener("pointercancel", (event) => {
    if (event.pointerId !== dragPointerId) {
      return;
    }

    finishDrag();
    resetPointerState();
  });

  bubble.addEventListener("lostpointercapture", () => {
    finishDrag();
  });

  bubble.addEventListener("click", (event) => {
    if (!suppressClick) {
      return;
    }

    event.preventDefault();
    event.stopPropagation();
    suppressClick = false;
  });

  window.addEventListener(
    "resize",
    () => {
      const rect = syncBubbleMetrics();
      const position = pendingPosition || { left: rect.left, top: rect.top };
      const clamped = applyPosition(position.left, position.top);
      persistPosition(clamped);
    },
    { passive: true },
  );

  normalizeInitialPosition();
})();
