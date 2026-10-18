---
version: alpha
name: Uber
description: Bold black and white. Tight type. Urban energy.
colors:
  primary: "#000000"
  secondary: "#545454"
  tertiary: "#000000"
  neutral: "#EEEEEE"
  surface: "#FFFFFF"
  on-primary: "#FFFFFF"
typography:
  display:
    fontFamily: Inter
    fontSize: 4.5rem
    fontWeight: 800
    letterSpacing: "-0.04em"
  h1:
    fontFamily: Inter
    fontSize: 2.3rem
    fontWeight: 700
  body:
    fontFamily: Inter
    fontSize: 0.98rem
    lineHeight: 1.55
  label:
    fontFamily: Inter
    fontSize: 0.78rem
    fontWeight: 700
    letterSpacing: "0"
rounded:
  sm: 2px
  md: 4px
  lg: 6px
spacing:
  sm: 8px
  md: 16px
  lg: 32px
components:
  button-primary:
    backgroundColor: "{colors.tertiary}"
    textColor: "{colors.on-primary}"
    rounded: "{rounded.md}"
    padding: 12px 20px
  card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.primary}"
    rounded: "{rounded.lg}"
    padding: 24px
---
## Overview

Uber: bold monochrome mobility platform — tight muscular sans, urban rhythm, near-zero chrome.

## Colors

The palette is built around high-contrast neutrals and a single accent that drives interaction.

- **Primary (`#000000`):** Headlines and core text.
- **Secondary (`#545454`):** Borders, captions, and metadata.
- **Tertiary (`#000000`):** The sole driver for interaction. Reserve it.
- **Neutral (`#EEEEEE`):** The page foundation.

## Typography

- **display:** Inter 4.5rem
- **h1:** Inter 2.3rem
- **body:** Inter 0.98rem
- **label:** Inter 0.78rem

## Do's and Don'ts

- **Do** use Tertiary for exactly one action per screen.
- **Do** let Neutral carry the composition — negative space is a feature.
- **Don't** introduce gradients. This system is flat on purpose.
- **Don't** mix Tertiary with alternate accents; the single-accent rule is load-bearing.
