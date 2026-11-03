(() => {
  const video = document.getElementById("ownerVideo");
  if (!video) return;
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const manualPlayback = reducedMotion.matches || Boolean(navigator.connection?.saveData);
  video.parentElement.classList.toggle("is-manual-playback", manualPlayback);
  window.initializeTouchVideoSound?.(video, manualPlayback
    ? () => video.play().catch(() => {}) : null);

  let previousVolume = video.volume;
  video.addEventListener("volumechange", () => {
    const adjustedVolume = video.volume !== previousVolume;
    previousVolume = video.volume;
    if (adjustedVolume && video.volume > 0 && video.muted) video.muted = false;
  });

  let visible = false;
  let pausedByViewer = false;
  let automaticPause = false;
  function syncPlayback() {
    if (!visible || document.hidden) {
      if (!video.paused) {
        automaticPause = true;
        video.pause();
      }
    } else if (!pausedByViewer && !reducedMotion.matches && !navigator.connection?.saveData) {
      video.play().catch(() => {});
    }
  }
  video.addEventListener("pause", () => {
    if (!automaticPause) pausedByViewer = true;
    automaticPause = false;
  });
  video.addEventListener("play", () => { pausedByViewer = false; });
  if (typeof IntersectionObserver === "function") {
    new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting && entry.intersectionRatio >= 0.35;
      syncPlayback();
    }, { threshold: 0.35 }).observe(video);
  }
  document.addEventListener("visibilitychange", syncPlayback);
})();
