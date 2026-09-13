# Responsive UI and browser behavior

## Source map

- Shared theme/product styles: `static/css/styles/base.css`.
- Headings, cart/checkout, chips, floating controls: `static/css/styles/layout.css`.
- Navigation: `static/css/styles/nav.css`, `templates/base.html`.
- Product actions: `templates/product_detail.html`, `static/js/product_detail.js`.
- Mini-cart: `templates/index.html`, `static/js/catalog.js`, `templates/partials/cart_icon.html`.
- Reels: `static/js/inline_reels.js`, initialized by `home_reels.js` and `reels.js`; reusable `templates/partials/latest_videos_strip.html`.
- Owner video: `static/js/trade_shows.js`, `templates/trade_shows.html`.

## Mobile sizing and sticky elements

- Mobile chips use `max-width: 767.98px`, 40px minimum height, and vertical centering. Sticky section rows reduce vertical padding to `.7rem` so bigger controls occupy existing space. Preserve horizontal category scrolling and desktop dimensions for mobile-only changes.
- Cart/checkout code badges have separate selectors and narrow-screen overrides. Current mobile minimum height is 34px; desktop checkout uses 36px. Check long codes too.
- Empty-cart Product Reels uses the partial's `reels_view_all_button` option for an outlined button; standard strips use chips. Preserve intentional variants.
- `Browse Catalog` previously overflowed its narrow `minmax(0, 1fr)` heading column. Mobile rows with `.page-back-btn` now use an intrinsic-width button column and flexible heading. Rows also containing `.page-title-action` keep a third intrinsic-width column. Hide the invisible centering spacer on mobile. Check Team, About, Contact, member pages, and Trade Shows after shared button changes.
- `.product-detail-top-actions` is a legacy name: the actions now form a **fixed bottom row**. Desktop width caps at 760px; mobile uses four compact columns. Preserve safe-area padding and body clearance so footer/last content remain reachable. Check labels after quantity updates, not just `Add to Order`.
- The catalog mini-cart is separate: desktop stays expanded; mobile collapses scrolling down and expands scrolling up or on toggle. Preserve total-piece versus distinct-style counts, the shared navbar cart icon, and Review order.
- Check fixed controls against the navbar, mobile trade-show bar, mini-cart, WhatsApp bubble, safe areas, and virtual keyboard. One bar's rules do not apply automatically to another page.

## WhatsApp drag in Chromium

`static/js/whatsapp_float.js` and the homepage link work together:

- Capture the pointer on `pointerdown`, before native anchor dragging takes over.
- Keep `draggable="false"`, the `dragstart` prevent-default guard, and touch-action handling.
- Preserve the movement threshold and post-drag click suppression: dragging must not launch WhatsApp, but normal clicking must still work.
- Retain pointer-cancel/lost-capture cleanup, saved-position handling, and viewport clamping after resize.

Safari working does not prove Chrome/Edge working. Exercise an actual drag in Chromium and then resize to a narrow viewport. Verify deployment/cache state before claiming a local fix resolves production Chrome.

## Audio and playback

- Autoplay begins muted for browser compatibility. Preserve native controls, active-card handling, out-of-view/search-focus pausing, and fullscreen advancement.
- `inline_reels.js` remembers `preferredMutedState` and `preferredVolumeLevel`. Only a positive **changed volume level** on the active video should unmute it; a mute-only event must stay muted. The old `muted && volume > 0` check confused programmatic/mute changes with volume intent.
- `trade_shows.js` separately compares the owner video's previous volume and unmutes on a changed positive level. Preserve coordination that prevents owner and reel videos playing simultaneously.
- Verify muted autoplay, slider adjustment, deliberate mute/unmute, volume zero, advancing reels, and programmatic volume restoration. Inactive videos must not overwrite the active preference.
- Local Chromium checks demonstrated slider-to-unmute and stable manual mute. Physical phone volume keys were not verified. Do not promise OS hardware keys will unmute HTML media; verify on the target phone and preserve a native unmute path.

Navigation's shortened collapse transition is about 180ms. Preserve reduced-motion behavior and check animation plus final layout; duration alone does not prove smoothness.
