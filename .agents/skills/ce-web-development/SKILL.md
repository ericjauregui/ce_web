---
name: ce-web-development
description: Maintain the California Earrings ce_web Flask storefront using its established catalog, responsive UI, video, team-contact asset, order, and caching conventions. Use for implementation, debugging, or QA in this repository.
---

# California Earrings development

Use this skill to avoid rediscovering product decisions and regression-prone behavior. Source paths are relative to the repository root. These notes were checked against code on 2026-09-12; verify affected code before extending it. Historical validation is not evidence about a new checkout or production deployment.

## Working conventions

- This is Flask/Jinja with Bootstrap and vanilla JavaScript. Keep domain logic in `domains/`, content in `catalog/`, shared markup in template partials, and behavior in existing page/shared scripts.
- Preserve the established dark background, champagne-gold accents, typography, real product/member images, and wholesale ordering language. Start visual changes from the actual current page.
- Check `git status --short --branch`. Recent work used `dev`; do not assume the current branch or that local fixes reached production.
- Orders contain quantities and item counts, never prices, currency, or monetary amounts, including nested metadata. This is a deliberate product constraint.
- Preserve collection identifiers, product codes, and asset references during copy edits. The collection label is **Telephone Earrings**, with identifier `telephone-earrings`.
- Site-wide fixes belong in shared selectors/partials, with verification of affected variants. Two-part headings and headings with a third action need different responsive grid treatment.

## Read the relevant reference

- [Responsive UI and browser behavior](references/ui-and-media.md): catalog buttons/chips, sticky actions, mini-cart, WhatsApp drag, video sound.
- [Catalog and trade shows](references/content.md): content sources, copy constraints, reusable events, SEO.
- [Team contact assets](references/team-assets.md): branded static vCard QR generation, portraits, social previews, contact cards.
- [Orders and caching](references/orders-and-caching.md): durable snapshots, idempotency, exports, private downloads, operational documentation.
- [Local verification](references/verification.md): commands, test selection, browser checks, evidence limits.

## Workflow

1. Inspect the current source and relevant reference. Explicit new requirements can change these conventions; this skill does not override user intent.
2. Make the smallest cohesive change across shared surfaces. Check independent content overrides as well as primary JSON labels.
3. Verify observable behavior proportional to the change. Responsive CSS needs a rendered browser check; QR presentation needs separate scan validation; order persistence needs database tests.
4. Report the change, verification, and whether it is local, committed, or deployed. A skipped test, simulated mobile viewport, or screenshot is not real-device evidence.

Use existing runbooks for deployment/database work within the user's authorized scope. This skill does not initiate deployments, real orders, or email delivery by itself.
