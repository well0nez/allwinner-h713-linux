// SPDX-License-Identifier: GPL-2.0
/*
 * gles-probe -- can the Mali do the zero-copy video pass at all?
 *
 * Runs ON THE TARGET. Build:
 *   gcc -O2 -o gles-probe gles-probe.c -lEGL -lGLESv2
 *
 * M3 measured the cap as the ~44 MB/s CPU read of the decoder's CMA output
 * buffer. The GPU escapes that only if it can import the decoder's buffer as a
 * dma-buf and render into the scanout region without the CPU touching either.
 * That needs four things, and this reports which of them the stack actually
 * has, before any of it is built on:
 *
 *   1. EGL_EXT_image_dma_buf_import        -- import a dma-buf as an EGLImage
 *   2. GL_OES_EGL_image_external           -- sample it as a texture
 *   3. an NV12-capable import              -- two planes, one image
 *   4. a dma-buf for the scanout region    -- the render target
 *
 * Prints, does not assume. A missing extension here changes the design rather
 * than costing a debugging session later.
 */
#define _GNU_SOURCE
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <GLES2/gl2.h>
#include <GLES2/gl2ext.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

/* From decd_types.h, same as decd-client.c. */
#define DECD_IOC_MAP_LINEAR_BUFFER 0xc010640bu
struct dec_linear_map_req {
	uint32_t phys;
	uint32_t size;
	uint32_t dma_addr;
	uint32_t reserved;
};

#define SCANOUT_PHYS 0x6c100000u
#define SCANOUT_SIZE 0x400000u

static int has(const char *exts, const char *name)
{
	const char *p = exts;
	size_t n = strlen(name);

	while (p && (p = strstr(p, name))) {
		if ((p == exts || p[-1] == ' ') && (p[n] == ' ' || p[n] == 0))
			return 1;
		p += n;
	}
	return 0;
}

static void report(const char *what, int ok)
{
	printf("  %-38s %s\n", what, ok ? "YES" : "no");
}

int main(void)
{
	EGLDisplay dpy;
	EGLContext ctx;
	EGLConfig cfg;
	EGLint n, major, minor;
	const char *egl_exts, *gl_exts;
	int fd;

	static const EGLint cfg_attr[] = {
		EGL_SURFACE_TYPE, EGL_PBUFFER_BIT,
		EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT,
		EGL_NONE
	};
	static const EGLint ctx_attr[] = { EGL_CONTEXT_CLIENT_VERSION, 2, EGL_NONE };

	dpy = eglGetDisplay(EGL_DEFAULT_DISPLAY);
	if (!eglInitialize(dpy, &major, &minor)) {
		fprintf(stderr, "eglInitialize failed: 0x%x "
			"(run with EGL_PLATFORM=surfaceless)\n", eglGetError());
		return 1;
	}
	eglBindAPI(EGL_OPENGL_ES_API);
	eglChooseConfig(dpy, cfg_attr, &cfg, 1, &n);
	ctx = eglCreateContext(dpy, cfg, EGL_NO_CONTEXT, ctx_attr);
	eglMakeCurrent(dpy, EGL_NO_SURFACE, EGL_NO_SURFACE, ctx);

	printf("EGL %d.%d, renderer %s\n\n", major, minor, glGetString(GL_RENDERER));

	egl_exts = eglQueryString(dpy, EGL_EXTENSIONS);
	gl_exts = (const char *)glGetString(GL_EXTENSIONS);

	printf("import path:\n");
	report("EGL_EXT_image_dma_buf_import",
	       has(egl_exts, "EGL_EXT_image_dma_buf_import"));
	report("EGL_EXT_image_dma_buf_import_modifiers",
	       has(egl_exts, "EGL_EXT_image_dma_buf_import_modifiers"));
	report("EGL_KHR_image_base", has(egl_exts, "EGL_KHR_image_base"));
	report("eglCreateImageKHR resolves",
	       eglGetProcAddress("eglCreateImageKHR") != NULL);

	printf("\nsample path:\n");
	report("GL_OES_EGL_image", has(gl_exts, "GL_OES_EGL_image"));
	report("GL_OES_EGL_image_external",
	       has(gl_exts, "GL_OES_EGL_image_external"));
	report("GL_OES_EGL_image_external_essl3",
	       has(gl_exts, "GL_OES_EGL_image_external_essl3"));
	report("glEGLImageTargetTexture2DOES resolves",
	       eglGetProcAddress("glEGLImageTargetTexture2DOES") != NULL);

	printf("\nrender-target path:\n");
	report("GL_OES_EGL_image_external as FBO colour",
	       has(gl_exts, "GL_EXT_color_buffer_half_float") ||
	       has(gl_exts, "GL_OES_rgb8_rgba8"));
	report("GL_OES_rgb8_rgba8 (RGBA8 renderbuffer)",
	       has(gl_exts, "GL_OES_rgb8_rgba8"));

	printf("\nscanout dma-buf via DECD:\n");
	fd = open("/dev/decd", O_RDWR);
	if (fd < 0) {
		printf("  /dev/decd not open (insmod sunxi-decd.ko?) -- skipped\n");
	} else {
		struct dec_linear_map_req req = {
			.phys = SCANOUT_PHYS, .size = SCANOUT_SIZE,
		};
		struct {
			unsigned long long user_ptr, user_ptr2;
			unsigned arg0, r0, arg1, r1;
		} hdr = { 0 };

		hdr.user_ptr = (unsigned long long)(uintptr_t)&req;
		if (ioctl(fd, DECD_IOC_MAP_LINEAR_BUFFER, &hdr) < 0) {
			perror("  MAP_LINEAR_BUFFER");
		} else {
			printf("  MAP_LINEAR_BUFFER ok: phys=%08x size=%08x "
			       "dma_addr=%08x\n", req.phys, req.size, req.dma_addr);
			printf("  NOTE: returns a dma_addr, not an fd -- check whether\n"
			       "        anything here can hand EGL a dma-buf FD.\n");
		}
		close(fd);
	}

	printf("\nfull EGL extension string:\n%s\n", egl_exts);
	printf("\nfull GL extension string:\n%s\n", gl_exts);
	return 0;
}
