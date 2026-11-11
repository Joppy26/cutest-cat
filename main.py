#!/usr/bin/env python3
"""Draw the cutest cat — make.fun bounty cutest-cat-01.

A deterministic program (Python 3.13, standard library only) that draws one
cute cat and writes it to $MAKEFUN_OUTPUT_DIR/entry.png (default /output).

The cat is drawn with a tiny span-based rasterizer: circles, ellipses,
polygons and thick bezier strokes, with 1-pixel edge antialiasing. No
randomness, no wall clock, no network: two runs write identical bytes.
"""
import math
import os
import struct
import zlib

W = H = 1024

# ---------------------------------------------------------------- palette
BG_TOP = (255, 248, 236)
BG_BOT = (255, 231, 204)
BODY = (255, 233, 201)
CHEST = (255, 247, 234)
GINGER = (246, 168, 92)
GINGER_DARK = (224, 138, 60)
MUZZLE = (255, 237, 211)
EAR_PINK = (255, 179, 193)
NOSE = (242, 125, 141)
NOSE_DARK = (226, 93, 113)
EYE = (46, 31, 20)
WHITE = (255, 255, 255)
BLUSH = (255, 159, 176)
WHISKER = (90, 60, 40)
BOW = (242, 125, 141)


def clamp(v, a, b):
    return a if v < a else b if v > b else v


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


class Canvas:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.px = bytearray(w * h * 3)

    def set(self, x, y, color, alpha=1.0):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 3
            if alpha >= 1.0:
                self.px[i:i + 3] = bytes(color)
            else:
                for c in range(3):
                    self.px[i + c] = int(self.px[i + c] * (1 - alpha) + color[c] * alpha)

    def hspan(self, x0, x1, y, color, alpha=1.0):
        if y < 0 or y >= self.h:
            return
        x0 = max(0, x0)
        x1 = min(self.w - 1, x1)
        if x1 < x0:
            return
        if alpha >= 1.0:
            row = bytes(color) * (x1 - x0 + 1)
            i = (y * self.w + x0) * 3
            self.px[i:i + len(row)] = row
        else:
            for x in range(x0, x1 + 1):
                self.set(x, y, color, alpha)

    def circle(self, cx, cy, r, color, alpha=1.0):
        y0 = max(0, int(math.ceil(cy - r)))
        y1 = min(self.h - 1, int(math.floor(cy + r)))
        for y in range(y0, y1 + 1):
            dy = y - cy
            dx = math.sqrt(max(0.0, r * r - dy * dy))
            fx0, fx1 = cx - dx, cx + dx
            ix0, ix1 = int(math.ceil(fx0)), int(math.floor(fx1))
            self.hspan(ix0, ix1, y, color, alpha)
            lx = ix0 - 1
            if lx >= 0:
                self.set(lx, y, color, alpha * clamp(ix0 - fx0, 0, 1))
            rx = ix1 + 1
            if rx < self.w:
                self.set(rx, y, color, alpha * clamp(fx1 - ix1, 0, 1))

    def ellipse(self, cx, cy, rx, ry, color, alpha=1.0):
        y0 = max(0, int(math.ceil(cy - ry)))
        y1 = min(self.h - 1, int(math.floor(cy + ry)))
        for y in range(y0, y1 + 1):
            dy = (y - cy) / ry
            dx = rx * math.sqrt(max(0.0, 1.0 - dy * dy))
            fx0, fx1 = cx - dx, cx + dx
            ix0, ix1 = int(math.ceil(fx0)), int(math.floor(fx1))
            self.hspan(ix0, ix1, y, color, alpha)
            lx = ix0 - 1
            if lx >= 0:
                self.set(lx, y, color, alpha * clamp(ix0 - fx0, 0, 1))
            rxp = ix1 + 1
            if rxp < self.w:
                self.set(rxp, y, color, alpha * clamp(fx1 - ix1, 0, 1))

    def polygon(self, pts, color, alpha=1.0):
        ys = [p[1] for p in pts]
        y0 = max(0, int(math.ceil(min(ys))))
        y1 = min(self.h - 1, int(math.floor(max(ys))))
        n = len(pts)
        for y in range(y0, y1 + 1):
            xs = []
            for i in range(n):
                x1, y1p = pts[i]
                x2, y2p = pts[(i + 1) % n]
                if (y1p <= y < y2p) or (y2p <= y < y1p):
                    xs.append(x1 + (y - y1p) * (x2 - x1) / (y2p - y1p))
            xs.sort()
            for k in range(0, len(xs) - 1, 2):
                self.hspan(int(math.ceil(xs[k])), int(math.floor(xs[k + 1])), y, color, alpha)

    def bezier(self, p0, p1, p2, thick, color, alpha=1.0, steps=48):
        for i in range(steps + 1):
            t = i / steps
            x = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0]
            y = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1]
            self.circle(x, y, thick / 2.0, color, alpha)

    def thick_line(self, p0, p1, thick, color, alpha=1.0):
        self.bezier(p0, ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2), p1, thick, color, alpha, steps=24)


def rot(x, y, ang, cx=512, cy=500):
    c, s = math.cos(ang), math.sin(ang)
    dx, dy = x - cx, y - cy
    return (cx + dx * c - dy * s, cy + dx * s + dy * c)


def draw():
    cv = Canvas(W, H)
    # background: warm vertical gradient
    for y in range(H):
        cv.hspan(0, W - 1, y, lerp(BG_TOP, BG_BOT, y / (H - 1)))
    # soft pastel bokeh, very faint
    for (x, y, r, col) in [
        (150, 170, 90, (255, 183, 197)), (880, 150, 70, (255, 214, 140)),
        (120, 850, 110, (255, 214, 140)), (900, 860, 90, (255, 183, 197)),
        (512, 90, 60, (186, 232, 200)),
    ]:
        cv.circle(x, y, r, col, alpha=0.13)

    # curled tail, right side, behind the body
    cv.bezier((830, 990), (940, 880), (905, 715), 46, GINGER, steps=40)
    cv.circle(905, 715, 23, MUZZLE)  # cream tail tip

    # body and chest
    cv.ellipse(512, 1060, 390, 270, BODY)
    cv.ellipse(512, 1010, 210, 190, CHEST)

    # front paws at the bottom edge
    for px in (395, 629):
        cv.ellipse(px, 955, 100, 48, CHEST)
        for tx in (px - 28, px + 28):
            cv.thick_line((tx, 930), (tx, 968), 4, GINGER_DARK, alpha=0.55)

    # ---- head group, tilted -5 degrees for charm ----
    ang = -0.09
    P = lambda x, y: rot(x, y, ang)

    # head outline + head
    cv.circle(512, 500, 306, GINGER_DARK)
    cv.circle(512, 500, 300, GINGER)

    # ears: outer triangle, then ginger, then pink inner
    # big ears with tall tips so they read clearly above the head
    for ear in (
        [(270, 330), (350, 140), (440, 300)],
        [(754, 330), (674, 140), (584, 300)],
    ):
        pts = [P(x, y) for x, y in ear]
        cx = sum(p[0] for p in pts) / 3
        cy = sum(p[1] for p in pts) / 3
        big = [(cx + (x - cx) * 1.07, cy + (y - cy) * 1.07) for x, y in pts]
        cv.polygon(big, GINGER_DARK)
        cv.polygon(pts, GINGER)
        small = [(cx + (x - cx) * 0.55, cy + (y - cy) * 0.55) for x, y in pts]
        cv.polygon(small, EAR_PINK)

    # hair tuft on top
    cv.polygon([P(478, 212), P(512, 172), P(546, 212)], GINGER_DARK)

    # cream muzzle
    mx, my = P(512, 625)
    cv.ellipse(mx, my, 175, 125, MUZZLE)

    # big bright eyes
    for ex, ey in [(398, 478), (626, 478)]:
        cx, cy = P(ex, ey)
        cv.circle(cx, cy, 58, EYE)
        hx, hy = P(ex - 16, ey - 18)
        cv.circle(hx, hy, 19, WHITE)
        hx2, hy2 = P(ex + 15, ey + 15)
        cv.circle(hx2, hy2, 7, WHITE)

    # blush cheeks
    for bx, by in [(362, 598), (662, 598)]:
        cx, cy = P(bx, by)
        cv.ellipse(cx, cy, 44, 25, BLUSH, alpha=0.45)

    # pink nose, rounded triangle, bigger so it reads at small size
    nose = [P(486, 570), P(538, 570), P(512, 606)]
    cv.polygon(nose, NOSE)
    for vx, vy in nose:
        cv.circle(vx, vy, 11, NOSE)
    nx, ny = P(502, 580)
    cv.circle(nx, ny, 6, WHITE, alpha=0.7)

    # little "w" mouth
    m0 = P(512, 610)
    cv.bezier(m0, P(492, 632), P(472, 640), 5, EYE, alpha=0.85)
    cv.bezier(m0, P(532, 632), P(552, 640), 5, EYE, alpha=0.85)

    # whiskers, three per side
    for (sx, sy, ex, ey, cxp, cyp) in [
        (375, 585, 232, 545, 300, 560), (372, 592, 228, 590, 300, 590),
        (378, 600, 238, 632, 305, 615),
        (649, 585, 792, 545, 724, 560), (652, 592, 796, 590, 724, 590),
        (646, 600, 786, 632, 719, 615),
    ]:
        cv.bezier(P(sx, sy), P(cxp, cyp), P(ex, ey), 4, WHISKER, alpha=0.6)

    # pink bow at the base of the right ear
    bx, by = P(706, 302)
    cv.polygon([(bx - 44, by - 24), (bx, by), (bx - 44, by + 24)], BOW)
    cv.polygon([(bx + 44, by - 24), (bx, by), (bx + 44, by + 24)], BOW)
    cv.circle(bx, by, 16, NOSE_DARK)

    return cv


def write_png(path, cv):
    raw = bytearray()
    for y in range(cv.h):
        raw.append(0)
        raw += cv.px[y * cv.w * 3:(y + 1) * cv.w * 3]
    comp = zlib.compress(bytes(raw), 9)

    def chunk(typ, data):
        out = struct.pack(">I", len(data)) + typ + data
        return out + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", cv.w, cv.h, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", comp)
    png += chunk(b"IEND", b"")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(png)
    return len(png)


def main():
    outdir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    path = os.path.join(outdir, "entry.png")
    size = write_png(path, draw())
    print(f"wrote {path} ({size} bytes)")


if __name__ == "__main__":
    main()
