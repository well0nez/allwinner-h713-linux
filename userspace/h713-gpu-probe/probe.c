/* SPDX-License-Identifier: GPL-2.0 */
/*
 * h713-gpu-probe -- the GPU foundation tool for keystone stages S1 and S2:
 * GBM + EGL + GLES2 on the render node, no window system, no display.
 *
 *   h713-gpu-probe [-d /dev/dri/renderD128] info | render N | load SECONDS
 *
 * info: EGL/GL strings and "present"/"MISSING" for the four extensions the warp
 * needs (AP2d M6); exit 0 only with all four. render: a 256x256 test texture,
 * nearest sampled on one full-viewport quad into a 1920x1080 RGBA8 FBO for N
 * frames; every 100th frame is read back and its CRC32 checked against the CPU
 * rule stated at expect_crc(). load: 64 dependent texture fetches per fragment
 * for SECONDS; every 100th frame's CRC32 against the first sample's. Both modes
 * glFinish per frame (one frame in flight, as the warp runs), so the fps carry
 * the submit gap. Exit 0 only if every sample matched. CRC32 is zlib's.
 */
#define _GNU_SOURCE
#define EGL_NO_X11
#include <fcntl.h>
#include <glob.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <zlib.h>
#include <gbm.h>          /* before EGL: defines __GBM__, the native types */
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <GLES2/gl2.h>

#define W 1920
#define H 1080
#define TW 256
#define S(x) ((x) ? (const char *)(x) : "n/a")

static EGLDisplay dpy;
static int have_ctx, missing;
static const char *VS =
	"attribute vec2 a_pos; attribute vec2 a_uv; varying vec2 v_uv;\n"
	"void main() { gl_Position = vec4(a_pos, 0.0, 1.0); v_uv = a_uv; }\n";
static const char *FS_RENDER =
	"precision highp float; varying vec2 v_uv; uniform sampler2D u_tex;\n"
	"void main() { gl_FragColor = texture2D(u_tex, v_uv); }\n";
static const char *FS_LOAD =
	"precision highp float; varying vec2 v_uv; uniform sampler2D u_tex;\n"
	"void main() { vec2 p = v_uv; vec4 acc = vec4(0.0);\n"
	"  for (int i = 0; i < 64; i++) { vec4 t = texture2D(u_tex, p);\n"
	"    acc += t; p = fract(p + t.xy * 0.37 + vec2(0.013, 0.029)); }\n"
	"  gl_FragColor = acc / 64.0; }\n";
static const char *NEED[] = { "EGL_EXT_image_dma_buf_import", "EGL_KHR_surfaceless_context",
			      "EGL_ANDROID_native_fence_sync", "GL_OES_EGL_image" };
static const char *SYS[][2] = {
	{ "zone0", "/sys/class/thermal/thermal_zone0/temp" },
	{ "zone1", "/sys/class/thermal/thermal_zone1/temp" },
	{ "fan1", "/sys/class/hwmon/hwmon*/fan1_input" },
	{ "gpu_freq", "/sys/class/devfreq/1800000.gpu/cur_freq" },
	{ "gpu_pm", "/sys/devices/platform/soc/1800000.gpu/power/runtime_status" } };

static int fail(const char *what)
{
	fprintf(stderr, "h713-gpu-probe: %s: egl 0x%x gl 0x%x\n", what, eglGetError(),
		have_ctx ? glGetError() : 0);
	return 1;
}

static int has_ext(const char *list, const char *name)
{
	size_t n = strlen(name);
	for (; list && (list = strstr(list, name)); list += n)
		if (list[n] == ' ' || !list[n])
			return 1;
	return 0;
}

static double now(void)
{
	struct timespec ts;
	clock_gettime(CLOCK_MONOTONIC, &ts);
	return ts.tv_sec + ts.tv_nsec / 1e9;
}

/* One line with the first line of every SYS file (glob), n/a if unreadable. */
static void status(double t)
{
	char buf[64];
	glob_t g;
	FILE *f;
	int i;
	printf("status t=%.0fs", t);
	for (i = 0; i < 5; i++) {
		f = !glob(SYS[i][1], 0, NULL, &g) && g.gl_pathc ? fopen(g.gl_pathv[0], "r") : NULL;
		globfree(&g);
		if (!f || !fgets(buf, sizeof buf, f))
			strcpy(buf, "n/a");
		if (f)
			fclose(f);
		printf(" %s=%.*s", SYS[i][0], (int)strcspn(buf, "\n"), buf);
	}
	printf("\n");
	fflush(stdout);
}

/* GBM device, EGL display, surfaceless ES2 context, the strings, the NEED[]
 * lines. No pbuffer fallback: Mesa's GBM platform offers EGL_WINDOW_BIT
 * configs only (platform_drm.c), and its EGL always has surfaceless. */
static int setup(const char *dev)
{
	static const EGLint cattr[] = { EGL_CONTEXT_CLIENT_VERSION, 2, EGL_NONE };
	static const EGLint attr[] = { EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT, EGL_NONE };
	int fd = open(dev, O_RDWR | O_CLOEXEC), i, rc = 0;
	struct gbm_device *gbm = fd < 0 ? NULL : gbm_create_device(fd);
	const char *el, *gl = NULL;
	EGLContext ctx;
	EGLConfig cfg;
	EGLint n = 0, v[2];
	if (!gbm) {
		perror(dev);
		return 1;
	}
	dpy = eglGetPlatformDisplay(EGL_PLATFORM_GBM_KHR, gbm, NULL);
	if (dpy == EGL_NO_DISPLAY)
		dpy = eglGetDisplay((EGLNativeDisplayType)gbm);
	if (dpy == EGL_NO_DISPLAY || !eglInitialize(dpy, v, v + 1))
		return fail("eglInitialize");
	printf("egl vendor %s\negl version %s\n", S(eglQueryString(dpy, EGL_VENDOR)),
	       S(eglQueryString(dpy, EGL_VERSION)));
	el = eglQueryString(dpy, EGL_EXTENSIONS);
	if (!eglBindAPI(EGL_OPENGL_ES_API) || !eglChooseConfig(dpy, attr, &cfg, 1, &n) || !n ||
	    (ctx = eglCreateContext(dpy, cfg, EGL_NO_CONTEXT, cattr)) == EGL_NO_CONTEXT ||
	    !eglMakeCurrent(dpy, EGL_NO_SURFACE, EGL_NO_SURFACE, ctx)) {
		rc = fail("surfaceless ES2 context");
	} else {
		have_ctx = 1;
		gl = (const char *)glGetString(GL_EXTENSIONS);
		printf("gl renderer %s\ngl version %s\n", S(glGetString(GL_RENDERER)),
		       S(glGetString(GL_VERSION)));
	}
	for (i = 0; i < 4; i++, missing += !n) {
		n = has_ext(i < 3 ? el : gl, NEED[i]);
		printf("%s %s\n", NEED[i], n ? "present" : "MISSING");
	}
	return rc;
}

/* Program, test texture, 1920x1080 FBO, the quad: everything but the draw. */
static int scene(const char *fs)
{
	static const GLfloat quad[] = { -1, -1, 0, 0,  1, -1, W / 2048.f, 0,
					-1, 1, 0, H / 1024.f,  1, 1, W / 2048.f, H / 1024.f };
	static unsigned char tex[TW * TW * 4];
	const char *src[] = { VS, fs };
	GLuint prog = glCreateProgram(), t[2], s, fb;
	GLint ok = 0;
	char log[512];
	int i;
	for (i = 0; i < 2; i++) {
		s = glCreateShader(i ? GL_FRAGMENT_SHADER : GL_VERTEX_SHADER);
		glShaderSource(s, 1, &src[i], NULL);
		glCompileShader(s);
		glGetShaderiv(s, GL_COMPILE_STATUS, &ok);
		if (!ok) {
			glGetShaderInfoLog(s, sizeof log, NULL, log);
			return fail(log);
		}
		glAttachShader(prog, s);
	}
	glBindAttribLocation(prog, 0, "a_pos");
	glBindAttribLocation(prog, 1, "a_uv");
	glLinkProgram(prog);
	glGetProgramiv(prog, GL_LINK_STATUS, &ok);
	if (!ok)
		return fail("program link");
	for (i = 0; i < TW * TW; i++) {
		tex[i * 4] = i % TW; tex[i * 4 + 1] = i / TW;
		tex[i * 4 + 2] = (i % TW) ^ (i / TW); tex[i * 4 + 3] = 255;
	}
	glGenTextures(2, t);
	glGenFramebuffers(1, &fb);
	glBindTexture(GL_TEXTURE_2D, t[1]);                    /* the FBO colour */
	glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, W, H, 0, GL_RGBA, GL_UNSIGNED_BYTE, NULL);
	glBindFramebuffer(GL_FRAMEBUFFER, fb);
	glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, t[1], 0);
	if (glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE)
		return fail("framebuffer incomplete");
	glBindTexture(GL_TEXTURE_2D, t[0]);                    /* the test texture */
	glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
	glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
	glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
	glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
	glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, TW, TW, 0, GL_RGBA, GL_UNSIGNED_BYTE, tex);
	glViewport(0, 0, W, H);
	glUseProgram(prog);
	glUniform1i(glGetUniformLocation(prog, "u_tex"), 0);
	for (i = 0; i < 2; i++) {
		glVertexAttribPointer(i, 2, GL_FLOAT, GL_FALSE, 16, quad + 2 * i);
		glEnableVertexAttribArray(i);
	}
	return glGetError() ? fail("scene setup") : 0;
}

/* CRC rule. The quad magnifies the texture by powers of two, 8x in x and 4x
 * in y, with CLAMP_TO_EDGE, so pixel (x, y) - y from the bottom, as
 * glReadPixels delivers it - shows texel (x / 8, min(y / 4, 255)), and texel
 * (tx, ty) = (tx, ty, tx ^ ty, 255). Every sample point is exactly
 * representable in float and >= 1/16 texel from a texel boundary, so nearest
 * sampling is exact on any GPU. The brief's floor(x * 256 / 1920) puts 128
 * columns and 8 rows exactly on a boundary, implementation-defined there. */
static unsigned long expect_crc(void)
{
	unsigned char row[W * 4];
	unsigned long crc = crc32(0L, Z_NULL, 0);
	int x, y, ty;
	for (y = 0; y < H; y++) {
		ty = y / 4 < TW ? y / 4 : TW - 1;
		for (x = 0; x < W; x++) {
			row[x * 4] = x / 8; row[x * 4 + 1] = ty;
			row[x * 4 + 2] = (x / 8) ^ ty; row[x * 4 + 3] = 255;
		}
		crc = crc32(crc, row, sizeof row);
	}
	return crc;
}

/* frames > 0: render mode, samples against want; else load mode for seconds,
 * samples against the first one. Returns the number of mismatching samples. */
static int run(long frames, double seconds, unsigned long want)
{
	unsigned char *pix = malloc((size_t)W * H * 4);
	double t0 = now(), t, t_sample = t0, t_status = t0, fps, lo = 1e9, hi = 0;
	long frame = 0, f_sample = 0, f_status = 0;
	int bad = 0, last;
	if (!pix)
		return fail("malloc");
	if (frames)
		printf("expect crc %08lx\n", want);
	do {
		frame++;
		glClear(GL_COLOR_BUFFER_BIT);
		glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
		glFinish();
		t = now();
		last = frames ? frame >= frames : t - t0 >= seconds;
		if (frame % 100 == 0 || last) {
			unsigned long crc;
			fps = (frame - f_sample) / (t - t_sample);
			glReadPixels(0, 0, W, H, GL_RGBA, GL_UNSIGNED_BYTE, pix);
			crc = crc32(crc32(0L, Z_NULL, 0), pix, W * H * 4);
			if (!frames && !f_sample)
				want = crc;
			bad += crc != want;
			printf("frame %ld fps %.1f crc %08lx %s\n", frame, fps, crc,
			       crc == want ? "ok" : "MISMATCH");
			fflush(stdout);
			f_sample = frame; t_sample = now();
		}
		if (t - t_status >= 10 || last) {
			fps = (frame - f_status) / (t - t_status);
			lo = fps < lo ? fps : lo; hi = fps > hi ? fps : hi;
			status(t - t0);
			f_status = frame; t_status = t;
		}
	} while (!last);
	printf("done frames %ld avg_fps %.1f min_fps %.1f max_fps %.1f mismatches %d\n",
	       frame, frame / (t - t0), lo, hi, bad);
	free(pix);
	sleep(1);                        /* panfrost autosuspends after 50 ms idle */
	status(now() - t0);
	return bad;
}

int main(int argc, char **argv)
{
	const char *dev = "/dev/dri/renderD128";
	long frames;
	double seconds;
	int rc;
	if (argc > 2 && !strcmp(argv[1], "-d")) {
		dev = argv[2]; argv += 2; argc -= 2;
	}
	frames = argc == 3 && !strcmp(argv[1], "render") ? atol(argv[2]) : 0;
	seconds = argc == 3 && !strcmp(argv[1], "load") ? atof(argv[2]) : 0;
	if (frames <= 0 && seconds <= 0 && (argc != 2 || strcmp(argv[1], "info"))) {
		fputs("h713-gpu-probe [-d /dev/dri/renderD128] info | render N | load SECONDS\n",
		      stderr);
		return 2;
	}
	rc = setup(dev);
	if (frames <= 0 && seconds <= 0)
		return rc || missing;
	if (rc || scene(frames ? FS_RENDER : FS_LOAD))
		return 1;
	return run(frames, seconds, frames ? expect_crc() : 0) ? 1 : 0;
}
