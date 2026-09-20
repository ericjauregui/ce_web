# Trade-show asset sources

- `jis-fall-logo.png`: official JIS Fall logo served by jisshow.com, downloaded 2026-09-09.
- `jis-spring-logo.png`: official JIS Spring logo served by jisshow.com, downloaded 2026-09-09.
- `jck-logo-white.png`: official white JCK logo linked from JCK Exhibitor Resources, downloaded 2026-09-09.
- `miami-night.webp` and `las-vegas-night.webp`: generated with OpenAI's built-in image generator for this site. No brand marks or text were requested.
- `product-*.webp`: OpenAI-assisted background edits of the matching repository product image. Prompts required the jewelry design and product details to remain unchanged.

Official event pages:

- https://www.jisshow.com/fall/en-us.html
- https://www.jisshow.com/spring/en-us.html
- https://lasvegas.jckonline.com/en-us/exhibit/exhibitor-resources.html

Verified again on 2026-09-20: all three local logo files matched the official
website downloads byte-for-byte. Exact URLs and SHA-256 hashes are recorded in
`catalog/trade_show_logo_sources.json`. Social previews composite these original
files after GPT Images generation; the image model does not recreate the logos.
