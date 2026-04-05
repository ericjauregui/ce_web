(() => {
  const shellSelector = ".scroll-cue-shell";
  const trackSelector = ".scroll-cue-track";
  const buttonSelector = ".scroll-cue-button";
  const leftButtonSelector = ".scroll-cue-button--left";
  const rightButtonSelector = ".scroll-cue-button--right";
  const rafIds = new WeakMap();
  const attentionTimers = new WeakMap();
  const activationTimers = new WeakMap();
  const pendingActivationDirections = new WeakMap();
  const observedShells = new WeakSet();

  function getButtonLabel(shell, direction) {
    const directionLabel = direction === "left" ? "left" : "right";

    if (shell.classList.contains("scroll-cue-shell--chips")) {
      return `Scroll categories ${directionLabel}`;
    }

    if (shell.classList.contains("scroll-cue-shell--reels")) {
      return `Scroll content ${directionLabel}`;
    }

    return `Scroll ${directionLabel}`;
  }

  function getButton(shell, direction) {
    if (!shell) {
      return null;
    }

    if (direction === "left") {
      return shell.querySelector(leftButtonSelector);
    }

    return shell.querySelector(rightButtonSelector);
  }

  function ensureButton(shell, direction) {
    if (!shell) {
      return null;
    }

    const existingButton = getButton(shell, direction);
    if (existingButton) {
      return existingButton;
    }

    const button = document.createElement("button");
    button.type = "button";
    button.className = `scroll-cue-button scroll-cue-button--${direction}`;
    button.setAttribute("aria-label", getButtonLabel(shell, direction));
    button.setAttribute("tabindex", "-1");
    button.textContent = direction === "left" ? "<" : ">";
    shell.appendChild(button);
    return button;
  }

  function getScrollStep(track) {
    if (!(track instanceof Element)) {
      return 0;
    }

    return Math.max(160, Math.round(track.clientWidth * 0.72));
  }

  function resolveShell(target) {
    if (!(target instanceof Element)) {
      return null;
    }

    if (target.matches(shellSelector)) {
      return target;
    }

    if (target.matches(trackSelector)) {
      return target.closest(shellSelector);
    }

    return target.closest(shellSelector);
  }

  function getTrack(shell) {
    return shell ? shell.querySelector(trackSelector) : null;
  }

  function isReelTrack(shell, track) {
    return Boolean(
      shell &&
      track &&
      shell.classList.contains("scroll-cue-shell--reels") &&
      track.classList.contains("inline-reel-track"),
    );
  }

  function queueVisibleReelActivation(track) {
    const direction = pendingActivationDirections.get(track);
    if (!direction) {
      return;
    }

    const existingTimer = activationTimers.get(track);
    if (existingTimer) {
      window.clearTimeout(existingTimer);
    }

    const timer = window.setTimeout(() => {
      activationTimers.delete(track);
      pendingActivationDirections.delete(track);
      track.dispatchEvent(
        new CustomEvent("ce:scroll-cue-activate-visible", {
          bubbles: false,
          detail: { direction },
        }),
      );
    }, 150);

    activationTimers.set(track, timer);
  }

  function requestVisibleReelActivation(shell, track, direction) {
    if (!isReelTrack(shell, track)) {
      return;
    }

    pendingActivationDirections.set(track, direction);
    queueVisibleReelActivation(track);
  }

  function syncShell(shell) {
    const track = getTrack(shell);
    const leftButton = getButton(shell, "left");
    const rightButton = getButton(shell, "right");
    if (!track) {
      return;
    }

    const maxScrollLeft = Math.max(0, track.scrollWidth - track.clientWidth);
    const isOverflowing = maxScrollLeft > 1;
    const canScrollLeft = isOverflowing && track.scrollLeft > 1;
    const canScrollRight =
      isOverflowing && track.scrollLeft < maxScrollLeft - 1;

    shell.classList.toggle("is-overflowing", isOverflowing);
    shell.classList.toggle("can-scroll-left", canScrollLeft);
    shell.classList.toggle("can-scroll-right", canScrollRight);

    if (leftButton) {
      leftButton.disabled = !canScrollLeft;
      leftButton.setAttribute("aria-hidden", canScrollLeft ? "false" : "true");
      leftButton.setAttribute("tabindex", canScrollLeft ? "0" : "-1");
    }

    if (rightButton) {
      rightButton.disabled = !canScrollRight;
      rightButton.setAttribute(
        "aria-hidden",
        canScrollRight ? "false" : "true",
      );
      rightButton.setAttribute("tabindex", canScrollRight ? "0" : "-1");
    }
  }

  function queueSync(shell) {
    if (!(shell instanceof Element)) {
      return;
    }

    const existingFrame = rafIds.get(shell);
    if (existingFrame) {
      return;
    }

    const frame = window.requestAnimationFrame(() => {
      rafIds.delete(shell);
      syncShell(shell);
    });
    rafIds.set(shell, frame);
  }

  function observeShell(shell) {
    if (!(shell instanceof Element) || observedShells.has(shell)) {
      queueSync(shell);
      return;
    }

    const track = getTrack(shell);
    const leftButton = ensureButton(shell, "left");
    const rightButton = ensureButton(shell, "right");
    if (!track) {
      return;
    }

    observedShells.add(shell);
    track.addEventListener(
      "scroll",
      () => {
        queueSync(shell);
        if (pendingActivationDirections.has(track)) {
          queueVisibleReelActivation(track);
        }
      },
      { passive: true },
    );
    window.addEventListener("resize", () => queueSync(shell), {
      passive: true,
    });

    if (typeof ResizeObserver === "function") {
      const resizeObserver = new ResizeObserver(() => queueSync(shell));
      resizeObserver.observe(shell);
      resizeObserver.observe(track);
      Array.from(track.children).forEach((child) =>
        resizeObserver.observe(child),
      );
    }

    if (leftButton) {
      leftButton.addEventListener("click", () => {
        track.scrollBy({ left: -getScrollStep(track), behavior: "smooth" });
        requestVisibleReelActivation(shell, track, "left");
      });
    }

    if (rightButton) {
      rightButton.addEventListener("click", () => {
        track.scrollBy({ left: getScrollStep(track), behavior: "smooth" });
        requestVisibleReelActivation(shell, track, "right");
      });
    }

    queueSync(shell);
  }

  function initializeScrollCues() {
    document
      .querySelectorAll(shellSelector)
      .forEach((shell) => observeShell(shell));
  }

  function refreshScrollCue(target) {
    const shell = target ? resolveShell(target) : null;
    if (shell) {
      queueSync(shell);
      return;
    }

    initializeScrollCues();
  }

  function triggerScrollCueAttention(target) {
    const shell = resolveShell(target);
    if (!shell || !shell.classList.contains("scroll-cue-shell--reels")) {
      return;
    }

    const rightButton = getButton(shell, "right");
    if (rightButton && !rightButton.disabled) {
      rightButton.click();
      return;
    }

    const existingTimer = attentionTimers.get(shell);
    if (existingTimer) {
      window.clearTimeout(existingTimer);
    }

    shell.classList.remove("is-attentioning");
    // Force restart so rapid reel endings still retrigger the animation.
    void shell.offsetWidth;
    shell.classList.add("is-attentioning");

    const timer = window.setTimeout(() => {
      shell.classList.remove("is-attentioning");
      attentionTimers.delete(shell);
    }, 680);
    attentionTimers.set(shell, timer);
  }

  function onReady(callback) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", callback, { once: true });
      return;
    }

    callback();
  }

  window.initializeScrollCues = initializeScrollCues;
  window.refreshScrollCue = refreshScrollCue;
  window.triggerScrollCueAttention = triggerScrollCueAttention;

  onReady(initializeScrollCues);
  window.addEventListener("load", initializeScrollCues, { once: true });
})();
