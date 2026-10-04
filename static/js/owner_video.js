(() => {
  const video = document.getElementById("ownerVideo");
  if (!video) return;
  window.initializeTouchVideoSound?.(video);

  let previousVolume = video.volume;
  video.addEventListener("volumechange", () => {
    const adjustedVolume = video.volume !== previousVolume;
    previousVolume = video.volume;
    if (adjustedVolume && video.volume > 0 && video.muted) video.muted = false;
  });

  let visible = false;
  let pausedByViewer = false;
  let automaticPause = false;
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  function syncPlayback() {
    if (!visible || document.hidden) {
      if (!video.paused) {
        automaticPause = true;
        video.pause();
      }
    } else if (!pausedByViewer && !reducedMotion.matches) {
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
