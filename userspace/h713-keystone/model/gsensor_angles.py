#!/usr/bin/env python3
"""Raw accelerometer counts -> the GsX/GsY the vendor keystone consumes.

A host-side reference for the whole chain on the HY310 projector.  Kernel
half: chip register pair -> counts (stk_read_accel_rawdata @ 0xC06BC5F4), the
axis swap its two callers apply (stk_work_queue @ 0xC06BD1D4 and
shake_for_vafocus @ 0xC06BEAE0), and what sensor_xyz_mode_show @ 0xC06BB6E4
prints.  App half: GsensorUtils.get_xyz_intVal (GsensorUtils.java:112-143),
setgsensorInit (arm64 0x00026A38, arm32 0x0001C890), get_gsensor_du (arm64
0x00026A60, arm32 0x0001C8BC) and the sign flip, dead band and 360.0 sentinel
of LocalService.optKeystoneFun (LocalService.java:1099-1130).  0xC06Bxxxx is
ida/vmlinux.elf.i64, the rest ida/libduRYXtp-arm{64,32}.so.i64 (sha256 in
REPORT.txt section 0).

GsX is the roll about the optical axis, GsY the pitch.  AP2c's
draw_ret_map_point @ 0x0002EC28 takes them as its third and fourth argument:
gs_y replaces the camera pitch (du_y_eff = -gs_y - OFF_AXIS) whenever
-60 < gs_y < 60, and gs_x is the z rotation of set_rotate_yxz / set_rotate_zxy.
"""

import math
import struct

_F32 = struct.Struct("<f")
DEG_PER_RAD = 57.29578            # the vendor's constant, not 180/math.pi


def f32(x):
    """Round to IEEE-754 binary32, as every VFP float store does."""
    return _F32.unpack(_F32.pack(x))[0]


def i32(x):
    """Wrap to signed 32-bit, as the MUL/MADD of the sums of squares do."""
    x &= 0xFFFFFFFF
    return x - 0x100000000 if x >= 0x80000000 else x


def fsqrt(x):
    """FSQRT: a negative operand gives NaN instead of raising."""
    return math.sqrt(x) if x >= 0.0 else float("nan")


def fdiv(a, b):
    """FDIV: no trap.  0/0 is NaN, x/0 a signed infinity.  A level device takes
    this path: with x = y = 0 the z term divides by zero and GsZ reads 90."""
    if b != 0.0:
        return a / b
    return float("nan") if a == 0.0 else math.copysign(float("inf"), a)


# ---------------------------------------------------------------------------
# 1  KERNEL SIDE - drivers/input/sensor/stk/stk83xx/stk83xx.c
# ---------------------------------------------------------------------------
# stk_get_pid @ 0xC06BBD78 reads register 0x0F three times.  0x11 means an
# SC7A20 (LIS2DH register map, WHO_AM_I at 0x0F); it then sets device_chip = 1
# and RETURNS, so data_shift (stk_data+0x66) keeps its kzalloc value 0.
# Otherwise register 0x00 holds the Sensortek PID and selects the shift.
SC7A20_WHO_AM_I = 0x11
STK_DATA_SHIFT = {0x23: 4, 0x25: 0, 0x26: 0, 0x86: 6, 0x87: 4}
# sc7a20_reg_init @ 0xC06BF050, in write order.  0x23 = 0x98 is BDU + full
# scale 01 (+-4 g) + HR (12 bit), 0x20 = 0x37 is ODR 25 Hz with x/y/z enabled.
SC7A20_REG_INIT = ((0x20, 0x37), (0x1F, 0x01), (0x23, 0x98), (0x21, 0x73),
                   (0x30, 0x2A), (0x32, 0x02), (0x33, 0x00), (0x25, 0x03),
                   (0x22, 0x10))
# HR leaves the 12-bit sample left justified and the driver never shifts it
# back, so one g is 500 digits * 16 (2 mg per digit).
SC7A20_COUNTS_PER_G = 8000
SC7A20_IIO_SHIFT = 4              # st_accel 12-bit channel, scan_type.shift

# stk_range_selection @ 0xC06BBF28 writes register 0x0F; its low nibble
# 3/5/8/12 (+-2/4/8/16 g) maps to counts per g.  The 16 g row forgets the pid.
STK_SENSITIVITY = {
    3: {0x25: 0x4000, 0x26: 0x4000, 0x86: 256, "default": 1024},
    5: {0x25: 0x2000, 0x26: 0x2000, 0x86: 128, "default": 512},
    8: {0x25: 0x1000, 0x26: 0x1000, 0x86: 64, "default": 256},
    12: {"default": 2048}}


def decode_block(block6, data_shift=0):
    """stk_read_accel_rawdata @ 0xC06BC5F4: six bytes, three little endian s16
    arithmetically shifted right by data_shift.  The SC7A20 burst is register
    0xA8 (0x28 auto-increment), the Sensortek 0x02; both give X, Y, Z."""
    out = []
    for k in range(0, 6, 2):
        v = block6[k] | (block6[k + 1] << 8)
        if v >= 0x8000:
            v -= 0x10000
        out.append(v >> data_shift)
    return tuple(out)


# stk_work_queue @ 0xC06BD1D4 calls shake_for_vafocus(-xyz[0], xyz[1], xyz[2])
# ("RSB R0, R0, #0" at 0xC06BD1E0) and shake_for_vafocus @ 0xC06BEAE0 calls
# set_cur_gsensor_xyz(cur_y, -cur_x, cur_z, 1), so the two negations of the
# chip x cancel: a plain x/y swap, determinant -1, a mirror not a rotation.
KERNEL_REMAP = ((0, 1, 0), (1, 0, 0), (0, 0, 1))


def kernel_axis_remap(chip_xyz, matrix=KERNEL_REMAP):
    """Chip axes -> the triple set_cur_gsensor_xyz @ 0xC06BB98C stores in
    g_last_x / g_last_y / g_last_z.  KERNEL_REMAP is its own inverse."""
    return tuple(sum(m[k] * chip_xyz[k] for k in range(3)) for m in matrix)


# stk,direction (stk_data+0x4C) and stk,swipe_xy (+0x50) are stored by
# stk_i2c_probe @ 0xC06BF944 / 0xC06BF950 and read back by stk_direction_show
# @ 0xC06BD8F8 and stk_swipe_xy_show @ 0xC06BD8D0.  Nothing else in
# 0xC06BB000..0xC06C1600 touches them, so direction = 2 moves no axis here.
DIRECTION_REMAP = {d: KERNEL_REMAP for d in range(8)}


def xyz_data_text(triple):
    """sensor_xyz_mode_show @ 0xC06BB6E4: sprintf(buf, "%d,%d,%d\\n", g_last_x,
    g_last_y, g_last_z).  Raw counts, refreshed every report_cnt-th work queue
    run (report_cnt = 2 at 0xC147B700).  The 4-sample average in
    shake_for_vafocus feeds sensor_angle, so xyz_data has no low-pass."""
    return "%d,%d,%d\n" % tuple(triple)


def parse_xyz_data(text):
    """GsensorUtils.get_xyz_intVal (GsensorUtils.java:112-143), by hand and
    quirky: a '-' anywhere in a field only counts if it is the character the
    field started on, and any non-digit closes the field."""
    out = [0, 0, 0]
    if text is None:
        return out
    i, minus = 0, 0
    for k, ch in enumerate(text):
        if i > 2:
            break
        if ch == "-":
            minus = k
        elif "0" <= ch <= "9":
            out[i] = out[i] * 10 + (ord(ch) - 48)
            if k + 1 == len(text) and text[minus] == "-":
                out[i] = -out[i]
        else:
            if text[minus] == "-":
                out[i] = -out[i]
            i += 1
            minus = k + 1
    return out


# ---------------------------------------------------------------------------
# 2  APP AND LIBRARY SIDE - com.hysd.vafocus plus libduRYXtp.so
# ---------------------------------------------------------------------------
_INIT = [0, 0, 0]                 # gXInitsensorVal, gYInitsensorVal, gZInit...


def atan_call(v):
    """_Z8atanCallf, arm64 0x00011930 / arm32 0x0000B5A8: atanf in single
    precision, widened, times 57.29578 in double."""
    return f32(math.atan(f32(v))) * DEG_PER_RAD


def set_gsensor_init(x, y, z):
    """setgsensorInit @ 0x00026A38 (arm32 0x0001C890), fed from the factory
    string "x,y,z" under SecureStorage / Settings.Global key GsInitXYZ."""
    _INIT[:] = [int(x), int(y), int(z)]
    return list(_INIT)


def check_gsensor_data_ok(x, y, z):
    """LocalService.checkGsensorDataOk (LocalService.java:582), the gate the
    factory reference must pass: not all zero, z >= 0, |x| and |y| <= |z|."""
    return (not (x == 0 and y == 0 and z == 0)) and z >= 0 \
        and abs(x) <= abs(z) and abs(y) <= abs(z)


def _axis_angles(v):
    """The three atan terms: the angle between the gravity vector and the plane
    each axis is normal to.  Sums of squares 32-bit int, division and
    subtraction double, the argument of atanf and the result float."""
    x, y, z = int(v[0]), int(v[1]), int(v[2])
    if x == 0 and y == 0 and z == 0:
        return (0.0, 0.0, 0.0)     # the all-zero guards at 0x00026AD8, 0x26B78
    xx, yy, zz = i32(x * x), i32(y * y), i32(z * z)
    return (atan_call(fdiv(x, fsqrt(i32(zz + yy)))),
            atan_call(fdiv(y, fsqrt(i32(zz + xx)))),
            atan_call(fdiv(z, fsqrt(i32(yy + xx)))))


def get_gsensor_du(x, y, z, init=None):
    """get_gsensor_du @ 0x00026A60 (arm32 0x0001C8BC): the three tilt angles in
    degrees, current attitude minus the stored factory attitude.  Index 0 is
    GsX, index 1 GsY, index 2 the unused GsZ."""
    cur = _axis_angles((x, y, z))
    ref = _axis_angles(_INIT if init is None else init)
    return tuple(f32(cur[k] - ref[k]) for k in range(3))


DEAD_BAND_DEG = 0.3               # LocalService.java:1121
DEAD_BAND_S7CI20_DEG = 5.0        # LocalService.java:1113, sensor_type == 2
GSY_IGNORE = 360.0                # "this axis carries no information"


def opt_keystone_angles(counts, init=None, sensor_type=1, hsavetype=0,
                        tpwithgsy=True):
    """LocalService.optKeystoneFun (LocalService.java:1099-1130): the two
    angles handed to AP2c's draw_ret_map_point.  sensor_type (sensor_type_show
    @ 0xC06BB6C0) can only read 0, 1, 3, 4 or 5 here, so the 5.0 degree branch
    is dead code, modelled only because the app still carries it."""
    du = get_gsensor_du(counts[0], counts[1], counts[2], init)
    gs_x, gs_y = du[0], du[1]
    if counts[2] < 0:                      # z below: the device hangs over
        gs_x, gs_y = f32(-gs_x), f32(-gs_y)
    if sensor_type == 2:
        if hsavetype == 1:
            gs_y = GSY_IGNORE
        if -DEAD_BAND_S7CI20_DEG < gs_x < DEAD_BAND_S7CI20_DEG:
            gs_x = 0.0
    elif -DEAD_BAND_DEG < gs_x < DEAD_BAND_DEG:
        gs_x = 0.0                         # GsY has NO dead band
    if not tpwithgsy:                      # persist.sys.tpwithgsy == "0"
        gs_y = GSY_IGNORE
    return gs_x, gs_y


# --- 3  THE MAINLINE IIO EQUIVALENT ----------------------------------------
# st_accel_core.c:1245ff serves the SC7A20 with st_accel_12bit_channels and
# st_sensors_read_raw does "*val >>= ch->scan_type.shift" (shift = 4), so
# in_accel_*_raw is the 12-bit digit and in_accel_scale IIO_G_TO_M_S_2(2000).
# The atan arguments are ratios, so a common positive factor cancels exactly.
IIO_TO_VENDOR_AXIS = {"y": 0, "x": 1, "z": 2}


def iio_to_vendor_counts(accel_x, accel_y, accel_z,
                         factor=1 << SC7A20_IIO_SHIFT):
    """in_accel_{x,y,z}_raw -> the triple xyz_data would print.  The swap is
    KERNEL_REMAP; factor only restores the left justification and never changes
    an angle."""
    return (accel_y * factor, accel_x * factor, accel_z * factor)


def counts_from_gvector(gx, gy, gz, counts_per_g=SC7A20_COUNTS_PER_G):
    """A synthetic ADC: a gravity vector in the VENDOR frame -> counts."""
    return tuple(int(round(c * counts_per_g)) for c in (gx, gy, gz))


def gvector_for_tilt(pitch_deg, roll_deg=0.0):
    """The unit gravity vector in the vendor frame for a projector pitched up
    by pitch_deg and rolled by roll_deg.  GsY reads the pitch back exactly at
    any roll, GsX the roll only at zero pitch: the two do not commute."""
    p, r = math.radians(pitch_deg), math.radians(roll_deg)
    v = (math.sin(r) * math.cos(p), math.sin(p), math.cos(p) * math.cos(r))
    n = math.sqrt(sum(c * c for c in v))
    return tuple(c / n for c in v)
