(() => {
  if (typeof window.initializeInlineReelTrack !== "function") {
    return;
  }
  window.initializeInlineReelTrack({
    trackId: "reelRow",
    defaultStatus: "Tap any reel for sound",
    enableArrowNav: true,
  });
})();
