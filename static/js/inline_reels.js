(() => {
  function initializeInlineReelTrack(options) {
    const {
      trackId,
      statusNodeId = null,
      defaultStatus = "Tap any reel for sound",
      enableArrowNav = false,
      activeStatusText = null,
    } = options || {};

    const track = typeof trackId === "string" ? document.getElementById(trackId) : null;
    if (!track) {
      return;
    }

    const cards = Array.from(track.querySelectorAll(".inline-reel-card"));
    const videos = Array.from(track.querySelectorAll(".inline-reel-video"));
    const statusNode = statusNodeId ? document.getElementById(statusNodeId) : null;
    const AUTOPRIME_CARD_COUNT = 5;
    let activeCard = null;
    let preferredAudiblePlayback = false;
    let scrollCueFrame = 0;
    const supportsHover = window.matchMedia && window.matchMedia("(hover: hover) and (pointer: fine)").matches;

    function isVideoAudible(video) {
      return Boolean(video) && !video.muted && video.volume > 0.01;
    }

    function syncPreferredAudiblePlayback(video) {
      if (!video) {
        return;
      }

      preferredAudiblePlayback = isVideoAudible(video);
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
          video.currentTime = Math.min(0.08, Number.isFinite(video.duration) ? video.duration || 0.08 : 0.08);
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
        video.controls = false;
        video.pause();
        if (card.classList.contains("is-active")) {
          syncCardState(card, false);
        }
      });

    }

    function playMuted(video, enableControls = false) {
      loadVideo(video);
      video.controls = enableControls;
      video.muted = true;
      preferredAudiblePlayback = false;
      const playPromise = video.play();
      if (playPromise && typeof playPromise.catch === "function") {
        playPromise.catch(() => {
          // Autoplay may be deferred by browser policy.
        });
      }
    }

    function toggleCardAudio(card) {
      const video = card ? card.querySelector(".inline-reel-video") : null;
      if (!video) {
        return;
      }

      video.controls = true;
      video.muted = !video.muted;
      syncPreferredAudiblePlayback(video);
    }

    async function activateCard(card, options = {}) {
      const { unmute = true, scrollIntoView = true } = options;
      const video = card.querySelector(".inline-reel-video");
      if (!video) {
        return;
      }

      muteAndPauseOtherReels(card);

      activeCard = card;
      loadVideo(video);
      if (scrollIntoView) {
        card.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });
      }

      video.controls = true;
      video.muted = !unmute;
      syncPreferredAudiblePlayback(video);
      syncCardState(card, true);
      setTrackStatus(activeStatusText || defaultStatus);

      try {
        await video.play();
      } catch (_err) {
        video.muted = true;
        syncPreferredAudiblePlayback(video);
        syncCardState(card, true);
        try {
          await video.play();
        } catch (_playErr) {
          // Controls remain available.
        }
      }
    }

    async function playNextReel(currentCard, keepUnmuted) {
      const currentIndex = cards.indexOf(currentCard);
      if (currentIndex < 0 || cards.length < 2) {
        return;
      }

      const nextCard = cards[(currentIndex + 1) % cards.length];
      if (!nextCard) {
        return;
      }

      await activateCard(nextCard, { unmute: keepUnmuted, scrollIntoView: true });
    }

    function scheduleThumbnailPriming() {
      const thumbnailObserver = new IntersectionObserver((entries) => {
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
      }, {
        root: track,
        rootMargin: "220px 0px",
        threshold: 0.01,
      });

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
          window.setTimeout(() => {
            primeThumbnailFrame(video, card, true);
          }, Math.min(550, index * 95));
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
        if (typeof window.triggerScrollCueAttention === "function") {
          window.triggerScrollCueAttention(track);
        }
        syncPreferredAudiblePlayback(video);
        void playNextReel(card, preferredAudiblePlayback);
      });

      video.addEventListener("volumechange", () => {
        if (card !== activeCard) {
          return;
        }

        syncPreferredAudiblePlayback(video);
      });

      syncCardState(card, false);
    });
    scheduleThumbnailPriming();

    function autoActivateFirstCard() {
      const firstCard = cards[0];
      const firstVideo = firstCard ? firstCard.querySelector(".inline-reel-video") : null;
      if (!firstCard || !firstVideo) {
        return;
      }

      syncCardState(firstCard, true);
      activeCard = firstCard;
      playMuted(firstVideo, true);
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
        if (target.closest("video")) {
          return;
        }

        toggleCardAudio(card);
        return;
      }

      void activateCard(card);
    });

    track.addEventListener("keydown", (event) => {
      const card = event.target instanceof Element ? event.target.closest(".inline-reel-card") : null;
      if (!card) {
        return;
      }

      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        if (card === activeCard) {
          toggleCardAudio(card);
          return;
        }
        void activateCard(card);
      }
    });

    if (supportsHover) {
      cards.forEach((card) => {
        card.addEventListener("mouseenter", () => {
          if (card === activeCard) {
            return;
          }

          void activateCard(card, { unmute: false, scrollIntoView: false });
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
        const nextIndex = (startIndex + direction + cards.length) % cards.length;
        const nextCard = cards[nextIndex];
        if (!nextCard) {
          return;
        }

        nextCard.focus({ preventScroll: true });
        void activateCard(nextCard);
      });
    }

    setTrackStatus(defaultStatus);
    autoActivateFirstCard();
    queueScrollCueRefresh();
  }

  window.initializeInlineReelTrack = initializeInlineReelTrack;
})();
