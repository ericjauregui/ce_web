# California Earrings (Flask Catalog)

## Key features
- SEO basics (titles, meta descriptions, Open Graph)
- Collections/sections (configured in `catalog/collections.json`)
- Responsive 2–4 column product grid with tap-to-expand description drawers
- Catalog interactions are maintained in `static/js/catalog.js`
- Search controls (`?q=...`)
- Sitemap + robots.txt
- Optional free analytics via env vars (Plausible or GoatCounter)
- Optional QR codes pointing customers to the catalog homepage

## Managing products
Edit `catalog/products.json`.

Recommended fields per product:
- `code`, `name`, `collection`
- `description`
- `tags` (for search)

### Collections
Edit `catalog/collections.json`:
- `order`: list of collection keys in desired order
- `labels`: mapping key -> display label

## Free analytics (optional)
Set ONE of these environment variables on Render:
- `PLAUSIBLE_DOMAIN=californiaearrings.com`
- OR `GOATCOUNTER_URL=https://YOURACCOUNT.goatcounter.com/count`

## Link preview thumbnail (Open Graph)
To show an image thumbnail when sharing links in iMessage, WhatsApp, Instagram DMs, etc., set:

- `SITE_BASE_URL=https://californiaearrings.com`

This ensures Open Graph/Twitter image URLs are absolute and crawlable.

## QR codes (optional)
Generate QR codes for catalog discovery:

```bash
pip install -r requirements.txt
python scripts/generate_qr_codes.py --base-url https://californiaearrings.com
```

This writes QR images to `static/qr/`.


## Social reels (TikTok embeds)
Edit `catalog/social.json`:
- `tiktok.profile_url`
- `tiktok.videos` (list of TikTok video URLs)
- `instagram.profile_url`

Note: autoplay behavior is controlled by TikTok/Instagram and may require user interaction on some devices.

## Meet the team
Edit `catalog/team.json` to add members.
Optionally add headshots to `static/team/` and set `photo` to the filename.

## Automated tests
Run API smoke tests with:

```bash
python -m unittest discover -s tests
```
