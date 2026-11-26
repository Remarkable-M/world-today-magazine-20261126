# Design spec — "THE DAY IN BRIEF" (modern magazine edition)

A bold, modern editorial-magazine front page that sums up the world news of
Thursday 26 November 2026 in ONE square image. This is a second, deliberately
different entry in the same make.fun competition (news-image-20261126): the
first entry was a classic black-and-white broadsheet; this one is a colorful,
modern magazine cover — big type, color blocks, airy grid.

## Canvas and hard rules (competition requirements — non-negotiable)

- Entry point `main.py` (Python 3.13) at the REPO ROOT; it writes the image to
  `/output/entry.png` (honor `$OUTPUT_DIR` when set).
- Output: exactly 1024×1024 px, PNG, ≤ 1 MiB, deterministic (two runs →
  byte-identical output), NO network access at run time.
- Python standard library + Pillow only.
- ALL files live at the repo root — no subfolders: main.py, README.md, LICENSE,
  stories.json, hero.png, entry.png (a pre-rendered copy for fallback), and the
  font files (.ttf) the program loads BY PATH from the repo root.
- All visible text comes from stories.json — do not invent or alter headlines.
- Text must never overflow its box: measure with Pillow's text metrics, wrap,
  and shrink-to-fit. Margins ≥ 24 px on all sides.

## Look and layout (1024×1024)

Palette: white background #FFFFFF; deep navy ink #14213D; coral red #E63946;
teal #0E7C7B; gold #E9A13B; light grey #F2F2F2 for card separators.

1. Masthead (top, ~90 px):
   - "THE DAY IN BRIEF" in extra-bold grotesque sans, ~64 px, navy, left.
   - A coral-red block/rule under the title; on the same line at the right,
     the date_line "Thursday, 26 November 2026" in small caps grey-navy,
     and the tagline under it.
2. Lead block (~next 430 px):
   - hero.png as a full-width band (~300 px tall, cover-cropped).
   - A coral chip with the lead section name ("AI MARKETS") overlaid at the
     hero's top-left corner.
   - Lead headline below the hero, ~40 px extra-bold navy, up to 3 lines.
   - Lead summary ~16 px, dark grey, up to 3 lines; the caption in italic
     coral or small caps at the side if space allows (optional).
3. Story grid (next ~380 px): 3 columns. 11 stories from stories.json in
   order, flowed into the columns (4/4/3). Each story:
   - a small colored section chip (rotate navy → coral → teal → gold),
   - headline ~19 px bold navy, wrapped,
   - summary ~13.5 px dark grey,
   - thin light-grey divider between stories.
4. Footer band (~70 px): full-width navy band; inside, the On This Day title
   in gold bold + its text in white ~14 px (one or two lines), and the
   footer_note in small light text at the right or on a second line.

## Typography

- Headlines: a heavy grotesque (e.g. Archivo Black, or Archivo/Inter ExtraBold)
  — download the TTF(s) once at build time and COMMIT them at the repo root;
  the program loads fonts by path only (no system-font lookups), and must
  raise a clear error if a font file is missing.
- Body: a clean sans (Inter or Source Sans 3), regular + bold + italic.
- Render the superscript in "3.2×10⁻⁸" correctly (the 10⁻⁸ glyphs are in the
  stories.json string; the chosen fonts must contain them — if not, draw the
  exponent as a smaller raised run of text).

## Program behavior

- Read stories.json and hero.png from the repo root (script directory).
- Compose programmatically with Pillow: no pre-baked text in images.
- If the PNG exceeds 1 MiB, quantize (adaptive palette) until it fits.
- Keep a fallback: if Pillow is unavailable, copy the repo-root entry.png to
  the output path.
- After generating, verify: size 1024×1024, file ≤ 1 MiB, run twice and
  confirm identical bytes, and visually inspect the render for overflow.
