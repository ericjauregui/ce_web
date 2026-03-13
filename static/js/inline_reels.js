(() => {
  function initializeInlineReelTrack(options) {
    const {
      trackId,
      statusNodeId = null,
      defaultStatus = "Tap any reel for sound",
      enableArrowNav = false,
      activeStatusText = null,
      pauseWhenOutOfView = false,
    } = options || {};

    const track =
      typeof trackId === "string" ? document.getElementById(trackId) : null;
    if (!track) {
      return;
    }

    const cards = Array.from(track.querySelectorAll(".inline-reel-card"));
    const videos = Array.from(track.querySelectorAll(".inline-reel-video"));
    const statusNode = statusNodeId
      ? document.getElementById(statusNodeId)
      : null;
    const AUTOPRIME_CARD_COUNT = 5;
    const TOUCH_CONTROLS_HIDE_DELAY_MS = 2400;
    let activeCard = null;
    let preferredMutedState = true;
    let preferredVolumeLevel = 1;
    let scrollCueFrame = 0;
    let trackInViewport = true;
    let keepFullscreenOnAdvance = false;
    let fullscreenHostCard = null;
    let fullscreenPlaybackIndex = -1;
    let alignmentSettleTimers = [];
    let controlsHideTimer = 0;
    const supportsHover =
      window.matchMedia &&
      window.matchMedia("(hover: hover) and (pointer: fine)").matches;

    function pauseActiveCardPlayback() {
      if (!activeCard) {
        return;
      }

      const video = activeCard.querySelector(".inline-reel-video");
      if (!video) {
        return;
      }

      video.pause();
    }

    function rememberPreferredPlaybackState(video) {
      if (!video) {
        return;
      }

      preferredMutedState = video.muted;
      preferredVolumeLevel = Math.min(1, Math.max(0, video.volume));
    }

    function clearControlsHideTimer() {
      if (!controlsHideTimer) {
        return;
      }

      window.clearTimeout(controlsHideTimer);
      controlsHideTimer = 0;
    }

    function clearAlignmentSettleTimers() {
      alignmentSettleTimers.forEach((timer) => {
        window.clearTimeout(timer);
      });
      alignmentSettleTimers = [];
    }

    function setControlsVisibility(video, visible) {
      if (!video) {
        return;
      }

      if (visible || isVideoPresentingFullscreen(video)) {
        clearControlsHideTimer();
        video.controls = true;
        return;
      }

      if (
        video !== (activeCard && activeCard.querySelector(".inline-reel-video"))
      ) {
        video.controls = false;
        return;
      }

      video.controls = false;
    }

    function scheduleControlsHide(video, delay = TOUCH_CONTROLS_HIDE_DELAY_MS) {
      if (!video || isVideoPresentingFullscreen(video)) {
        return;
      }

      clearControlsHideTimer();
      controlsHideTimer = window.setTimeout(() => {
        controlsHideTimer = 0;
        setControlsVisibility(video, false);
      }, delay);
    }

    function revealControlsForCard(card, options = {}) {
      const { autoHide = !supportsHover } = options;
      if (!card || card !== activeCard) {
        return;
      }

      const video = card.querySelector(".inline-reel-video");
      if (!video) {
        return;
      }

      setControlsVisibility(video, true);
      if (autoHide) {
        scheduleControlsHide(video);
      }
    }

    function isNearPlaybackEnd(video) {
      if (!video || !Number.isFinite(video.duration) || video.duration <= 0) {
        return false;
      }

      return video.currentTime >= Math.max(0, video.duration - 0.25);
    }

    function isVideoPresentingFullscreen(video) {
      if (!video) {
        return false;
      }

      return Boolean(
        document.fullscreenElement === video ||
        document.webkitFullscreenElement === video ||
        video.webkitDisplayingFullscreen,
      );
    }

    function resetFullscreenPlaybackSession() {
      fullscreenHostCard = null;
      fullscreenPlaybackIndex = -1;
    }

    function getFullscreenSequenceCard() {
      if (fullscreenPlaybackIndex < 0) {
        return null;
      }

      return cards[fullscreenPlaybackIndex] || null;
    }

    function getPlaybackIndexForCard(card) {
      if (card && fullscreenHostCard === card && fullscreenPlaybackIndex >= 0) {
        return fullscreenPlaybackIndex;
      }

      return cards.indexOf(card);
    }

    async function syncInlineCardFromFullscreenExit() {
      const sequenceCard = getFullscreenSequenceCard();
      resetFullscreenPlaybackSession();
      if (!sequenceCard || sequenceCard === activeCard) {
        return;
      }

      await activateCard(sequenceCard, {
        scrollIntoView: true,
        scrollAlignment: "start",
      });
    }

    async function enterVideoFullscreen(video) {
      if (!video || isVideoPresentingFullscreen(video)) {
        return;
      }

      if (typeof video.requestFullscreen === "function") {
        try {
          await video.requestFullscreen();
          return;
        } catch (_err) {
          // Fall back to vendor-prefixed fullscreen when available.
        }
      }

      if (typeof video.webkitEnterFullscreen === "function") {
        try {
          video.webkitEnterFullscreen();
        } catch (_err) {
          // Ignore unsupported fullscreen transitions.
        }
      }
    }

    function alignCardToTrackStart(card, behavior = "smooth") {
      if (!card || typeof track.scrollTo !== "function") {
        return;
      }

      const trackRect = track.getBoundingClientRect();
      const cardRect = card.getBoundingClientRect();
      const trackStyles = window.getComputedStyle(track);
      const trackPaddingStart = Number.parseFloat(trackStyles.paddingLeft) || 0;
      const maxScrollLeft = Math.max(0, track.scrollWidth - track.clientWidth);
      const targetLeft =
        track.scrollLeft + cardRect.left - trackRect.left - trackPaddingStart;

      track.scrollTo({
        left: Math.min(maxScrollLeft, Math.max(0, targetLeft)),
        behavior,
      });
    }

    function settleCardAtTrackStart(card, behavior = "smooth") {
      if (!card) {
        return;
      }

      clearAlignmentSettleTimers();
      alignCardToTrackStart(card, behavior);

      [120, 240].forEach((delay) => {
        const timer = window.setTimeout(() => {
          alignCardToTrackStart(card, "auto");
          alignmentSettleTimers = alignmentSettleTimers.filter(
            (activeTimer) => activeTimer !== timer,
          );
        }, delay);
        alignmentSettleTimers.push(timer);
      });
    }

    function scrollCardIntoView(card, options = {}) {
      const { alignment = "center", behavior = "smooth" } = options;
      if (!card) {
        return;
      }

      if (alignment === "start") {
        settleCardAtTrackStart(card, behavior);
        return;
      }

      card.scrollIntoView({
        behavior,
        block: "nearest",
        inline: "center",
      });
    }

    function setupViewportPauseGuard() {
      if (!pauseWhenOutOfView || typeof IntersectionObserver !== "function") {
        return;
      }

      const viewportObserver = new IntersectionObserver(
        (entries) => {
          const [entry] = entries;
          const isVisible = Boolean(
            entry && entry.isIntersecting && entry.intersectionRatio >= 0.2,
          );
          trackInViewport = isVisible;

          if (!isVisible) {
            pauseActiveCardPlayback();
          }
        },
        {
          root: null,
          threshold: [0, 0.2, 0.4],
        },
      );

      viewportObserver.observe(track);
    }

    function queueScrollCueRefresh() {
      if (typeof window.refreshScrollCue !== "function" || scrollCueFrame) {
        return;
      }

      scrollCueFrame = window.requestAnimationFrame(() => {
        scrollCueFrame = 0;
        window.refreshScrollCue(track);
      });
    }

    function setTrackStatus(text) {
      if (statusNode) {
        statusNode.textContent = text;
      }
    }

    function loadVideo(video) {
      if (!video) {
        return;
      }

      if (video.dataset.loadedSrc === "true") {
        return;
      }

      const src = video.getAttribute("data-src");
      if (!src) {
        return;
      }

      if (video.getAttribute("src") === src) {
        video.dataset.loadedSrc = "true";
        return;
      }

      video.src = src;
      video.dataset.loadedSrc = "true";
      video.load();
    }

    function primeThumbnailFrame(video, card, eager = false) {
      if (!video || !card || video.dataset.thumbnailPrimed === "true") {
        return;
      }

      const markLoaded = () => {
        card.classList.add("is-loaded");
        video.dataset.thumbnailPrimed = "true";
      };

      const seekToFrame = () => {
        if (video.dataset.thumbnailPrimed === "true") {
          return;
        }

        if (video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) {
          markLoaded();
          return;
        }

        const handleSeeked = () => {
          video.removeEventListener("seeked", handleSeeked);
          markLoaded();
        };

        video.addEventListener("seeked", handleSeeked, { once: true });
        try {
          video.currentTime = Math.min(
            0.08,
            Number.isFinite(video.duration) ? video.duration || 0.08 : 0.08,
          );
        } catch (_err) {
          markLoaded();
        }
      };

      if (video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) {
        markLoaded();
        return;
      }

      video.addEventListener("loadeddata", markLoaded, { once: true });
      video.addEventListener("loadedmetadata", seekToFrame, { once: true });
      if (eager) {
        loadVideo(video);
      }
    }

    function syncCardState(card, active) {
      card.classList.toggle("is-active", active);
      card.setAttribute("aria-expanded", active ? "true" : "false");
      queueScrollCueRefresh();
    }

    function muteAndPauseOtherReels(exceptCard = null) {
      cards.forEach((card) => {
        const video = card.querySelector(".inline-reel-video");
        if (!video || card === exceptCard) {
          return;
        }

        video.muted = true;
        setControlsVisibility(video, false);
        video.pause();
        if (card.classList.contains("is-active")) {
          syncCardState(card, false);
        }
      });
    }

    function playMuted(video, enableControls = false) {
      loadVideo(video);
      setControlsVisibility(video, enableControls);
      video.volume = preferredVolumeLevel;
      video.muted = true;
      preferredMutedState = true;
      const playPromise = video.play();
      if (playPromise && typeof playPromise.catch === "function") {
        playPromise.catch(() => {
          // Autoplay may be deferred by browser policy.
        });
      }
    }

    async function continueFullscreenPlayback(
      currentCard,
      currentVideo,
      nextCard,
    ) {
      if (!currentCard || !currentVideo || !nextCard) {
        return false;
      }

      const nextVideo = nextCard.querySelector(".inline-reel-video");
      const nextSrc = nextVideo
        ? nextVideo.getAttribute("data-src") || nextVideo.getAttribute("src")
        : null;
      if (!nextSrc) {
        return false;
      }

      fullscreenHostCard = currentCard;
      fullscreenPlaybackIndex = cards.indexOf(nextCard);
      if (fullscreenPlaybackIndex < 0) {
        resetFullscreenPlaybackSession();
        return false;
      }

      loadVideo(nextVideo);
      if (activeCard && activeCard !== nextCard) {
        syncCardState(activeCard, false);
      }
      syncCardState(nextCard, true);
      scrollCardIntoView(nextCard, { alignment: "start" });

      currentVideo.controls = true;
      currentVideo.volume = preferredVolumeLevel;
      currentVideo.muted = preferredMutedState;

      if (currentVideo.getAttribute("src") !== nextSrc) {
        currentVideo.src = nextSrc;
      }
      currentVideo.load();

      try {
        await currentVideo.play();
      } catch (_err) {
        if (!preferredMutedState) {
          currentVideo.muted = true;
        }

        try {
          await currentVideo.play();
        } catch (_playErr) {
          return false;
        }
      }

      return true;
    }

    async function activateCard(card, options = {}) {
      const {
        scrollIntoView = true,
        scrollAlignment = "center",
        preserveFullscreen = false,
      } = options;
      const video = card.querySelector(".inline-reel-video");
      if (!video) {
        return;
      }

      if (!preserveFullscreen) {
        resetFullscreenPlaybackSession();
      }

      const previousActiveVideo = activeCard
        ? activeCard.querySelector(".inline-reel-video")
        : null;
      rememberPreferredPlaybackState(previousActiveVideo);

      muteAndPauseOtherReels(card);

      activeCard = card;
      loadVideo(video);
      if (scrollIntoView) {
        scrollCardIntoView(card, { alignment: scrollAlignment });
      }

      setControlsVisibility(video, false);
      video.volume = preferredVolumeLevel;
      video.muted = preferredMutedState;
      syncCardState(card, true);
      setTrackStatus(activeStatusText || defaultStatus);

      try {
        await video.play();
        if (preserveFullscreen) {
          keepFullscreenOnAdvance = true;
          void enterVideoFullscreen(video);
        }
      } catch (_err) {
        if (!preferredMutedState) {
          video.muted = true;
        }
        syncCardState(card, true);
        try {
          await video.play();
          if (preserveFullscreen) {
            keepFullscreenOnAdvance = true;
            void enterVideoFullscreen(video);
          }
        } catch (_playErr) {
          // Controls remain available.
        }
      }
    }

    async function playNextReel(currentCard) {
      if (pauseWhenOutOfView && !trackInViewport) {
        pauseActiveCardPlayback();
        return;
      }

      const currentVideo = currentCard
        ? currentCard.querySelector(".inline-reel-video")
        : null;
      rememberPreferredPlaybackState(currentVideo);

      const keepFullscreen =
        keepFullscreenOnAdvance || isVideoPresentingFullscreen(currentVideo);
      const currentIndex = getPlaybackIndexForCard(currentCard);
      if (currentIndex < 0 || cards.length < 2) {
        return;
      }

      const nextCard = cards[(currentIndex + 1) % cards.length];
      if (!nextCard) {
        return;
      }

      if (keepFullscreen && currentVideo) {
        const continuedInFullscreen = await continueFullscreenPlayback(
          currentCard,
          currentVideo,
          nextCard,
        );
        if (continuedInFullscreen) {
          return;
        }
      }

      await activateCard(nextCard, {
        scrollIntoView: true,
        scrollAlignment: "start",
        preserveFullscreen: keepFullscreen,
      });
    }

    function scheduleThumbnailPriming() {
      const thumbnailObserver = new IntersectionObserver(
        (entries) => {
          entries.forEach((entry) => {
            if (!entry.isIntersecting) {
              return;
            }

            const video = entry.target;
            const card = video.closest(".inline-reel-card");
            if (!card) {
              return;
            }

            primeThumbnailFrame(video, card, true);
            thumbnailObserver.unobserve(video);
          });
        },
        {
          root: track,
          rootMargin: "220px 0px",
          threshold: 0.01,
        },
      );

      videos.forEach((video, index) => {
        const card = video.closest(".inline-reel-card");
        if (!card) {
          return;
        }

        syncCardState(card, false);
        if (index < AUTOPRIME_CARD_COUNT) {
          if (index === 0) {
            primeThumbnailFrame(video, card, true);
            return;
          }

          // Stagger first few cards so they appear quickly without a single burst.
          window.setTimeout(
            () => {
              primeThumbnailFrame(video, card, true);
            },
            Math.min(550, index * 95),
          );
          return;
        }

        // Remaining cards lazy-prime as they approach viewport.
        thumbnailObserver.observe(video);
      });
    }

    videos.forEach((video) => {
      const card = video.closest(".inline-reel-card");
      if (!card) {
        return;
      }

      // Native controls remain available, but looping is handled by advancing to the next card.
      video.loop = false;

      video.addEventListener("ended", () => {
        if (card !== activeCard) {
          return;
        }
        if (pauseWhenOutOfView && !trackInViewport) {
          video.pause();
          return;
        }
        if (typeof window.triggerScrollCueAttention === "function") {
          window.triggerScrollCueAttention(track);
        }
        void playNextReel(card);
      });

      video.addEventListener("volumechange", () => {
        if (card !== activeCard) {
          return;
        }

        const volumeWasRaisedWhileMuted =
          preferredMutedState &&
          video.muted &&
          video.volume > preferredVolumeLevel;
        if (volumeWasRaisedWhileMuted) {
          video.muted = false;
        }

        rememberPreferredPlaybackState(video);
      });

      video.addEventListener("webkitbeginfullscreen", () => {
        if (card !== activeCard) {
          return;
        }

        keepFullscreenOnAdvance = true;
        setControlsVisibility(video, true);
      });

      video.addEventListener("webkitendfullscreen", () => {
        if (card !== activeCard || isNearPlaybackEnd(video)) {
          return;
        }

        keepFullscreenOnAdvance = false;
        scheduleControlsHide(video, 120);
        void syncInlineCardFromFullscreenExit();
      });

      syncCardState(card, false);
    });
    scheduleThumbnailPriming();

    function autoActivateFirstCard() {
      const firstCard = cards[0];
      const firstVideo = firstCard
        ? firstCard.querySelector(".inline-reel-video")
        : null;
      if (!firstCard || !firstVideo) {
        return;
      }

      syncCardState(firstCard, true);
      activeCard = firstCard;
      playMuted(firstVideo);
    }

    track.addEventListener("click", (event) => {
      const target = event.target instanceof Element ? event.target : null;
      if (!target) {
        return;
      }

      const card = target.closest(".inline-reel-card");
      if (!card) {
        return;
      }

      if (card === activeCard) {
        revealControlsForCard(card, { autoHide: !supportsHover });
        return;
      }

      void activateCard(card);
    });

    track.addEventListener("keydown", (event) => {
      const card =
        event.target instanceof Element
          ? event.target.closest(".inline-reel-card")
          : null;
      if (!card) {
        return;
      }

      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        if (card === activeCard) {
          revealControlsForCard(card, { autoHide: false });
          return;
        }
        void activateCard(card);
      }
    });

    track.addEventListener("focusin", (event) => {
      const card =
        event.target instanceof Element
          ? event.target.closest(".inline-reel-card")
          : null;
      if (!card) {
        return;
      }

      revealControlsForCard(card, { autoHide: false });
    });

    track.addEventListener("focusout", (event) => {
      const card =
        event.target instanceof Element
          ? event.target.closest(".inline-reel-card")
          : null;
      if (!card || card !== activeCard) {
        return;
      }

      const nextTarget = event.relatedTarget;
      if (nextTarget instanceof Element && card.contains(nextTarget)) {
        return;
      }

      scheduleControlsHide(card.querySelector(".inline-reel-video"), 120);
    });

    track.addEventListener(
      "pointermove",
      (event) => {
        if (!supportsHover) {
          return;
        }

        const card =
          event.target instanceof Element
            ? event.target.closest(".inline-reel-card")
            : null;
        if (!card || card !== activeCard) {
          return;
        }

        revealControlsForCard(card, { autoHide: false });
      },
      { passive: true },
    );

    track.addEventListener(
      "touchstart",
      (event) => {
        const card =
          event.target instanceof Element
            ? event.target.closest(".inline-reel-card")
            : null;
        if (!card || card !== activeCard) {
          return;
        }

        revealControlsForCard(card, { autoHide: true });
      },
      { passive: true },
    );

    if (supportsHover) {
      cards.forEach((card) => {
        card.addEventListener("mouseenter", () => {
          if (card === activeCard) {
            revealControlsForCard(card, { autoHide: false });
            return;
          }

          void activateCard(card, { scrollIntoView: false });
        });

        card.addEventListener("mouseleave", () => {
          if (card !== activeCard) {
            return;
          }

          scheduleControlsHide(card.querySelector(".inline-reel-video"), 120);
        });
      });
    }

    if (enableArrowNav) {
      document.addEventListener("keydown", (event) => {
        if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") {
          return;
        }

        const currentIndex = activeCard ? cards.indexOf(activeCard) : -1;
        const startIndex = currentIndex >= 0 ? currentIndex : 0;
        const direction = event.key === "ArrowRight" ? 1 : -1;
        const nextIndex =
          (startIndex + direction + cards.length) % cards.length;
        const nextCard = cards[nextIndex];
        if (!nextCard) {
          return;
        }

        nextCard.focus({ preventScroll: true });
        void activateCard(nextCard);
      });
    }

    document.addEventListener("fullscreenchange", () => {
      const activeVideo = activeCard
        ? activeCard.querySelector(".inline-reel-video")
        : null;
      if (activeVideo && document.fullscreenElement === activeVideo) {
        keepFullscreenOnAdvance = true;
        setControlsVisibility(activeVideo, true);
        return;
      }

      if (!document.fullscreenElement && !isNearPlaybackEnd(activeVideo)) {
        keepFullscreenOnAdvance = false;
        scheduleControlsHide(activeVideo, 120);
        void syncInlineCardFromFullscreenExit();
      }
    });

    setTrackStatus(defaultStatus);
    setupViewportPauseGuard();
    autoActivateFirstCard();
    queueScrollCueRefresh();
  }

  window.initializeInlineReelTrack = initializeInlineReelTrack;
})();
