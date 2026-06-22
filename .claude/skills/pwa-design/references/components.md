# Component Patterns

Contents: Navigation · Lists · Mobile data tables · Forms & inputs · Ticket cards ·
Charts & sparklines · Gestures & sheets · Empty / loading / error states & microcopy.

## Navigation
- **Bottom tab bar, ≤5 anchors.** Stroke icons only (1.5–2px, e.g. lucide) — never
  filled/duotone (reads consumer). Active = accent icon+label; inactive = dim tier.
  Overflow → a "More" sheet or side drawer.
- Persistent across the app; respect `env(safe-area-inset-bottom)`.
- Sub-navigation = pill tabs under the header; keep the active state in the accent tint.

## Lists (divided list, not a card-per-row)
- Put rows inside ONE card with `--border`-subtle dividers between them — denser,
  scans faster than a card per row.
- Row anatomy: identity (ticker + name) left; value + colored % right; optional
  inline sparkline. Right-align numbers, tabular-nums.
- Tappable row → detail; left-border color to encode direction/sentiment (reuse this
  left-border language across lists, news, calendar, P&L for visual consistency).

## Mobile data tables (beat horizontal scroll)
- **Prioritize columns:** show 3–4 essential columns on a phone; hide the rest behind
  row-expand or a detail view. A horizontal scroll wall is a last resort.
- If you must scroll horizontally: **sticky header row + sticky first column** so the
  identifier and labels stay visible.
- **Card-per-row on very narrow screens** (stack label:value pairs) when a grid won't fit.
- Right-align all numerics with `tabular-nums`; left-align text; zebra striping or
  hover tint for row tracking. Row tap target ≥ 44px tall.
- Color deltas green/red + ▲/▼; prices in `--text-hi`; labels in the muted tier.

## Forms & inputs (mobile-critical)
- **16px minimum font-size on inputs** — smaller triggers iOS auto-zoom on focus.
- Use the right **`type`/`inputmode`**: `inputmode="decimal"` for prices,
  `inputmode="numeric"` for PINs/quantities, `type="email"`, `type="tel"` — surfaces
  the correct keypad.
- **`autocomplete` tokens** (`username`, `current-password`, `one-time-code`, `cc-number`)
  for autofill; `autocapitalize`/`autocorrect` off for symbols/codes.
- Labels **above** the field (not placeholder-as-label — placeholders vanish on input
  and fail a11y). Large touch targets; ≥8px between fields.
- **Validate on blur** (not every keystroke); show the error **inline at the field**;
  **preserve user input** on error; be explicit about which value is wrong.
- Primary action full-width, in the thumb zone; disable + show progress on submit.

## Ticket cards (signals / trades / orders)
- One `--surface` card per item: bold **direction/title** at top, a **confidence/
  conviction meter**, a **key-value grid** (Entry · Stop · TP1/2/3) in mono tabular,
  an accent **strategy chip**, timestamp in the dim tier.
- Show **R:R** (reward÷risk) as a colored chip. Left-border encodes direction.
- A small **price ladder** (SL · Entry · TP markers at true relative positions) makes
  risk asymmetry visible at a glance; differentiate the TPs (brightness ramp).

## Charts & sparklines
- **Sparklines (Tufte):** height ≈ text x-height (~14–20px), inline; **no frame, axes,
  ticks, or gridlines** (data-ink ratio → 1.0); thin single stroke colored by net
  direction; optional one end-point dot + faint min/max band. That's the only non-data ink.
- **Touch tooltips, not hover:** tap a point → tooltip (offset so the finger doesn't
  occlude it); tap empty → dismiss. For time series, **tap-hold + drag a vertical
  crosshair** to scrub precise values (shared across series at that x).
- **Hit area ≥ 24px** (ideally 44px) around small dots — expand with invisible padding.
- **Gridlines recede:** lighter than labels and than the data; ~10% opacity / very
  light gray. Don't show major + minor gridlines both prominently. Emphasize the zero
  baseline slightly. Reference lines: thin, distinct, **directly labeled**.
- **Never pie for >5 slices** (group into "Other" or use a bar) or for precise
  comparison — bars win. Prefer **direct labels** over a legend; fall back to a top
  legend only when labels won't fit.
- Double-encode color (▲/▼, +/−, shape) — never red/green alone.

## Gestures & sheets
- **Targets:** Apple HIG 44×44pt · Material 48×48dp · WCAG 2.2 AA 24px / AAA 44px.
  Floor for a fintech PWA: **44–48px**; expand hit area with padding. **≥8px spacing**
  between targets (16px+ for frequent ones).
- **Thumb zone:** primary actions in the **bottom third**; destructive/rare actions top.
- **Pull-to-refresh:** trigger ≈ **80dp** drag (indicator offset ~56dp). **Disable
  native PTR/overscroll** with `overscroll-behavior-y: contain` (or `none`).
- **Bottom sheets:** detents `.medium` (~50%) and `.large` (full); show a **grabber/
  drag handle (≥48dp touch target)**; dismiss by dragging past the lowest detent;
  modal adds a scrim. Set `overscroll-behavior: contain` on the sheet's scroller.
- **Edge gestures:** keep custom controls/horizontal swipes **>16pt from screen edges**
  (they fight iOS/Android system back). Use `overscroll-behavior-x: contain` on
  horizontal scrollers. **Avoid double-tap** (conflicts with browser zoom) and never
  make **long-press** the only path to a primary action (undiscoverable).

## Empty / loading / error states & microcopy
- **Empty state = illustration/icon + headline (<10 words) + 1–2 sentence body +
  ONE primary CTA.** Three types, designed distinctly:
  - **First-use:** explain what will appear + a "get started" action (optionally show
    an image of the populated state).
  - **No-results:** explain why + offer recovery ("Try adjusting your search/filters").
    Never a dead end.
  - **Error:** what happened + **Try Again** + an escape hatch.
- **Error microcopy:** say what happened AND how to recover; human language, no raw
  codes alone; don't blame the user; place the message **at the source** (next to the
  field); preserve input.
- **Error placement:** inline (default, form/validation) · toast (only low-severity
  transient/background — never for must-act errors) · full-page (critical load failure,
  with Try Again + Go Home/Support).
- Build in **Retry** (failed ops) and **Undo** (destructive/slips); confirm or undo
  destructive actions.
