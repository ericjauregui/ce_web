(() => {
  const endpoint = "/api/analytics/event";
  const contextElement = document.querySelector("[data-analytics-context]");
  const pageContext = contextElement?.dataset.analyticsContext || null;
  const campaignKeys = ["utm_source", "utm_medium", "utm_campaign"];

  function campaignValue(key) {
    const value = new URLSearchParams(window.location.search).get(key);
    if (!value) return null;
    const normalized = value.trim().replace(/\s+/g, " ");
    if (!/^[A-Za-z0-9][A-Za-z0-9 ._-]{0,79}$/.test(normalized)) return null;
    if (/^\d{7,}$/.test(normalized)) return null;
    return normalized;
  }

  function externalReferrerHost() {
    if (!document.referrer) return null;
    try {
      const referrer = new URL(document.referrer);
      if (!/^https?:$/.test(referrer.protocol)) return null;
      if (referrer.hostname.toLowerCase() === window.location.hostname.toLowerCase()) return null;
      return referrer.hostname;
    } catch (_) {
      return null;
    }
  }

  function send(eventType, clickTarget = null) {
    const payload = {
      event_type: eventType,
      page_path: window.location.pathname,
    };
    if (pageContext) payload.page_context = pageContext;
    if (clickTarget) payload.click_target = clickTarget;
    if (eventType === "page_view") {
      const referrerHost = externalReferrerHost();
      if (referrerHost) payload.referrer_host = referrerHost;
      for (const key of campaignKeys) {
        const value = campaignValue(key);
        if (value) payload[key] = value;
      }
    }

    const body = JSON.stringify(payload);
    try {
      if (navigator.sendBeacon && navigator.sendBeacon(
        endpoint,
        new Blob([body], { type: "application/json" })
      )) return;
    } catch (_) { /* Analytics must not interrupt the page action. */ }

    fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
      keepalive: true,
      credentials: "same-origin",
    }).catch(() => {});
  }

  function targetFor(element) {
    if (!(element instanceof HTMLAnchorElement)) {
      const detailPath = element.getAttribute("data-detail-url");
      if (detailPath) return `internal:${new URL(detailPath, window.location.href).pathname}`;
      const id = element.id || "";
      return /^[A-Za-z0-9_-]{1,80}$/.test(id) ? `button:${id}` : "button";
    }

    const href = element.getAttribute("href") || "";
    if (/^mailto:/i.test(href)) return "contact:email";
    if (/^tel:/i.test(href)) return "contact:phone";

    let destination;
    try {
      destination = new URL(href, window.location.href);
    } catch (_) {
      return "external:other";
    }

    if (destination.origin === window.location.origin) {
      return `internal:${destination.pathname}`;
    }

    const hostname = destination.hostname.toLowerCase().replace(/^www\./, "");
    if (hostname === "wa.me" || hostname === "whatsapp.com" || hostname.endsWith(".whatsapp.com")) {
      return "external:whatsapp";
    }
    if (hostname === "instagram.com" || hostname.endsWith(".instagram.com")) {
      return "external:instagram";
    }
    if (hostname === "tiktok.com" || hostname.endsWith(".tiktok.com")) {
      return "external:tiktok";
    }
    if (hostname === "facebook.com" || hostname.endsWith(".facebook.com")) {
      return "external:facebook";
    }
    if (hostname === "youtube.com" || hostname.endsWith(".youtube.com") || hostname === "youtu.be") {
      return "external:youtube";
    }
    if (hostname === "maps.google.com" || hostname === "google.com") {
      return "external:maps";
    }
    return "external:other";
  }

  send("page_view");

  document.addEventListener("click", (event) => {
    if (!(event.target instanceof Element)) return;
    const target = event.target.closest(
      "a[href], button, input[type='button'], input[type='submit'], input[type='reset'], [role='button']"
    );
    if (!target) return;
    send("click", targetFor(target));
  }, true);

  window.addEventListener("pageshow", (event) => {
    if (event.persisted) send("page_view");
  });
})();
