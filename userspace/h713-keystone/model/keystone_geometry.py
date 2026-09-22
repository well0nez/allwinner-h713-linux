#!/usr/bin/env python3
"""Vendor four-corner keystone geometry of the H713 projectors, as a model.

A standalone reference for the chain tilt angles -> four corner insets that the
vendor app com.hysd.vafocus runs before it sends SurfaceFlinger transaction
1050.  Every formula below names the function it came from; they all live in

    umbau/work/AP2c/ida/v7a_libduRYXtp.so.i64
    <- material/x/tpjz_allwinner/lib/armeabi-v7a/libduRYXtp.so
    sha256 cd888c5c189de158cd36227ae2c15a8afbc99106bed5ce111f1c562f2d3d9873
    ELF32 ARM shared object, IDA image base 0, so a file offset is the address.

Renamed vendor functions: reset_TouSheBi -> reset_tou_she_bi,
setReferencePoint -> _reference_points, check_center_XYgate -> _center_gate,
obstacle_px2xyrMap -> make_px2xyr, sub_39DD8 -> idiv, read_ini_flle ->
HY310_INI plus ini_crc, setkeystoneValue -> clamp_corner, efect_tp_correct ->
to_permille, androidN_tp_correct -> parcel_floats; the rest keep their names.
Not modelled (see REPORT.txt): the obstacle branch of px_space_find_max_rect,
px_space_adjust_rect @ 0x0002A710, and the DLP (DLP_AXIS != 0) frustum.
"""

import math
import struct

_F32 = struct.Struct("<f")
_DEG = 3.1415926 / 180.0          # the vendor's pi, not math.pi


def f32(x):
    """Round to IEEE-754 binary32, as every ARM VFP float store does."""
    return _F32.unpack(_F32.pack(x))[0]


def itrunc(x):
    """C cast float -> int: truncate towards zero."""
    return int(x)


def idiv(a, b):
    """C signed division, truncating towards zero (sub_39DD8 @ 0x00039DD8)."""
    q = abs(a) // abs(b)
    return q if (a < 0) == (b < 0) else -q


def sin_call(v):                  # _Z7sinCallf @ 0x0000B548
    return math.sin(v * _DEG)


def cos_call(v):                  # _Z7cosCallf @ 0x0000B578
    return math.cos(v * _DEG)


def acos_call(v):                 # _Z8acosCallf @ 0x0000B5D0; acosf gives NaN
    return math.acos(max(-1.0, min(1.0, f32(v)))) * 57.29578


# --- the optics: material/lib/camprjspe.ini, sha256 7ff05ee22562dc721d5701
# a2a046ef530c1dc6b03ae96de7e541313ea5f8cc5.  OFF_AXIS and LCD_AXIS are absent
# from the HY310 file, so their .bss globals (0x0003FAE8, 0x0003FAEC) stay 0.
HY310_INI = {
    "DLP_AXIS": 0, "F": 64.555834, "Whalf": 39.478412, "Hhalf": 22.145381,
    "U1": 67.484363, "U2": 66.334363, "Vdec": 28.200000, "LCD_O": -4.0,
    "step1": 18, "step2": 180, "fdd": 1700.0, "OFF_AXIS": 0.0, "LCD_AXIS": 0.0,
}
HY310_INI_CRC = "7ba20fb015999a40"


def ini_crc(ini):
    """The checksum read_ini_flle @ 0x0002ACA8 compares before it accepts the
    file; a mismatch logs "CPP:CRC error" and the whole ini is discarded."""
    f, u1, u2 = ini["F"], ini["U1"], ini["U2"]
    # the association matters for the last mantissa byte: Vdec + (a + b)
    value = ini["Vdec"] + (ini["Whalf"] * (f * u1 / (u1 - f)) / u1
                           + ini["Hhalf"] * (f * u2 / (u2 - f)) / u2)
    return struct.pack("<d", value).hex()


def reset_tou_she_bi(ini, fdd_int):
    """reset_TouSheBi(0, fdd, 0, mode=1) @ 0x0002BE78.  Thin lens: the panel
    sits off = Vdec + (LCD_O + U2) behind the lens, the wall at fdd.  Returns
    the half-field tangents; single precision throughout, as in the binary."""
    f = f32(ini["F"])
    whalf2 = f32(f32(ini["Whalf"]) + f32(ini["Whalf"]))
    hhalf2 = f32(f32(ini["Hhalf"]) + f32(ini["Hhalf"]))
    off = f32(f32(ini["Vdec"]) + f32(f32(ini["LCD_O"]) + f32(ini["U2"])))
    off_axis = ini["OFF_AXIS"]
    d = fdd_int
    if off_axis < -0.001 or off_axis > 0.001:
        d = itrunc(float(d) / cos_call(off_axis))
    v = f32(f32(off - f32(f32(f * d) / f32(float(d) - f))) + float(d))
    dd = f32(v - f)                                     # CELIANF_D
    u = f32(f32(f * v) / f32(v - f))
    w = f32(f32(whalf2 * v) / u)                        # CELIANF_W
    h = f32(f32(hhalf2 * v) / u)                        # CELIANF_H
    return {"celianf_w": w, "celianf_h": h, "celianf_d": dd,
            "tan_lr_v": f32(w / f32(dd + dd)),
            "tan_hp_v": f32(h / f32(dd + dd)),
            "tan_hw_v": f32(h / w)}


# --- rotations --------------------------------------------------------------
def _rot(axis, a):
    """One elementary rotation by a degrees, right handed: the three matrices
    the set_rotate_* functions keep at 0x0003DE70 / 0x0003DEB8 / 0x0003DF00."""
    s, c = sin_call(a), cos_call(a)
    if axis == "x":
        return [[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]]
    if axis == "y":
        return [[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]]
    return [[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]]


def _mm(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)]
            for i in range(3)]


def set_rotate_yxz(a1, a2, a3):   # 0x0002842C: Ry(-a2) . Rx(-a1) . Rz(a3)
    return _mm(_rot("y", -a2), _mm(_rot("x", -a1), _rot("z", a3)))


def set_rotate_zxy(a1, a2, a3):   # 0x00028724: Rz(a3) . Rx(-a1) . Ry(-a2)
    return _mm(_rot("z", a3), _mm(_rot("x", -a1), _rot("y", -a2)))


def set_rotate_zyx(a1, a2, a3):   # 0x00028140: Rz(a3) . Ry(-a2) . Rx(-a1)
    return _mm(_rot("z", a3), _mm(_rot("y", -a2), _rot("x", -a1)))


def xl_rotate_f(m, x, y, z):
    """xl_rotate_f @ 0x00028AE4: a double 3x3 applied to a float vector."""
    return tuple(f32(r[0] * x + r[1] * y + r[2] * z) for r in m)


def _project(m, x, y, fdd):
    """Rotate (x, y, -fdd), intersect the ray with the wall plane z = -fdd.
    The binary negates the point and divides by -fdd; both negations cancel."""
    rx, ry, rz = xl_rotate_f(m, -x, -y, fdd)
    s = f32(f32(-fdd) / rz)
    return f32(rx * s), f32(ry * s)


def make_px2xyr(m, fdd, hx, hy, shift, lcd_w, lcd_h):
    """obstacle_px2xyrMap @ 0x0002F438: panel pixel -> wall plane, truncated.
    Panel row 0 maps to the BOTTOM of the frustum, row lcd_h to the top; that
    is the vendor's axis convention, not a mistake here."""
    def px2xyr(px, py):
        gx = f32(f32(f32(hx * px) + f32(hx * px)) / lcd_w)
        gy = f32(f32(f32(hy * py) + f32(hy * py)) / lcd_h)
        bx, by = _project(m, f32(gx - hx), f32(f32(gy - hy) + shift), fdd)
        return itrunc(bx), itrunc(by)
    return px2xyr


# --- the inscribed rectangle: the binary SEARCHES for it (2368 bytes of
# integer scanline code), there is no closed form in the library or here ------
_ZOOM_WIDTH = {0: 1920, 1: 1728, 2: 1440}


def _scanlines(x, y, ytop, ybot):
    """The left and right boundary of the quad per integer scanline, one entry
    per row from ytop downwards.  Same edges and the same truncating division
    as the loop at 0x00029B6C+0x1F0, whose four trees share this rule."""
    left, right = [0] * (ytop - ybot + 3), [0] * (ytop - ybot + 3)
    flat = y[0] == y[1]

    def ip(row, ya, xa, yb, xb):
        return idiv((row - ya) * (xb - xa), yb - ya) + xa

    for row in range(ytop, ybot - 1, -1):
        if row > y[2]:                            # top edge RT -> LT
            lv = ip(row, y[3], x[3], y[2], x[2])
        elif row > y[0]:                          # left edge LT -> LB
            lv = ip(row, y[2], x[2], y[0], x[0])
        else:                                     # bottom edge LB -> RB
            lv = x[0] if flat else ip(row, y[0], x[0], y[1], x[1])
        if row > y[3]:                            # top edge LT -> RT
            rv = ip(row, y[2], x[2], y[3], x[3])
        elif row > y[1]:                          # right edge RT -> RB
            rv = ip(row, y[3], x[3], y[1], x[1])
        else:                                     # bottom edge RB -> LB
            rv = x[1] if flat else ip(row, y[1], x[1], y[0], x[0])
        left[ytop - row] = lv
        right[ytop - row] = rv
    return left, right


def _reference_points(px2xyr, xoff, yoff, x, y, lcd_w, lcd_h):
    """setReferencePoint @ 0x00037E9C: the quad-space centre and the two
    vertical rulers a11[33..48] and a11[49..65].  The horizontal rulers
    a11[0..32] are only read by the obstacle branch and are skipped."""
    cx0, cy0 = px2xyr(lcd_w // 2, lcd_h // 2)
    cx, cy = cx0 + xoff, cy0 + yoff       # the quad-space panel centre

    def dist(px, py):
        mx, my = px2xyr(px, py)
        dy = f32(float(my + yoff) - float(cy))
        dx = f32(float(mx + xoff) - float(cx))
        return math.sqrt(dy * dy + dx * dx)

    def ruler(ia, ib, base, rows):
        sl = f32((y[ia] - y[ib]) / float(x[ia] - x[ib]))
        cxp, d0 = lcd_w // 2, dist(lcd_w // 2, base)
        off = f32(float(cy) - f32(f32(y[ia] - f32(sl * x[ia])) + f32(sl * cx)))
        return [itrunc(f32(float(cy) - f32(f32(off * dist(cxp, r)) / d0)))
                for r in rows]

    rb = ruler(0, 1, 0, [(k * 1080) >> 5 for k in range(16)])
    rt = ruler(2, 3, lcd_h, [(17280 + k * 1080) >> 5 for k in range(17)])
    return cx, cy, rb, rt


def _center_gate(rb, rt, ylo, yhi):
    """check_center_XYgate @ 0x0003832C: how far off centre the rectangle sits,
    counted in ruler buckets.  The caller drops a candidate above 4."""
    ruler = list(rb) + list(rt)
    if ruler[0] > ylo or ruler[32] < yhi:
        return 200
    lo = 100
    for k in range(16):
        if ruler[k] <= ylo < ruler[k + 1]:
            lo = 15 - k
            break
    hi = 200
    for j in range(16):
        if ruler[16 + j] <= yhi < ruler[17 + j]:
            hi = j
            break
    return abs(lo - hi)


def px_space_find_max_rect(quad, zoom_scale, px2xyr, lcd_w=1920, lcd_h=1080):
    """px_space_find_max_rect @ 0x00029B6C, the non-obstacle path.  Two integer
    passes over candidate rows: pass one probes only the centre row with a
    half-width step of 10, pass two every row from the bottom to the top ruler
    with step 1, starting at the best half-width of pass one.  The rectangle
    keeps the aspect target_width : 1080.  Returns (x_left, x_right, y_top,
    y_bottom) in quad space, or None."""
    wt = _ZOOM_WIDTH.get(zoom_scale, 1920)
    xi, yi = [itrunc(p[0]) for p in quad], [itrunc(p[1]) for p in quad]
    xoff, yoff = abs(min(xi)) + 20, abs(min(yi)) + 20
    x, y = [v + xoff for v in xi], [v + yoff for v in yi]
    ytop, ybot = max(y[2], y[3]), min(y[0], y[1])
    if ytop - ybot <= -3:
        return None                       # "CPP: Mem error total_LINE=%d"
    nline = ytop - ybot + 2
    left, right = _scanlines(x, y, ytop, ybot)
    cx, cy, rb, rt = _reference_points(px2xyr, xoff, yoff, x, y, lcd_w, lcd_h)

    # the registers the binary leaves in place when the search finds nothing
    bx0, bx1, by0, by1 = x[0], x[2] - x[3], y[2] - y[3], y[1] - y[3]
    area, width2, half, gate = 0, 16, 16 // 2, False
    for first in (True, False):
        if first:
            row_from = row_to = cy
            half, step = width2 // 2, 10
        else:
            row_from, row_to, step = rb[0], rt[16], 1
        if ytop - row_from > nline:
            row_from = ytop - nline
        if ytop < row_to:
            row_to = ytop
        row = row_from
        while row <= row_to:
            keep = half
            i = ytop - row
            if 0 <= i <= nline:
                lim = min(right[i] - cx, cx - left[i])
                hw = half
                while hw < lim:
                    h = idiv(2160 * hw, wt)
                    if first:
                        top, bot = row + h // 2, row - h // 2
                    else:
                        top, bot = row + h, row
                    if ytop < top or bot < ybot:
                        break
                    lxc, rxc = cx - hw, cx + hw
                    it, ib = ytop - top, ytop - bot
                    bad = 1 if (lxc < left[it] or lxc > right[it]) else 0
                    if rxc < left[it] or rxc > right[it]:
                        bad += 2
                    if lxc < left[ib] or lxc > right[ib]:
                        bad = 1
                    if rxc < left[ib]:
                        break
                    if bad or rxc > right[ib]:
                        break
                    a = h * 2 * hw
                    if a > area:
                        if not (gate and _center_gate(rb, rt, bot, top) > 4):
                            bx0, bx1, by0, by1 = lxc, rxc, top, bot
                            width2, keep, area = 2 * hw, hw, a
                    hw += step
            row += 1
            half = keep
        gate = True

    reject = (bx1 - bx0 <= 40)
    if bx1 - bx0 >= 40:
        reject = (by0 - by1 <= 29)
    if reject:
        return None                       # "CPP:PX  max_lx=... --- error"
    return (float(bx0 - xoff), float(bx1 - xoff),
            float(by0 - yoff), float(by1 - yoff))


# --- the whole chain --------------------------------------------------------
def _clip(v, n):                  # the two-sided clamp of 0x0002EC28+0x2A0
    return n - 1 if v >= n else (0 if v < 0 else v)


def draw_ret_map_point(du_r, du_y, gs_x, gs_y, zoom_scale=0, ini=None,
                       lcd_w=1920, lcd_h=1080):
    """draw_ret_map_point @ 0x0002EC28.  du_r / du_y are the camera's roll and
    pitch in degrees, gs_x and gs_y the two g-sensor angles.  Returns the eight
    panel-pixel insets in the order the vendor logs them: LT.x, LT.y, RT.x,
    RT.y, LB.x, LB.y, RB.x, RB.y, each inward from its own edge
    ("CPP:OUT:LT(%4d,%4d) ...")."""
    ini = HY310_INI if ini is None else ini
    fdd = f32(ini["fdd"])
    opt = reset_tou_she_bi(ini, itrunc(fdd))

    # which way is the wall: rotate the optical axis and read two components
    m = set_rotate_zyx(du_y, du_r, gs_x)
    nx, ny, nz = xl_rotate_f(m, 0.0, 0.0, 1.0)
    norm = math.sqrt(ny * ny + nx * nx + nz * nz)
    du_r_eff = 90.0 - acos_call(nx / norm)
    du_y_eff = 90.0 - acos_call(ny / norm)
    if -60.0 < gs_y < 60.0:               # the g-sensor overrides the camera
        oa = ini["OFF_AXIS"]
        du_y_eff = f32(-gs_y) - (oa if oa < -0.001 or oa > 0.001 else 0.0)

    hx = f32(fdd * opt["tan_lr_v"])
    hy = f32(fdd * opt["tan_hp_v"])
    lcd_axis = ini["LCD_AXIS"]
    shift = f32(f32(hy + hy) * lcd_axis) if abs(lcd_axis) > 0.001 else 0.0
    y_bot, y_top = f32(shift - hy), f32(hy + shift)

    m = set_rotate_yxz(du_y_eff, du_r_eff, -gs_x)
    quad = [_project(m, -hx, y_bot, fdd), _project(m, hx, y_bot, fdd),
            _project(m, -hx, y_top, fdd), _project(m, hx, y_top, fdd)]
    px2 = make_px2xyr(m, fdd, hx, hy, shift, lcd_w, lcd_h)
    rect = px_space_find_max_rect(quad, zoom_scale, px2, lcd_w, lcd_h)
    if rect is None:
        return [0] * 8
    xl, xr, yt, yb = rect

    m = set_rotate_zxy(-du_y_eff, -du_r_eff, gs_x)   # the inverse rotation

    def back(px, py):
        bx, by = _project(m, px, py, fdd)
        ix = itrunc(f32(f32(f32(bx - -hx) * lcd_w) / f32(hx + hx)))
        iy = itrunc(f32(f32(f32(by - y_bot) * lcd_h) / f32(hy + hy)))
        return _clip(ix, lcd_w), _clip(iy, lcd_h)

    lt, rt_ = back(xl, yt), back(xr, yt)
    lb, rb = back(xl, yb), back(xr, yb)
    return [max(0, lt[0]), max(0, lcd_h - 1 - lt[1]),
            max(0, lcd_w - 1 - rt_[0]), max(0, lcd_h - 1 - rt_[1]),
            max(0, lb[0]), max(0, lb[1]),
            max(0, lcd_w - 1 - rb[0]), max(0, rb[1])]


def to_permille(px8):
    """efect_tp_correct (PropertiesUtils.java:38-57): the eight panel pixels as
    integer per-mille, the unit of persist.htc.keystone.*; divisors literal."""
    return [itrunc(px8[i] / (1920.0 if i % 2 == 0 else 1080.0) * 1000.0)
            for i in range(8)]


def parcel_floats(px8, screen_w=1920, screen_h=1080):
    """androidN_tp_correct (TpCorrectUtils.java:19-41): the eight floats of
    transaction 1050, order lb_x, lb_y, lt_x, lt_y, rt_x, rt_y, rb_x, rb_y."""
    ltx, lty, rtx, rty, lbx, lby, rbx, rby = px8
    w, h = float(screen_w), float(screen_h)
    return [f32(lbx / w), f32(lby / h), f32(ltx / w), f32(lty / h),
            f32(rtx / w), f32(rty / h), f32(rbx / w), f32(rby / h)]


_OPPOSITE = {"lt": ("rt", "lb"), "lb": ("rb", "lt"),
             "rt": ("lt", "rb"), "rb": ("lb", "rt")}


def clamp_corner(corners, name, value, min_h=1000, min_v=1000):
    """KeystoneUtils.setkeystoneValue (KeystoneUtils.java:146-275).  corners
    maps "lt"/"lb"/"rt"/"rb" to (x, y) per-mille; x is clamped against the
    corner on the same row, y against the one in the same column, so two
    opposite corners can never pull the picture in by more than its size."""
    ox, oy = _OPPOSITE[name]
    x, y = value
    if x < 0:
        x = 0
    elif corners[ox][0] + x > min_h:
        x = min_h - corners[ox][0]
    if y < 0:
        y = 0
    elif corners[oy][1] + y > min_v:
        y = min_v - corners[oy][1]
    return x, y
