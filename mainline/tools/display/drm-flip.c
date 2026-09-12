// SPDX-License-Identifier: GPL-2.0
/*
 * drm-flip -- does the H713 KMS driver actually modeset and page-flip?
 *
 * Runs ON THE TARGET. Build:  gcc -O2 -o drm-flip drm-flip.c
 *
 * No libdrm: this talks to the kernel through raw ioctls and the UAPI headers
 * in /usr/include/drm, which are present on every image. libdrm's headers are
 * not, and a display instrument that cannot run on the minimal rootfs is an
 * instrument you will not have when you need it.
 *
 * This is the gate for sun50i-h713-afbd. "The module loaded" and "a card node
 * appeared" prove only that probe returned 0; neither touches scanout.
 *
 *   info      enumerate every card node, its connectors, CRTCs and modes
 *   set       allocate a dumb buffer, fill it, and SETCRTC to it
 *   flip N    page-flip between two differently coloured buffers N times,
 *             waiting for each completion event, and report the rate
 *   alloc     allocate full-screen dumb buffers until one fails, and report
 *             how many the driver's memory actually yielded
 *
 * `flip` is the one that matters. The driver arms the page-flip event against
 * the vblank interrupt, so an event that never arrives means the vblank bits
 * taken from the vendor DECD driver (+0xc0/+0xc4) are wrong -- the single most
 * likely way this driver is broken, and named as such in docs/kms-display.md.
 * A rate near the panel's ~59.7 Hz means the whole chain works: modeset, plane
 * update, the AFBD commit sequence, and vblank.
 *
 * The buffers are flat colours on purpose. This asks whether flips complete and
 * how fast, not whether the image is correct; tearing already has an instrument
 * (tools/video/gles-tear.c).
 *
 * It picks the card node that actually has CRTCs, because panfrost takes minor
 * 0 as a render-only device and would otherwise be mistaken for the display.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

#include <drm/drm.h>
#include <drm/drm_fourcc.h>
#include <drm/drm_mode.h>

static double now_ms(void)
{
	struct timespec ts;

	clock_gettime(CLOCK_MONOTONIC, &ts);
	return ts.tv_sec * 1000.0 + ts.tv_nsec / 1e6;
}

static int xioctl(int fd, unsigned long req, void *arg, const char *what)
{
	if (ioctl(fd, req, arg) < 0) {
		fprintf(stderr, "%s: %s\n", what, strerror(errno));
		return -1;
	}
	return 0;
}

struct fb {
	uint32_t handle, pitch, fb_id;
	uint64_t size;
	uint8_t *map;
};

static int make_fb(int fd, uint32_t w, uint32_t h, uint32_t colour, struct fb *out)
{
	struct drm_mode_create_dumb creq;
	struct drm_mode_map_dumb mreq;
	struct drm_mode_fb_cmd2 fbc;
	uint64_t i;

	memset(&creq, 0, sizeof(creq));
	creq.width = w;
	creq.height = h;
	creq.bpp = 32;
	if (xioctl(fd, DRM_IOCTL_MODE_CREATE_DUMB, &creq, "CREATE_DUMB"))
		return -1;
	out->handle = creq.handle;
	out->pitch = creq.pitch;
	out->size = creq.size;

	memset(&fbc, 0, sizeof(fbc));
	fbc.width = w;
	fbc.height = h;
	fbc.pixel_format = DRM_FORMAT_XRGB8888;
	fbc.handles[0] = creq.handle;
	fbc.pitches[0] = creq.pitch;
	if (xioctl(fd, DRM_IOCTL_MODE_ADDFB2, &fbc, "ADDFB2"))
		return -1;
	out->fb_id = fbc.fb_id;

	memset(&mreq, 0, sizeof(mreq));
	mreq.handle = creq.handle;
	if (xioctl(fd, DRM_IOCTL_MODE_MAP_DUMB, &mreq, "MAP_DUMB"))
		return -1;
	out->map = mmap(NULL, creq.size, PROT_READ | PROT_WRITE, MAP_SHARED,
			fd, mreq.offset);
	if (out->map == MAP_FAILED) {
		fprintf(stderr, "mmap: %s\n", strerror(errno));
		return -1;
	}
	for (i = 0; i < creq.size / 4; i++)
		((uint32_t *)out->map)[i] = colour;

	printf("  fb %u: %ux%u pitch %u size %llu\n", out->fb_id, w, h,
	       out->pitch, (unsigned long long)out->size);
	return 0;
}

/*
 * Fetch the connector twice: once for the counts, once for the arrays. Only the
 * mode list is wanted, so the other pointers stay NULL with their counts zeroed
 * on the second pass.
 */
static int get_connector(int fd, uint32_t id, struct drm_mode_get_connector *c,
			 struct drm_mode_modeinfo **modes)
{
	memset(c, 0, sizeof(*c));
	c->connector_id = id;
	if (xioctl(fd, DRM_IOCTL_MODE_GETCONNECTOR, c, "GETCONNECTOR"))
		return -1;
	*modes = NULL;
	if (!c->count_modes)
		return 0;

	*modes = calloc(c->count_modes, sizeof(**modes));
	if (!*modes)
		return -1;
	c->modes_ptr = (uint64_t)(uintptr_t)*modes;
	c->count_props = 0;
	c->props_ptr = 0;
	c->prop_values_ptr = 0;
	c->count_encoders = 0;
	c->encoders_ptr = 0;
	if (xioctl(fd, DRM_IOCTL_MODE_GETCONNECTOR, c, "GETCONNECTOR(2)")) {
		free(*modes);
		*modes = NULL;
		return -1;
	}
	return 0;
}

/* Open the first card node that has at least one CRTC. */
static int open_kms(char *path_out, size_t n)
{
	int i;

	for (i = 0; i < 8; i++) {
		struct drm_mode_card_res res;
		char path[64];
		int fd;

		snprintf(path, sizeof(path), "/dev/dri/card%d", i);
		fd = open(path, O_RDWR | O_CLOEXEC);
		if (fd < 0)
			continue;
		memset(&res, 0, sizeof(res));
		if (ioctl(fd, DRM_IOCTL_MODE_GETRESOURCES, &res) == 0 &&
		    res.count_crtcs > 0) {
			snprintf(path_out, n, "%s", path);
			return fd;
		}
		printf("  %s: no CRTCs (render-only), skipping\n", path);
		close(fd);
	}
	return -1;
}

int main(int argc, char **argv)
{
	const char *cmd = argc > 1 ? argv[1] : "info";
	int nflips = argc > 2 ? atoi(argv[2]) : 120;
	struct drm_mode_card_res res;
	struct drm_mode_get_connector conn;
	struct drm_mode_modeinfo *modes = NULL, mode;
	struct drm_mode_crtc setc;
	struct fb fbs[2];
	uint32_t *crtcs, *conns, crtc_id = 0, conn_id = 0;
	char path[64];
	int fd, i;

	fd = open_kms(path, sizeof(path));
	if (fd < 0) {
		fprintf(stderr, "no DRM card with CRTCs -- is sun50i-h713-afbd loaded?\n");
		return 1;
	}

	memset(&res, 0, sizeof(res));
	if (xioctl(fd, DRM_IOCTL_MODE_GETRESOURCES, &res, "GETRESOURCES"))
		return 1;
	crtcs = calloc(res.count_crtcs, 4);
	conns = calloc(res.count_connectors, 4);
	res.crtc_id_ptr = (uint64_t)(uintptr_t)crtcs;
	res.connector_id_ptr = (uint64_t)(uintptr_t)conns;
	res.count_fbs = 0;
	res.fb_id_ptr = 0;
	res.count_encoders = 0;
	res.encoder_id_ptr = 0;
	if (xioctl(fd, DRM_IOCTL_MODE_GETRESOURCES, &res, "GETRESOURCES(2)"))
		return 1;

	printf("%s: %u connector(s), %u crtc(s), fb %ux%u..%ux%u\n", path,
	       res.count_connectors, res.count_crtcs, res.min_width,
	       res.min_height, res.max_width, res.max_height);

	for (i = 0; i < (int)res.count_connectors; i++) {
		if (get_connector(fd, conns[i], &conn, &modes))
			continue;
		printf("connector %u type %u: %s, %u mode(s)\n", conn.connector_id,
		       conn.connector_type,
		       conn.connection == 1 ? "connected" :
		       conn.connection == 2 ? "disconnected" : "unknown",
		       conn.count_modes);
		if (modes && conn.count_modes && !conn_id) {
			conn_id = conn.connector_id;
			mode = modes[0];
		}
		if (!strcmp(cmd, "info") && modes) {
			int m;

			for (m = 0; m < (int)conn.count_modes; m++)
				printf("  mode %d: %s %ux%u@%u Hz, clock %u kHz\n",
				       m, modes[m].name, modes[m].hdisplay,
				       modes[m].vdisplay, modes[m].vrefresh,
				       modes[m].clock);
		}
		free(modes);
		modes = NULL;
	}
	if (res.count_crtcs)
		crtc_id = crtcs[0];
	printf("using crtc %u, connector %u\n", crtc_id, conn_id);

	if (!strcmp(cmd, "info"))
		return 0;
	if (!crtc_id || !conn_id) {
		fprintf(stderr, "no usable crtc/connector\n");
		return 1;
	}

	/*
	 * How many full-screen buffers can this driver actually hand out? The
	 * answer is not "pool size / buffer size": a dma-coherent reserved pool
	 * allocates in power-of-two page orders, so a 3.6 MiB buffer occupies a
	 * 4 MiB aligned slot and a 16 MiB pool yields four, not the four-and-a-
	 * half the arithmetic suggests. A client that wants more than are left
	 * fails with ENOMEM at CREATE_DUMB, which is how this mode came to
	 * exist -- mpv did exactly that.
	 */
	if (!strcmp(cmd, "alloc")) {
		int n = 0;

		for (;;) {
			struct drm_mode_create_dumb creq;

			memset(&creq, 0, sizeof(creq));
			creq.width = mode.hdisplay;
			creq.height = mode.vdisplay;
			creq.bpp = 32;
			if (ioctl(fd, DRM_IOCTL_MODE_CREATE_DUMB, &creq) < 0) {
				printf("allocation %d failed: %s\n", n + 1,
				       strerror(errno));
				break;
			}
			n++;
			printf("  buffer %d: handle %u, %llu bytes\n", n,
			       creq.handle, (unsigned long long)creq.size);
			if (n >= 64)
				break;
		}
		printf("%d full-screen buffer(s) available to a client\n", n);
		return 0;
	}

	printf("mode: %s %ux%u@%u Hz, clock %u kHz\n", mode.name, mode.hdisplay,
	       mode.vdisplay, mode.vrefresh, mode.clock);

	if (make_fb(fd, mode.hdisplay, mode.vdisplay, 0x00202080, &fbs[0]))
		return 1;
	if (make_fb(fd, mode.hdisplay, mode.vdisplay, 0x00208020, &fbs[1]))
		return 1;

	memset(&setc, 0, sizeof(setc));
	setc.crtc_id = crtc_id;
	setc.fb_id = fbs[0].fb_id;
	setc.set_connectors_ptr = (uint64_t)(uintptr_t)&conn_id;
	setc.count_connectors = 1;
	setc.mode = mode;
	setc.mode_valid = 1;
	if (xioctl(fd, DRM_IOCTL_MODE_SETCRTC, &setc, "SETCRTC"))
		return 1;
	printf("SETCRTC ok -- the panel should now be flat blue\n");

	if (!strcmp(cmd, "set")) {
		sleep(3);
		return 0;
	}
	if (strcmp(cmd, "flip")) {
		fprintf(stderr, "usage: drm-flip [info|set|alloc|flip [N]]\n");
		return 2;
	}

	{
		double t0 = now_ms();
		int timeouts = 0;

		for (i = 0; i < nflips; i++) {
			struct drm_mode_crtc_page_flip flip;
			struct fb *next = &fbs[(i + 1) & 1];
			fd_set fds;
			struct timeval tv = { .tv_sec = 1, .tv_usec = 0 };
			char buf[128];

			memset(&flip, 0, sizeof(flip));
			flip.crtc_id = crtc_id;
			flip.fb_id = next->fb_id;
			flip.flags = DRM_MODE_PAGE_FLIP_EVENT;
			if (xioctl(fd, DRM_IOCTL_MODE_PAGE_FLIP, &flip, "PAGE_FLIP"))
				return 1;

			FD_ZERO(&fds);
			FD_SET(fd, &fds);
			/*
			 * A flip that never reports back is the signature of a
			 * vblank interrupt that is not arriving. Say that,
			 * rather than hanging forever.
			 */
			if (select(fd + 1, &fds, NULL, NULL, &tv) <= 0) {
				timeouts++;
				fprintf(stderr,
					"flip %d: no completion event in 1 s -- vblank is not firing\n",
					i);
				if (timeouts > 2)
					return 1;
				continue;
			}
			if (read(fd, buf, sizeof(buf)) < 0) {
				fprintf(stderr, "read event: %s\n", strerror(errno));
				return 1;
			}
		}
		{
			double el = now_ms() - t0;

			printf("%d flips in %.0f ms = %.2f fps, %d timeout(s)\n",
			       nflips, el, nflips / (el / 1000.0), timeouts);
		}
	}
	return 0;
}
