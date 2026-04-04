// SPDX-License-Identifier: MIT
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>

#include <drm/drm.h>
#include <drm/drm_fourcc.h>
#include <drm/drm_mode.h>

struct display_target {
	uint32_t conn_id;
	uint32_t crtc_id;
	struct drm_mode_modeinfo mode;
};

static int drm_ioctl(int fd, unsigned long req, void *arg, const char *what)
{
	if (ioctl(fd, req, arg) == 0)
		return 0;
	perror(what);
	return -errno;
}

static void fill_pattern(uint32_t *buf, uint32_t width, uint32_t height, uint32_t stride)
{
	uint32_t x, y;
	uint32_t pixels_per_line = stride / 4;

	for (y = 0; y < height; y++) {
		for (x = 0; x < width; x++) {
			uint8_t r = (x * 255) / (width ? width : 1);
			uint8_t g = (y * 255) / (height ? height : 1);
			uint8_t b = ((x / 64) ^ (y / 64)) ? 0xFF : 0x20;
			buf[y * pixels_per_line + x] = 0xFF000000u | (r << 16) | (g << 8) | b;
		}
	}
}

static int find_display_target(int fd, struct display_target *out)
{
	struct drm_mode_card_res res = {0};
	struct drm_mode_get_connector conn = {0};
	struct drm_mode_get_encoder enc = {0};
	struct drm_mode_modeinfo *modes = NULL;
	uint32_t *conn_encoders = NULL;
	uint32_t *crtcs = NULL, *connectors = NULL, *encoders = NULL;
	uint32_t conn_id = 0, crtc_id = 0, enc_id = 0;
	uint32_t conn_mode_count = 0;
	uint32_t i;
	int ret = -1;

	if (drm_ioctl(fd, DRM_IOCTL_MODE_GETRESOURCES, &res, "GETRESOURCES(count)"))
		goto out;

	crtcs = calloc(res.count_crtcs, sizeof(*crtcs));
	connectors = calloc(res.count_connectors, sizeof(*connectors));
	encoders = calloc(res.count_encoders, sizeof(*encoders));
	if (!crtcs || !connectors || !encoders) {
		fprintf(stderr, "alloc resources failed\n");
		goto out;
	}

	res.crtc_id_ptr = (uintptr_t)crtcs;
	res.connector_id_ptr = (uintptr_t)connectors;
	res.encoder_id_ptr = (uintptr_t)encoders;
	if (drm_ioctl(fd, DRM_IOCTL_MODE_GETRESOURCES, &res, "GETRESOURCES(data)"))
		goto out;

	for (i = 0; i < res.count_connectors; i++) {
		memset(&conn, 0, sizeof(conn));
		conn.connector_id = connectors[i];
		if (drm_ioctl(fd, DRM_IOCTL_MODE_GETCONNECTOR, &conn, "GETCONNECTOR(count)"))
			goto out;
		if (conn.connection != 1 || conn.count_modes == 0)
			continue;
		conn_id = connectors[i];
		enc_id = conn.encoder_id;
		conn_mode_count = conn.count_modes;
		break;
	}

	if (!conn_id) {
		fprintf(stderr, "no connected connector with modes\n");
		goto out;
	}

	modes = calloc(conn_mode_count, sizeof(*modes));
	conn_encoders = calloc(conn.count_encoders ? conn.count_encoders : 4,
			       sizeof(*conn_encoders));
	if (!modes || !conn_encoders) {
		fprintf(stderr, "alloc modes failed\n");
		goto out;
	}

	memset(&conn, 0, sizeof(conn));
	conn.connector_id = conn_id;
	conn.count_modes = conn_mode_count;
	conn.count_encoders = 4;
	conn.modes_ptr = (uintptr_t)modes;
	conn.encoders_ptr = (uintptr_t)conn_encoders;
	if (drm_ioctl(fd, DRM_IOCTL_MODE_GETCONNECTOR, &conn, "GETCONNECTOR(data)"))
		goto out;

	if (!conn.count_modes) {
		fprintf(stderr, "connector has no modes after fetch\n");
		goto out;
	}

	if (enc_id) {
		memset(&enc, 0, sizeof(enc));
		enc.encoder_id = enc_id;
		if (drm_ioctl(fd, DRM_IOCTL_MODE_GETENCODER, &enc, "GETENCODER"))
			goto out;
	}

	if (enc.crtc_id)
		crtc_id = enc.crtc_id;
	else if (res.count_crtcs)
		crtc_id = crtcs[0];

	if (!crtc_id) {
		fprintf(stderr, "no CRTC available\n");
		goto out;
	}

	out->conn_id = conn_id;
	out->crtc_id = crtc_id;
	out->mode = modes[0];
	ret = 0;

out:
	free(modes);
	free(conn_encoders);
	free(encoders);
	free(connectors);
	free(crtcs);
	return ret;
}

static int run_prime_bidir_smoke(int display_fd, const char *render_node,
				 uint32_t display_handle, uint32_t *out_display_import_handle)
{
	struct drm_prime_handle export_display = {0};
	struct drm_prime_handle import_render = {0};
	struct drm_prime_handle export_render = {0};
	struct drm_prime_handle import_display = {0};
	struct drm_gem_close close_req = {0};
	int render_fd;
	int ret = -1;

	export_display.fd = -1;
	export_render.fd = -1;

	export_display.handle = display_handle;
	export_display.flags = DRM_CLOEXEC | DRM_RDWR;
	if (drm_ioctl(display_fd, DRM_IOCTL_PRIME_HANDLE_TO_FD, &export_display,
		      "PRIME_HANDLE_TO_FD(display->fd)"))
		return -1;

	render_fd = open(render_node, O_RDWR | O_CLOEXEC);
	if (render_fd < 0) {
		perror("open render card");
		close(export_display.fd);
		return -1;
	}

	import_render.fd = export_display.fd;
	import_render.flags = DRM_CLOEXEC | DRM_RDWR;
	if (drm_ioctl(render_fd, DRM_IOCTL_PRIME_FD_TO_HANDLE, &import_render,
		      "PRIME_FD_TO_HANDLE(fd->render)"))
		goto out;

	export_render.handle = import_render.handle;
	export_render.flags = DRM_CLOEXEC | DRM_RDWR;
	if (drm_ioctl(render_fd, DRM_IOCTL_PRIME_HANDLE_TO_FD, &export_render,
		      "PRIME_HANDLE_TO_FD(render->fd)"))
		goto out;

	import_display.fd = export_render.fd;
	import_display.flags = DRM_CLOEXEC | DRM_RDWR;
	if (drm_ioctl(display_fd, DRM_IOCTL_PRIME_FD_TO_HANDLE, &import_display,
		      "PRIME_FD_TO_HANDLE(fd->display)"))
		goto out;

	close_req.handle = import_render.handle;
	if (drm_ioctl(render_fd, DRM_IOCTL_GEM_CLOSE, &close_req,
		      "GEM_CLOSE(render imported handle)"))
		goto out;

	*out_display_import_handle = import_display.handle;
	ret = 0;

out:
	if (export_render.fd >= 0)
		close(export_render.fd);
	close(render_fd);
	close(export_display.fd);
	return ret;
}

int main(int argc, char **argv)
{
	const char *display_node = "/dev/dri/card1";
	const char *render_node = "/dev/dri/card0";
	unsigned int hold_seconds = 30;
	bool prime_smoke = false;
	struct display_target target = {0};
	struct drm_mode_create_dumb create = {0};
	struct drm_mode_map_dumb map = {0};
	struct drm_mode_fb_cmd2 fb = {0};
	struct drm_mode_crtc crtc = {0};
	struct drm_mode_destroy_dumb destroy = {0};
	struct drm_gem_close close_req = {0};
	uint32_t rmfb_id = 0;
	uint32_t display_import_handle = 0;
	uint32_t fb_handle = 0;
	void *map_addr = MAP_FAILED;
	int fd;
	int ret = 1;

	if (argc >= 2)
		display_node = argv[1];

	for (int i = 2; i < argc; i++) {
		if (!strcmp(argv[i], "--prime")) {
			prime_smoke = true;
			if (i + 1 < argc && strncmp(argv[i + 1], "--", 2)) {
				render_node = argv[++i];
			}
		} else if (!strcmp(argv[i], "--hold-seconds")) {
			if (i + 1 >= argc) {
				fprintf(stderr, "missing value for --hold-seconds\n");
				return 1;
			}
			hold_seconds = (unsigned int)strtoul(argv[++i], NULL, 10);
		} else {
			fprintf(stderr,
				"Usage: %s [display_card] [--prime [render_card]] [--hold-seconds N]\n",
				argv[0]);
			return 1;
		}
	}

	fd = open(display_node, O_RDWR | O_CLOEXEC);
	if (fd < 0) {
		perror("open drm node");
		return 1;
	}

	if (find_display_target(fd, &target))
		goto out;

	printf("Using display=%s connector=%u crtc=%u mode=%s %ux%u\n",
	       display_node, target.conn_id, target.crtc_id,
	       target.mode.name, target.mode.hdisplay, target.mode.vdisplay);

	create.width = target.mode.hdisplay;
	create.height = 1088;
	create.bpp = 32;
	if (drm_ioctl(fd, DRM_IOCTL_MODE_CREATE_DUMB, &create, "CREATE_DUMB"))
		goto out;

	fb.width = create.width;
	fb.height = create.height;
	fb.pixel_format = DRM_FORMAT_XRGB8888;
	fb_handle = create.handle;
	fb.handles[0] = fb_handle;
	fb.pitches[0] = create.pitch;
	fb.offsets[0] = 0;

	map.handle = create.handle;
	if (drm_ioctl(fd, DRM_IOCTL_MODE_MAP_DUMB, &map, "MAP_DUMB"))
		goto out;

	map_addr = mmap(NULL, create.size, PROT_READ | PROT_WRITE, MAP_SHARED, fd,
			map.offset);
	if (map_addr == MAP_FAILED) {
		perror("mmap dumb");
		goto out;
	}

	fill_pattern((uint32_t *)map_addr, create.width, create.height, create.pitch);

	if (prime_smoke) {
		if (run_prime_bidir_smoke(fd, render_node, create.handle,
					 &display_import_handle))
			goto out;
		fb_handle = display_import_handle;
		printf("PRIME bidir: display->render and render->display succeeded\n");
	}

	fb.handles[0] = fb_handle;
	if (drm_ioctl(fd, DRM_IOCTL_MODE_ADDFB2, &fb, "ADDFB2"))
		goto out;

	crtc.crtc_id = target.crtc_id;
	crtc.fb_id = fb.fb_id;
	crtc.set_connectors_ptr = (uintptr_t)&target.conn_id;
	crtc.count_connectors = 1;
	crtc.mode = target.mode;
	crtc.mode_valid = 1;
	crtc.x = 0;
	crtc.y = 0;
	if (drm_ioctl(fd, DRM_IOCTL_MODE_SETCRTC, &crtc, "SETCRTC"))
		goto out;

	printf("Modeset succeeded. Holding for %us...\n", hold_seconds);
	sleep(hold_seconds);
	ret = 0;

out:
	if (map_addr != MAP_FAILED)
		munmap(map_addr, create.size);
	if (fb.fb_id) {
		rmfb_id = fb.fb_id;
		if (drm_ioctl(fd, DRM_IOCTL_MODE_RMFB, &rmfb_id, "RMFB"))
			fprintf(stderr, "RMFB failed\n");
	}
	if (display_import_handle && display_import_handle != create.handle) {
		close_req.handle = display_import_handle;
		if (drm_ioctl(fd, DRM_IOCTL_GEM_CLOSE, &close_req,
			      "GEM_CLOSE(display imported handle)"))
			fprintf(stderr, "GEM_CLOSE(display imported handle) failed\n");
	}
	if (create.handle) {
		destroy.handle = create.handle;
		if (drm_ioctl(fd, DRM_IOCTL_MODE_DESTROY_DUMB, &destroy, "DESTROY_DUMB"))
			fprintf(stderr, "DESTROY_DUMB failed\n");
	}
	close(fd);
	return ret;
}
