# Global Markets — Website

A fast, responsive, animated landing site for a trading platform.
Built with plain HTML/CSS/JS — **no build step, no dependencies**.

## Run / preview
Just open `index.html` in a browser. Or serve locally:

```bash
cd website
python3 -m http.server 8080
# visit http://localhost:8080
```

## File structure
- `index.html` — page markup & content
- `styles.css` — all styling, theme variables, responsive rules, animations
- `script.js` — live quote ticker, scroll reveals, count-up stats, mobile nav, contact form

## 🎨 Rebrand it (colors / logo / footer)
Everything is centralised so swapping your brand is quick:

| What | Where |
|------|-------|
| **Colors** | `styles.css` → `:root { --accent, --accent-2, --bg, ... }` |
| **Logo** | `index.html` → `.brand-mark` SVG (header + footer) — paste your real logo |
| **Footer / contact** | `index.html` → `<footer class="site-footer">` and the `#contact` section |
| **Brand name** | search `Global<span class="brand-accent">Markets</span>` |

> Send me your real brand colors (hex), logo, and contact details and I'll
> drop them in — no rebuild needed.

## Features included
- 📱 Fully responsive (mobile nav, fluid grids, `clamp()` typography)
- ⚡ Performance-minded (no frameworks, deferred JS, paused animations when tab hidden)
- ✨ Animations: scroll reveals, count-up stats, animated chart draw, live price flashes, marquee ticker
- ♿ Accessibility: skip link, reduced-motion support, focus styles, ARIA labels
- 🧩 Sections: Hero, Live Markets, Stats, Platform showcase, Features, Accounts/Pricing, CTA, Contact, Footer

## Notes
- Market prices are a **simulated demo feed** (`script.js` → `instruments`). Wire to a real
  data source (e.g. a websocket/API) when ready.
- The contact form is client-side only — connect it to your email service or backend endpoint.
