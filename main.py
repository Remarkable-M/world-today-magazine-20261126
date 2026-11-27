#!/usr/bin/env python3
"""THE DAY IN BRIEF - a modern magazine front page for Thursday 26 November 2026.

Composes one 1024x1024 PNG from stories.json and hero.png with Pillow, using
only the TrueType fonts committed beside this file (loaded by path).

Output: $OUTPUT_DIR/entry.png, or /output/entry.png when OUTPUT_DIR is unset.
Deterministic (no clock, no randomness, no network). If Pillow is not
installed, the pre-rendered entry.png from the repository root is copied to
the output path instead, so both paths publish the same bytes.
"""

import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.environ.get("OUTPUT_DIR") or "/output"
OUT_NAME = "entry.png"
MAX_BYTES = 1048576
W = H = 1024
MARGIN = 28          # outer margin for every text box (spec: >= 24 px)
SAFE = 24            # hard limit no glyph may cross

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # the stdlib-only sandbox: publish the pre-rendered page
    Image = None

# Palette (design-spec.md)
WHITE = (255, 255, 255)
NAVY = (0x14, 0x21, 0x3D)
CORAL = (0xE6, 0x39, 0x46)
TEAL = (0x0E, 0x7C, 0x7B)
GOLD = (0xE9, 0xA1, 0x3B)
LIGHT = (0xF2, 0xF2, 0xF2)
BODY = (0x3B, 0x41, 0x4F)       # dark grey body text
MUTED = (0x5A, 0x64, 0x7B)      # grey-navy for the date line
FOOT_NOTE = (0xA8, 0xB2, 0xC9)  # light text on the navy band
CHIP_COLORS = [(NAVY, WHITE), (CORAL, WHITE), (TEAL, WHITE), (GOLD, NAVY)]

FONT_FILES = {
    "display": "ArchivoBlack-Regular.ttf",
    "bold": "SourceSans3-Bold.ttf",
    "semi": "SourceSans3-Semibold.ttf",
    "regular": "SourceSans3-Regular.ttf",
    "italic": "SourceSans3-It.ttf",
}

SUPERSCRIPTS = {
    "\u2070": "0", "\u00b9": "1", "\u00b2": "2", "\u00b3": "3", "\u2074": "4",
    "\u2075": "5", "\u2076": "6", "\u2077": "7", "\u2078": "8", "\u2079": "9",
    "\u207a": "+", "\u207b": "-", "\u207c": "=", "\u207d": "(", "\u207e": ")",
}

LOG = {}     # field key -> words drawn, in order (for the verbatim check)
INK = []     # (key, ink bbox, allowed box) for the overflow check


# ----------------------------------------------------------------- fonts ---

_FONTS = {}


def load_font(face, size):
    key = (face, round(size * 8) / 8)
    if key not in _FONTS:
        path = os.path.join(HERE, FONT_FILES[face])
        if not os.path.isfile(path):
            raise FileNotFoundError(
                "font file missing: %s (main.py loads its fonts only from the "
                "repository root, next to main.py)" % path)
        _FONTS[key] = ImageFont.truetype(
            path, key[1], layout_engine=ImageFont.Layout.BASIC)
    return _FONTS[key]


_GLYPHS = {}


def _render_glyph(font, ch):
    side = int(font.size * 2) + 8
    im = Image.new("L", (side, side), 0)
    ImageDraw.Draw(im).text((4, 4), ch, font=font, fill=255)
    return im.tobytes()


def has_glyph(font, ch):
    """True when the font draws ch itself rather than its .notdef box."""
    key = (font.path, font.size, ch)
    if key not in _GLYPHS:
        drawn = _render_glyph(font, ch)
        missing = _render_glyph(font, "\U0010fffd")
        _GLYPHS[key] = drawn != missing and any(drawn)
    return _GLYPHS[key]


class Style:
    """One face, size and colour; measures words, faking absent superscripts."""

    _cache = {}

    def __new__(cls, face, size, fill):
        key = (face, round(size * 8) / 8, fill)
        if key not in cls._cache:
            obj = super().__new__(cls)
            obj._setup(face, key[1], fill)
            cls._cache[key] = obj
        return cls._cache[key]

    def _setup(self, face, size, fill):
        self.face, self.size, self.fill = face, size, fill
        self.font = load_font(face, size)
        self.sup_font = load_font(face, size * 0.62)
        self.asc = -self.font.getbbox("Hdhlk|", anchor="ls")[1]
        self.desc = self.font.getbbox("gjpqy|", anchor="ls")[3]
        self.cap = -self.font.getbbox("H", anchor="ls")[1]
        self.space = self.font.getlength(" ")

    def chunks(self, word):
        """Split a word into [text, fake_superscript] runs."""
        out = []
        for ch in word:
            fake = ch in SUPERSCRIPTS and not has_glyph(self.font, ch)
            if out and out[-1][1] == fake:
                out[-1][0] += ch
            else:
                out.append([ch, fake])
        return out

    def width(self, word):
        total = 0.0
        for text, fake in self.chunks(word):
            if fake:
                total += self.sup_font.getlength(
                    "".join(SUPERSCRIPTS[c] for c in text))
            else:
                total += self.font.getlength(text)
        return total


# ------------------------------------------------------------ paragraphs ---

class Para:
    """Greedy word wrap of styled runs, broken only at spaces."""

    def __init__(self, runs, width, line_h, first_indent=0.0, align="left"):
        self.width, self.line_h = width, line_h
        self.first_indent, self.align = first_indent, align
        self.words = []
        for text, style, key in runs:
            for word in text.split(" "):
                if word:
                    self.words.append((word, style, key, style.width(word)))
        self.ok = True
        self.lines = self._wrap()
        first = self.lines[0] if self.lines else []
        last = self.lines[-1] if self.lines else []
        self.asc = max((w[1].asc for w in first), default=0)
        self.desc = max((w[1].desc for w in last), default=0)
        self.height = self.asc + (len(self.lines) - 1) * line_h + self.desc

    def _wrap(self):
        lines, cur, cur_w = [], [], 0.0
        for item in self.words:
            avail = self.width - (0 if lines else self.first_indent)
            if not cur:
                if item[3] > avail:
                    self.ok = False
                cur, cur_w = [item], item[3]
                continue
            trial = cur_w + cur[-1][1].space + item[3]
            if trial <= avail:
                cur.append(item)
                cur_w = trial
            else:
                lines.append(cur)
                if item[3] > self.width:
                    self.ok = False
                cur, cur_w = [item], item[3]
        if cur:
            lines.append(cur)
        return lines

    def line_width(self, line):
        total = sum(w[3] for w in line)
        return total + sum(w[1].space for w in line[:-1])

    def draw(self, draw, x, y):
        box = (x, y, x + self.width, y + self.height)
        base = y + self.asc
        for i, line in enumerate(self.lines):
            cx = x + (self.first_indent if i == 0 else 0)
            if self.align == "right":
                cx = x + self.width - self.line_width(line)
            for word, style, key, wwidth in line:
                LOG.setdefault(key, []).append(word)
                draw_word(draw, cx, base, word, style, key, box)
                cx += wwidth + style.space
            base += self.line_h
        return box


def draw_word(draw, x, base, word, style, key, box):
    for text, fake in style.chunks(word):
        if fake:
            digits = "".join(SUPERSCRIPTS[c] for c in text)
            raised = base - style.size * 0.36
            draw.text((x, raised), digits, font=style.sup_font,
                      fill=style.fill, anchor="ls")
            ink = draw.textbbox((x, raised), digits, font=style.sup_font,
                                anchor="ls")
            x += style.sup_font.getlength(digits)
        else:
            draw.text((x, base), text, font=style.font, fill=style.fill,
                      anchor="ls")
            ink = draw.textbbox((x, base), text, font=style.font, anchor="ls")
            x += style.font.getlength(text)
        INK.append((key, ink, box))


def fit_para(make_runs, width, sizes, line_factor, max_lines, max_h=None):
    """Largest size whose wrap fits max_lines (and max_h); else the smallest."""
    para = None
    for size in sizes:
        para = Para(make_runs(size), width, size * line_factor)
        if para.ok and len(para.lines) <= max_lines and (
                max_h is None or para.height <= max_h):
            return para
    raise RuntimeError("text does not fit even at %.1f px" % sizes[-1])


def steps(hi, lo, step):
    out, v = [], hi
    while v >= lo - 1e-9:
        out.append(round(v, 2))
        v -= step
    return out


# ------------------------------------------------------- labels and chips --

def tracked_width(text, font, tracking):
    return sum(font.getlength(c) for c in text) + tracking * (len(text) - 1)


def draw_tracked(draw, x, base, text, font, fill, tracking, key, box):
    LOG.setdefault(key, []).extend(text.split(" "))
    for c in text:
        draw.text((x, base), c, font=font, fill=fill, anchor="ls")
        if c != " ":
            INK.append((key, draw.textbbox((x, base), c, font=font,
                                           anchor="ls"), box))
        x += font.getlength(c) + tracking


class Chip:
    """A filled section label: tracked caps on a colour block."""

    def __init__(self, text, size, bg, fg, pad_x=None, pad_y=None):
        self.text, self.bg, self.fg = text, bg, fg
        self.font = load_font("bold", size)
        self.tracking = size * 0.09
        self.cap = -self.font.getbbox("H", anchor="ls")[1]
        self.pad_x = size * 0.55 if pad_x is None else pad_x
        self.pad_y = size * 0.32 if pad_y is None else pad_y
        self.w = tracked_width(text, self.font, self.tracking) + 2 * self.pad_x
        self.h = self.cap + 2 * self.pad_y

    def draw(self, draw, x, y, key, box):
        draw.rectangle((round(x), round(y), round(x + self.w) - 1,
                        round(y + self.h) - 1), fill=self.bg)
        INK.append((key, (x, y, x + self.w, y + self.h), box))
        draw_tracked(draw, x + self.pad_x, y + self.pad_y + self.cap,
                     self.text, self.font, self.fg, self.tracking, key, box)


def small_caps_runs(text, size, fill):
    """Fake small caps: capitals full size, lower case as smaller capitals."""
    big = load_font("semi", size)
    small = load_font("semi", size * 0.8)
    runs = []
    for c in text:
        font = small if c.islower() else big
        runs.append((c.upper(), font, fill))
    return runs


# ------------------------------------------------------------------ page ---

def cover_crop(img, w, h, focus_y):
    sw, sh = img.size
    scale = max(w / sw, h / sh)
    cw, ch = w / scale, h / scale
    left = (sw - cw) / 2
    top = min(max(focus_y * sh - ch / 2, 0), sh - ch)
    return img.resize((w, h), Image.Resampling.LANCZOS,
                      box=(left, top, left + cw, top + ch))


def story_block(story, index, width, s):
    hs, ss = 19.0 * s, 13.5 * s
    bg, fg = CHIP_COLORS[index % 4]
    chip = Chip(story["section"], max(9.0, hs * 0.56), bg, fg)
    head_style = Style("bold", hs, NAVY)
    body_style = Style("regular", ss, BODY)
    key = "story%d" % index
    head = Para([(story["headline"], head_style, key + ".headline")],
                width, hs * 1.08, first_indent=chip.w + hs * 0.35)
    body = Para([(story["summary"], body_style, key + ".summary")],
                width, ss * 1.24)
    gap = 4 * s
    return {"chip": chip, "head": head, "body": body, "gap": gap,
            "key": key, "ok": head.ok and body.ok,
            "height": head.height + gap + body.height}


def plan_grid(stories, col_w, s):
    cols = [stories[0:4], stories[4:8], stories[8:11]]
    out, idx = [], 0
    divider = 13 * s
    for col in cols:
        blocks = []
        for story in col:
            blocks.append(story_block(story, idx, col_w, s))
            idx += 1
        height = sum(b["height"] for b in blocks) + divider * (len(blocks) - 1)
        out.append({"blocks": blocks, "height": height, "divider": divider,
                    "ok": all(b["ok"] for b in blocks)})
    return out


def plan(data):
    content_w = W - 2 * MARGIN
    p = {"content_w": content_w}

    # Masthead: title shrinks to leave room for the date block on the right.
    date_runs = small_caps_runs(data["date_line"], 14.0, MUTED)
    date_w = sum(f.getlength(c) for c, f, _ in date_runs) + 0.9 * (
        len(date_runs) - 1)
    tag_style = Style("italic", 15.0, NAVY)
    tag_w = tag_style.width(data["tagline"]) + tag_style.space * (
        data["tagline"].count(" "))
    right_w = max(date_w, tag_w)
    title_size = 64.0
    while True:
        tfont = load_font("display", title_size)
        if tfont.getlength("THE DAY IN BRIEF") <= content_w - right_w - 28:
            break
        title_size -= 1.0
    p.update(date_runs=date_runs, date_w=date_w, tag_style=tag_style,
             title_font=tfont, title_size=title_size)
    title_cap = -tfont.getbbox("THE DAY IN BRIEF", anchor="ls")[1]
    p["title_base"] = MARGIN + title_cap
    p["bar_top"] = p["title_base"] + 11
    p["bar_bottom"] = p["bar_top"] + 8
    hero_top = p["bar_bottom"] + 14

    # Footer band: On This Day (gold title + white text) and the footer note.
    otd = data["on_this_day"]
    note_w = 196
    otd_w = content_w - note_w - 28
    p["otd"] = Para([(otd["title"], Style("bold", 15.5, GOLD), "otd.title"),
                     (otd["text"], Style("regular", 15.0, WHITE), "otd.text")],
                    otd_w, 19.5)
    p["note"] = Para([(data["footer_note"], Style("italic", 13.0, FOOT_NOTE),
                       "footer_note")], note_w, 16.5, align="right")
    foot_text_h = max(p["otd"].height, p["note"].height)
    p["band_top"] = H - SAFE - 2 - foot_text_h - 18
    grid_bottom = p["band_top"] - 16

    lead = data["lead"]
    col_gap = 22
    col_w = (content_w - 2 * col_gap) / 3
    p["col_w"], p["col_gap"] = col_w, col_gap
    best = None
    for hero_h in range(300, 219, -10):
        head = fit_para(
            lambda z: [(lead["headline"], Style("display", z, NAVY),
                        "lead.headline")],
            content_w, steps(40, 28, 1), 1.1, 3)
        body = fit_para(
            lambda z: [(lead["summary"], Style("regular", z, BODY),
                        "lead.summary"),
                       (lead["source"], Style("italic", z * 0.9, CORAL),
                        "lead.source")],
            content_w, steps(16.5, 14, 0.5), 1.25, 3)
        head_top = hero_top + hero_h + 13
        body_top = head_top + head.height + 9
        rule_top = body_top + body.height + 13
        grid_top = rule_top + 3 + 14
        grid_h = grid_bottom - grid_top
        for s in steps(1.0, 0.80, 0.01):
            grid = plan_grid(data["stories"], col_w, s)
            tallest = max(c["height"] for c in grid)
            if all(c["ok"] for c in grid) and tallest <= grid_h:
                cand = (s, hero_h, head, body, head_top, body_top, rule_top,
                        grid_top, grid_h, grid)
                if best is None or s > best[0] + 1e-9:
                    best = cand
                break
        if best is not None and best[0] >= 0.90:
            break
    if best is None:
        raise RuntimeError("the story grid does not fit the page")
    (p["s"], p["hero_h"], p["lead_head"], p["lead_body"], p["head_top"],
     p["body_top"], p["rule_top"], p["grid_top"], p["grid_h"],
     p["grid"]) = best
    p["hero_top"] = hero_top
    return p


def render(data, hero):
    p = plan(data)
    img = Image.new("RGB", (W, H), WHITE)
    d = ImageDraw.Draw(img)
    cw = p["content_w"]
    right = MARGIN + cw

    # --- masthead
    tbox = (MARGIN, MARGIN - 4, right, p["bar_top"])
    title = "THE DAY IN BRIEF"
    d.text((MARGIN, p["title_base"]), title, font=p["title_font"], fill=NAVY,
           anchor="ls")
    INK.append(("masthead", d.textbbox((MARGIN, p["title_base"]), title,
                                       font=p["title_font"], anchor="ls"),
                tbox))
    LOG["masthead"] = title.split(" ")
    title_w = p["title_font"].getlength("THE DAY IN BRIEF")
    d.rectangle((MARGIN, p["bar_bottom"] - 3, right - 1, p["bar_bottom"] - 1),
                fill=NAVY)
    d.rectangle((MARGIN, p["bar_top"], round(MARGIN + title_w) - 1,
                 p["bar_bottom"] - 1), fill=CORAL)
    sq, gap = 12, 5
    x = right - 4 * sq - 3 * gap
    for color in (NAVY, CORAL, TEAL, GOLD):
        d.rectangle((x, MARGIN, x + sq - 1, MARGIN + sq - 1), fill=color)
        x += sq + gap
    date_base = MARGIN + sq + 23
    x = right - p["date_w"]
    LOG["date_line"] = data["date_line"].split(" ")
    for ch, font, fill in p["date_runs"]:
        d.text((x, date_base), ch, font=font, fill=fill, anchor="ls")
        if ch != " ":
            INK.append(("date_line", d.textbbox((x, date_base), ch, font=font,
                                                anchor="ls"), tbox))
        x += font.getlength(ch) + 0.9
    tag = Para([(data["tagline"], p["tag_style"], "tagline")], p["date_w"] + 80,
               18, align="right")
    tag.draw(d, right - tag.width, date_base + 7)

    # --- lead: hero band with chip and caption
    lead = data["lead"]
    ht, hh = p["hero_top"], p["hero_h"]
    band = cover_crop(hero, cw, hh, 0.36)
    img.paste(band, (MARGIN, ht))
    hbox = (MARGIN, ht, right, ht + hh)
    chip = Chip(lead["section"], 14.0, CORAL, WHITE, pad_x=11, pad_y=8)
    chip.draw(d, MARGIN, ht, "lead.section", hbox)
    cap_style = Style("italic", 14.5, WHITE)
    cap = Para([(lead["caption"], cap_style, "lead.caption")], 420, 18,
               align="right")
    cap_w = cap.line_width(cap.lines[0]) if len(cap.lines) == 1 else cap.width
    pad = 10
    bx1, by1 = right, ht + hh
    bx0, by0 = bx1 - cap_w - 2 * pad, by1 - cap.height - 2 * pad
    region = img.crop((round(bx0), round(by0), bx1, by1))
    img.paste(Image.blend(region, Image.new("RGB", region.size, NAVY), 0.82),
              (round(bx0), round(by0)))
    d.rectangle((round(bx0), round(by0), round(bx0) + 3, by1 - 1), fill=CORAL)
    cap.draw(d, bx1 - pad - cap.width, by0 + pad)

    p["lead_head"].draw(d, MARGIN, p["head_top"])
    p["lead_body"].draw(d, MARGIN, p["body_top"])
    d.rectangle((MARGIN, p["rule_top"], right - 1, p["rule_top"] + 2),
                fill=NAVY)

    # --- story grid, 4/4/3, gaps stretched so the columns share one bottom
    gt, gh, colw = p["grid_top"], p["grid_h"], p["col_w"]
    for ci, col in enumerate(p["grid"]):
        cx = MARGIN + ci * (colw + p["col_gap"])
        if ci:
            lx = round(cx - p["col_gap"] / 2) - 1
            d.rectangle((lx, gt, lx + 1, gt + gh), fill=LIGHT)
        n = len(col["blocks"])
        extra = (gh - col["height"]) / (n - 1) if n > 1 else 0
        divider = col["divider"] + min(extra, 48)
        y = gt
        for bi, b in enumerate(col["blocks"]):
            cbox = (cx, y, cx + colw, y + b["height"])
            head = b["head"]
            base = y + head.asc
            chip = b["chip"]
            chip_y = base - head.lines[0][0][1].cap / 2 - chip.h / 2
            chip.draw(d, cx, chip_y, b["key"] + ".section", cbox)
            head.draw(d, cx, y)
            b["body"].draw(d, cx, y + head.height + b["gap"])
            y += b["height"]
            if bi < n - 1:
                ly = round(y + divider / 2) - 1
                d.rectangle((round(cx), ly, round(cx + colw) - 1, ly + 1),
                            fill=LIGHT)
                y += divider

    # --- footer band
    bt = p["band_top"]
    d.rectangle((0, bt, W - 1, H - 1), fill=NAVY)
    d.rectangle((0, bt, W - 1, bt + 3), fill=GOLD)
    p["otd"].draw(d, MARGIN, bt + 18)
    note = p["note"]
    note.draw(d, right - note.width, bt + 18 + p["otd"].height - note.height)
    return img, p


def check_ink():
    bad = []
    for key, ink, box in INK:
        x0, y0, x1, y1 = ink
        if x0 < box[0] - 1 or y0 < box[1] - 1 or x1 > box[2] + 1 or \
                y1 > box[3] + 1:
            bad.append((key, "outside its box", ink, box))
        if x0 < SAFE or y0 < SAFE or x1 > W - SAFE or y1 > H - SAFE:
            bad.append((key, "inside the outer margin", ink))
    if bad:
        raise RuntimeError("text overflow: %r" % bad[:5])


def encode(img, path):
    img.save(path, format="PNG", optimize=True)
    colors = 256
    while os.path.getsize(path) > MAX_BYTES and colors >= 16:
        img.quantize(colors=colors, method=Image.Quantize.MEDIANCUT,
                     dither=Image.Dither.NONE).save(path, format="PNG",
                                                    optimize=True)
        colors //= 2


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    dst = os.path.join(OUT_DIR, OUT_NAME)
    if Image is None:
        shutil.copyfile(os.path.join(HERE, "entry.png"), dst)
        os.chmod(dst, 0o644)
        print("Pillow not available: copied the pre-rendered entry.png to", dst)
        return
    with open(os.path.join(HERE, "stories.json"), encoding="utf-8") as fh:
        data = json.load(fh)
    with Image.open(os.path.join(HERE, "hero.png")) as im:
        hero = im.convert("RGB")
    img, p = render(data, hero)
    check_ink()
    encode(img, dst)
    os.chmod(dst, 0o644)
    print("wrote %s (%d bytes, grid scale %.2f, hero %d px)" % (
        dst, os.path.getsize(dst), p["s"], p["hero_h"]))


if __name__ == "__main__":
    sys.exit(main())
