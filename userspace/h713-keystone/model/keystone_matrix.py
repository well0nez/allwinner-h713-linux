"""Reference model of the H713 vendor keystone warp (analysis only, no device code).
Port of the ACTIVE vendor warp, function by function:
  getKeyStoneMatrix(float *tran)  [_Z17getKeyStoneMatrixPf]  @ 0x000031E8
  sub_3658 (4x4 multiply, column major, NEON)                @ 0x00003658
  draw_edge(int w, int h)         [_Z9draw_edgeii]           @ 0x00003C64
    all three in system_a_libkeystone.so, ELF32 ARM, IDA image base 0 (file offset ==
    virtual address), sha256 9b86b44807366bb77504905f172d1e77424eae81ec3deaff55235e7d02ec91b5
  KeystoneUtils.setkeystoneValue / UpdateKeystone            KeystoneUtils.java:146 / :306
  consumer: GLESRenderEngine::drawLayers @ 0x00118B50 in system_a_libsurfaceflinger.so does
    mProjectionMatrix (this+192) := K * mProjectionMatrix (call at 0x001192F8,
    android::details::operator*<float>) - K is applied AFTER that projection.
Conventions: a matrix is 16 floats in OpenGL COLUMN MAJOR order, m[4*col+row], translation in
m[12..14].  Input is eight integer per-mille inward insets in the order the apps send them
over binder transaction 1050: lb_x, lb_y, lt_x, lt_y, rt_x, rt_y, rb_x, rb_y.  The four
libkeystone slots are numbered 0..3 in that order; libkeystone's own log strings call them
"left top", "left bottom", "right bottom", "right top", which contradicts the app names (AP2
open question 4), so this module speaks of slots and keeps both name sets as constants.
The device computes in float32, this model in double (the wire values are rounded to float32
because the parcel carries float32), so expect 1e-7 relative agreement and not bit equality.
"""

import math
import struct

# ---------------------------------------------------------------- vendor constants
SLOT_NAMES = ("lb", "lt", "rt", "rb")                      # KeystoneUtils.UpdateKeystone :306
SLOT_LOG_NAMES = ("left top", "left bottom",               # libkeystone log strings inside
                  "right bottom", "right top")             # getKeyStoneMatrix @ 0x000031E8
VERTEX_Z = 0.2                    # gKeyStoneVertice @ 0x00006A04, z of every corner
DEFAULT_CORNERS = ((-1.0, 1.0), (-1.0, -1.0), (1.0, -1.0), (1.0, 1.0))  # the untouched panel
IDENTITY = (1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0)
DEFAULT_MIN_H = 1000              # KeystoneUtils.minH_size, overwritten by Config
DEFAULT_MIN_V = 1000              # KeystoneUtils.minV_size; the native check is 0..1000 each
ALIAS_ENABLE_DEFAULT = 1          # persist.display.keystone.alias.enable, draw_edge @ 0x00003C64
ALIAS_SCALE_DEFAULT = 4           # persist.display.keystone.alias.scale
ALIAS_EDGE_DEFAULT = 20           # persist.display.keystone.alias.edge
# The two shaders draw_edge really compiles, byte for byte out of .rodata (AP2 excerpts/08).
EDGE_VERTEX_SHADER = (            # string at 0x00001484, 178 bytes
    "#version 320 es\n"
    "out vec2 texCoord;\n"
    "in vec3 aOnScreenPosition;\n"
    "in vec3 aTexCoords;\n"
    "void main() {\n"
    "   texCoord = aTexCoords.xy;\n"
    "   gl_Position = vec4(aOnScreenPosition.xyz, 1.0);\n"
    "}\n")
EDGE_FRAGMENT_SHADER = (          # string at 0x000012B4, 180 bytes
    "#version 320 es\n"
    "precision mediump float;\n"
    "layout(binding=0) uniform sampler2D texSampler;\n"
    "in vec2 texCoord;\n"
    "out vec4 color;\n"
    "void main() {\n"
    "  color = texture(texSampler, texCoord);\n"
    "}\n")
EDGE_ATTRIBUTES = ("aOnScreenPosition", "aTexCoords")      # glGetAttribLocation in draw_edge
EDGE_UNIFORMS = ("texSampler",)                            # glGetUniformLocation, set to unit 5
# The dead tessellation path (render_frame @ 0x00003790) has four more shaders, at 0x00001553,
# 0x00001994, 0x000016AA and 0x00001D19; not modelled here - AP2 section 2b.


class KeystoneRejected(ValueError):
    """A corner left [-1, +1] in NDC - what getKeyStoneMatrix logs and refuses."""
    def __init__(self, slot, x, y):
        self.slot, self.x, self.y = slot, x, y
        ValueError.__init__(self, "%s:wrong input translation para, x:%5f, y:%5f"
                            % (SLOT_LOG_NAMES[slot], x, y))


def _f32(value):
    """Round to float32, the width of the parcel floats and of every vendor register."""
    return struct.unpack("<f", struct.pack("<f", float(value)))[0]


def _div(num, den):
    """C float division: libkeystone has no zero guard, a degenerate quad gives inf/nan."""
    if den == 0.0:
        if num == 0.0 or num != num:
            return float("nan")
        return math.copysign(float("inf"), num) * math.copysign(1.0, den)
    return num / den


# ---------------------------------------------------------------- app side
def clamp_permille(permille, min_h=DEFAULT_MIN_H, min_v=DEFAULT_MIN_V):
    """KeystoneUtils.setkeystoneValue @ KeystoneUtils.java:146-275, all four corners at once.

    x of a slot is clamped to [0, min_h - x of the slot at the other end of its row], y to
    [0, min_v - y of the slot at the other end of its column] (getKeystoneOppositeTo*XY,
    :113-145); the partner comes out of the persist.display.keystone_* properties, i.e. the
    value SurfaceFlinger last accepted.  The upper clamp is not clamped to zero again, so a
    partner above min_h/min_v (only reachable after Config lowered them) yields a negative
    value - the vendor's behaviour.
    """
    v = [int(x) for x in permille]
    if len(v) != 8:
        raise ValueError("expected 8 per-mille values, got %d" % len(v))
    row_partner = (3, 2, 1, 0)        # lb<->rb, lt<->rt on x   (same panel row)
    col_partner = (1, 0, 3, 2)        # lb<->lt, rt<->rb on y   (same panel column)
    for slot in range(4):             # four setkeystoneValue calls in slot order
        x, y = v[2 * slot], v[2 * slot + 1]
        v[2 * slot] = 0 if x < 0 else min(x, min_h - v[2 * row_partner[slot]])
        v[2 * slot + 1] = 0 if y < 0 else min(y, min_v - v[2 * col_partner[slot] + 1])
    return tuple(v)


def fractions_from_permille(permille):
    """UpdateKeystone :306-331 - value * 0.001 as a double, written as a float32 parcel float."""
    return tuple(_f32(int(t) * 0.001) for t in permille)


# ---------------------------------------------------------------- getKeyStoneMatrix
def corners_from_ndc_fractions(tran, check=True):
    """Step 1 of getKeyStoneMatrix @ 0x000031E8: eight fractions -> gKeyStoneVertice.

        v0 = ( 2*t0 - 1 ,  1 - 2*t1 , 0.2 )      slot 0, app "lb", log "left top"
        v1 = ( 2*t2 - 1 ,  2*t3 - 1 , 0.2 )      slot 1, app "lt", log "left bottom"
        v2 = ( 1 - 2*t4 ,  2*t5 - 1 , 0.2 )      slot 2, app "rt", log "right bottom"
        v3 = ( 1 - 2*t6 ,  1 - 2*t7 , 0.2 )      slot 3, app "rb", log "right top"

    Every coordinate is checked against [-1, +1]; the first failure raises.  Slots 0..2 are
    rejected by "x < -1 or x > 1 or y < -1 or y > 1", slot 3 by the negated form, so a NaN
    passes 0..2 and is rejected by 3 - a vendor asymmetry, kept.  check=False skips the check,
    which is how KeystoneState reproduces a partially updated gKeyStoneVertice.
    """
    t = [float(x) for x in tran]
    if len(t) != 8:
        raise ValueError("expected 8 fractions, got %d" % len(t))
    corners = [(t[0] + t[0] - 1.0, 1.0 - (t[1] + t[1])),
               (t[2] + t[2] - 1.0, t[3] + t[3] - 1.0),
               (1.0 - (t[4] + t[4]), t[5] + t[5] - 1.0),
               (1.0 - (t[6] + t[6]), 1.0 - (t[7] + t[7]))]
    for slot in range(4 if check else 0):
        x, y = corners[slot]
        bad = ((y < -1.0) or (x > 1.0) or (x < -1.0) or (y > 1.0) if slot < 3
               else not (y >= -1.0 and x <= 1.0 and x >= -1.0 and y <= 1.0))
        if bad:
            raise KeystoneRejected(slot, x, y)
    return tuple((x, y, VERTEX_Z) for x, y in corners)


def mat_mul(a, b):
    """sub_3658 @ 0x00003658: out = a * b, column major, column of out from columns of a."""
    out = [0.0] * 16
    for j in range(4):
        for r in range(4):
            out[4 * j + r] = (a[r] * b[4 * j] + a[4 + r] * b[4 * j + 1]
                              + a[8 + r] * b[4 * j + 2] + a[12 + r] * b[4 * j + 3])
    return tuple(out)


def unit_square_to_quad(corners):
    """Step 2 of getKeyStoneMatrix @ 0x000031E8 (+0x1B0..+0x310): the projective solve.

    The classic unit-square-to-quad homography with the origin at v1, u towards v2 and v
    towards v0, two cross products and NO pivoting - no branch, no swap, no degeneracy test
    in the vendor code, only the two divisions below:

        A = (v0.x-v3.x)*(v2.y-v3.y)        B = (v2.x-v3.x)*(v0.y-v3.y)
        N = v1.x + v3.x - v2.x - v0.x      D = v1.y + v3.y - v2.y - v0.y
        g = ((v2.x-v3.x)*D - N*(v2.y-v3.y)) / (B - A)     -> m[7],  the v perspective term
        h = ((v0.x-v3.x)*D - N*(v0.y-v3.y)) / (A - B)     -> m[3],  the u perspective term
        m[0] = v2.x - v1.x + v2.x*h        m[1] = v2.y - v1.y + v2.y*h
        m[4] = v0.x - v1.x + v0.x*g        m[5] = v0.y - v1.y + v0.y*g
        m[12] = v1.x                       m[13] = v1.y
    B - A is the cross product of (v2-v3) and (v0-v3), zero exactly for a degenerate quad -
    the vendor then divides by zero and stores inf/nan, which _div reproduces.
    """
    (v0x, v0y), (v1x, v1y), (v2x, v2y), (v3x, v3y) = [(c[0], c[1]) for c in corners]
    a = (v0x - v3x) * (v2y - v3y)
    b = (v2x - v3x) * (v0y - v3y)
    n = (v1x + (v3x - v2x)) - v0x
    d = (v1y + (v3y - v2y)) - v0y
    g = _div((v2x - v3x) * d - n * (v2y - v3y), b - a)
    h = _div((v0x - v3x) * d - n * (v0y - v3y), a - b)
    return (v2x - v1x + v2x * h, v2y - v1y + v2y * h, 0.0, h,
            v0x - v1x + v0x * g, v0y - v1y + v0y * g, 0.0, g,
            0.0, 0.0, 1.0, 0.0,
            v1x, v1y, 0.0, 1.0)


# The two fixed matrices getKeyStoneMatrix builds on the stack before the solve, out of the
# prologue at 0x00003208..0x00003278: NDC -> unit square, applied right to left.
NDC_SCALE = (0.5, 0.0, 0.0, 0.0, 0.0, 0.5, 0.0, 0.0,      # at sp+0xD0, diag(0.5, 0.5, 1, 1)
             0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0)
NDC_TRANSLATE = (1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0,  # at sp+0x110, translate(1, 1, 1)
                 0.0, 0.0, 1.0, 0.0, 1.0, 1.0, 1.0, 1.0)  # m[14] = 1.0 translates z as well:
# it cancels the near plane of the vendor's projection (setViewportAndProjection @ 0x0011AA64
# builds a FRUSTUM, near 1, far 2, m[11] = -1, m[15] = 0), so z_clip ends at 0 for every vertex.
# A port feeding a z = 0 quad gets z_clip = 1 instead and loses every vertex whose w drops below
# 1 - drop the z part of the translate there, or put the quad at z = -1.


def keystone_matrix(permille, clamp=False, min_h=DEFAULT_MIN_H, min_v=DEFAULT_MIN_V):
    """Eight per-mille inward insets -> the 4x4 SurfaceFlinger post-multiplies, column major.

    K = M1 * NDC_SCALE * NDC_TRANSLATE - the two sub_3658 calls at 0x000034F8 (M1*S) and
    0x00003504 ((M1*S)*T).  Raises KeystoneRejected like the vendor.
    """
    if clamp:
        permille = clamp_permille(permille, min_h, min_v)
    corners = corners_from_ndc_fractions(fractions_from_permille(permille))
    return mat_mul(mat_mul(unit_square_to_quad(corners), NDC_SCALE), NDC_TRANSLATE)


def apply_matrix(m, x, y, z=0.0):
    """Project one point through a column-major 4x4 and divide out w, as the rasteriser does."""
    xo = m[0] * x + m[4] * y + m[8] * z + m[12]
    yo = m[1] * x + m[5] * y + m[9] * z + m[13]
    zo = m[2] * x + m[6] * y + m[10] * z + m[14]
    w = m[3] * x + m[7] * y + m[11] * z + m[15]
    return (xo / w, yo / w, zo / w)


def to_float32(m):
    """Round a matrix to the float32 the device stores in gKeyStoneMatrix @ 0x00006914."""
    return tuple(_f32(v) for v in m)


class KeystoneState(object):
    """The three libkeystone globals, so the cache and the partial update can be tested:
    gLastTran @ 0x00006A34 (32 bytes, memcmp'd), gKeyStoneMatrix @ 0x00006914 (last good
    result, identity at load), gKeyStoneVertice @ 0x00006A04 (.bss, zero at load).  Two
    vendor behaviours only show up here: the first call after boot with eight zeros is a
    memcmp HIT, so the boot path returns the identity from the cache and never runs the solve;
    and a changed tran first overwrites gLastTran and resets gKeyStoneVertice to the default
    quad, then fills it corner by corner, so a rejected set leaves a mix behind - and that
    mix is what draw_edge draws.
    """

    def __init__(self):
        self.last_tran = (0.0,) * 8
        self.matrix = IDENTITY
        self.vertices = ((0.0, 0.0, 0.0),) * 4          # .bss

    def update(self, permille, clamp=False, min_h=DEFAULT_MIN_H, min_v=DEFAULT_MIN_V):
        """One getKeyStoneMatrix call; returns the matrix, keeps the previous one on refusal."""
        if clamp:
            permille = clamp_permille(permille, min_h, min_v)
        tran = fractions_from_permille(permille)
        if tran == self.last_tran:
            return self.matrix
        self.last_tran = tran
        self.vertices = tuple((x, y, VERTEX_Z) for x, y in DEFAULT_CORNERS)
        try:
            corners = corners_from_ndc_fractions(tran)
        except KeystoneRejected as exc:
            accepted = list(self.vertices)
            raw = corners_from_ndc_fractions(tran, check=False)
            for slot in range(exc.slot):
                accepted[slot] = raw[slot]
            self.vertices = tuple(accepted)
            return self.matrix
        self.vertices = corners
        self.matrix = mat_mul(mat_mul(unit_square_to_quad(corners), NDC_SCALE), NDC_TRANSLATE)
        return self.matrix


# ---------------------------------------------------------------- draw_edge
def edge_quad(width, height, corners=None, enable=ALIAS_ENABLE_DEFAULT,
              scale=ALIAS_SCALE_DEFAULT, edge=ALIAS_EDGE_DEFAULT):
    """draw_edge @ 0x00003C64: the anti-aliasing quad over the warped picture, or None.

    enable/scale/edge are persist.display.keystone.alias.{enable,scale,edge}, property_get_int32
    with defaults 1/4/20; scale == 0 falls back to 4 (+0x96).  The mask is ((w/scale)+15) & ~15
    by ((h/scale)+15) & ~15 GL_ALPHA texels, one-texel border 255-edge, interior 0, built once
    (gEdgeStart) and reused - a later resolution change does NOT rebuild it.  The positions are
    the x and y of gKeyStoneVertice copied into gLumFullScreenVertices @ 0x00006954 (only x and
    y, so z stays the 0.2 from .data); the texture coordinates are the untouched
    gLumFullTexVertice @ 0x00006984.  GL_TRIANGLE_FAN, 4 vertices, texture unit 5, GL_BLEND,
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA).
    """
    if not enable:
        return None
    scale = scale or 4                # CMP R4,#0 / MOVEQ R4,#4 at 0x00003CF2..0x00003CFA
    if corners is None:
        corners = tuple((x, y, VERTEX_Z) for x, y in DEFAULT_CORNERS)
    mask_w = (int(width) // scale + 15) & ~15
    mask_h = (int(height) // scale + 15) & ~15
    return {
        "mask_width": mask_w, "mask_height": mask_h, "mask_texels": mask_w * mask_h,
        "border_value": 255 - edge, "interior_value": 0,
        "format": "GL_ALPHA/GL_UNSIGNED_BYTE",
        "positions": tuple((c[0], c[1], VERTEX_Z) for c in corners),
        "tex_coords": ((0.0, 1.0, VERTEX_Z), (0.0, 0.0, VERTEX_Z),
                       (1.0, 0.0, VERTEX_Z), (1.0, 1.0, VERTEX_Z)),
        "draw_mode": "GL_TRIANGLE_FAN", "vertex_count": 4, "texture_unit": 5,
        "blend": ("GL_SRC_ALPHA", "GL_ONE_MINUS_SRC_ALPHA"),
    }


def edge_mask(mask_width, mask_height, border_value):
    """The texels draw_edge uploads: zero everywhere, border_value on the outermost ring."""
    buf = bytearray(mask_width * mask_height)
    buf[0:mask_width] = bytes(bytearray([border_value])) * mask_width
    buf[(mask_height - 1) * mask_width:] = bytes(bytearray([border_value])) * mask_width
    for y in range(mask_height):
        buf[y * mask_width] = border_value
        buf[y * mask_width + mask_width - 1] = border_value
    return bytes(buf)
