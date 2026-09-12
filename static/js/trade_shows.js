(() => {
  const show = JSON.parse(document.getElementById("showDownloadData").textContent);
  const escapeText = (text) => String(text).replace(/\\/g, "\\\\").replace(/\n/g, "\\n").replace(/[,;]/g, "\\$&");
  function download(lines, type, filename) {
    const url = URL.createObjectURL(new Blob([lines.join("\r\n") + "\r\n"], { type }));
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  document.getElementById("saveShowCalendar").addEventListener("click", () => {
    const end = new Date(show.end + "T00:00:00Z");
    end.setUTCDate(end.getUTCDate() + 1);
    download(["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//California Earrings//Trade Shows//EN", "BEGIN:VEVENT", "UID:" + show.start + "-trade-show@californiaearrings.com", "DTSTAMP:" + new Date().toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, ""), "DTSTART;VALUE=DATE:" + show.start.replace(/-/g, ""), "DTEND;VALUE=DATE:" + end.toISOString().slice(0, 10).replace(/-/g, ""), "SUMMARY:" + escapeText("California Earrings at " + show.name), "LOCATION:" + escapeText([show.venue, show.address, show.city, show.booth].join(", ")), "DESCRIPTION:" + escapeText("Visit us at " + show.booth + ". Show dates; check the official website for daily hours."), "END:VEVENT", "END:VCALENDAR"], "text/calendar", "trade-show.ics");
  });
  const mobileBar = document.getElementById("showMobileBar");
  if (typeof IntersectionObserver === "function") {
    let pastHero = false;
    let contactVisible = false;
    const nav = document.getElementById("nav");
    const syncBar = () => {
      const editing = document.activeElement?.matches("input, textarea, select");
      mobileBar.hidden = !pastHero || contactVisible || editing || Boolean(nav?.classList.contains("show"));
    };
    new IntersectionObserver(([entry]) => {
      pastHero = !entry.isIntersecting && entry.boundingClientRect.top < 0;
      syncBar();
    }).observe(document.querySelector(".trade-show-hero"));
    new IntersectionObserver(([entry]) => {
      contactVisible = entry.isIntersecting;
      syncBar();
    }).observe(document.getElementById("show-updates"));
    if (nav) new MutationObserver(syncBar).observe(nav, { attributes: true, attributeFilter: ["class"] });
    document.addEventListener("focusin", syncBar);
    document.addEventListener("focusout", () => setTimeout(syncBar, 0));
  }
  document.addEventListener("play", (event) => {
    if (!(event.target instanceof HTMLVideoElement)) return;
    document.querySelectorAll(".trade-show-page video").forEach((other) => {
      if (other !== event.target && !other.paused) other.pause();
    });
  }, true);
  const video = document.getElementById("ownerVideo");
  if (!video) return;

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
