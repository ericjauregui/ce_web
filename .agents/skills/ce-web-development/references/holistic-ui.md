# Holistic California Earrings UI foundation

Owner-requested November 2, 2026. Use with this repository's existing UI/media,
content, orders/caching and verification references. This is design guidance, not
permission to install dependencies, change functionality or release production.

## Shared foundation, platform-specific execution

Keep hierarchy, spacing, typography, accessible states and purposeful motion
coherent across California Earrings products. Separate three implementation modes:
native mobile apps need device/keyboard/gesture behavior; operational browser apps
need dense keyboard-accessible workflows; this public storefront needs recognizable
products and low-friction wholesale order requests. Shared principles do not require
shared runtimes or identical layouts. This repository uses the storefront mode.

Preserve dark #0d0d0d, champagne #d7c07a, Lato/Playfair Display and real imagery.
Improve existing shared CSS/partials before inventing a new design system. Make
product identity, quantity controls and the next action clear; avoid decorative
badges, repetitive panels and effects that compete with jewelry imagery.

## Storefront behavior must stay intact

- Quantity-only wholesale ordering, no prices/currency, product/collection IDs,
  product imagery, global-market language and Telephone Earrings terminology.
- Serialized cart writes, confirmed-response quantities, undo, validation and
  idempotent order submission. No optimistic success without canonical evidence.
- Fixed-bottom product actions, compact mobile mini-cart, safe areas, WhatsApp
  drag/click suppression and coordinated video mute/autoplay behavior.
- Crawlable content, metadata, structured data and analytics. Do not add retail
  checkout charges or pricing markup. Native UI references do not justify React,
  Expo, canvas or universal styling runtimes in this Flask/Jinja website.

Use brief CSS feedback for a real interaction, preserve normal animations and
honor system reduced motion. Essential actions need visible touch/keyboard routes;
hover or long press is optional. No forced autoplay, looping decoration, broad
animated blur or animation that delays quantity entry or navigation.

## References: adapt ideas, not whole stacks

- [BoardUI](https://www.boardui.com/): visual hierarchy and consistent controls.
- [Magic UI](https://magicui.design/): restrained feedback translated to existing CSS.
- [Interface Lineage](https://interfacelineage.com/): explain which user task an
  interaction improves; preserve memory/context and truthful progress.
- [Expo skills](https://github.com/expo/skills) and
  [Obytes](https://github.com/obytes/react-native-template-obytes): native project
  guidance, not a replacement storefront scaffold.
- [React Native Reusables](https://github.com/founded-labs/react-native-reusables),
  [gluestack](https://github.com/gluestack/gluestack-ui), and
  [Tamagui](https://github.com/tamagui/tamagui): control-state/token ideas only here;
  do not introduce their styling/runtime dependencies for polish.
- [Bottom sheet](https://github.com/gorhom/react-native-bottom-sheet) and
  [carousel](https://github.com/dohooo/react-native-reanimated-carousel): study
  dismissal, keyboard and swipe alternatives; prefer existing accessible dialogs,
  gallery behavior or CSS scroll-snap when a demonstrated need calls for them.
- [Gifted Charts](https://github.com/Abhinandan-Kushwaha/react-native-gifted-charts),
  [Skia](https://github.com/wcandillon/react-native-skia), and
  [VisionCamera](https://github.com/margelo/react-native-vision-camera): specialized
  native capabilities with no default customer-storefront role. Do not install
  graphics/camera/chart engines for decorative UI. Check current docs and licenses
  before any selective code reuse; these links authorize neither scripts nor assets.

## No notable regression: measure rather than promise

Keep image derivatives/original fallbacks, hero preload matching, lazy catalog and
reel loading, reserved aspect ratios, noscript imagery, self-hosted fonts, caches,
fingerprinting and generated CSS manifests. Rebuild relevant generated assets using
existing commands. No new remote font/media/runtime by default.

Before/after comparison uses the same representative routes, browser/device/network
and cold/warm conditions: LCP, CLS, interaction response, bytes/request count,
JS/CSS payload, long tasks and scrolling. Count all eager dependencies, not just
one entry file. A shorter stylesheet does not prove faster user interaction.

Use actual rendered views and existing E2E/source-matched evidence. Cover relevant
phone/desktop widths, keyboard, zoom, reduced motion, long names/codes, empty,
pending/error and undo states. Historical UX reports can contain later fixes;
verify a defect in current code/pixels before proposing it. No live orders/email
tests. Report unavailable measurements/device validation honestly. Preserve the
repository's dev-first release workflow and independently verify any authorized
production deployment; a pushed commit alone is not deployment evidence.
