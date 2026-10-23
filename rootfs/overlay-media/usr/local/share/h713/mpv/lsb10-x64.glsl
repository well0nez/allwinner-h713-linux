// lsb10-x64.glsl - 10 bit samples in the low bits of a 16-bit word (the AV1 core's PL10, exported as linear P010
// with V4L2_REQUEST_LSB10_LINEAR=1) read by GL as v/65535; times 64 they are P010's v<<6, which mpv's conversion expects.
// Hooked on the planes, before the YUV->RGB matrix, which would otherwise get a picture 64 times too dark.
// Written for this project from the mpv user-shader manual; mpv --profile=av1-10bit loads it (/etc/mpv/mpv.conf).
//!HOOK LUMA
//!HOOK CHROMA
//!BIND HOOKED
vec4 hook() { vec4 c = HOOKED_tex(HOOKED_pos); return vec4(c.rgb * 64.0, c.a); }
