#!/usr/bin/env python3
"""
Independent check of the box design. Needs numpy.

Builds every finger-jointed panel at zero kerf, places it in 3D on a 0.25 mm voxel
grid, then checks that
  1. no two panels occupy the same volume (no overlaps),
  2. the union of panels is exactly the intended shell (no holes, no extra material),
  3. the lid, rails and exit wall have the clearances the design assumes,
  4. every part sits inside the 900 x 600 mm bed.
Run:  python3 verify_box.py
"""
import sys

import numpy as np

import box_generator as bg

S = 4  # voxels per mm


def raster(poly, U, V):
    """Even-odd point-in-polygon on voxel centres. Returns bool array (U*S, V*S)."""
    us = (np.arange(int(round(U * S))) + 0.5) / S
    vs = (np.arange(int(round(V * S))) + 0.5) / S
    px, py = np.meshgrid(us, vs, indexing='ij')
    inside = np.zeros(px.shape, dtype=bool)
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if y1 == y2:
            continue
        cond = ((y1 > py) != (y2 > py)) & (px < (x2 - x1) * (py - y1) / (y2 - y1) + x1)
        inside ^= cond
    return inside


def main():
    P = bg.Params()
    X, Y, Z, Zl, t = int(P.X), int(P.Y), int(P.Z), int(P.Z_low), int(P.t)
    assert (X, Y, Z, Zl) == (P.X, P.Y, P.Z, P.Z_low), 'use whole-millimetre dimensions for the voxel check'
    ts = t * S
    grid = np.zeros((X * S, Y * S, Z * S), dtype=np.uint8)
    panels = {name: (U, V, bg.make_panel(U, V, e, P.t, 0.0, P.finger)) for name, (U, V, e) in bg.panel_edges(P).items()}

    m = {n: raster(p, U, V) for n, (U, V, p) in panels.items()}
    grid[:, :, 0:ts] += m['bottom'][:, :, None]
    grid[:, 0:ts, :] += m['front'][:, None, :]
    grid[:, (Y - t) * S:Y * S, :] += m['back'][:, None, :]
    grid[0:ts, :, :] += m['end_closed'][None, :, :]
    grid[(X - t) * S:X * S, :, 0:Zl * S] += m['end_exit'][None, :, :]

    expected = np.zeros_like(grid, dtype=bool)
    expected[:, :, :] = True
    expected[ts:(X - t) * S, ts:(Y - t) * S, ts:] = False              # cavity, open top
    expected[(X - t) * S:, ts:(Y - t) * S, Zl * S:] = False            # exit opening above the low wall

    overlap = int((grid > 1).sum())
    occupied = grid > 0
    missing = int((expected & ~occupied).sum())
    extra = int((~expected & occupied).sum())
    vox_mm3 = 1.0 / S ** 3
    ok = True

    def check(label, passed, detail=''):
        nonlocal ok
        ok = ok and passed
        print('%-58s %s %s' % (label, 'PASS' if passed else 'FAIL', detail))

    print('Outer %dx%dx%d mm, exit wall %d mm, sheet %.1f mm, finger %.1f mm' % (X, Y, Z, Zl, P.t, P.finger))
    check('Joints: no overlapping material', overlap == 0, '(%.1f mm3)' % (overlap * vox_mm3))
    check('Joints: no holes in the shell', missing == 0, '(%.1f mm3)' % (missing * vox_mm3))
    check('Joints: no material outside the shell', extra == 0, '(%.1f mm3)' % (extra * vox_mm3))

    # lid and rail geometry (mm)
    lower_top = P.z_lid
    lower_bot = P.z_lid - P.rail_h
    upper_bot = P.z_lid + P.t + P.lid_gap
    upper_top = upper_bot + P.rail_h
    side_clear = (P.inner_wid - P.lid_w) / 2.0
    overlap_rail = P.t - side_clear
    check('Lid fits between side walls', P.lid_w < P.inner_wid and P.lid_l < P.inner_len,
          '(lid %.1f x %.1f in %.1f x %.1f)' % (P.lid_l, P.lid_w, P.inner_len, P.inner_wid))
    check('Lid rests on rails by at least 2 mm', overlap_rail >= 2.0, '(%.2f mm each side)' % overlap_rail)
    check('Exit wall top below lid underside', Zl < P.z_lid, '(%.1f < %.1f)' % (Zl, P.z_lid))
    check('Upper rail top below wall top', upper_top <= Z, '(%.1f <= %d)' % (upper_top, Z))
    check('Lower rail below lid, above bottom plate', P.t < lower_bot < lower_top, '(%.1f to %.1f)' % (lower_bot, lower_top))
    check('Rails fit between end walls', P.inner_len <= X - 2 * P.t + 1e-9)

    # nesting
    for k in (0.0, P.kerf):
        svg = bg.sheet_svg(P, k, 1)
        check('Single set nests on %dx%d bed (kerf %.2f)' % (P.bed_w, P.bed_h, k), svg is not None)
    n = 1
    while n < 60 and bg.sheet_svg(P, P.kerf, n + 1) is not None:
        n += 1
    print('Sets per sheet: %d' % n)

    # kerf rule: fingers wider, notches narrower, by exactly the kerf
    k = 0.2
    base = bg.edge_pts(176.0, {'kind': 'male'}, 3.0, 0.0, 8.0)
    comp = bg.edge_pts(176.0, {'kind': 'male'}, 3.0, k, 8.0)
    fw0 = base[1][0] - base[0][0]
    fw1 = comp[1][0] - comp[0][0]
    nw0 = base[3][0] - base[2][0]
    nw1 = comp[3][0] - comp[2][0]
    check('Kerf: end finger grows by kerf/2 (one side free)', abs((fw1 - fw0) - k / 2) < 1e-6, '(%.3f)' % (fw1 - fw0))
    check('Kerf: notch shrinks by kerf', abs((nw0 - nw1) - k) < 1e-6, '(%.3f)' % (nw0 - nw1))

    print('\nALL CHECKS PASSED' if ok else '\nCHECKS FAILED')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
