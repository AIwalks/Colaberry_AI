# Skill: frontend_design

## Purpose

Define the visual and UX standards for rendering AI-generated insight cards in a modern, clean, high-signal interface.

This skill is not code — it is the **design contract** that governs how insight data is presented to end users. Any frontend component that renders insights must follow these standards. The goal is a production-ready UI that communicates AI output with clarity, trust, and intent — not a generic dashboard widget.

---

## Design Intent

Inspired by premium frontend design systems (Linear, Vercel, Stripe):

- **Structured layout** — every field has a defined visual role; nothing floats or competes
- **Strong spacing** — generous internal padding; elements breathe
- **Clear information hierarchy** — title dominates, supporting fields follow in a deliberate reading order
- **Polished, high-impact UI** — subtle elevation, refined typography, purposeful color use

The interface should feel like a product decision was made about every pixel — not like raw API output pasted into a box.

---

## Inputs

Each rendered insight card receives the following data:

| Field                | Type    | Description                                              |
|----------------------|---------|----------------------------------------------------------|
| `title`              | str     | Short label summarizing the insight                      |
| `confidence`         | float   | Model certainty (0.0 – 1.0)                              |
| `entity_type`        | str     | Who the insight is about (e.g. "student", "cohort")      |
| `explanation`        | str     | Human-readable description of what the insight means     |
| `recommended_action` | str     | Concrete next step for a human to take                   |
| `insight_type`       | str     | Category: "kpi" or "risk"                                |

---

## Outputs

A visually complete card component that presents the above data with:

- A **card container** with consistent padding, border radius, and subtle shadow
- A **title row** with the insight title and type badge side-by-side
- A **metadata row** showing entity type as a subtle label
- A **confidence indicator** rendered as a prominent chip/badge with numeric percentage
- An **Explanation section** with a clear section label above the body text
- A **Recommended Action section** with a clear section label and visually distinct treatment

---

## Rules

### Card Container
- Padding: `20px 24px`
- Border radius: `10px`
- Box shadow: `0 2px 8px rgba(0,0,0,0.07)`
- Background: white or a very subtle tint; never a heavy colored background
- Left border accent: `4px solid` in the type color (green for KPI, red for Risk)
- Border: `1px solid #e5e7eb`
- No gradient backgrounds on the card itself

### Typography
- Title: `17px`, `font-weight: 700`, `color: #111827`
- Section labels: `11px`, `font-weight: 700`, `text-transform: uppercase`, `letter-spacing: 0.07em`, `color: #9ca3af`
- Body text (explanation, action): `14px`, `line-height: 1.6`, `color: #374151`
- Metadata row: `12px`, `color: #6b7280`
- All text must be left-aligned

### Spacing
- Between title row and metadata row: `6px`
- Between metadata row and confidence row: `12px`
- Between confidence row and first section: `16px`
- Between sections: `12px`
- Section label to section body: `4px`

### Confidence Badge
- Render as a filled chip: background in the type color family, bold percentage value
- Example: KPI at 85% → green chip: `#dcfce7` background, `#15803d` text, value `85%`
- Risk at 72% → red chip: `#fee2e2` background, `#b91c1c` text, value `72%`
- Include the label "Confidence" before the chip so context is clear
- Badge size: `font-size: 12px`, `font-weight: 700`, `padding: 3px 10px`, `border-radius: 20px`

### Type Badge
- Rendered in the title row, flush right
- Short uppercase label: `KPI` or `RISK`
- Same color family as confidence badge
- `font-size: 11px`, `font-weight: 700`, `letter-spacing: 0.06em`

### Explanation Section
- Label: `EXPLANATION` (uppercase, small, muted)
- Body: full paragraph text, 14px, `color: #374151`
- No border, no box — just clean label + text

### Recommended Action Section
- Label: `RECOMMENDED ACTION` (uppercase, small, muted)
- Body: 14px, `color: #374151`
- Visually set apart from explanation: use a very subtle top border (`1px solid #f3f4f6`) or increased spacing above
- Optionally: a thin left rule in the accent color to signal "this is the action"

### Entity Type Metadata
- Displayed below the title row as a one-line metadata strip
- Format: `Entity: student` or `Type: cohort`
- `font-size: 12px`, `color: #6b7280`
- No badge — just plain inline label

### What to Avoid
- Do not use heavy colored backgrounds on the card (ruins readability)
- Do not use emojis or icons unless a proper icon system is in place
- Do not render raw confidence floats (0.85) — always convert to percentage (85%)
- Do not stack confidence and type badge in the same chip
- Do not render the `body` field alongside `explanation` — they duplicate intent; show `explanation` only
- Do not add animations or transitions to cards
- Do not redesign the header, nav, filters, or input controls — only the card component
