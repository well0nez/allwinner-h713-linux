/* SPDX-License-Identifier: GPL-2.0 */
/*
 * h713-gpu-probe scanout -- keystone stages S3 and S4 (umbau/plan/keystone/PLAN.md):
 * libdrm + GBM + EGL + GLES2, KMS on card1, no X11, no Wayland. The decisions, the
 * device command lines and the line budget are in umbau/work/KS3/REPORT.txt.
 *
 *   scanout [-r RENDER] [-c CARD] [-v VIDEO] [-y nv16|planes] scanout N|formats|capture N
 *
 * scanout N  two XRGB8888 dumb buffers of the mode's size, PRIME-exported, imported
 *            into EGL on the render node, N fenced frames of a gradient with a bar
 *            moving one pixel per frame onto the primary plane. Takes DRM master:
 *            `h713-tv ctl off` and stop the unit first; nothing is restored on exit,
 *            `ctl auto` puts the ring back. Exit 0 if commits == flips == N, no error.
 * formats    eglQueryDmaBufFormatsEXT, then one NV16-filled dumb buffer imported as
 *            DRM_FORMAT_NV16 (samplerExternalOES) and as DRM_FORMAT_R8 + GR88 (our
 *            own BT.709 shader), each sampled into a 4x4 FBO and checked against
 *            bt709(). A report, exit 0 unless nothing imports; needs no master.
 * capture N  S4: hdmirx slots by VIDIOC_EXPBUF, one EGLImage set per slot, the same
 *            fenced flips. Exit 0 on 0 timeouts and commits == flips. The exporter it
 *            needs is kernel patch 0136y, in since 22.09 (PLAN section 8): six planes.
 */
#define _GNU_SOURCE
#define EGL_NO_X11
#include <errno.h>
#include <fcntl.h>
#include <glob.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <linux/videodev2.h>
#include <xf86drm.h>
#include <xf86drmMode.h>
#include <drm_fourcc.h>
#include <gbm.h>		/* before EGL: defines __GBM__, the native types */
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <GLES2/gl2.h>
#include <GLES2/gl2ext.h>

#define FW 64			/* the formats probe picture, one dumb buffer */
#define FH 64
#define NBUF 2			/* scanout targets: one shown, one drawn into */
#define NCAP 3			/* capture slots, as design M5 and S4 ask for */
#define NPROP 11
#define VNAME "sun50i-h713-hdmirx"
#define ERR(...) (fprintf(stderr, "scanout: " __VA_ARGS__), 1)
#define VIOC(r, p) (ioctl(vfd, r, p) ? ERR(#r ": %s\n", strerror(errno)) : 0)
#define DIOC(r, p) (drmIoctl(card, r, p) ? ERR(#r ": %s\n", strerror(errno)) : 0)
#define PROC(x) eglGetProcAddress(x)

struct buf {			/* one scanout target: dumb buffer -> EGL -> FBO */
	uint32_t handle, fb_id;
	int prime;
	EGLImageKHR img;
	GLuint rb, fbo;
};

static const char *VS =
	"attribute vec2 a_pos; attribute vec2 a_uv; varying vec2 v_uv;\n"
	"void main() { gl_Position = vec4(a_pos, 0.0, 1.0); v_uv = a_uv; }\n";
static const char *FS_GRAD =
	"precision highp float; varying vec2 v_uv; uniform float u_bar;\n"
	"void main() { float g = v_uv.x; float b = step(abs(gl_FragCoord.x - u_bar), 1.0);\n"
	"  gl_FragColor = mix(vec4(g, g * 0.5, 1.0 - g, 1.0), vec4(1.0), b); }\n";
static const char *FS_EXT =	/* whatever Mesa makes of a whole NV16 image */
	"#extension GL_OES_EGL_image_external : require\n"
	"precision highp float; varying vec2 v_uv; uniform samplerExternalOES u_ext;\n"
	"void main() { gl_FragColor = texture2D(u_ext, v_uv); }\n";
/* Design M8, BT.709 limited range; bt709() below predicts this exactly. GR88 is
 * "[15:0] G:R 8:8 little endian", so the first chroma byte, Cb, lands in .r. */
static const char *FS_YUV =
	"precision highp float; varying vec2 v_uv; uniform sampler2D u_y, u_c;\n"
	"void main() { float y = 1.1643835 * (texture2D(u_y, v_uv).r - 0.0625);\n"
	"  vec2 c = texture2D(u_c, v_uv).rg - 0.5;\n"
	"  gl_FragColor = vec4(y + 1.7927411 * c.y, y - 0.2132486 * c.x - 0.5329093 * c.y,\n"
	"                      y + 2.1124018 * c.x, 1.0); }\n";
static const char *NEED[] = { "EGL_EXT_image_dma_buf_import", "EGL_KHR_surfaceless_context",
			      "EGL_ANDROID_native_fence_sync", "GL_OES_EGL_image" };
static const char *SYS[][2] = {
	{ "zone0", "/sys/class/thermal/thermal_zone0/temp" },
	{ "zone1", "/sys/class/thermal/thermal_zone1/temp" },
	{ "fan1", "/sys/class/hwmon/hwmon*/fan1_input" },
	{ "gpu_freq", "/sys/class/devfreq/1800000.gpu/cur_freq" },
	{ "gpu_pm", "/sys/devices/platform/soc/1800000.gpu/power/runtime_status" } };
/* the plane properties of one commit, in this order; IN_FENCE_FD may be absent */
static const char *PROP[] = { "FB_ID", "CRTC_ID", "SRC_X", "SRC_Y", "SRC_W", "SRC_H",
			      "CRTC_X", "CRTC_Y", "CRTC_W", "CRTC_H", "IN_FENCE_FD" };
static const char *PTYPE[] = { "type" };

static PFNEGLCREATEIMAGEKHRPROC p_img_new;
static PFNEGLDESTROYIMAGEKHRPROC p_img_del;
static PFNEGLCREATESYNCKHRPROC p_sync_new;
static PFNEGLDESTROYSYNCKHRPROC p_sync_del;
static PFNEGLDUPNATIVEFENCEFDANDROIDPROC p_sync_fd;
static PFNEGLQUERYDMABUFFORMATSEXTPROC p_fmt_list;
static PFNGLEGLIMAGETARGETRENDERBUFFERSTORAGEOESPROC p_img_rb;
static PFNGLEGLIMAGETARGETTEXTURE2DOESPROC p_img_tex;
static EGLDisplay dpy;
static int have_ctx, card = -1, vfd = -1, master, flipped, capfd[NCAP][2];
static EGLImageKHR capimg[NCAP][2];
static uint32_t crtc_id, plane_id, conn_id, mode_w, mode_h, pid[NPROP];
static struct buf bufs[NBUF];
static long n_commit, n_flip, n_err, n_slow, n_nofence, n_timeout, n_late;

static int fail(const char *what)
{
	fprintf(stderr, "scanout: %s: egl 0x%x gl 0x%x\n", what, eglGetError(),
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

/* fps every 100 frames, and probe.c's status line out of SYS every 10 s */
static void tick(long frame, double t0, int last)
{
	static double t_f, t_s;
	static long f_f;
	double t = now();
	char b[64];
	glob_t g;
	FILE *f;
	int i;
	if (!t_f) t_f = t_s = t0;
	if (frame % 100 == 0 || last) {
		printf("frame %ld fps %.1f commits %ld flips %ld errors %ld slow_fence %ld\n",
		       frame, (frame - f_f) / (t - t_f), n_commit, n_flip, n_err, n_slow);
		f_f = frame; t_f = t;
	}
	if (t - t_s < 10 && !last && frame) return;
	t_s = t;
	printf("status t=%.0fs", t - t0);
	for (i = 0; i < 5; i++) {
		f = !glob(SYS[i][1], 0, NULL, &g) && g.gl_pathc ? fopen(g.gl_pathv[0], "r") : NULL;
		globfree(&g);
		if (!f || !fgets(b, sizeof b, f)) strcpy(b, "n/a");
		if (f) fclose(f);
		printf(" %s=%.*s", SYS[i][0], (int)strcspn(b, "\n"), b);
	}
	printf("\n"); fflush(stdout);
}

/* GBM on the render node, EGL, a surfaceless ES2 context, and the extensions the
 * warp needs by name (design M6). GBM never touches card1: Mesa pairs a display
 * node with a render driver only for KMS names it knows (PLAN S3). */
static int setup(const char *dev)
{
	static const EGLint cattr[] = { EGL_CONTEXT_CLIENT_VERSION, 2, EGL_NONE };
	static const EGLint attr[] = { EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT, EGL_NONE };
	int fd = open(dev, O_RDWR | O_CLOEXEC), i, bad = 0;
	struct gbm_device *gbm = fd < 0 ? NULL : gbm_create_device(fd);
	const char *el, *gl;
	EGLContext ctx;
	EGLConfig cfg;
	EGLint n = 0, v[2];
	if (!gbm) return ERR("%s: %s\n", dev, strerror(errno));
	dpy = eglGetPlatformDisplay(EGL_PLATFORM_GBM_KHR, gbm, NULL);
	if (dpy == EGL_NO_DISPLAY || !eglInitialize(dpy, v, v + 1)) return fail("eglInitialize");
	el = eglQueryString(dpy, EGL_EXTENSIONS);
	if (!eglBindAPI(EGL_OPENGL_ES_API) || !eglChooseConfig(dpy, attr, &cfg, 1, &n) || !n ||
	    (ctx = eglCreateContext(dpy, cfg, EGL_NO_CONTEXT, cattr)) == EGL_NO_CONTEXT ||
	    !eglMakeCurrent(dpy, EGL_NO_SURFACE, EGL_NO_SURFACE, ctx))
		return fail("surfaceless ES2 context");
	have_ctx = 1;
	gl = (const char *)glGetString(GL_EXTENSIONS);
	printf("render %s, %s\n", dev, (const char *)glGetString(GL_RENDERER));
	for (i = 0; i < 4; i++, bad += !n)
		printf("%s %s\n", NEED[i],
		       (n = has_ext(i < 3 ? el : gl, NEED[i])) ? "present" : "MISSING");
	p_img_new = (PFNEGLCREATEIMAGEKHRPROC)PROC("eglCreateImageKHR");
	p_img_del = (PFNEGLDESTROYIMAGEKHRPROC)PROC("eglDestroyImageKHR");
	p_sync_new = (PFNEGLCREATESYNCKHRPROC)PROC("eglCreateSyncKHR");
	p_sync_del = (PFNEGLDESTROYSYNCKHRPROC)PROC("eglDestroySyncKHR");
	p_sync_fd = (PFNEGLDUPNATIVEFENCEFDANDROIDPROC)PROC("eglDupNativeFenceFDANDROID");
	p_fmt_list = (PFNEGLQUERYDMABUFFORMATSEXTPROC)PROC("eglQueryDmaBufFormatsEXT");
	p_img_rb = (PFNGLEGLIMAGETARGETRENDERBUFFERSTORAGEOESPROC)PROC("glEGLImageTargetRenderbufferStorageOES");
	p_img_tex = (PFNGLEGLIMAGETARGETTEXTURE2DOESPROC)PROC("glEGLImageTargetTexture2DOES");
	if (bad || !p_img_new || !p_sync_new || !p_sync_fd || !p_img_rb || !p_img_tex)
		return ERR("the EGL/GLES entry points of design M6 are not all there\n");
	return 0;
}

/* ids[] take the property ids of names[]; the return is the value of names[0] */
static uint64_t props(uint32_t obj, uint32_t type, const char **names, int n, uint32_t *ids)
{
	drmModeObjectProperties *l = drmModeObjectGetProperties(card, obj, type);
	uint64_t v0 = 0;
	uint32_t i;
	int j;
	for (i = 0; l && i < l->count_props; i++) {
		drmModePropertyRes *p = drmModeGetProperty(card, l->props[i]);
		for (j = 0; p && j < n; j++)
			if (!strcmp(p->name, names[j])) {
				ids[j] = p->prop_id;
				if (!j) v0 = l->prop_values[i];
			}
		if (p) drmModeFreeProperty(p);
	}
	if (l) drmModeFreeObjectProperties(l);
	return v0;
}

/* The CRTC is taken as it stands, exactly as h713-tv does it (main.c
 * display_find_crtc): the panel is up before this tool starts and it never sets a
 * mode. The primary plane is the PRIMARY-type plane on that CRTC that lists
 * XRGB8888; the connector is read for the log only, without a probe. */
static int kms_find(const char *path)
{
	drmModeRes *res;
	drmModePlaneRes *pr;
	unsigned int i, j, ci = 0;
	uint32_t tid = 0;
	if (card < 0) return ERR("%s: %s\n", path, strerror(errno));
	if (drmSetClientCap(card, DRM_CLIENT_CAP_UNIVERSAL_PLANES, 1) ||
	    drmSetClientCap(card, DRM_CLIENT_CAP_ATOMIC, 1))
		return ERR("%s has no atomic API: %s\n", path, strerror(errno));
	if (drmSetMaster(card))
		return ERR("SET_MASTER on %s: %s -- run `h713-tv ctl off` and stop the unit\n",
			   path, strerror(errno));
	master = 1;
	if (!(res = drmModeGetResources(card))) return ERR("no KMS: %s\n", strerror(errno));
	for (i = 0; i < (unsigned int)res->count_crtcs && !crtc_id; i++) {
		drmModeCrtc *c = drmModeGetCrtc(card, res->crtcs[i]);
		if (c && c->mode_valid) {
			crtc_id = c->crtc_id; ci = i;
			mode_w = c->mode.hdisplay; mode_h = c->mode.vdisplay;
		}
		if (c) drmModeFreeCrtc(c);
	}
	for (i = 0; i < (unsigned int)res->count_connectors && !conn_id; i++) {
		drmModeConnector *c = drmModeGetConnectorCurrent(card, res->connectors[i]);
		if (c && c->connection == DRM_MODE_CONNECTED && c->encoder_id)
			conn_id = c->connector_id;
		if (c) drmModeFreeConnector(c);
	}
	drmModeFreeResources(res);
	if (!crtc_id) return ERR("no CRTC drives a mode -- is the console up?\n");
	pr = drmModeGetPlaneResources(card);
	for (i = 0; pr && i < pr->count_planes && !plane_id; i++) {
		drmModePlane *p = drmModeGetPlane(card, pr->planes[i]);
		int rgb = 0;
		if (p && (p->possible_crtcs & (1u << ci)) &&
		    props(p->plane_id, DRM_MODE_OBJECT_PLANE, PTYPE, 1, &tid) ==
		    DRM_PLANE_TYPE_PRIMARY) {
			for (j = 0; j < p->count_formats; j++)
				rgb |= p->formats[j] == DRM_FORMAT_XRGB8888;
			plane_id = rgb ? p->plane_id : 0;
		}
		if (p) drmModeFreePlane(p);
	}
	if (pr) drmModeFreePlaneResources(pr);
	if (!plane_id) return ERR("no primary plane with XRGB8888 on CRTC %u\n", crtc_id);
	props(plane_id, DRM_MODE_OBJECT_PLANE, PROP, NPROP, pid);
	if (!pid[0] || !pid[1]) return ERR("the primary plane has no FB_ID/CRTC_ID\n");
	printf("kms %s: connector %u, crtc %u, primary plane %u, mode %ux%u, IN_FENCE_FD %s\n",
	       path, conn_id, crtc_id, plane_id, mode_w, mode_h, pid[10] ? "yes" : "NO");
	return 0;
}

/* an EGLImage over one or two dma-buf planes; fd1 < 0 means one plane */
static EGLImageKHR img_new(int fourcc, int w, int h, int fd0, int off0, int p0,
			   int fd1, int off1, int p1, int yuv)
{
	EGLint a[23], i = 0;
	a[i++] = EGL_WIDTH; a[i++] = w; a[i++] = EGL_HEIGHT; a[i++] = h;
	a[i++] = EGL_LINUX_DRM_FOURCC_EXT; a[i++] = fourcc;
	a[i++] = EGL_DMA_BUF_PLANE0_FD_EXT; a[i++] = fd0;
	a[i++] = EGL_DMA_BUF_PLANE0_OFFSET_EXT; a[i++] = off0;
	a[i++] = EGL_DMA_BUF_PLANE0_PITCH_EXT; a[i++] = p0;
	if (fd1 >= 0) {
		a[i++] = EGL_DMA_BUF_PLANE1_FD_EXT; a[i++] = fd1;
		a[i++] = EGL_DMA_BUF_PLANE1_OFFSET_EXT; a[i++] = off1;
		a[i++] = EGL_DMA_BUF_PLANE1_PITCH_EXT; a[i++] = p1;
	}
	if (yuv) {
		a[i++] = EGL_YUV_COLOR_SPACE_HINT_EXT; a[i++] = EGL_ITU_REC709_EXT;
		a[i++] = EGL_SAMPLE_RANGE_HINT_EXT; a[i++] = EGL_YUV_NARROW_RANGE_EXT;
	}
	a[i] = EGL_NONE;
	return p_img_new(dpy, EGL_NO_CONTEXT, EGL_LINUX_DMA_BUF_EXT, NULL, a);
}

static GLuint tex_new(EGLImageKHR img, GLenum tgt, int unit)
{
	GLuint t;
	glGenTextures(1, &t); glActiveTexture(GL_TEXTURE0 + unit); glBindTexture(tgt, t);
	glTexParameteri(tgt, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
	glTexParameteri(tgt, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
	glTexParameteri(tgt, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
	glTexParameteri(tgt, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
	p_img_tex(tgt, img);
	return t;
}

static GLuint program(const char *fs)
{
	const char *src[2] = { VS, fs };
	GLuint prog = glCreateProgram(), s;
	char log[512];
	GLint ok = 0;
	int i;
	for (i = 0; i < 2; i++) {
		s = glCreateShader(i ? GL_FRAGMENT_SHADER : GL_VERTEX_SHADER);
		glShaderSource(s, 1, &src[i], NULL);
		glCompileShader(s);
		glGetShaderiv(s, GL_COMPILE_STATUS, &ok);
		if (!ok) {
			glGetShaderInfoLog(s, sizeof log, NULL, log);
			return fail(log) * 0;
		}
		glAttachShader(prog, s);
	}
	glBindAttribLocation(prog, 0, "a_pos"); glBindAttribLocation(prog, 1, "a_uv");
	glLinkProgram(prog);
	glGetProgramiv(prog, GL_LINK_STATUS, &ok);
	return ok ? prog : (GLuint)(fail("program link") * 0);
}

/* GL's origin is the first row in memory, which the scanout shows at the top, so
 * v = 0 belongs to pos.y = -1; a wrong guess mirrors the picture vertically. */
static void draw(GLuint prog, int w, int h)
{
	static const GLfloat q[] = { -1, -1, 0, 0,  1, -1, 1, 0,  -1, 1, 0, 1,  1, 1, 1, 1 };
	glViewport(0, 0, w, h);
	glUseProgram(prog);
	glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 16, q);
	glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, 16, q + 2);
	glEnableVertexAttribArray(0); glEnableVertexAttribArray(1);
	glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
}

static int buf_new(struct buf *b)
{
	struct drm_mode_create_dumb c;
	uint32_t h[4] = { 0 }, p[4] = { 0 }, o[4] = { 0 };
	memset(&c, 0, sizeof c);
	c.width = mode_w; c.height = mode_h; c.bpp = 32; b->prime = -1;
	if (DIOC(DRM_IOCTL_MODE_CREATE_DUMB, &c)) return 1;
	b->handle = h[0] = c.handle; p[0] = c.pitch;
	if (drmModeAddFB2(card, mode_w, mode_h, DRM_FORMAT_XRGB8888, h, p, o, &b->fb_id, 0))
		return ERR("AddFB2: %s\n", strerror(errno));
	if (drmPrimeHandleToFD(card, c.handle, DRM_CLOEXEC | DRM_RDWR, &b->prime))
		return ERR("PRIME_HANDLE_TO_FD: %s\n", strerror(errno));
	b->img = img_new(DRM_FORMAT_XRGB8888, mode_w, mode_h, b->prime, 0, c.pitch, -1, 0, 0, 0);
	if (b->img == EGL_NO_IMAGE_KHR) return fail("XRGB8888 import of a scanout buffer");
	glGenRenderbuffers(1, &b->rb); glGenFramebuffers(1, &b->fbo);
	glBindRenderbuffer(GL_RENDERBUFFER, b->rb);
	p_img_rb(GL_RENDERBUFFER, b->img);
	glBindFramebuffer(GL_FRAMEBUFFER, b->fbo);
	glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_RENDERBUFFER, b->rb);
	if (glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE)
		return fail("FBO on the imported scanout buffer");
	return 0;
}

static void on_flip(int fd, unsigned int q, unsigned int s, unsigned int us, void *u)
{
	(void)fd; (void)q; (void)s; (void)us; (void)u;
	n_flip++; flipped = 1;
}

/* One fenced commit and the wait for its flip event. The kernel does not close an
 * IN_FENCE_FD, so the fd stays ours and joins the poll() that already waits for the
 * flip event: the fence timing costs one pollfd, no extra syscall, no blocking. A
 * poll on the fence before the commit would serialise exactly the overlap the fence
 * exists for, so it is not done -- slow_fence counts frames whose fence had not
 * signalled 8 ms after creation, seen from inside the flip wait. */
static int flip(struct buf *b, int first)
{
	uint64_t val[NPROP];
	drmModeAtomicReq *req;
	struct pollfd pf[2];
	drmEventContext ev;
	EGLSyncKHR sy;
	double t0;
	int fence = -1, ok = 1, rc, i;
	uint32_t fl = DRM_MODE_ATOMIC_NONBLOCK | DRM_MODE_PAGE_FLIP_EVENT |
		      (first ? DRM_MODE_ATOMIC_ALLOW_MODESET : 0u);
	sy = p_sync_new(dpy, EGL_SYNC_NATIVE_FENCE_ANDROID, NULL);
	glFlush();
	if (sy != EGL_NO_SYNC_KHR) {
		fence = p_sync_fd(dpy, sy);
		p_sync_del(dpy, sy);
	}
	if (fence < 0) { glFinish(); n_nofence++; }	/* no fence: CPU wait, counted */
	val[0] = b->fb_id; val[1] = crtc_id; val[2] = val[3] = val[6] = val[7] = 0;
	val[4] = (uint64_t)mode_w << 16; val[5] = (uint64_t)mode_h << 16;
	val[8] = mode_w; val[9] = mode_h; val[10] = (uint64_t)fence;
	req = drmModeAtomicAlloc();
	for (i = 0; req && i < NPROP; i++)
		if (pid[i] && (i < 10 || fence >= 0))
			ok &= drmModeAtomicAddProperty(req, plane_id, pid[i], val[i]) >= 0;
	rc = req && ok ? drmModeAtomicCommit(card, req, fl, NULL) : -EINVAL;
	drmModeAtomicFree(req);
	if (rc) {
		n_err++;
		if (fence >= 0) close(fence);
		return ERR("commit refused: %s (EINVAL: the simple-pipe helper wants the fb at the mode's size and offset 0)\n",
			   strerror(errno));
	}
	n_commit++;
	t0 = now();
	memset(&ev, 0, sizeof ev);
	ev.version = 2; ev.page_flip_handler = on_flip;
	pf[0].fd = card; pf[1].fd = fence; pf[0].events = pf[1].events = POLLIN;
	for (flipped = 0; !flipped; ) {
		rc = poll(pf, 2, 1000);
		if (rc < 0 && errno == EINTR) continue;
		if (rc <= 0) {
			n_err++;
			if (fence >= 0) close(fence);
			return ERR("no flip event within 1 s\n");
		}
		if (pf[1].fd >= 0 && pf[1].revents) {
			n_slow += now() - t0 > 0.008;
			pf[1].fd = -1;
		}
		if (pf[0].revents) drmHandleEvent(card, &ev);
	}
	if (fence >= 0) close(fence);
	return 0;
}

static int cmd_scanout(long frames)
{
	GLuint prog = program(FS_GRAD);
	double t0;
	long f;
	int i;
	if (!prog) return 1;
	for (i = 0; i < NBUF; i++)
		if (buf_new(&bufs[i])) return 1;
	t0 = now();
	tick(0, t0, 0);
	for (f = 1; f <= frames; f++) {
		struct buf *b = &bufs[f % NBUF];	/* the one not on screen */
		glBindFramebuffer(GL_FRAMEBUFFER, b->fbo);
		glUseProgram(prog);
		glUniform1f(glGetUniformLocation(prog, "u_bar"), (float)(f % mode_w));
		draw(prog, mode_w, mode_h);
		if (flip(b, f == 1)) break;
		tick(f, t0, f == frames);
	}
	printf("done frames %ld commits %ld flips %ld errors %ld slow_fence %ld no_fence %ld\n",
	       f - 1, n_commit, n_flip, n_err, n_slow, n_nofence);
	return n_err || n_commit != frames || n_flip != frames;
}

/* the sample our own shader must produce for one Y/Cb/Cr triple, 0..255 */
static void bt709(const int *yuv, int *out)
{
	double l = 1.1643835 * (yuv[0] - 16), a = yuv[1] - 128, b = yuv[2] - 128, v[3];
	int i;
	v[0] = l + 1.7927411 * b; v[2] = l + 2.1124018 * a;
	v[1] = l - 0.2132486 * a - 0.5329093 * b;
	for (i = 0; i < 3; i++)
		out[i] = v[i] < 0 ? 0 : v[i] > 255 ? 255 : (int)(v[i] + 0.5);
}

/* sample one import into the bound 4x4 FBO and say how far off it came out */
static int verdict(const char *tag, GLuint prog, GLenum tgt, EGLImageKHR y, EGLImageKHR c,
		   const int *want)
{
	unsigned char px[4] = { 0 };
	int i, off = 0;
	if (!prog || y == EGL_NO_IMAGE_KHR || (c == EGL_NO_IMAGE_KHR && tgt == GL_TEXTURE_2D))
		return printf("  %s: import refused (EGL error 0x%x)\n", tag, eglGetError()) * 0;
	glUseProgram(prog);
	glUniform1i(glGetUniformLocation(prog, tgt == GL_TEXTURE_2D ? "u_y" : "u_ext"), 0);
	tex_new(y, tgt, 0);
	if (tgt == GL_TEXTURE_2D) {
		glUniform1i(glGetUniformLocation(prog, "u_c"), 1);
		tex_new(c, GL_TEXTURE_2D, 1);
	}
	draw(prog, 4, 4);
	glReadPixels(0, 0, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE, px);
	for (i = 0; i < 3; i++) off += abs((int)px[i] - want[i]) > 2;
	printf("  %s: supported, sampled rgb = %d %d %d, %s\n", tag, px[0], px[1], px[2],
	       off ? "OFF" : "within 2");
	p_img_del(dpy, y);
	if (c != EGL_NO_IMAGE_KHR) p_img_del(dpy, c);
	return 1;
}

static int cmd_formats(void)
{
	static const int col[2][3] = { { 0x80, 0x80, 0x80 }, { 0x51, 0x5a, 0xf0 } };
	struct drm_mode_create_dumb c;
	struct drm_mode_map_dumb m;
	GLuint fbo, t, ext = program(FS_EXT), yuv = program(FS_YUV);
	unsigned char *map;
	int n = 0, i, j, k, want[3], got = 0;
	EGLint *fmt;
	if (p_fmt_list && p_fmt_list(dpy, 0, NULL, &n) && n > 0 &&
	    (fmt = calloc(n, sizeof *fmt)) != NULL) {
		p_fmt_list(dpy, n, fmt, &n);
		printf("dma_buf formats (%d):", n);
		for (i = 0; i < n; i++) printf(" %.4s", (const char *)&fmt[i]);
		printf("\n"); free(fmt);
	} else {
		printf("dma_buf formats: eglQueryDmaBufFormatsEXT answered nothing\n");
	}
	memset(&c, 0, sizeof c); memset(&m, 0, sizeof m);
	c.width = FW; c.height = FH * 2; c.bpp = 8;	/* NV16: chroma below luma */
	if (DIOC(DRM_IOCTL_MODE_CREATE_DUMB, &c)) return 1;
	bufs[0].handle = m.handle = c.handle; bufs[0].prime = -1;   /* cleanup() frees it */
	if (DIOC(DRM_IOCTL_MODE_MAP_DUMB, &m)) return 1;
	map = mmap(NULL, c.size, PROT_READ | PROT_WRITE, MAP_SHARED, card, m.offset);
	if (map == MAP_FAILED) return ERR("mmap: %s\n", strerror(errno));
	if (drmPrimeHandleToFD(card, c.handle, DRM_CLOEXEC | DRM_RDWR, &bufs[0].prime))
		return ERR("PRIME_HANDLE_TO_FD: %s\n", strerror(errno));
	glGenTextures(1, &t); glGenFramebuffers(1, &fbo);
	glBindTexture(GL_TEXTURE_2D, t);
	glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, 4, 4, 0, GL_RGBA, GL_UNSIGNED_BYTE, NULL);
	glBindFramebuffer(GL_FRAMEBUFFER, fbo);
	glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, t, 0);
	if (glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE)
		return fail("the 4x4 readback FBO");
	for (k = 0; k < 2; k++) {
		for (i = 0; i < FH; i++) {
			memset(map + (size_t)i * c.pitch, col[k][0], FW);
			for (j = 0; j < FW; j += 2) {
				map[(size_t)(FH + i) * c.pitch + j] = col[k][1];
				map[(size_t)(FH + i) * c.pitch + j + 1] = col[k][2];
			}
		}
		bt709(col[k], want);
		printf("fill y=%02x cb=%02x cr=%02x expect rgb = %d %d %d\n", col[k][0],
		       col[k][1], col[k][2], want[0], want[1], want[2]);
		got += verdict("nv16 external", ext, GL_TEXTURE_EXTERNAL_OES,
			       img_new(DRM_FORMAT_NV16, FW, FH, bufs[0].prime, 0, c.pitch,
				       bufs[0].prime, c.pitch * FH, c.pitch, 1),
			       EGL_NO_IMAGE_KHR, want);
		got += verdict("r8 + gr88", yuv, GL_TEXTURE_2D,
			       img_new(DRM_FORMAT_R8, FW, FH, bufs[0].prime, 0, c.pitch,
				       -1, 0, 0, 0),
			       img_new(DRM_FORMAT_GR88, FW / 2, FH, bufs[0].prime,
				       c.pitch * FH, c.pitch, -1, 0, 0, 0), want);
	}
	munmap(map, c.size);
	return got ? 0 : ERR("neither NV16 nor R8 + GR88 imported\n");
}

/* The capture node is found by driver name, not by number: v4l2_capability has
 * __u8 driver[16], so the kernel reports at most "sun50i-h713-hdm" of our
 * 18-character name and only a prefix compare can match (h713-tv capture_open). */
static int v4l_open(const char *want, int *caps)
{
	struct v4l2_capability vc;
	char path[32];
	int i;
	for (i = 0; i < 64; i++) {
		snprintf(path, sizeof path, "/dev/video%d", i);
		vfd = open(want ? want : path, O_RDWR | O_CLOEXEC);
		if (vfd >= 0) {
			memset(&vc, 0, sizeof vc);
			if (!ioctl(vfd, VIDIOC_QUERYCAP, &vc) &&
			    !strncmp((char *)vc.driver, VNAME, sizeof vc.driver - 1)) {
				printf("capture %s (%s, %s)\n", want ? want : path,
				       vc.driver, vc.card);
				*caps = (int)(vc.device_caps ? vc.device_caps : vc.capabilities);
				return 0;
			}
			close(vfd); vfd = -1;
		}
		if (want) return ERR("%s is not a %s node\n", want, VNAME);
	}
	return ERR("no /dev/video* belongs to %s\n", VNAME);
}

/* S4. The slot contract, from change-list S3 and design M5: three slots at 60 Hz
 * means the firmware overwrites a slot every 50 ms and the exported dma-buf carries
 * no fence that says so. A slot therefore goes back with QBUF only after the flip
 * event that consumed its render has arrived; flip() waits for that event, so the
 * QBUF below is the first moment at which the GPU is provably done with the slot. */
static int cmd_capture(long frames, const char *dev, int nv16)
{
	struct v4l2_plane pl[VIDEO_MAX_PLANES];
	struct v4l2_requestbuffers rb;
	struct v4l2_exportbuffer ex;
	struct v4l2_format f;
	struct v4l2_buffer b;
	GLuint tex[NCAP][2], prog;
	int caps = 0, mp, np, w, h, p0, p1, off1, i, j, type;
	double t0, td;
	long fr;
	if (v4l_open(dev, &caps)) return 1;
	mp = !!(caps & V4L2_CAP_VIDEO_CAPTURE_MPLANE);
	type = mp ? V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE : V4L2_BUF_TYPE_VIDEO_CAPTURE;
	memset(&f, 0, sizeof f);
	f.type = type;
	if (VIOC(VIDIOC_G_FMT, &f)) return 1;	/* no S_FMT: the signal is the format */
	np = mp ? f.fmt.pix_mp.num_planes : 1;
	w = mp ? (int)f.fmt.pix_mp.width : (int)f.fmt.pix.width;
	h = mp ? (int)f.fmt.pix_mp.height : (int)f.fmt.pix.height;
	p0 = mp ? (int)f.fmt.pix_mp.plane_fmt[0].bytesperline : (int)f.fmt.pix.bytesperline;
	p1 = mp && np > 1 ? (int)f.fmt.pix_mp.plane_fmt[1].bytesperline : p0;
	off1 = np > 1 ? 0 : p0 * h;	/* one dma-buf per plane, or both in one */
	printf("capture %dx%d %s, pitch %d/%d, %d plane(s), import as %s\n", w, h,
	       mp ? "multiplanar" : "single-planar", p0, p1, np, nv16 ? "nv16" : "planes");
	memset(&rb, 0, sizeof rb);
	rb.count = NCAP; rb.type = type; rb.memory = V4L2_MEMORY_MMAP;
	if (VIOC(VIDIOC_REQBUFS, &rb) || rb.count < NCAP)
		return ERR("REQBUFS gave %u of %d buffers\n", rb.count, NCAP);
	if (!(prog = program(nv16 ? FS_EXT : FS_YUV))) return 1;
	for (i = 0; i < NBUF; i++)
		if (buf_new(&bufs[i])) return 1;
	for (i = 0; i < NCAP; i++) {
		for (j = 0; j < (np > 1 ? 2 : 1); j++) {
			memset(&ex, 0, sizeof ex);
			ex.type = type; ex.index = i; ex.plane = j;
			ex.flags = O_RDONLY | O_CLOEXEC;
			if (VIOC(VIDIOC_EXPBUF, &ex))
				return ERR("  .get_dmabuf comes with kernel 0136y - is that one running?\n");
			capfd[i][j] = ex.fd;
		}
		if (np <= 1) capfd[i][1] = capfd[i][0];
		/* EGL takes the stride separately, so the image is w wide even on a
		 * 1366-in-1376 line and no texture coordinate is divided by the pitch
		 * as design M5 feared. */
		capimg[i][0] = nv16 ?
			img_new(DRM_FORMAT_NV16, w, h, capfd[i][0], 0, p0,
				capfd[i][1], off1, p1, 1) :
			img_new(DRM_FORMAT_R8, w, h, capfd[i][0], 0, p0, -1, 0, 0, 0);
		if (!nv16)
			capimg[i][1] = img_new(DRM_FORMAT_GR88, w / 2, h, capfd[i][1],
					       off1, p1, -1, 0, 0, 0);
		if (capimg[i][0] == EGL_NO_IMAGE_KHR ||
		    (!nv16 && capimg[i][1] == EGL_NO_IMAGE_KHR))
			return fail("dma-buf import of a capture slot");
		tex[i][0] = tex_new(capimg[i][0],
				    nv16 ? GL_TEXTURE_EXTERNAL_OES : GL_TEXTURE_2D, 0);
		if (!nv16) tex[i][1] = tex_new(capimg[i][1], GL_TEXTURE_2D, 1);
		memset(&b, 0, sizeof b); memset(pl, 0, sizeof pl);
		b.type = type; b.memory = V4L2_MEMORY_MMAP; b.index = i;
		b.m.planes = pl; b.length = np;
		if (VIOC(VIDIOC_QBUF, &b)) return 1;
	}
	if (VIOC(VIDIOC_STREAMON, &type)) return 1;
	glUseProgram(prog);
	glUniform1i(glGetUniformLocation(prog, nv16 ? "u_ext" : "u_y"), 0);
	if (!nv16) glUniform1i(glGetUniformLocation(prog, "u_c"), 1);
	t0 = now();
	tick(0, t0, 0);
	for (fr = 1; fr <= frames; fr++) {
		struct pollfd pf = { vfd, POLLIN, 0 };
		struct buf *sb = &bufs[fr % NBUF];
		if (poll(&pf, 1, 100) <= 0) { n_timeout++; continue; }
		memset(&b, 0, sizeof b); memset(pl, 0, sizeof pl);
		b.type = type; b.memory = V4L2_MEMORY_MMAP; b.m.planes = pl; b.length = np;
		if (VIOC(VIDIOC_DQBUF, &b)) return 1;
		td = now();
		glBindFramebuffer(GL_FRAMEBUFFER, sb->fbo);
		glUseProgram(prog);
		glActiveTexture(GL_TEXTURE0);
		glBindTexture(nv16 ? GL_TEXTURE_EXTERNAL_OES : GL_TEXTURE_2D, tex[b.index][0]);
		if (!nv16) {
			glActiveTexture(GL_TEXTURE1);
			glBindTexture(GL_TEXTURE_2D, tex[b.index][1]);
		}
		draw(prog, mode_w, mode_h);
		if (flip(sb, fr == 1)) break;
		n_late += now() - td > 0.033;
		if (VIOC(VIDIOC_QBUF, &b)) return 1;	/* only now: see above */
		tick(fr, t0, fr == frames);
	}
	ioctl(vfd, VIDIOC_STREAMOFF, &type);
	printf("done frames %ld commits %ld flips %ld errors %ld slow_fence %ld timeouts %ld late %ld\n",
	       fr - 1, n_commit, n_flip, n_err, n_slow, n_timeout, n_late);
	return n_err || n_timeout || n_commit != n_flip;
}

/* the one exit path: every image, buffer, fd and handle this tool made */
static void cleanup(void)
{
	struct drm_mode_destroy_dumb d;
	int i, j;
	for (i = 0; i < NCAP; i++)
		for (j = 0; j < 2; j++) {
			if (capimg[i][j] && p_img_del) p_img_del(dpy, capimg[i][j]);
			if (capfd[i][j] > 0 && (!j || capfd[i][1] != capfd[i][0]))
				close(capfd[i][j]);
		}
	for (i = 0; i < NBUF; i++) {
		struct buf *b = &bufs[i];
		if (b->img && p_img_del) p_img_del(dpy, b->img);
		if (b->fbo) glDeleteFramebuffers(1, &b->fbo);
		if (b->rb) glDeleteRenderbuffers(1, &b->rb);
		if (b->prime > 0) close(b->prime);
		if (b->fb_id) drmModeRmFB(card, b->fb_id);
		if (b->handle) {
			memset(&d, 0, sizeof d);
			d.handle = b->handle;
			drmIoctl(card, DRM_IOCTL_MODE_DESTROY_DUMB, &d);
		}
	}
	if (dpy != EGL_NO_DISPLAY) eglTerminate(dpy);
	if (vfd >= 0) close(vfd);
	if (master) drmDropMaster(card);
	if (card >= 0) close(card);
}

int main(int argc, char **argv)
{
	const char *render = "/dev/dri/renderD128", *kms = "/dev/dri/card1", *video = NULL;
	int nv16 = 0, rc = 2, i;
	long n;
	for (i = 1; i + 1 < argc && argv[i][0] == '-' && argv[i][2] == 0; i += 2) {
		if (argv[i][1] == 'r') render = argv[i + 1];
		else if (argv[i][1] == 'c') kms = argv[i + 1];
		else if (argv[i][1] == 'v') video = argv[i + 1];
		else if (argv[i][1] == 'y') nv16 = !strcmp(argv[i + 1], "nv16");
		else break;
	}
	argv += i - 1; argc -= i - 1;
	n = argc == 3 ? atol(argv[2]) : 0;
	if (argc < 2 || (n <= 0 && strcmp(argv[1], "formats"))) {
		fputs("h713-gpu-probe-scanout [-r RENDER] [-c CARD] [-v VIDEO] [-y nv16|planes]\n"
		      "                       scanout N | formats | capture N\n", stderr);
		return 2;
	}
	if (setup(render)) goto out;
	card = open(kms, O_RDWR | O_CLOEXEC);
	if (!strcmp(argv[1], "formats"))		/* a dumb buffer needs no master */
		rc = card < 0 ? ERR("%s: %s\n", kms, strerror(errno)) : cmd_formats();
	else if (kms_find(kms)) rc = 1;
	else if (!strcmp(argv[1], "scanout")) rc = cmd_scanout(n);
	else if (!strcmp(argv[1], "capture")) rc = cmd_capture(n, video, nv16);
out:
	cleanup();
	return rc;
}
