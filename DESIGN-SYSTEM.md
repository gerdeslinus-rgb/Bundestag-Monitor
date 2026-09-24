# Bundestag Monitor — Instagram Carousel Design System

Final spec, approved. Implementation reference (`Bundestag Monitor Carousel v2.dc.html`; covers `Cover Options.dc.html`, chart `Seat Arc Slide.dc.html`, slide-4 patterns `Slide 4 Options.dc.html`).
Canvas: **1080 × 1350 px** (4:5), one `<section>` per slide. Five slides: cover, vote, debate, consequence, subscribe.

This system exists to make editorial news carousels that do **not** read as AI-generated. Every rule below came out of a real review round; the Don'ts are as binding as the Dos.

---

## 1. Color

| Token | Value | Use |
|---|---|---|
| `--ink` | `#151B20` | Dark slide grounds (every other slide, starting at the cover's own ground) |
| `--navy` | `#223341` | Headline highlight blocks, bar fills, pill fills; body ink on light slides |
| `--off-white` | `#FAFAF8` | Light slide grounds; text color on dark slides |
| `--card` | `#FFFFFF` | Card and pill surfaces |
| `--accent` | `#6FA0C8` | Steel blue: highlighted words in headlines, pending-state card fill (with ink text) |
| `--accent-deep` | `#2F6C9E` | The same blue where it must hold contrast on white (links, small emphasis) |
| Secondary text | off-white at `0.82` / navy at `0.75` | Supporting copy, footers, counters |

**Party colors — charts only.** CDU/CSU `#151B20`, SPD `#E3000F`, Grüne `#409A3C`, Linke `#BE3075`, AfD `#009EE0`, SSW `#003C8F`. Charts are the only place color leaves the palette; never use party colors for type, cards or backgrounds.

Rules
- **Two grounds carry the deck** (ink + off-white). The steel blue is the only accent and is used sparingly.
- **Alternate grounds, starting from the cover.** The cover's ground is set by the variant drawn per §6.1: a dark cover (`1a`, `1b`, `1d`, `1f`) gives ink → off-white → ink → off-white → ink, a light one (`1c`, `1e`) gives off-white → ink → off-white → ink → off-white. What is fixed is the alternation, not which slide number is dark: two identical grounds never sit next to each other. Max 2 background colors in the deck.
- No browns, no warm creams, no yellow, no gradients, no colored shadows.
- Never tint body text below `0.75` alpha; never apply opacity or `color-mix` to headline type.

## 2. Typography

- **Display:** Zilla Slab 700 — headlines, all large figures (`1.500 €`, `~127 €`, `01.01.27`, `335`), the `→` glyph.
- **Body/UI:** Archivo 400/500/700 — everything else. Two font families, never a third.
- **Exactly three font sizes per slide.** No fourth size, ever.
  - Display: `96px` (cover / closing) or `80px` (content slides)
  - Body: `32px`
  - Small: `24px` (footers, legends, chart sub-labels)
- Hierarchy inside a slide comes from **weight, color and case** — never from a new size.
- Headlines: `line-height: 1.0–1.06`, `letter-spacing: -0.02 to -0.025em`, `margin: 0`. The cover headline is uppercase and centered; content headlines are sentence case, left-aligned.
- Body: `line-height: 1.4`, `text-wrap: pretty`.
- Minimum size anywhere on the canvas: 24px.

### Line breaking (the rule that took the longest to get right)

Copy length is unknown at design time, so **the container must define the measure, not the text**.

- **Never** cap body copy with a `ch` max-width.
- **Never** use `text-wrap: balance` on body copy — it splits a sentence into even halves and breaks mid-phrase ("Sie soll die Inflation bei / Geldanlagen ausgleichen").
- `text-wrap: pretty` only, so copy runs the full width of its card or column and wraps where it must.
- `white-space: nowrap` only on figures and amounts (`1.500 €`), never on sentences.
- When a break must land in a specific place, express it structurally: one `<div>` per sentence in a `flex-direction: column` stack. Don't chase it with widths.
- Use `&nbsp;` inside amounts so the currency symbol never orphans.

## 3. Signature devices

1. **Highlight block on the last word** of a headline: `background: navy; color: accent; padding: 2px 16px 8px; display: inline-block` on light slides; inverted (off-white block, navy text) on ink slides. One per headline, last word or short phrase only. On the cover the highlight is accent-colored *words*, not a block.
2. **Cover layout**: six approved architectures, one picked per post, never twice in a row. Full spec and the rotation rule in §6. Common to all of them: uppercase slab headline, at most two supporting lines, and **nothing else on the cover** — no source, no @handle, no counter, no category chip, no label above the headline. The hook is the whole slide.
3. **Pill rows** for figure lists: `border-radius: 100px`, label left (32px/500), figure right in display size. Alternate white / navy fills down the stack.
4. **Rounded cards**: `border-radius: 20–24px`, no border, `box-shadow: 0 22px 44px -16px rgba(21,27,32,0.30)` on light grounds, `rgba(0,0,0,0.45)` on ink. Single, neutral, directional.
5. **Arrow list** (`→` in display size, accent or inherited color) instead of bullets or dots.
6. **Question badge** — the plain-language explainer card on slide 3 leads with an 84px navy circle holding a 60px Zilla Slab `?` in accent blue, placed in an 84px grid column that spans every text row of the card (`grid-template-columns: 84px 1fr; column-gap: 28px; grid-row: span N`). It echoes the 80px arrow track used by the lists below it, so both read as one system. One badge per deck, on the definition card only.
7. **Seat arc** — the default chart for a whole-chamber vote. See §4.
8. **Vote bars** — the compact alternative: 26px tall, `border-radius: 100px`, track `rgba(21,27,32,0.14)`, fill navy. A "No" is an **empty outlined track** (`border: 2px solid rgba(21,27,32,0.35)`, transparent fill) labelled `0 %` — never a filled bar, which reads as approval.

## 4. Charts

### Seat arc (`Seat Arc Slide.dc.html`)

- **Always on the off-white ground.** CDU/CSU's party color is `#151B20` — the ink ground itself. On ink the largest fraction's 208 dots disappear completely, leaving a hole through the middle of the arc, and its legend swatch goes with them. The party colors are fixed by §1 and the grounds alternate, so the constraint lands on the cover: **a deck with a seat arc takes a dark cover** (`1a`, `1b`, `1d`, `1f`), which puts slide 2 on off-white. Four variants still rotate; the alternation rule is untouched.
- **630 dots** — the real size of the current 21st Bundestag. Roster: CDU/CSU 208, AfD 152, SPD 120, Grüne 85, Linke 64, SSW 1. Keep this current; the FDP holds no seats and must not appear.
- Seated left to right in real chamber order: Linke, SSW, Grüne, SPD, CDU/CSU, AfD.
- **Filled dot = Ja** in that party's own color. **Hollow dot with that same color as its contour = dagegen or enthalten** — so internal dissent is visible inside each wedge, and one unique color per fraction.
- Centre of the arc holds the result in display size plus one small line: `335` / `von 316 benötigten`. The threshold is stated **once** on the slide — not repeated in the note below.
- Geometry is derived, never hardcoded: `W = 2 * (ro + DOT + PAD)`, `cx = W / 2`, `cy = ro + DOT + PAD`, `viewBox = "0 0 W H"`. A hardcoded viewBox clips the edge seats.
- Inner radius must clear the centre label box (`ri ≈ 260` for a ~460px line). Verify no dot overlaps the label.
- Legend below the arc, 2 columns, 24px: swatch + fraction + `Ja von Sitzen` (`183 von 208`), plus one key row explaining the hollow circle.

### Other options in the family

Stacked majority bar (compact, shows how close it was), Ja/Nein/Enthaltung rows per fraction (when dissent is the story), waffle grid (100 dots, for lay audiences), voting-record strip (one MP, one square per vote), deviation dot plot (MPs vs. their fraction line).

### Chart integrity

- One vote, one set of numbers: figures must agree across every slide and every chart.
- Party name + bar/dot only. No logos or trademarked marks.
- Always name the source and the Wahlperiode in the footer.

## 5. Slide skeleton

```
section  padding: 84px 76px 60px; display: flex; flex-direction: column
  h1/h2                      ← slide opens directly on the headline
  div  flex: 1; justify-content: center; gap: 34–48px   ← content region
  div  footer: page counter left, source/handle right (24px, opacity .75)
```

- The content region is `flex: 1` and **vertically centered** — this is what keeps the bottom of the frame from going empty.
- The cover has `padding: 0` on the section: photo block, then the ink panel carries its own padding.
- Footers on content slides only (2–5). The cover has none.
- A note or takeaway line under a card sits behind a full-width hairline (`border-top: 2px solid rgba(21,27,32,0.18)`), never next to a short stub bar.

## 6. Slide 1 — six cover variants (`Cover Options.dc.html`)

A recurring account dies of sameness. The cover is therefore the **only slide with a variable architecture**: six layouts, all built from the same two grounds, two fonts and three sizes, so the profile stays recognisable while no two posts look stamped from one mould.

### 6.1 Selection rule — enforce it in the workflow, not by taste

Covers are **chosen mechanically, never by mood**:

1. Filter by fit. `1a`/`1c` need a figure; `1c` needs a real before/after pair; `1b` needs a question a reader would actually type; `1d`/`1e`/`1f` need a photo that shows something. A photo that illustrates nothing (calculator, coin stack, stock-photo handshake) disqualifies every photo variant — fall back to `1a` or `1b`. **A seat arc on slide 2 disqualifies the light covers** (`1c`, `1e`): the arc has to sit on off-white, and the grounds alternate from the cover. See §4.
2. From the variants that remain, pick at **random**, excluding the last two used. Keep the last two ids in the posting workflow (one field, e.g. `lastCovers: ["1e","1a"]`) and exclude them from the draw. That guarantees a gap of three posts before a layout repeats and still alternates ground: dark (`1a`, `1b`, `1d`, `1f`) vs. light (`1c`, `1e`).
3. If the draw leaves nothing eligible, widen to "exclude the last one only" — never hand-pick a favourite, and never post the same architecture twice running.

For automation, a valid implementation is one line: `pick(eligible.filter(id => !lastCovers.includes(id)))`, then unshift the result onto `lastCovers` and truncate to 2.

### 6.2 Shared cover frame — true for all six

| Property | Value |
|---|---|
| Canvas | 1080 × 1350, `box-sizing: border-box` |
| Grounds | ink `#151B20` (1a, 1b, 1d, 1f) or off-white `#FAFAF8` (1c, 1e). Never a third ground |
| Headline | Zilla Slab 700, uppercase, `line-height: 1.02–1.04`, `letter-spacing: -0.025em`, `margin: 0` |
| Accent | exactly one accent move per cover: either accent-blue words (`#6FA0C8` on ink) or one highlight block (navy ground, accent text) on light. Never both |
| Support copy | 32px / `line-height: 1.4`, one `<div>` per sentence in a `flex-direction: column` stack, `gap: 12px`. One or two lines, never three |
| Vertical rhythm | content region `flex: 1; justify-content: center` so the block sits optically centred regardless of headline length |
| Type sizes | three per cover, no exceptions (see each variant) |
| Figures | `white-space: nowrap` + `&nbsp;` before `€` |
| Forbidden | footers, counters, sources, handles, eyebrows, rotated rails, emoji (the one permitted emoji lives on slide 4, never on the cover) |

**Length flexibility (the part that must not be hand-tuned).** Headlines run 3 to 14 words in practice, so every variant is built to absorb that without edits:

- No fixed heights and no `min-height` on any text block. Text areas are `flex: 1` with `justify-content: center`; photo blocks are the only `flex: none` elements.
- No `max-width` in `ch` and no `text-wrap: balance` anywhere on the cover. The padding box is the measure. `text-wrap: pretty` on support copy only.
- The headline is allowed to grow into the space the support copy doesn't use, because the whole stack is centred, not top-anchored. A long headline simply pushes the gaps outward.
- Every horizontal pairing is `baseline`-aligned with a fixed label track and an `auto` figure track, so a longer label never shifts the figure's baseline.
- Only if a headline exceeds ~14 words: cut words. Never tighten `line-height` below 1.0, never add a fourth size.
- **Headlines break at most 3 lines.** Hyphenation carries the load first: `hyphens: auto` with `hyphenate-limit-chars: 12 5 5`, so only words of 12+ characters break and never with a fragment shorter than 5. German compounds then break at the seam (`ELEKTROKLEINST-FAHRZEUGE`), and familiar short words (`PAUSCHALE`, `PROGRESSION`) stay whole.
- Only where that is not enough, the renderer steps the display size down in 8px stops until the headline fits 3 lines, never below 56px. It measures the rendered line boxes, so the step is exact rather than estimated. The smaller size **replaces** the 96 or 80, it does not add a size — the same shape as the 240 → 200 hero exception in §6.3.
  This is a last resort, not a licence: the right fix for a four-line headline is a shorter headline, and the renderer prints the step it took so the next draft can cut words instead. Without it a long compound simply took four lines at 96px, which breaks the cover — the support copy is pushed out of the stack and each line carries a single word fragment.

### 6.3 The variants

**1a Zahl zuerst** — no photo. Use when a single sum *is* the news.
`padding: 96px 76px 84px`, column, `justify-content: center`, `gap: 52px`. Hero figure 240px Zilla Slab 700 in accent (`line-height: 0.9`, `letter-spacing: -0.04em`, `nowrap`) directly above the 96px uppercase headline in off-white, no gap between them (one flex column, no `gap`) so they read as one block. Then a hairline `border-top: 3px solid rgba(250,250,248,0.28); padding-top: 40px` over one or two 32px lines, the second at `rgba(250,250,248,0.82)`. Sizes: 240 / 96 / 32. If the figure is longer than `1.500 €` (e.g. `12.500 €`), drop the hero to 200px — that is the only permitted deviation, and it replaces the 240, it doesn't add a size.

**1b Frage** — no photo. Use for explainers and anything people actually search.
`padding: 96px 76px 84px`, column, centred on both axes, `gap: 56px`, `text-align: center`. 200px off-white disc (`border-radius: 50%`, `flex: none`) holding a 140px Zilla Slab `?` in navy — the same device as the slide-3 badge, scaled up. Headline 96px uppercase with one or two accent-blue words. One 32px line at `rgba(250,250,248,0.82)`. Sizes: 96 / 32 (plus the badge glyph, which is a graphic, not type). The question must end in a question mark and must be answerable by the carousel.

**1c Vorher / Nachher** — light ground, no photo. Use when the change is two numbers.
`padding: 96px 76px 84px`, column, `justify-content: center`, `gap: 64px`. Headline 96px navy with the highlight block on the last word. Then a `gap: 28px` column of two rows, each `display: flex; align-items: baseline; gap: 28px`: a 32px/700 label in a `width: 150px; flex: none` track (`bisher` / `ab <Jahr>`) and the figure at 96px Zilla Slab. The old figure is **solid `#6E7C88`** with `text-decoration: line-through; text-decoration-thickness: 6px` — never an alpha tint, which fails contrast and violates §1. The new figure is full navy. Close with a `border-top: 3px solid rgba(34,51,65,0.18); padding-top: 40px` and one 32px line. Sizes: 96 / 32. Widen the label track past 150px only if a label wraps; both rows share the track so the figures stay flush.

**1d Senkrechter Schnitt** — photo left, full height. Use for portraits and upright scenes.
Section is `display: flex`, no padding. Left `width: 430px; flex: none; position: relative` photo column (full 1350 height, `fit="cover"`). Right column `flex: 1; min-width: 0; padding: 80px 64px`, centred column, `gap: 44px`. Headline **80px** (not 96 — the column is 650px wide) with accent words. One or two 32px lines at `0.82`. Sizes: 80 / 32. `min-width: 0` on the text column is load-bearing: without it a long unbroken word blows the photo column out.

**1e Foto unten** — light ground, mirrored baseline. The direct swap for the standard cover.
Column section, no padding. Text block first: `flex: 1; padding: 88px 76px`, centred, `gap: 40px`, headline 96px navy with the highlight block, then one 32px line. Photo block second: `height: 660px; flex: none`. Sizes: 96 / 32. The photo is fixed and the text block is elastic, so a longer headline eats its own whitespace and never pushes the image off-canvas.

**1f Vollbild mit Band** — photo over the whole canvas. Use only for a genuinely strong image and a short headline.
Section `position: relative`, ink fallback ground, one full-bleed `image-slot`. The text sits in an absolutely positioned band: `left: 0; right: 0; bottom: 0; background: #151B20; padding: 64px 72px 76px`, column, `gap: 32px`, headline 96px with accent words, one 32px line. Sizes: 96 / 32. The band is **solid ink, never a gradient or a translucent scrim**, and it grows upward with the text — which is why the headline here stays under about 8 words, or it swallows the photo. If the copy needs more room, switch to `1e`.

## 7. Slide 3 — den Begriff erklären

Slide 3 explains the one term the whole story hangs on, at the level of a smart 15-year-old: headline `Was ist ein <Begriff>` with the term in the highlight block, one white card (led by the question badge, §3.6) of plain-language explanation ending in a concrete worked example ("Bei 1.500 € Zinsen … zahlst du 0 € Steuern"), then a second section `Warum überhaupt ändern?` as 2–3 arrow bullets giving the reasons the change was debated. No jargon, no nested clauses.

## 8. Slide 4 — pick the pattern that fits the fact

Slide 4 answers "was heißt das für dich". There is **no default layout: choose one of the four patterns by what kind of change you are reporting.** Samples live in `Slide 4 Options.dc.html`. Picking wrong is the most common way this slide fails — a pill row full of prose, or a table for something that isn't numeric.

| Pattern | Use when | Shape |
|---|---|---|
| **4a Vorher / Nachher** | the change is quantitative | One card, grid `1fr auto auto`, column heads `bisher` (24px muted) / `ab <Jahr>` (24px bold). Row label 32/700 left, old value 32px muted, new value 80px display, both right-aligned, `align-items: baseline`. Anything that is *not* a before/after (a deadline, an action) leaves the table and becomes its own pill row below. |
| **4b Gilt für dich / gilt nicht** | eligibility is the story | Filled navy `Ja, wenn` card over an outlined `Nein, wenn` card, each a bullet list: 30px stroke icon (check / cross, `stroke-width: 2.4`, `margin-top: 7px`) + text in a `flex` row, `gap: 20px`, `align-items: flex-start`. |
| **4c Checkliste** | the change is automatic, or needs steps | Big payoff card first — `Nichts.` in display size plus one line of explanation — then `Nur in diesen Fällen musst du selbst ran` as arrow rows. The strongest pattern when the honest answer is "you don't have to do anything". |
| **4d Zwei Fälle** | an abstract rule needs a concrete case | Two labelled cards side by side (one white, one navy), same metrics in the same order under each: pictogram, case label 32/700, then `24px label / 80px figure` pairs. |

### Alignment rules that make these hold up

- **Arrow rows:** the arrow is 80px display type, but it must sit in `height: 45px; display: flex; align-items: center; line-height: 1` inside an 80px grid track. That centres the glyph on the **first line** of its text, so arrow and copy stay aligned whether the text runs one line or three. Never align an arrow with `line-height` tweaks.
- **Two-column compares (4d):** use **CSS subgrid** so the rows line up across both cards no matter how the headers wrap. Parent `display: grid; grid-template-columns: 1fr 1fr; grid-template-rows: auto auto auto auto`; each card `grid-row: 1 / -1; grid-template-rows: subgrid; display: grid; row-gap: 22px; align-content: start`. Never equalise columns by hand-tuned heights or `min-height`.
- **Icons:** stroke-only geometric pictograms, `fill: none; stroke: currentColor`, `stroke-linecap/linejoin: round`. 30px for bullet marks, 46px for the card pictogram in 4d. They inherit the card's text color, so they work on white and navy alike. Never emoji, never filled illustrative graphics — an icon is structure, not decoration. The single emoji permitted on a 4c `payoff` (see §9) is type, not an icon, and never replaces one.
- Figures keep `white-space: nowrap`; labels never do.

## 9. Images

- Photography only — real photos, black-and-white or desaturated news imagery.
- Cover: sized by the chosen variant (§6.3) — 430px column, 660px block, or full bleed. Later slides: `border-radius: 20–22px` frames, 270–290px tall, full column width.
- Use a drop-target placeholder while unfilled. Never ship a hand-drawn SVG illustration or generated-looking graphic.

---

## Do

- Open every slide on its headline.
- Keep the cover to headline + one line over the photo; metadata belongs on later slides.
- Keep three font sizes; differentiate with weight, color and case.
- One highlight block per headline.
- Center the content region vertically so the canvas is filled.
- Let copy fill its container and wrap on its own; control breaks structurally, one block per sentence.
- Put real numbers in display type — the figure is the visual.
- Derive chart geometry from its radii and check the rendered bounds.
- Cite the source (and Wahlperiode, for votes) in the footer.
- Layout with flex/grid + `gap`.

## Don't

- ❌ **No eyebrow / kicker headings above a headline** (no "Bundestag Monitor", no "ECONOMICS", no "Stand heute"). Hard rule.
- ❌ **No rotated / vertical side rails** anywhere.
- ❌ No source line, handle or counter on the cover.
- ❌ No cover architecture two posts in a row, and no hand-picking a favourite — the variant is drawn per §6.1.
- ❌ No fixed or `min-height` text blocks on a cover. A long headline is cut, not typeset around — the display size drops only as the renderer's automatic last resort under the 3-line rule in §6.2, never by hand and never below 56px.
- ❌ No emoji — with exactly one exception: the `payoff` line of the 4c follow-up slide may carry a single leading emoji, and only when the topic was classified `oeffentlich` (sport, culture, education) by the topic selection. That line is also the only place in the deck allowed a light touch — "🇩🇪 Anfeuern." instead of "Nichts." on a sports-funding card. Everywhere else, including icons, CTAs, headlines and body copy, emoji stay out. Topics touching injury, illness, death, crime, war, poverty or discrimination stay plain even under that exception.
- ❌ No `ch` measures and no `text-wrap: balance` on body copy.
- ❌ No `white-space: nowrap` on sentences to force a one-liner.
- ❌ No em-dashes in copy. Use a colon, a comma or a full stop.
- ❌ No fourth font size; no third font family.
- ❌ No AI-default fonts: Inter, Poppins, Outfit, Plus Jakarta Sans, Montserrat, Roboto, DM Sans, Space Grotesk.
- ❌ No dot/circle bullet lists — use arrows.
- ❌ No soft ambient blur shadows on identical white cards (the stacked-card look this redesign replaced); no colored or offset hard shadows.
- ❌ No gradient backgrounds, no glow, no icon-in-rounded-square badges.
- ❌ No browns, creams or yellow; no party colors outside charts.
- ❌ No empty lower third: if content stops mid-frame, grow the content, don't pad it.
- ❌ No stale roster or seat total — 630 seats, no FDP.
- ❌ No seat arc on the ink ground: CDU/CSU is the ink color and vanishes into it. A vote deck draws a dark cover so slide 2 lands light.
- ❌ A "No" vote is never a filled bar or dot; it is an empty outlined track or a hollow dot.
- ❌ No fact stated twice on the same slide.
- ❌ No party logos or trademarked marks.
- ❌ No prose where a pattern fits: slide 4 is never free text — pick 4a/4b/4c/4d.
- ❌ No hand-tuned heights or `min-height` to line up two columns — that is what subgrid is for.
- ❌ No arrow aligned by `line-height`; use the 45px centring box.
- ❌ No filler copy: every line carries a fact, a number or a consequence.

## Content voice

Short declaratives, German, du-form. Lead with the decision or the number, then the consequence. One idea per card; the card title states it, the line beneath explains why it matters. Numbers always with their basis (`335 von 316 benötigten`, `183 von 208`).
