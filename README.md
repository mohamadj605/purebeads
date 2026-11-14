# Aqeeq House storefront

Static luxury storefront for Cloudflare Pages. No build step, no monthly platform fee.
`aqeeqhouse.ca` and "Aqeeq House" are working placeholders. Search and replace them across the repo when the real brand and domain are settled.

## Files

| File | Purpose |
| --- | --- |
| `index.html` | The whole storefront: hero, engineering, collection, presentation, corporate gifting, warranty lookup, FAQ, JSON-LD |
| `functions/api/warranty.js` | Pages Function behind the warranty lookup (`GET /api/warranty?serial=...`) |
| `_headers` | Security and cache headers |
| `robots.txt`, `sitemap.xml` | Crawl files. Update the domain, add pages as they are built |

## Launch checklist

1. **Stripe Payment Links.** Create seven links in Stripe and paste each into `CONFIG.stripe` in `index.html`.
   - `aqeeq33:8` $149, `aqeeq33:10` $169, `aqeeq33:12` $189
   - `oud99:8` $249, `oud99:10` $289
   - `amber:33` $349, `amber:99` $489
   - Turn on shipping address collection and tax. The tassel and tone choices travel in `client_reference_id`, visible on each payment in the Stripe dashboard.
2. **Bulk quote form.** Set `CONFIG.quoteEndpoint` to a Formspree, Web3Forms or Pages Function URL. Until then the form shows a copy-and-email fallback.
3. **Warranty records.** In Cloudflare, create a KV namespace and bind it to the Pages project as `WARRANTY_KV`. Add one record per serial:
   `{"piece":"Aqeeq 33, 10 mm","materials":"...","strungOn":"2026-10-18","cord":"...","lot":"AQ-2026-07"}`
   Then set `CONFIG.demoRegistry` to `false`.
4. **Placeholders.** Replace the brand, domain and `hello@aqeeqhouse.ca` in `index.html` (including the JSON-LD block), `robots.txt` and `sitemap.xml`.
5. **Photography.** Add real product photos, an `og:image`, and `image` fields in the Product and business JSON-LD.
6. **Tailwind.** `index.html` uses the Tailwind Play CDN so the file previews anywhere. Before launch, compile it with the Tailwind CLI for a smaller, faster page.

## Deploy

Connect this repository to Cloudflare Pages with no build command and the root directory as the output directory. Add the custom domain under Pages, Custom domains.
