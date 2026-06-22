# Motion & Animation

Contents: Durations · Easing · Spring vs tween · What to animate · Reduced motion · Budget.

## Durations (Material 3 token scale — exact ms; duration scales with travel area)
- **Short** (micro-interactions, icon/state/selection changes): 50 / 100 / 150 / 200ms.
- **Medium** (component enter/exit, expanding cards, most transitions): 250 / 300 / 350 / 400ms.
- **Long** (large-area / full-width): 450 / 500 / 550 / 600ms.
- **Extra-long** (full-screen): 700–1000ms.
- **Practical defaults:** taps/micro **100–200ms**; component enter/exit **200–300ms**;
  page/screen transitions **300–400ms** (mobile may push to 400–500ms). Bigger
  element/distance ⇒ longer duration.

## Easing (Material 3 — exact cubic-bezier; ease-OUT to enter, ease-IN to exit)
- **Standard** `cubic-bezier(0.2, 0, 0, 1)` — begins+ends on screen (utility).
- **Decelerate (enter)** `cubic-bezier(0, 0, 0, 1)`.
- **Accelerate (exit)** `cubic-bezier(0.3, 0, 1, 1)`.
- **Emphasized decelerate (enter)** `cubic-bezier(0.05, 0.7, 0.1, 1)`.
- **Emphasized accelerate (exit)** `cubic-bezier(0.3, 0, 0.8, 0.15)`.
- **Linear** `cubic-bezier(0,0,1,1)` — only for continuous motion (progress, spinners).
- **Never** use linear or symmetric ease-in-out for element enter/exit — looks mechanical.

## Spring vs tween (duration+easing)
- **Tween** for deterministic, non-interactive transitions (page changes, fades,
  scripted reveals) where exact timing matters.
- **Spring** for interactive/gesture-driven motion (drag-to-dismiss, pull-to-
  refresh, sheet snapping, interruptible) — recomputes toward target on interrupt
  so a grabbed/flung element stays continuous. Modern model = **duration + bounce**
  (0 = no overshoot). For "snappy" non-bouncy UI springs use high damping (~0.8–1.0).
  Note: if you specify mass/stiffness/damping, the duration arg is ignored.

## What to animate vs NOT
- **Animate only `transform` and `opacity`** (compositor thread → holds 60fps on
  low-end devices). `filter` is compositor-capable but heavier.
- **Never animate** `width`, `height`, `top`, `left`, `margin`, `padding`,
  `background-color`, `box-shadow` — they trigger layout/paint every frame (~30fps jank).
- Apple HIG: don't add extra motion to high-frequency interactions (every tap).

## prefers-reduced-motion (accessibility requirement — vestibular safety)
- **Ship the reduced/minimal version as the DEFAULT**; gate full animation behind
  `@media (prefers-reduced-motion: no-preference)`.
- **Replace, don't remove feedback:** swap large positional/parallax/spinning/
  multi-axis motion for a simple opacity cross-fade or instant state change. Motion
  must never be the only channel for important info.

## 60fps budget
- **16.7ms per frame.** transform/opacity skip layout+paint (compositor).
- `will-change`: apply only to elements about to animate, just before, and remove
  after — leaving it on wastes GPU memory. Don't blanket-apply.
- Verify with Chrome DevTools "Frame Rendering Stats".
