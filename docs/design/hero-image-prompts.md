# Responsive hero artwork

Generated with the built-in GPT Images tool, using `static/assets/hero_bg.png` as the edit target. The original file is retained. Generated compositions are not pixel-identical copies of the original jewelry.

## Wide prompt

Edit the supplied jewelry background for a FULL BLEED desktop website hero. Output a wide 3:1 image, ideally 3072x1024. Preserve all jewelry pieces from the reference with exactly the same shapes, materials, gemstone cuts, colors, details and photographic realism; do not redesign products. Recompose the existing border arrangement to suit the wide canvas: left collection near left side, right collection near right side, bottom pieces along bottom left and bottom right, keeping the middle 50% width entirely dark empty textured black for website copy. All jewelry fully inside the image with 10% safe margin top and bottom. Extend the same original black leather-like texture and subtle gold particles seamlessly edge-to-edge; no blank padding, frames or visible boundaries. Keep black and gold mood. No text or logo. Only change canvas proportions, background extension and placement, not jewelry appearance.

Saved as `static/assets/hero_bg_wide.png`.

## Mobile prompt

Edit supplied image into a portrait mobile website hero background, aspect ratio 4:5. Preserve ALL existing jewelry designs exactly: same shapes, gemstone cuts, colors, metallic detail, no added or redesigned jewelry. Recompose jewelry into a delicate border concentrated across top 18% and bottom 18%, with only tiny accents at far side edges. Leave central 65% of height and middle 85% of width quiet dark black texture for large logo, text and buttons overlay. Uniformly reduce jewelry size as needed; no stretching. Keep every jewelry piece fully inside canvas with 8% outer safe margin. Extend original black leather-like background texture and subtle gold particles seamlessly all the way to edges. Full bleed, no flat padding or frame. Same photographic black and gold styling as source. No text or logos. Primary goal preserve the jewelry detail while adapting composition to portrait mobile screen.

Saved as `static/assets/hero_bg_mobile.png`.

## Layout

### Compact mobile revision

The active mobile asset is now `static/assets/hero_bg_mobile_compact.png`, generated with the built-in GPT Images tool from the original artwork. It places jewelry at the sides within the compact crop; the shared desktop gold-tint and dark-gradient layers apply across all artwork swaps. The older portrait variant remains on disk but is no longer used. Hero heights are unchanged by this revision.

Prompt:

Edit the supplied jewelry image into a SQUARE 1:1 full-bleed background for a COMPACT mobile website hero. Preserve the original jewelry designs, gem cuts, materials, colors and fine photographic detail as closely as possible. Important crop-safe composition: ALL recognizable jewelry must lie within the middle 55% of image HEIGHT (between y=22% and y=77%), arranged in two slender vertical clusters at LEFT x=7%-20% and RIGHT x=80%-93%. Put round diamond studs, open hearts, crosses, square studs and heart drops in the left cluster; crescent moons, cherries, red/white double hearts, infinity loops and open hearts in the right cluster. Reduce jewelry uniformly to fit, do not stretch shapes. Keep center x=24%-76% dark and empty for website text. TOP AND BOTTOM 20% contain only black texture and subtle gold dust, NO JEWELRY, because those areas get cropped on wider phones. Do not place jewelry along top or bottom border. Fill entire square edge to edge with original rich black textured surface and restrained gold flecks, no padding or visible frames. Jewelry should be bright and recognizable. No text, no logo. Adapt placement and background only, retain source product appearance.

Phones use the portrait variant, tablets use the original, and desktop widths from 1200px use the wide variant. Desktop and tablet hero heights follow the image proportions. Below 768px, the minimum height uses clamp(340px, 44svh, 420px) to keep the hero compact; content may grow the section further. The compact mobile frame crops the square background at the top and bottom on wider phones. Background cover always fills the section, with cropping where the frame and artwork proportions differ. Local Chrome checked at 320, 390, 768, 1440, and 2560px with no horizontal overflow. Not deployed.
