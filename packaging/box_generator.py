#!/usr/bin/env python3
"""
Slide-top masbaha presentation box: laser-cut file generator.

Outputs SVG in millimetres, sized for a 900 x 600 mm bed, with three layers:
    CUT      #FF0000  through-cut (hairline stroke)
    SCORE    #0000FF  light score line (plaque position on the lid)
    ENGRAVE  #000000  filled raster engraving (lid border and star motif)

Standard library only. Run:  python3 box_generator.py --out .

Construction (all parts 3 mm sheet, Baltic birch or walnut ply)
    bottom, front, back, closed end wall and exit end wall are finger-jointed.
    The exit end wall is lower than the others so the lid can slide out over it.
    Four rail strips are glued to the inside faces of the front and back walls.
    The lid slides between the lower and upper rails.

Kerf: every finger is drawn wider by KERF and every notch narrower by KERF so
the laser's material loss gives a snug fit. Measure the real kerf on the shop's
laser first (see kerf_test.svg) and pass it with --kerf.
"""
import argparse
import csv
import math
import os
import sys
from dataclasses import dataclass

CUT, SCORE, ENGRAVE = '#FF0000', '#0000FF', '#000000'


@dataclass
class Params:
    inner_len: float = 170.0   # interior length under the lid (x)
    inner_wid: float = 120.0   # interior width (y)
    inner_depth: float = 36.0  # interior depth from bottom plate to lid underside
    t: float = 3.0             # sheet thickness (measure your actual sheet)
    finger: float = 8.0        # nominal finger width
    kerf: float = 0.15         # laser kerf, mm (confirm with the shop)
    rail_h: float = 4.0        # rail strip height (rails protrude t into the box)
    lid_gap: float = 0.3       # gap between lid top and upper rail
    lid_clear: float = 0.4     # total side clearance of lid in the box
    exit_clear: float = 1.0    # exit wall top sits this far below the lid underside
    plaque_w: float = 60.0
    plaque_h: float = 20.0
    plaque_pad: float = 0.4    # score outline is this much larger than the plaque
    gap: float = 4.0           # spacing between parts on the sheet
    margin: float = 10.0       # sheet edge margin
    bed_w: float = 900.0
    bed_h: float = 600.0

    @property
    def X(self):
        return self.inner_len + 2 * self.t

    @property
    def Y(self):
        return self.inner_wid + 2 * self.t

    @property
    def z_lid(self):
        return self.t + self.inner_depth

    @property
    def Z_low(self):
        return math.floor(self.z_lid - self.exit_clear)

    @property
    def Z(self):
        return math.ceil(self.z_lid + self.t + self.lid_gap + self.rail_h)

    @property
    def lid_l(self):
        return self.inner_len - self.lid_clear

    @property
    def lid_w(self):
        return self.inner_wid - self.lid_clear


# ---------------------------------------------------------------- finger joints
def choose_m(Lj, f):
    """Number of equal interior segments (odd) so the two end segments are close to f."""
    best, m = None, 1
    while True:
        e = (Lj - m * f) / 2.0
        if e < 0.5 * f:
            break
        key = (abs(e - f), -e)
        if best is None or key < best[0]:
            best = (key, m, e)
        m += 2
    if best is None:
        raise ValueError('edge %.1f mm is too short for %.1f mm fingers' % (Lj, f))
    return best[1], best[2]


def joint_segments(Lj, f, kind):
    """[(a, b, d)] along joint coordinate s. d=0 is a finger, d=1 is a notch."""
    m, e = choose_m(Lj, f)
    widths = [e] + [f] * m + [e]
    segs, a = [], 0.0
    for i, w in enumerate(widths):
        d = (i % 2) if kind == 'male' else 1 - (i % 2)
        segs.append((a, a + w, d))
        a += w
    return segs


def edge_pts(L, spec, t, k, f):
    """Edge profile as (p, displacement) along traversal parameter p in [0, L]."""
    if not spec or spec.get('kind', 'flat') == 'flat':
        return [(0.0, 0.0), (L, 0.0)]
    Lj = spec.get('joint_len') or L
    segs = joint_segments(Lj, f, spec['kind'])
    if Lj < L - 1e-9:
        segs.append((Lj, L, 0))  # flat beyond the joint
    pts = []
    for i, (a, b, d) in enumerate(segs):
        a2 = a if i == 0 else a + (k / 2.0 if segs[i - 1][2] == 0 else -k / 2.0)
        b2 = b if i == len(segs) - 1 else b + (k / 2.0 if d == 0 else -k / 2.0)
        pts.append((a2, d * t))
        pts.append((b2, d * t))
    if spec.get('rev'):
        pts = [(L - s, dd) for s, dd in reversed(pts)]
    return pts


def make_panel(U, V, edges, t, k, f):
    """Closed polygon (list of (u, v)), y-up, counter-clockwise, rect [0,U] x [0,V]."""
    sides = ('bottom', 'right', 'top', 'left')
    E = {s: edge_pts(U if s in ('bottom', 'top') else V, edges.get(s), t, k, f) for s in sides}
    d0 = {s: E[s][0][1] for s in sides}    # displacement at the start of each edge
    d1 = {s: E[s][-1][1] for s in sides}   # displacement at the end of each edge
    # Corner points sit where the two displaced edge lines meet. This matters when both
    # edges end in a notch, otherwise the outline would cut a diagonal across the corner.
    corner = {
        ('left', 'bottom'): (d1['left'], d0['bottom']),
        ('bottom', 'right'): (U - d0['right'], d1['bottom']),
        ('right', 'top'): (U - d1['right'], V - d0['top']),
        ('top', 'left'): (d0['left'], V - d1['top']),
    }
    prev = {'bottom': 'left', 'right': 'bottom', 'top': 'right', 'left': 'top'}
    nxt = {'bottom': 'right', 'right': 'top', 'top': 'left', 'left': 'bottom'}
    out = []

    def add(q):
        q = (round(q[0], 4), round(q[1], 4))
        if not out or out[-1] != q:
            out.append(q)

    for side in sides:
        add(corner[(prev[side], side)])
        for p, d in E[side][1:-1]:
            if side == 'bottom':
                add((p, d))
            elif side == 'right':
                add((U - d, p))
            elif side == 'top':
                add((U - p, V - d))
            else:
                add((d, V - p))
    if out[0] == out[-1]:
        out.pop()
    return out


def panel_edges(P):
    """Edge specs for every finger-jointed panel. Joint coordinate s starts at the
    bottom (z = 0) or at x = 0 / y = 0. Top and left traversals run against s."""
    male = {'kind': 'male'}
    return {
        'bottom': (P.X, P.Y, {
            'bottom': dict(male), 'right': dict(male),
            'top': dict(male, rev=True), 'left': dict(male, rev=True)}),
        'front': (P.X, P.Z, {
            'bottom': {'kind': 'female'},
            'right': {'kind': 'male', 'joint_len': P.Z_low},
            'left': {'kind': 'male', 'rev': True}}),
        'back': (P.X, P.Z, {
            'bottom': {'kind': 'female'},
            'right': {'kind': 'male', 'joint_len': P.Z_low},
            'left': {'kind': 'male', 'rev': True}}),
        'end_closed': (P.Y, P.Z, {
            'bottom': {'kind': 'female'},
            'right': {'kind': 'female'},
            'left': {'kind': 'female', 'rev': True}}),
        'end_exit': (P.Y, P.Z_low, {
            'bottom': {'kind': 'female'},
            'right': {'kind': 'female'},
            'left': {'kind': 'female', 'rev': True}}),
    }


# ---------------------------------------------------------------- parts
def rect(w, h):
    return [(0.0, 0.0), (w, 0.0), (w, h), (0.0, h)]


def ngon(cx, cy, r, n, rot_deg):
    return [(cx + r * math.cos(math.radians(rot_deg + 360.0 * i / n)),
             cy + r * math.sin(math.radians(rot_deg + 360.0 * i / n))) for i in range(n)]


def lid_artwork(P):
    """Engrave: border frame, star ring and eight-point star. Score: plaque outline."""
    w, h = P.lid_l, P.lid_w
    cx, cy = w / 2.0, h / 2.0
    outer = [(5.0, 5.0), (w - 5.0, 5.0), (w - 5.0, h - 5.0), (5.0, h - 5.0)]
    inner = [(6.2, 6.2), (w - 6.2, 6.2), (w - 6.2, h - 6.2), (6.2, h - 6.2)]
    frame = {'polys': [outer, inner], 'rule': 'evenodd'}
    sy = cy + 18.0
    star = {'polys': [ngon(cx, sy, 20.0, 4, 45.0), ngon(cx, sy, 20.0, 4, 0.0)], 'rule': 'nonzero'}
    ring = {'polys': [ngon(cx, sy, 27.0, 144, 0.0), ngon(cx, sy, 25.8, 144, 0.0)], 'rule': 'evenodd'}
    pw, ph = P.plaque_w + P.plaque_pad, P.plaque_h + P.plaque_pad
    py = cy - 30.0
    score = [(cx - pw / 2, py - ph / 2), (cx + pw / 2, py - ph / 2),
             (cx + pw / 2, py + ph / 2), (cx - pw / 2, py + ph / 2)]
    return [frame, ring, star], [score]


def build_set(P, k):
    parts = []
    for name, (U, V, edges) in panel_edges(P).items():
        parts.append({'name': name, 'w': U, 'h': V, 'cut': [make_panel(U, V, edges, P.t, k, P.finger)]})
    eng, score = lid_artwork(P)
    parts.append({'name': 'lid', 'w': P.lid_l, 'h': P.lid_w, 'cut': [rect(P.lid_l, P.lid_w)],
                  'engrave': eng, 'score': score})
    for i in range(4):
        parts.append({'name': 'rail%d' % (i + 1), 'w': P.inner_len, 'h': P.rail_h,
                      'cut': [rect(P.inner_len, P.rail_h)]})
    return parts


# ---------------------------------------------------------------- nesting and output
def pack(items, bed_w, bed_h, margin, gap):
    """Shelf packing. items: [(key, w, h)]. Returns {key: (x, y)} or None."""
    order = sorted(items, key=lambda it: -it[2])
    pos, x, y, row_h = {}, margin, margin, 0.0
    for key, w, h in order:
        if x + w > bed_w - margin + 1e-9:
            x, y, row_h = margin, y + row_h + gap, 0.0
        if y + h > bed_h - margin + 1e-9 or w > bed_w - 2 * margin:
            return None
        pos[key] = (x, y)
        x += w + gap
        row_h = max(row_h, h)
    return pos


def fmt(v):
    s = ('%.3f' % v).rstrip('0').rstrip('.')
    return s if s not in ('', '-0') else '0'


def path_d(pts, ox, oy, H):
    return 'M' + ' L'.join('%s %s' % (fmt(ox + u), fmt(oy + H - v)) for u, v in pts) + ' Z'




def esc(s):
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def svg_doc(w, h, cut, score, engrave, labels, desc):
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<svg xmlns="http://www.w3.org/2000/svg" width="%smm" height="%smm" viewBox="0 0 %s %s">'
        % (fmt(w), fmt(h), fmt(w), fmt(h)),
        '<desc>%s</desc>' % esc(desc),
        '<g id="CUT_FF0000" fill="none" stroke="#FF0000" stroke-width="0.1">',
    ]
    out += ['<path d="%s"/>' % d for d in cut]
    out += ['</g>', '<g id="SCORE_0000FF" fill="none" stroke="#0000FF" stroke-width="0.1">']
    out += ['<path d="%s"/>' % d for d in score]
    out += ['</g>', '<g id="ENGRAVE_000000" fill="#000000" stroke="none">']
    out += engrave
    out.append('</g>')
    if labels:
        out.append('<g id="PREVIEW_LABELS_NOT_FOR_CUTTING">')
        out += labels
        out.append('</g>')
    out.append('</svg>')
    return '\n'.join(out) + '\n'


def sheet_svg(P, k, sets, preview=False):
    items, store = [], {}
    for s in range(sets):
        for part in build_set(P, k):
            key = (s, part['name'])
            store[key] = part
            items.append((key, part['w'], part['h']))
    pos = pack(items, P.bed_w, P.bed_h, P.margin, P.gap)
    if pos is None:
        return None
    cut, score, eng, labels = [], [], [], []
    for key, (ox, oy) in pos.items():
        part = store[key]
        H = part['h']
        cut += [path_d(poly, ox, oy, H) for poly in part['cut']]
        score += [path_d(poly, ox, oy, H) for poly in part.get('score', [])]
        for e in part.get('engrave', []):
            d = ' '.join(path_d(poly, ox, oy, H) for poly in e['polys'])
            eng.append('<path d="%s" fill-rule="%s"/>' % (d, e['rule']))
        if preview:
            size = min(6.0 if sets == 1 else 3.0, part['h'] * 0.6)
            text = key[1] if sets == 1 else 's%d %s' % (key[0] + 1, key[1])
            labels.append('<text x="%s" y="%s" text-anchor="middle" font-family="sans-serif" '
                          'font-size="%s" fill="#888888">%s</text>'
                          % (fmt(ox + part['w'] / 2.0), fmt(oy + H / 2.0 + size * 0.35), fmt(size), esc(text)))
    desc = ('Slide-top masbaha box, %d set(s). Units mm. Sheet %sx%s. Sheet thickness %s, kerf %s, finger %s. '
            'Layers: CUT #FF0000, SCORE #0000FF, ENGRAVE #000000.' % (sets, fmt(P.bed_w), fmt(P.bed_h), fmt(P.t), fmt(k), fmt(P.finger)))
    return svg_doc(P.bed_w, P.bed_h, cut, score, eng, labels, desc)


def plaque_sheet_svg(P, names):
    pw, ph = P.plaque_w, P.plaque_h
    cols = int((P.bed_w - 2 * P.margin + P.gap) // (pw + P.gap))
    cut, eng = [], []
    for i, name in enumerate(names):
        c, r = i % cols, i // cols
        ox, oy = P.margin + c * (pw + P.gap), P.margin + r * (ph + P.gap)
        if oy + ph > P.bed_h - P.margin:
            raise ValueError('too many plaques for one sheet (%d fit)' % (i))
        cut.append(path_d(rect(pw, ph), ox, oy, ph))
        eng.append('<text x="%s" y="%s" text-anchor="middle" font-family="Cormorant Garamond, Georgia, serif" '
                   'font-style="italic" font-size="9" fill="#000000">%s</text>'
                   % (fmt(ox + pw / 2.0), fmt(oy + ph / 2.0 + 3.0), esc(name)))
    desc = ('Name plaques %sx%s mm, %s mm sheet. Names are live text: convert text to outlines '
            'before sending to the laser shop.' % (fmt(pw), fmt(ph), fmt(P.t)))
    return svg_doc(P.bed_w, P.bed_h, cut, [], eng, [], desc)


def kerf_test_svg(P, kerfs=(0.0, 0.10, 0.15, 0.20, 0.25)):
    """Pairs of small finger-jointed coupons. Dots engraved on the left piece give the kerf index."""
    f, w, h, g, m = 6.0, 30.0, 20.0, 4.0, 5.0
    cut, eng = [], []
    for i, k in enumerate(kerfs):
        ox = m + i * (w + g)
        a = make_panel(w, h, {'bottom': {'kind': 'male'}}, P.t, k, f)
        b = make_panel(w, h, {'top': {'kind': 'female', 'rev': True}}, P.t, k, f)
        cut.append(path_d(a, ox, m, h))
        cut.append(path_d(b, ox, m + h + g, h))
        for j in range(i + 1):
            dot = ngon(ox + 6 + 4 * j, m + h / 2.0, 1.1, 24, 0)
            eng.append('<path d="M%s Z"/>' % ' L'.join('%s %s' % (fmt(x), fmt(y)) for x, y in dot))
    W, H = m * 2 + len(kerfs) * (w + g) - g, m * 2 + 2 * h + g
    desc = ('Kerf test coupons, kerf values %s mm drawn left to right (1 to %d dots). Cut, then press each pair '
            'together. The pair that is snug by hand, without force or wobble, gives the kerf to use.'
            % (', '.join(fmt(k) for k in kerfs), len(kerfs)))
    return svg_doc(W, H, cut, [], eng, [], desc)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', default='.', help='output folder')
    ap.add_argument('--kerf', type=float, default=Params.kerf)
    ap.add_argument('--thickness', type=float, default=Params.t)
    ap.add_argument('--finger', type=float, default=Params.finger)
    ap.add_argument('--inner-length', type=float, default=Params.inner_len)
    ap.add_argument('--inner-width', type=float, default=Params.inner_wid)
    ap.add_argument('--inner-depth', type=float, default=Params.inner_depth)
    ap.add_argument('--names', help='text file with one plaque name per line')
    a = ap.parse_args(argv)
    P = Params(inner_len=a.inner_length, inner_wid=a.inner_width, inner_depth=a.inner_depth,
               t=a.thickness, finger=a.finger, kerf=a.kerf)
    os.makedirs(a.out, exist_ok=True)

    def write(name, text):
        with open(os.path.join(a.out, name), 'w', encoding='utf-8') as fh:
            fh.write(text)

    n = 1
    while n < 60 and sheet_svg(P, a.kerf, n + 1) is not None:
        n += 1
    write('box_single_set.svg', sheet_svg(P, a.kerf, 1))
    write('box_sheet_%dx%d_%dsets.svg' % (P.bed_w, P.bed_h, n), sheet_svg(P, a.kerf, n))
    write('PREVIEW_box_single_set_labels.svg', sheet_svg(P, a.kerf, 1, preview=True))
    if a.names:
        with open(a.names, encoding='utf-8') as fh:
            names = [ln.strip() for ln in fh if ln.strip()]
    else:
        names = ['Amina', 'Yusuf', 'Maryam', 'Omar', 'Ibrahim', 'Layla', 'Zayd', 'Noor']
    write('plaque_sheet.svg', plaque_sheet_svg(P, names))
    write('kerf_test.svg', kerf_test_svg(P))
    print('Outer box %sx%sx%s mm (exit wall %s mm), interior %sx%sx%s mm, lid %sx%s mm'
          % (fmt(P.X), fmt(P.Y), fmt(P.Z), fmt(P.Z_low), fmt(P.inner_len), fmt(P.inner_wid),
             fmt(P.inner_depth), fmt(P.lid_l), fmt(P.lid_w)))
    print('%d box sets fit one %dx%d mm sheet; files written to %s' % (n, P.bed_w, P.bed_h, os.path.abspath(a.out)))


if __name__ == '__main__':
    sys.exit(main())
