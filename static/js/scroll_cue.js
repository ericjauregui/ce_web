(() => {
  const shellSelector = ".scroll-cue-shell";
  const trackSelector = ".scroll-cue-track";
  const rafIds = new WeakMap();
  const attentionTimers = new WeakMap();
  const observedShells = new WeakSet();

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

  function syncShell(shell) {
    const track = getTrack(shell);
    if (!track) {
      return;
    }

    const maxScrollLeft = Math.max(0, track.scrollWidth - track.clientWidth);
    const isOverflowing = maxScrollLeft > 1;
    const canScrollRight = isOverflowing && track.scrollLeft < maxScrollLeft - 1;

    shell.classList.toggle("is-overflowing", isOverflowing);
    shell.classList.toggle("can-scroll-right", canScrollRight);
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
    if (!track) {
      return;
    }

    observedShells.add(shell);
    track.addEventListener("scroll", () => queueSync(shell), { passive: true });
    window.addEventListener("resize", () => queueSync(shell), { passive: true });

    if (typeof ResizeObserver === "function") {
      const resizeObserver = new ResizeObserver(() => queueSync(shell));
      resizeObserver.observe(shell);
      resizeObserver.observe(track);
      Array.from(track.children).forEach((child) => resizeObserver.observe(child));
    }

    queueSync(shell);
  }

  function initializeScrollCues() {
    document.querySelectorAll(shellSelector).forEach((shell) => observeShell(shell));
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