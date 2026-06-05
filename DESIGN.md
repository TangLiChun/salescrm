---
name: Sales CRM
description: A field instrument for network-operator outreach: ASN role-email lookup, AI lead discovery, contact pipeline.
colors:
  petrol: "oklch(0.48 0.088 222)"
  petrol-strong: "oklch(0.42 0.090 222)"
  petrol-ink: "oklch(0.43 0.085 222)"
  petrol-tint: "oklch(0.95 0.02 222)"
  paper: "oklch(0.972 0.006 88)"
  surface: "oklch(0.993 0.004 88)"
  surface-sunk: "oklch(0.952 0.007 88)"
  ink: "oklch(0.28 0.022 256)"
  ink-soft: "oklch(0.40 0.02 256)"
  ink-muted: "oklch(0.49 0.016 256)"
  line: "oklch(0.895 0.006 90)"
  positive: "oklch(0.50 0.075 155)"
  caution: "oklch(0.60 0.09 72)"
  danger: "oklch(0.53 0.135 28)"
  on-accent: "oklch(0.985 0.004 88)"
typography:
  headline:
    fontFamily: "Inter, system-ui, -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif"
    fontSize: "1.375rem"
    fontWeight: 650
    lineHeight: 1.25
    letterSpacing: "-0.01em"
  title:
    fontFamily: "Inter, system-ui, -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif"
    fontSize: "1.125rem"
    fontWeight: 650
    lineHeight: 1.3
    letterSpacing: "-0.01em"
  body:
    fontFamily: "Inter, system-ui, -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.55
    letterSpacing: "normal"
  label:
    fontFamily: "ui-monospace, 'SF Mono', 'JetBrains Mono', Menlo, monospace"
    fontSize: "0.75rem"
    fontWeight: 600
    lineHeight: 1.4
    letterSpacing: "0.04em"
  data:
    fontFamily: "ui-monospace, 'SF Mono', 'JetBrains Mono', Menlo, monospace"
    fontSize: "0.8125rem"
    fontWeight: 500
    lineHeight: 1.5
    letterSpacing: "normal"
    fontFeature: "tabular-nums"
rounded:
  xs: "4px"
  sm: "6px"
  md: "8px"
  lg: "12px"
  pill: "999px"
spacing:
  "1": "4px"
  "2": "8px"
  "3": "12px"
  "4": "16px"
  "5": "20px"
  "6": "24px"
  "8": "32px"
components:
  button-primary:
    backgroundColor: "{colors.petrol}"
    textColor: "{colors.on-accent}"
    rounded: "{rounded.sm}"
    padding: "12px 16px"
  button-primary-hover:
    backgroundColor: "{colors.petrol-strong}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink-soft}"
    rounded: "{rounded.sm}"
    padding: "12px 16px"
  button-success:
    backgroundColor: "{colors.positive}"
    textColor: "{colors.on-accent}"
    rounded: "{rounded.sm}"
    padding: "12px 16px"
  tab-active:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.petrol-ink}"
    rounded: "{rounded.sm}"
    padding: "8px 16px"
  chip-role:
    backgroundColor: "{colors.petrol-tint}"
    textColor: "{colors.petrol-ink}"
    rounded: "{rounded.xs}"
    padding: "1px 8px"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "8px 12px"
  panel:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.lg}"
    padding: "20px"
---

# Design System: Sales CRM

## 1. Overview

**Creative North Star: "The Field Instrument"**

This is the interface of a precision instrument resting on engineering paper. The operator
is a sales or BD professional working network-infrastructure contacts (ASNs, ARIN role
emails, peering desks), reading dense tables in daylight for long stretches. The system
exists to make that reading exact and trustworthy. It is calm, it is engineered, and it
disappears into the task. It is an instrument, not a toy.

Two tensions carry the whole look. First, warm against cool: the canvas is a warm paper
neutral, the text is a cool blue-grey ink. That paper-and-ink contrast is what makes a
surface read as a measuring tool rather than a generic app. Second, prose against data:
human labels are set in a humanist sans, while every machine identifier (ASN, email,
handle, timestamp, count, score) is set in tabular monospace so columns align and digits
can be trusted at a glance.

The system explicitly rejects the generic blue-and-white B2B SaaS template. There is no
stock Tailwind blue, no pure-white floating cards, no soft drop-shadow haze, no pastel
badge soup, no hero-metric dashboard. If a stranger could guess the palette from the
category alone (a B2B tool, so it must be blue), the design has failed. The petrol accent
and warm paper are the antidote to that reflex.

**Key Characteristics:**
- Warm paper surfaces, cool ink text, one committed petrol accent.
- Machine data in tabular monospace; human language in a humanist sans.
- Hairline borders over shadows. Flat at rest, dense by intent.
- A restrained, low-chroma status palette where every color maps to a real state.
- Honest interaction states everywhere: hover, focus, disabled, empty, error.

## 2. Colors: Petrol on Warm Paper

A near-monochrome warm-paper field, anchored by a single deep petrol accent, with a muted
signal set reserved for status.

### Primary
- **Petrol** (`oklch(0.48 0.088 222)`): The one committed accent. Carries primary actions,
  links, active navigation, progress fills, focus rings, and the role chip. A deep teal-blue
  that is deliberately not stock blue. For text and links on paper it deepens to **Petrol Ink**
  (`oklch(0.43 0.085 222)`) to hold WCAG AA; on hover, fills darken to **Petrol Strong**
  (`oklch(0.42 0.090 222)`).

### Neutral
- **Paper** (`oklch(0.972 0.006 88)`): The app canvas. A warm off-white, never `#fff`.
- **Surface** (`oklch(0.993 0.004 88)`): Panels, cards, inputs. A warm near-white that sits
  just above the paper.
- **Surface Sunk** (`oklch(0.952 0.007 88)`): Table headers, toolbars, insets, note items,
  the sunken layer that recedes.
- **Ink** (`oklch(0.28 0.022 256)`): Primary text. A cool blue-grey, never pure black.
- **Ink Soft / Ink Muted** (`oklch(0.40 0.02 256)` / `oklch(0.49 0.016 256)`): Secondary
  labels, captions, helper text, table headers.
- **Line** (`oklch(0.895 0.006 90)`): Hairline borders and dividers, tinted warm like a
  crease in paper.

### Tertiary (Muted Signal Set)
Reserved strictly for status, never decoration. Each is low-chroma so the surface stays calm.
- **Positive** (`oklch(0.50 0.075 155)`): Moss green. Sent / enabled / interested / success.
- **Caution** (`oklch(0.60 0.09 72)`): Ochre. Unsent / contacted / in-progress, a gentle nudge.
- **Danger** (`oklch(0.53 0.135 28)`): Clay red. Errors and destructive actions only.

### Named Rules
**The One Petrol Rule.** There is exactly one accent hue. Petrol marks what is actionable or
active and nothing else. If two accents appear on a screen, one is wrong.

**The Warm-and-Cool Rule.** Surfaces are tinted warm (hue ~88), ink is tinted cool (hue ~256).
This tension is load-bearing. Never flatten both to a neutral grey, and never invert it.

**The No-Pure Rule.** Never `#fff` and never `#000`. Every neutral is tinted toward paper or ink.

## 3. Typography: Prose and Data

**Body / Display Font:** Inter, falling back to the native system sans (`system-ui`,
`-apple-system`) and CJK faces (`PingFang SC`, `Microsoft YaHei`, `Noto Sans SC`).
**Data / Label Font:** the platform monospace stack (`ui-monospace`, `SF Mono`,
`JetBrains Mono`, `Menlo`), always with `tabular-nums`.

**Character:** One humanist sans does all the talking; one monospace does all the counting.
The pairing reads as a working instrument: warm enough for Chinese-first labels, exact enough
for machine identifiers. No display or decorative faces appear anywhere.

### Hierarchy
- **Headline** (650, 1.375rem / 22px, line-height 1.25): Page title in the header. One per view.
- **Title** (650, 1.125rem / 18px, line-height 1.3): Panel and section headings (查询结果, 联系人列表).
- **Body** (400, 0.875rem / 14px, line-height 1.55): Default text and form values. Prose caps at 65-75ch.
- **Label** (600, 0.75rem / 12px, letter-spacing 0.04-0.18em, UPPERCASE, mono): The eyebrow
  kicker, table headers, chart titles, the default-account heading. The instrument's engraved labels.
- **Data** (500, 0.8125rem / 13px, mono, tabular-nums): Every ASN, email, handle, timestamp,
  score, and figure.

### Named Rules
**The Machine-Data-Is-Monospace Rule.** Any value a machine produced (ASN, email, handle, ID,
timestamp, count, score, score ramp) is monospace with tabular figures. Any value a human wrote
(org name, contact name, note body) is sans. This split is non-negotiable; it is how the operator
trusts the columns.

**The Engraved-Label Rule.** Structural labels (kickers, table headers, chart titles) are small,
uppercase, letter-spaced monospace. They read like markings stamped into an instrument panel.

## 4. Elevation

The system is flat by default. Depth comes from tonal layering (paper, surface, surface-sunk) and
hairline borders, not from shadows. A surface is defined by a 1px warm line, not by a glow. Two
shadows exist, both functional, never decorative: a barely-there lift on resting panels, and a real
pop reserved for overlays that must float above everything.

### Shadow Vocabulary
- **Resting Lift** (`box-shadow: 0 1px 2px oklch(0.28 0.03 256 / 0.06), 0 1px 1px oklch(0.28 0.03 256 / 0.04)`):
  A near-invisible lift on panels and the active tab chip, just enough to separate them from the canvas.
- **Overlay Pop** (`box-shadow: 0 20px 44px -14px oklch(0.26 0.05 256 / 0.30), 0 4px 12px -6px oklch(0.26 0.05 256 / 0.14)`):
  Modals only. The one place real elevation is allowed.

### Named Rules
**The Hairline-First Rule.** Reach for a 1px line before a shadow. If a box needs definition, give it
a border. Shadows are a last resort, and only the two above exist.

**The Flat-2014-Test.** If a card looks like a 2014 app, the shadow is too dark and the radius too round.
Pull the shadow toward zero and the corner toward 6-12px.

## 5. Components

### Buttons
- **Shape:** Gently squared corners (6px radius). Never pill-shaped, never sharp.
- **Primary:** Solid petrol fill with paper-white text, 12px x 16px padding. The single loud action
  per context (开始查询, 保存设置, AI 开始找线索).
- **Success:** Solid moss fill, reserved for committing imported data (导入选中联系人, 导入选中线索).
- **Secondary / Ghost:** Warm surface fill with a hairline border and ink-soft text. All utility actions
  (刷新, 导出 CSV, 退出登录). Hover lifts the border and text toward ink.
- **Text (link) buttons:** Petrol-ink, underline on hover. Used for inline row actions.
- **Hover / Focus:** 150ms ease-out on color; a 0.5px press translate on active; a 2px petrol focus
  outline with 2px offset on keyboard focus, always visible.

### Chips and Badges
- **Role chip:** Monospace, petrol-tint background, petrol-ink text, hairline petrol border, 4px radius.
  Roles are machine tokens (abuse, technical, noc), so they are mono.
- **Source tag:** Sans, neutral surface-sunk background, hairline border. A quiet provenance label.
- **Score badge:** Monospace, tabular, neutral bordered readout with a min-width so scores align.
- **Status badge:** A pill with a leading 5px dot in the status color, low-chroma tint background, and
  matching text. The dot means status is never carried by color alone.

### Cards / Containers
- **Corner Style:** 12px radius on panels, 8px on inner surfaces.
- **Background:** Surface over the paper canvas.
- **Shadow Strategy:** Resting Lift only (see Elevation). Modals use Overlay Pop.
- **Border:** Always a 1px warm hairline. The border, not the shadow, defines the box.
- **Internal Padding:** 20px on panels; 16px on insets. Nested cards are forbidden.

### Inputs / Fields
- **Style:** Surface background, 1px strong-hairline stroke, 6px radius, 8px x 12px padding.
- **Focus:** Border shifts to petrol with a 3px petrol-tint ring. No glow, no color flood.
- **Placeholder:** Ink-faint. Native `accent-color` is petrol, so checkboxes and selects tint to brand.

### Navigation
- **Style:** A single segmented toolbar, inset in a surface-sunk track with a hairline border. Tabs are
  text in ink-soft; the active tab is a raised surface chip with petrol-ink text and a Resting Lift.
- **States:** Inactive hover warms the background; active reads as a physically raised key.
- **Mobile:** The toolbar scrolls horizontally rather than wrapping, staying one continuous strip.

### Signature: The Readout Strip
The stats summary is not a grid of identical metric cards. It is one bordered readout bar divided by
hairlines, each cell showing a large monospace tabular number above a small uppercase label, like the
display of a measuring instrument. This is the deliberate antidote to the hero-metric dashboard cliche.

### Signature: The Data Table
Dense, hairline-ruled, with a sticky surface-sunk header in engraved uppercase labels. Machine columns
(ASN, email, handle, time) are monospace; human columns are sans. Rows warm on hover; sent rows carry a
faint positive tint. This table is the core working surface and earns the most density.

## 6. Do's and Don'ts

### Do:
- **Do** keep exactly one accent: petrol (`oklch(0.48 0.088 222)`) for actions, links, active state, focus.
- **Do** set every machine identifier (ASN, email, handle, timestamp, score, count) in tabular monospace.
- **Do** define surfaces with 1px warm hairlines; reach for a border before a shadow.
- **Do** tint every neutral, warm for surfaces (hue ~88), cool for ink (hue ~256).
- **Do** pair every status color with a dot or text label, so status never relies on color alone.
- **Do** give each interactive element honest hover, focus, disabled, empty, and error states.
- **Do** keep the status palette low-chroma and semantic: moss = positive, ochre = pending, clay = danger.

### Don't:
- **Don't** introduce stock Tailwind blue (`#2563eb`) or any second accent. The category reflex is blue; refuse it.
- **Don't** use pure-white floating cards, soft drop-shadow haze, or pastel badge soup.
- **Don't** build a hero-metric dashboard. Use the Readout Strip instead.
- **Don't** use `#fff` or `#000`; every neutral is tinted toward paper or ink.
- **Don't** add consumer-playful gradients, gradient text, or decorative glassmorphism.
- **Don't** color non-destructive actions red; only true deletions are clay-red.
- **Don't** nest cards, round corners past 12px, or let any interface read as "AI made this dashboard."
