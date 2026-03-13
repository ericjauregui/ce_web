(() => {
  if (typeof window.initializeInlineReelTrack !== "function") {
    return;
  }
  window.initializeInlineReelTrack({
    trackId: "latestVideosTrack",
    pauseWhenOutOfView: true,
  });
})();
