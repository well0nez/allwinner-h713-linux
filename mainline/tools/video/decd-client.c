// SPDX-License-Identifier: GPL-2.0
/*
 * decd-client -- drive the vendor DECD driver from userspace.
 *
 * Runs ON THE TARGET. Build: gcc -O2 -o decd-client decd-client.c
 *
 * This is the first consumer of /dev/decd. It exists because userspace can
 * neither resolve a buffer to a physical address nor program display
 * registers, which is why the vendor put frame submission in the kernel:
 * DECD_IOC_FRAME_SUBMIT hands the display a frame's physical addresses and the
 * CPU never reads the pixels.
 *
 * Structures are copied VERBATIM from the kernel's decd_types.h. They are a
 * binary ABI; a field out of place silently submits nonsense.
 *
 * Sharp edges in dec_frame_submit(), all of which fail quietly:
 *   - hdr.arg1 is a REPEAT COUNT. The enqueue loop is `while (repeat-- > 1)`,
 *     so 0 enqueues nothing at all.
 *   - desc->reserved0[0] is blue_en, and the submit path is
 *     `if (!desc->reserved0[0])`. Any non-zero byte there skips the frame.
 *   - It ALWAYS returns 0, even when disabled or when it did nothing. The
 *     returned fence fd and the panel are the only real feedback.
 *   - It refuses unless the device is enabled: PM_HINT must come first, and
 *     that is what triggers runtime resume -> dec_enable().
 */
#define _GNU_SOURCE
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

#define DECD_IOC_PM_HINT           0x40046401u
#define DECD_IOC_STOP_VIDEO_STREAM 0x40046408u
#define DECD_IOC_FRAME_SUBMIT      0x40706400u
#define DECD_IOC_GET_VSYNC_TS      0x8008640au
#define DECD_IOC_MAP_LINEAR_BUFFER 0xc010640bu

/* Verbatim from decd_types.h. */
struct dec_ioctl_header {
	uint64_t user_ptr;
	uint64_t user_ptr2;
	uint32_t arg0;
	uint32_t reserved0;
	uint32_t arg1;
	uint32_t reserved1;
};

struct dec_frame_submit_desc {
	uint8_t  linear;
	uint8_t  reserved0[3];          /* [0] is blue_en -- must stay 0 */
	int32_t  image_fd;
	uint32_t format;
	uint32_t reserved1[7];
	uint32_t width;
	uint32_t height;
	uint32_t reserved2[4];
	uint32_t align;
	uint32_t reserved3[2];
	int32_t  info_fd;
	uint32_t reserved4[4];
	uint8_t  split_fields;
	uint8_t  invert_field;
	uint8_t  field_mode;
	uint8_t  field_repeat;
	uint32_t field_sel0;
	uint32_t field_sel1;
	uint64_t y_phys;
	uint64_t c_phys;
};

struct dec_linear_map_req {
	uint32_t phys;
	uint32_t size;
	uint32_t dma_addr;
	uint32_t reserved;
};

#define W        1280
#define H        720
#define Y_PHYS   0x6c100000UL           /* the reserved uboot-scanout region */
#define C_PHYS   (Y_PHYS + (unsigned long)W * H)
#define NV12_SZ  ((size_t)W * H * 3 / 2)

/*
 * DEC_FORMAT_YUV420P. Note this is the format *id*, not the register code:
 * the AFBD register at 0x05600011 takes the fmt_attr_tbl ROW INDEX, which for
 * id 0 is 3. The driver owns that translation; we pass the id.
 */
#define DEC_FORMAT_YUV420P 0

static double now_ms(void)
{
	struct timespec ts;
	clock_gettime(CLOCK_MONOTONIC, &ts);
	return ts.tv_sec * 1000.0 + ts.tv_nsec / 1e6;
}

static int pm_hint(int fd, int on)
{
	struct dec_ioctl_header hdr = { .user_ptr = !!on };

	if (ioctl(fd, DECD_IOC_PM_HINT, &hdr) < 0) {
		perror("PM_HINT");
		return -1;
	}
	printf("PM_HINT %s ok\n", on ? "on" : "off");
	return 0;
}

/* Load an NV12 frame into the reserved region via /dev/mem. */
static int load_frame(const char *path)
{
	int mfd, ffd;
	void *map;
	uint8_t *buf = malloc(NV12_SZ);
	size_t got = 0;

	if (!buf)
		return -1;
	ffd = open(path, O_RDONLY);
	if (ffd < 0) { perror("open frame"); return -1; }
	while (got < NV12_SZ) {
		ssize_t r = read(ffd, buf + got, NV12_SZ - got);
		if (r <= 0) break;
		got += (size_t)r;
	}
	close(ffd);
	if (got != NV12_SZ) {
		fprintf(stderr, "short frame: %zu of %zu\n", got, NV12_SZ);
		return -1;
	}

	mfd = open("/dev/mem", O_RDWR | O_SYNC);
	if (mfd < 0) { perror("open /dev/mem"); return -1; }
	map = mmap(NULL, 0x800000, PROT_READ | PROT_WRITE, MAP_SHARED, mfd, Y_PHYS);
	if (map == MAP_FAILED) { perror("mmap scanout"); close(mfd); return -1; }
	memcpy(map, buf, NV12_SZ);
	__sync_synchronize();
	munmap(map, 0x800000);
	close(mfd);
	free(buf);
	printf("loaded %s -> Y %#lx  C %#lx\n", path, Y_PHYS, C_PHYS);
	return 0;
}

static int submit(int fd, int repeat)
{
	struct dec_frame_submit_desc desc;
	struct dec_ioctl_header hdr;
	int fence_fd = -1;

	memset(&desc, 0, sizeof(desc));
	desc.linear = 1;                /* y_phys/c_phys path, no dma-buf */
	desc.reserved0[0] = 0;          /* blue_en: MUST be 0 or the frame is dropped */
	desc.image_fd = -1;
	desc.info_fd = -1;
	desc.format = DEC_FORMAT_YUV420P;
	desc.width = W;
	desc.height = H;
	desc.align = 16;
	desc.y_phys = Y_PHYS;
	desc.c_phys = C_PHYS;

	memset(&hdr, 0, sizeof(hdr));
	hdr.user_ptr = (uint64_t)(uintptr_t)&desc;
	hdr.user_ptr2 = (uint64_t)(uintptr_t)&fence_fd;
	hdr.arg1 = repeat;              /* repeat count; 0 enqueues nothing */

	if (ioctl(fd, DECD_IOC_FRAME_SUBMIT, &hdr) < 0) {
		perror("FRAME_SUBMIT");
		return -1;
	}
	/*
	 * The ioctl returns 0 unconditionally, so a success here proves only
	 * that the call was made. A fence fd of -1 means the frame was NOT
	 * enqueued -- device disabled, blue_en set, or item creation failed --
	 * and dmesg carries "dec is not enabled!" for the first case.
	 */
	printf("FRAME_SUBMIT desc=%zu bytes, repeat=%d -> fence_fd=%d%s\n",
	       sizeof(desc), repeat, fence_fd,
	       fence_fd < 0 ? "  (NOT enqueued)" : "");
	if (fence_fd >= 0)
		close(fence_fd);
	return fence_fd >= 0 ? 0 : -1;
}

static void vsync_ts(int fd, int n)
{
	int i;

	for (i = 0; i < n; i++) {
		uint64_t ts = 0;
		struct dec_ioctl_header hdr = { 0 };
		double t0 = now_ms();

		hdr.user_ptr = (uint64_t)(uintptr_t)&ts;
		while (ioctl(fd, DECD_IOC_GET_VSYNC_TS, &hdr) < 0) {
			if (now_ms() - t0 > 200.0) {
				printf("  vsync %2d: TIMEOUT (ring empty)\n", i);
				goto next;
			}
		}
		printf("  vsync %2d: ts=%llu\n", i, (unsigned long long)ts);
next:
		;
	}
}

static void usage(void)
{
	fprintf(stderr,
		"usage: decd-client <cmd> [args]\n"
		"  pm on|off              runtime PM hint; 'on' triggers dec_enable()\n"
		"  vsync [n]              read n vsync timestamps from the driver ring\n"
		"  show <file.nv12> [ms]  pm on, load frame, submit, hold, pm off\n"
		"  submit <file.nv12>     load + submit only (leaves the device enabled)\n"
		"  stop                   STOP_VIDEO_STREAM\n");
}

int main(int argc, char **argv)
{
	int fd, ret = 0;

	if (argc < 2) { usage(); return 2; }

	fd = open("/dev/decd", O_RDWR);
	if (fd < 0) { perror("open /dev/decd"); return 1; }

	if (!strcmp(argv[1], "pm") && argc >= 3) {
		ret = pm_hint(fd, !strcmp(argv[2], "on"));
	} else if (!strcmp(argv[1], "vsync")) {
		vsync_ts(fd, argc >= 3 ? atoi(argv[2]) : 10);
	} else if (!strcmp(argv[1], "stop")) {
		struct dec_ioctl_header hdr = { 0 };

		ret = ioctl(fd, DECD_IOC_STOP_VIDEO_STREAM, &hdr);
		printf("STOP_VIDEO_STREAM -> %d\n", ret);
	} else if (!strcmp(argv[1], "submit") && argc >= 3) {
		if (load_frame(argv[2]) == 0)
			ret = submit(fd, 1);
	} else if (!strcmp(argv[1], "show") && argc >= 3) {
		unsigned dwell = argc >= 4 ? strtoul(argv[3], NULL, 0) : 10000;

		if (pm_hint(fd, 1) < 0) { close(fd); return 1; }
		if (load_frame(argv[2]) < 0) { close(fd); return 1; }
		ret = submit(fd, 1);
		printf("holding %u ms -- look at the panel\n", dwell);
		usleep(dwell * 1000);
		/*
		 * Deliberately NOT pm off. dec_disable() asserts the SHARED
		 * rst_bus_disp, which resets the whole display block and wipes
		 * U-Boot's programming -- measured 2026-08-14: one off/on cycle
		 * zeroed ctrl/stride/src and blanked the panel until a U-Boot
		 * reboot. It is also how the 2026-08-12 run's panel state was
		 * lost before anyone looked. `decd-client pm off` does it
		 * explicitly if the reset is actually wanted.
		 */
		printf("leaving device enabled; 'pm off' would reset the display "
		       "block (shared rst_bus_disp)\n");
	} else {
		usage();
		ret = 2;
	}

	close(fd);
	return ret ? 1 : 0;
}
