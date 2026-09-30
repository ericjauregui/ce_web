(() => {
  const endpoint = "/api/analytics/event";
  const contextElement = document.querySelector("[data-analytics-context]");
  const pageContext = contextElement?.dataset.analyticsContext || null;
  const checkoutForm = document.getElementById("checkoutForm");
  // The confirmation is rendered by POST /checkout, but is a separate journey step.
  const pagePath = document.querySelector('[data-analytics-page="/order-submitted"]')
    ? "/order-submitted" : safePath(window.location.pathname);
  const campaignKeys = ["utm_source", "utm_medium", "utm_campaign"];

  function safePath(path) {
    return path.replace(/^\/download\/order\/[^/]+\.(csv|pdf)$/, "/download/order/file.$1");
  }

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

  function send(eventType, clickTarget = null, extra = null) {
    const payload = {
      event_type: eventType,
      page_path: pagePath,
    };
    if (pageContext) payload.page_context = pageContext;
    if (clickTarget) payload.click_target = clickTarget;
    if (extra && typeof extra === "object") Object.assign(payload, extra);
    if (eventType === "page_view" && payload.page_path === pagePath) {
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

  function actionSlug(value) {
    const slug = String(value || "")
      .normalize("NFKD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .replace(/&/g, " and ")
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .split("-")
      .filter(Boolean)
      .slice(0, 20)
      .join("-")
      .slice(0, 80)
      .replace(/-+$/g, "");
    return slug || "unlabeled-control";
  }

  function targetFor(element) {
    if (element.matches(".add-to-cart-btn")) return "action:add-to-order";

    const explicitTarget = element.getAttribute("data-analytics-target");
    if (/^(?:action|component):[a-z0-9]+(?:-[a-z0-9]+){0,19}$/.test(explicitTarget || "")) {
      return explicitTarget;
    }

    if (element.matches("summary") && element.closest("#contactQr")) return "action:toggle-contact-qr";
    if (element.matches(".product-share-btn")) return "action:share-product";

    if (element.closest("#cartContentCard")) {
      if (element.matches(".qty-minus")) return "action:order-summary-quantity-minus";
      if (element.matches(".qty-plus")) return "action:order-summary-quantity-plus";
      if (element.matches(".qty-remove")) return "action:order-summary-remove-item";
      if (element.matches(".cart-undo-btn")) return element.closest(".cart-undo-clear")
        ? "action:order-summary-undo-clear" : "action:order-summary-undo-removal";
      if (element.matches("#clearOrderBtn")) return "action:order-summary-clear";
      if (element.matches(".cart-checkout-btn")) return "action:order-summary-checkout";
    }

    if (element.matches(".qty-adjust-btn")) {
      return element.dataset.delta === "-1" ? "action:order-quantity-minus" : "action:order-quantity-plus";
    }
    if (element.matches(".qty-clear-btn")) return "action:order-remove-item";

    const productCard = element.closest(".product-card");
    if (productCard && !(element instanceof HTMLAnchorElement) && !element.closest(".add-to-cart-btn, .qty-adjust-btn, .qty-clear-btn")) {
      return "component:product-card";
    }

    if (!(element instanceof HTMLAnchorElement)) {
      const label = element.getAttribute("aria-label") || element.textContent || element.value || element.id;
      return `action:${actionSlug(label)}`;
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
      const download = destination.pathname.match(/^\/download\/order\/[^/]+\.(csv|pdf)$/);
      if (download) return `action:download-order-${download[1]}`;
      return `internal:${safePath(destination.pathname)}`;
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

  document.getElementById("cartDrawer")?.addEventListener("shown.bs.offcanvas", () => {
    send("page_view", null, { page_path: "/order-summary" });
  });

  if (checkoutForm) {
    let activeSince = document.visibilityState === "hidden" ? null : performance.now();
    const recordedFields = new Set();
    const checkoutFields = [
      ["name", '[name="name"]'],
      ["company", '[name="company"]'],
      ["phone", '[name="phone"]'],
      ["email", '[name="email"]'],
      ["address_line_1", '[name="address_line_1"]'],
      ["address_line_2", '[name="address_line_2"]'],
      ["city", '[name="city"]'],
      ["state", '[name="state"]'],
      ["postal_code", '[name="postal_code"]'],
      ["country", '[name="country"]'],
    ];

    function recordActiveCheckoutTime() {
      if (activeSince === null) return;
      const activeSeconds = Math.floor((performance.now() - activeSince) / 1000);
      activeSince = null;
      if (activeSeconds > 0) {
        send("page_duration", null, {
          duration_seconds: Math.min(1800, activeSeconds),
        });
      }
    }

    function resumeActiveCheckoutTime() {
      if (activeSince === null) activeSince = performance.now();
    }

    function recordCheckoutFieldProgress() {
      const form = checkoutForm;
      checkoutFields.forEach(([fieldKey, selector]) => {
        const field = form.querySelector(selector);
        if (field instanceof HTMLInputElement && field.value.trim() && !recordedFields.has(fieldKey)) {
          recordedFields.add(fieldKey);
          send("checkout_field", null, { field_key: fieldKey });
        }
      });
    }

    // Save progress as it happens; mobile tab closure may never deliver pagehide.
    for (const eventType of ["input", "change", "focusout", "keyup"]) {
      checkoutForm.addEventListener(eventType, recordCheckoutFieldProgress);
    }
    checkoutForm.addEventListener("ce:checkout-option-selected", (event) => {
      const field = {country: "country", state: "state", phone_country: "phone-country"}[event.target.name];
      if (field) send("click", `action:checkout-select-${field}`);
      recordCheckoutFieldProgress();
    });
    recordCheckoutFieldProgress();

    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "hidden") {
        recordActiveCheckoutTime();
        recordCheckoutFieldProgress();
      } else {
        resumeActiveCheckoutTime();
      }
    });
    window.addEventListener("pagehide", () => {
      recordActiveCheckoutTime();
      recordCheckoutFieldProgress();
    });
    window.addEventListener("pageshow", (event) => {
      if (event.persisted) {
        resumeActiveCheckoutTime();
        send("page_view");
      }
    });
  }

  document.addEventListener("submit", (event) => {
    if (event.target === checkoutForm) {
      send("click", "action:checkout-submit");
    } else if (event.target instanceof HTMLFormElement && event.target.id === "navSearchForm") {
      send("click", "action:catalog-search");
    }
  }, true);

  document.addEventListener("change", (event) => {
    if (!(event.target instanceof Element)) return;
    if (event.target.matches(".qty-input") && event.target.closest("#cartContentCard")) {
      send("click", "action:order-summary-quantity-edit");
    } else if (event.target.matches(".product-qty-input")) {
      send("click", "action:order-quantity-edit");
    }
  }, true);

  document.addEventListener("keydown", (event) => {
    if (event.repeat || !["Enter", " "].includes(event.key) || !(event.target instanceof Element)) return;
    // Native buttons/links generate click themselves. These custom cards do not.
    if (event.target.matches(".product-card[role='button'], .inline-reel-card[role='button']")) {
      send("click", targetFor(event.target));
    }
  }, true);

  document.addEventListener("click", (event) => {
    if (!(event.target instanceof Element)) return;
    if (event.target.closest("input:not([type=submit]):not([type=button]):not([type=reset]), textarea, select, .checkout-combobox__option")) return;
    const target = event.target.closest(
      "a[href], summary, button, input[type='button'], input[type='submit'], input[type='reset'], [role='button']"
    );
    if (!target || target.matches(":disabled") || target.getAttribute("aria-disabled") === "true") return;
    // Track submit attempts from the form event so keyboard and pointer agree.
    if (target.closest("#checkoutForm") && target.matches("button[type='submit'], input[type='submit']")) return;
    send("click", targetFor(target));
  }, true);

  if (!checkoutForm) {
    window.addEventListener("pageshow", (event) => {
      if (event.persisted) send("page_view");
    });
  }
})();
