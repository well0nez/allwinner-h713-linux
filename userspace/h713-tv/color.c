// SPDX-License-Identifier: GPL-2.0
#ifndef _GNU_SOURCE
#define _GNU_SOURCE		/* as in main.c: the same strtol() (C23 binary prefix) and the same headers */
#endif
/*
 * h713-tv -- the display firmware's own colour: white balance and colour management.
 *
 * This part stands by itself: the ways to the hardware are four function pointers (struct fwc_io), and a made-up
 * firmware behind them is all its host test needs (tests/test_color.c). The interface to main.c is color.h; the
 * journal and the reply of a control command are main.c's.
 */
#include <ctype.h>
#include <errno.h>
#include <dirent.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <time.h>
#include <unistd.h>

#include <sys/ioctl.h>
#include <sys/mman.h>

#include "color.h"

/* ------------------------------------------------------------------ *
 * The firmware's colour: white balance and colour management
 *
 * Two of the vendor's picture settings are not V4L2 controls and not LUT
 * entries; they are two calls into the display firmware, THal_Vp_SetWhiteBalance
 * and THal_Vp_SetColorManagement (the vendor's HAL sends them for the factory
 * menu's "white balance" and "colour manager"). Both take the *physical address of
 * a block in the shared cpu_comm memory*, so a call needs two things this
 * program otherwise never touches: a slot in that memory, and the call itself
 * through /dev/cpu_comm (IOCTL_CALL; the release image has no debugfs, so
 * "ctl rpc" cannot do it).
 *
 *   THal_Vp_SetWhiteBalance   0xfc42fe0c  one word: the block, six u32
 *       {R gain, G gain, B gain, R offset, G offset, B offset}, each 0..1023,
 *       512 neutral. The firmware copies the words during the call. EVERY
 *       word that is not 0xFFFF is written; but 0xFFFF is no "leave it": the
 *       firmware took the next-best number for it (blue gain 0, offsets -512,
 *       measured 18.10.2026). So all six are always sent, and nothing else is.
 *   THal_Vp_SetColorManagement 0xf00ca77d two words: the block, the number of
 *       axes (12). Per axis {hue, saturation, value} as 8-bit MAGNITUDES; the
 *       sign of an entry is a bit in the register block 0x05140300.. that the
 *       vendor's HAL sets itself (libpq set_decrease_value), before the call.
 *       The firmware reads the block LATER (its application thread), compares
 *       it with a cache of what it last wrote and writes only the entries that
 *       differ: the block must stay where it is, and an entry that already
 *       equals the cache is not written again even if the register was changed
 *       behind its back.
 *
 * Where the blocks live. The cpu_comm region (reserved memory in the board
 * file, 5 MiB at 0x4E300000 on the H713 boards) belongs to nobody in particular
 * on the Linux side; the HDMI receiver's driver uses fixed offsets in it
 * (+0x36000 the HDCP 2.2 key, +0x37000 the Wce_SetWindow structures, +0x37100
 * the six words of the backlight PWM info, +0x400000 the THal_Vp_Init staging)
 * and has done so since the first picture. The two slots here are in the same
 * mapped window the driver already owns, behind its last user:
 *
 *   +0x37200  white balance, 8 words: the six values, a mark, the mark inverted
 *   +0x37300  colour management, 40 words: 12 x 3 magnitudes, the rest zero,
 *             a mark, the mark inverted
 *
 * Not +0x37100 (where the first probe wrote): that is the backlight PWM block of
 * the board file's allwinner,backlight-pwm-info. Before a block is written
 * the slot must be empty (all zero) or carry this program's mark; anything else
 * is somebody's, and nothing is written. The cpu_comm region must be the one the
 * board file names (reserved-memory cpu-comm@...) and carry the transport's magic,
 * and the firmware must be the one these addresses were read from: four of its
 * strings (the RPC names and the TSE feature "wb_r_gain") are looked for at the
 * addresses they have in display.bin. Otherwise the whole feature says why it
 * is not there, and nothing is sent. Registers are read through /dev/mem to see
 * that the call did what it was asked to (and to notice that the firmware has
 * forgotten it).
 *
 * What the user's numbers mean.
 *   wb_*       absolute, the firmware's own scale: gain 0..1023 (512 = 1.0, 1023
 *              = 2.0), offset 0..1023 (512 = 0).
 *   cm_*       a signed step on top of what the picture mode itself puts into
 *              the entry (-255..255, 0 = leave as the firmware had it). The
 *              firmware's own value of each entry is read from the registers the
 *              first time this program changes anything and kept in
 *              /run/h713-tv-state/cm-base, so that 0 always means "as the
 *              board comes", whatever happened in between. (The vendor's factory
 *              menu writes the number itself; on boards whose picture mode puts
 *              a non-zero value into an entry that would make "saturation +10"
 *              mean "saturation 10".)
 *
 * When it is sent: at the start, if the registers do not hold what is wanted;
 * on every "ctl set"; and again after anything that may make the firmware
 * forget (a source selected again, a source change event) -- if, and only if,
 * the registers have changed. A re-send of the colour management first sends
 * the mismatching entries one off, so that the firmware's cache does not hide
 * the change. A picture mode is different: it writes the board's colour values
 * of its own, so the base moves with it (fwc_mode_begin()).
 * ------------------------------------------------------------------ */

#define FWC_WB_NEUTRAL	512
#define FWC_WB_MAX	1023
#define FWC_CM_MAX	255
#define FWC_NEG_ZERO	(-256)		/* an entry of 0 whose sign bit is set: kept so that "neutral" gives the bit back too */

#define FWC_RPC_WB	0xfc42fe0cu	/* THal_Vp_SetWhiteBalance_1_000 */
#define FWC_RPC_CM	0xf00ca77du	/* THal_Vp_SetColorManagement_1_000 */
#define FWC_IOCTL_CALL	0xC0087F26u	/* /dev/cpu_comm CPUComm_Call, a 168-byte message */

/* the cpu_comm region when the board file is not asked (Kernel 0024: cpu-comm@4e300000) */
#define FWC_SHM_BASE	0x4E300000u
#define FWC_SHM_SIZE	0x500000u
#define FWC_SHM_MAGIC	0xDEADBEEFu
#define FWC_SHM_MAGIC1	0x90u		/* the transport's magic words, SHMEM_OFF_MAGIC1/2 */
#define FWC_SHM_MAGIC2	0x75B8u
/* what the HDMI receiver's driver uses in the same window (hdmirx 0094, 0168) */
#define FWC_SMM_HEAD	0x2D000u	/* the firmware's allocator (Trid_SMM), grows upwards: word 47 its start, word 45 its size */
#define FWC_SHM_HDMIRX_END	0x37118u	/* Wce 0x37000..0x37047, backlight PWM 0x37100..0x37117 */
#define FWC_SHM_WB	0x37200u
#define FWC_SHM_WB_WORDS	8
#define FWC_SHM_CM	0x37300u
#define FWC_SHM_CM_WORDS	40
#define FWC_SHM_WINDOW_END	0x38000u	/* the window the receiver maps; the slots stay inside */
#define FWC_MARK_WB	0x42573748u	/* "H7WB" */
#define FWC_MARK_CM	0x4d433748u	/* "H7CM" */

_Static_assert(FWC_SHM_WB >= FWC_SHM_HDMIRX_END, "the white balance slot is behind the receiver's");
_Static_assert(FWC_SHM_WB + 4 * FWC_SHM_WB_WORDS <= FWC_SHM_CM, "the slots do not overlap");
_Static_assert(FWC_SHM_CM + 4 * FWC_SHM_CM_WORDS <= FWC_SHM_WINDOW_END, "the slots stay in the receiver's window");
_Static_assert(FWC_SHM_CM_WORDS >= FWC_CM_N + 2, "the colour management block fits");

#define FWC_BASE_FILE	"/run/h713-tv-state/cm-base"
#define FWC_VERIFY_MS	400

/* the registers (pq_custom.TSE features wb_*; Firmware table 0x8B22F824 for the colour management) */
#define FWC_REG_WB_D4	0x051C00D4u
#define FWC_REG_WB_D8	0x051C00D8u
#define FWC_REG_WB_DC	0x051C00DCu
#define FWC_REG_WB_E0	0x051C00E0u
#define FWC_REG_CM_FLAGS	0x05140300u
#define FWC_REG_CM_FIRST	0x0514030Cu
#define FWC_REG_CM_ENABLE	0x0514045Cu	/* bit 31 clear: the colour manager is on */

static const char *const fwc_wb_name[FWC_WB_N] = {
	"wb_r_gain", "wb_g_gain", "wb_b_gain", "wb_r_offset", "wb_g_offset", "wb_b_offset",
};

/* the vendor's E_AW_CM_RANGE_*, by number; the number is the hardware axis */
static const char *const fwc_cm_axis[FWC_CM_AXES] = {
	"red", "lips", "skintone", "yellow", "yellow_green", "green", "cyan", "blue",
	"blue_purple", "purple", "reserve0", "reserve1",
};
static const char *const fwc_cm_comp[3] = { "hue", "sat", "value" };

/* strings of the firmware this was written for, at the addresses they have in display.bin (ARM physical) */
static const struct { uint32_t phys; const char *text; } fwc_sig[] = {
	{ 0x4B2002A4u, "wb_r_gain" },
	{ 0x4B22DDA8u, "THal_Vp_SetWhiteBalance" },
	{ 0x4B22D5F0u, "THal_Vp_SetColorManagement" },
	{ 0x4B1EBF58u, "OnHalColorManagementChange" },
};

/* the ways to the hardware; the tests put a made-up firmware in their place */
struct fwc_io {
	bool (*rd)(uint32_t phys, uint32_t *v);
	bool (*wr)(uint32_t phys, uint32_t v);
	/* the call; false: why in err */
	bool (*call)(uint32_t id, const uint32_t *args, unsigned int n, char *err, size_t en);
	/* the cpu_comm region of the board file */
	bool (*region)(uint32_t *base, uint32_t *size);
};

struct fwc {
	const struct fwc_io *io;
	int wb[FWC_WB_N];		/* wanted */
	int cm[FWC_CM_N];		/* wanted, a step on the firmware's own value */
	int cm_base[FWC_CM_N];		/* the firmware's own value, signed; FWC_NEG_ZERO: magnitude 0 with the sign bit set */
	bool cm_base_ok;
	bool mode_open;			/* fwc_mode_begin() has taken the steps off, fwc_mode_end() has not laid them on yet */
	const char *base_path;		/* NULL: not kept over a restart of this program */
	bool probed, ok;
	char why[200];			/* why not ok, in the words of the journal */
	uint32_t shm;			/* base of the cpu_comm region */
	bool wb_applied;		/* the registers held the wanted values after the last send */
	bool cm_applied;
	unsigned int sends_wb, sends_cm, repairs;
	char last[160];			/* the last send, for the status */
	/* /dev/mem, pages mapped on demand */
	int memfd;
	struct { uint32_t page; bool wr; volatile uint32_t *va; } pg[16];
	unsigned int npg;
};

static struct fwc fwc = { .memfd = -1, .base_path = FWC_BASE_FILE };

/* ---- the real hardware: /dev/mem, /dev/cpu_comm, the board file ---- */

static volatile uint32_t *fwc_page(uint32_t phys, bool wr)
{
	uint32_t page = phys & ~0xfffu;
	unsigned int i;
	void *va;

	for (i = 0; i < fwc.npg; i++)
		if (fwc.pg[i].page == page && (fwc.pg[i].wr || !wr))
			return fwc.pg[i].va;
	if (fwc.memfd < 0) {
		fwc.memfd = open("/dev/mem", O_RDWR | O_SYNC | O_CLOEXEC);
		if (fwc.memfd < 0)
			return NULL;
	}
	if (fwc.npg == sizeof(fwc.pg) / sizeof(fwc.pg[0]))
		return NULL;
	va = mmap(NULL, 4096, PROT_READ | (wr ? PROT_WRITE : 0), MAP_SHARED, fwc.memfd, (off_t)page);
	if (va == MAP_FAILED)
		return NULL;
	fwc.pg[fwc.npg].page = page;
	fwc.pg[fwc.npg].wr = wr;
	fwc.pg[fwc.npg].va = va;

	return fwc.pg[fwc.npg++].va;
}

static bool fwc_hw_rd(uint32_t phys, uint32_t *v)
{
	volatile uint32_t *p = fwc_page(phys, false);

	if (!p || (phys & 3))
		return false;
	*v = p[(phys & 0xfff) >> 2];

	return true;
}

static bool fwc_hw_wr(uint32_t phys, uint32_t v)
{
	volatile uint32_t *p = fwc_page(phys, true);

	if (!p || (phys & 3))
		return false;
	p[(phys & 0xfff) >> 2] = v;
	__sync_synchronize();

	return true;
}

static bool fwc_hw_call(uint32_t id, const uint32_t *args, unsigned int n, char *err, size_t en)
{
	unsigned char buf[168];
	uint16_t cpu = 1;			/* the MIPS */
	uint32_t cnt = n;
	unsigned int i;
	int fd;

	memset(buf, 0, sizeof(buf));
	memcpy(buf + 2, &cpu, 2);
	memcpy(buf + 40, &id, 4);
	memcpy(buf + 64, &cnt, 4);
	for (i = 0; i < n && i < 10; i++)
		memcpy(buf + 68 + 4 * i, &args[i], 4);
	fd = open("/dev/cpu_comm", O_RDWR | O_CLOEXEC);
	if (fd < 0) {
		snprintf(err, en, "/dev/cpu_comm: %s", strerror(errno));
		return false;
	}
	if (ioctl(fd, FWC_IOCTL_CALL, buf)) {
		snprintf(err, en, "RPC %#x: %s", id, strerror(errno));
		close(fd);
		return false;
	}
	close(fd);

	return true;
}

/* reserved-memory/cpu-comm@*: reg = <base size> in #address-cells/#size-cells cells */
static bool fwc_hw_region(uint32_t *base, uint32_t *size)
{
	static const char root[] = "/sys/firmware/devicetree/base/reserved-memory";
	char path[320];
	unsigned char raw[32], cells[4];
	uint64_t b = 0, s = 0;
	struct dirent *de;
	unsigned int ac, sc, i;
	FILE *f;
	DIR *dir;

	snprintf(path, sizeof(path), "%s/#address-cells", root);
	f = fopen(path, "r");
	if (!f || fread(cells, 1, 4, f) != 4) {
		if (f)
			fclose(f);
		return false;
	}
	fclose(f);
	ac = (unsigned int)cells[3] | (unsigned int)cells[2] << 8;
	snprintf(path, sizeof(path), "%s/#size-cells", root);
	f = fopen(path, "r");
	if (!f || fread(cells, 1, 4, f) != 4) {
		if (f)
			fclose(f);
		return false;
	}
	fclose(f);
	sc = (unsigned int)cells[3] | (unsigned int)cells[2] << 8;
	if (ac < 1 || ac > 2 || sc < 1 || sc > 2)
		return false;
	dir = opendir(root);
	if (!dir)
		return false;
	while ((de = readdir(dir))) {
		size_t got;

		if (strncmp(de->d_name, "cpu-comm@", 9))
			continue;
		snprintf(path, sizeof(path), "%s/%s/reg", root, de->d_name);
		f = fopen(path, "r");
		if (!f)
			continue;
		got = fread(raw, 1, sizeof(raw), f);
		fclose(f);
		if (got < 4 * (ac + sc))
			continue;
		for (i = 0; i < ac; i++)
			b = b << 32 | ((uint32_t)raw[4 * i] << 24 | (uint32_t)raw[4 * i + 1] << 16 |
				       (uint32_t)raw[4 * i + 2] << 8 | raw[4 * i + 3]);
		for (i = ac; i < ac + sc; i++)
			s = s << 32 | ((uint32_t)raw[4 * i] << 24 | (uint32_t)raw[4 * i + 1] << 16 |
				       (uint32_t)raw[4 * i + 2] << 8 | raw[4 * i + 3]);
		closedir(dir);
		if (b > 0xffffffffull || s > 0xffffffffull || !s)
			return false;
		*base = (uint32_t)b;
		*size = (uint32_t)s;

		return true;
	}
	closedir(dir);

	return false;
}

static const struct fwc_io fwc_hw = {
	.rd = fwc_hw_rd, .wr = fwc_hw_wr, .call = fwc_hw_call, .region = fwc_hw_region,
};

/* ---- the numbers: what the registers hold for a wanted value ---- */

/* the register field (12 bits) the firmware's curve makes of a value: pq_custom.TSE, features wb_* */
static unsigned int fwc_wb_expect(unsigned int i, int v)
{
	double y;

	if (i < 3)
		y = v <= 512 ? 4.0 * v : 2048.0 + (v - 512) * 2047.0 / 511.0;
	else
		y = v <= 512 ? 4.0 * v - 2048.0 : (v - 512) * 2047.0 / 511.0;

	return (unsigned int)(int)y & 0xfffu;
}

/* the register and shift of word i of the block: R/G gain in DC, B gain in E0, offsets in D4/D8 */
static void fwc_wb_field(unsigned int i, uint32_t *reg, unsigned int *sh)
{
	static const struct { uint32_t reg; unsigned int sh; } f[FWC_WB_N] = {
		{ FWC_REG_WB_DC, 16 }, { FWC_REG_WB_DC, 0 }, { FWC_REG_WB_E0, 16 },
		{ FWC_REG_WB_D4, 0 }, { FWC_REG_WB_D8, 16 }, { FWC_REG_WB_D8, 0 },
	};

	*reg = f[i].reg;
	*sh = f[i].sh;
}

/* the magnitude of entry e (axis e/3, hue/saturation/value): register and shift */
static void fwc_cm_field(unsigned int e, uint32_t *reg, unsigned int *sh)
{
	unsigned int a = e / 3, k = e % 3;
	uint32_t w0 = FWC_REG_CM_FIRST + (a / 2) * 0x34u + (a % 2) * 0x1cu;

	*reg = k ? w0 + 4 : w0;
	*sh = k == 0 ? 16 : k == 1 ? 24 : 16;
}

/* the sign of entry e: a bit in the three flag words, four axes each, the first axis in the top byte */
static void fwc_cm_sign(unsigned int e, uint32_t *reg, unsigned int *bit)
{
	unsigned int a = e / 3, k = e % 3;

	*reg = FWC_REG_CM_FLAGS + 4 * (a / 4);
	*bit = 25 + k - 8 * (a % 4);
}

static int fwc_clamp(int v, int lo, int hi)
{
	return v < lo ? lo : v > hi ? hi : v;
}

static bool fwc_cm_any(void)
{
	unsigned int e;

	for (e = 0; e < FWC_CM_N; e++)
		if (fwc.cm[e])
			return true;

	return false;
}

static bool fwc_wb_neutral(void)
{
	unsigned int i;

	for (i = 0; i < FWC_WB_N; i++)
		if (fwc.wb[i] != FWC_WB_NEUTRAL)
			return false;

	return true;
}

/* ---- is the machinery there, and is it the one these addresses belong to ---- */

static bool fwc_probe(void)
{
	uint32_t base, size, v;
	unsigned int i, j;

	if (fwc.ok)
		return true;
	fwc.probed = true;
	if (!fwc.io)
		fwc.io = &fwc_hw;
	if (!fwc.io->region(&base, &size)) {
		base = FWC_SHM_BASE;
		size = FWC_SHM_SIZE;
	}
	fwc.shm = base;
	if (FWC_SHM_WINDOW_END > size) {
		snprintf(fwc.why, sizeof(fwc.why), "the cpu_comm region (%#x + %#x) does not reach the receiver's window",
			 base, size);
		return false;
	}
	if (!fwc.io->rd(base + FWC_SHM_MAGIC1, &v) || v != FWC_SHM_MAGIC ||
	    !fwc.io->rd(base + FWC_SHM_MAGIC2, &v) || v != FWC_SHM_MAGIC) {
		snprintf(fwc.why, sizeof(fwc.why),
			 "no cpu_comm transport at %#x (the magic is not there, or /dev/mem cannot be read)", base);
		return false;
	}
	for (i = 0; i < sizeof(fwc_sig) / sizeof(fwc_sig[0]); i++) {
		for (j = 0; j <= strlen(fwc_sig[i].text); j++) {
			uint32_t a = fwc_sig[i].phys + j, w;

			if (!fwc.io->rd(a & ~3u, &w) || (w >> (8 * (a & 3)) & 0xff) != (unsigned char)fwc_sig[i].text[j]) {
				snprintf(fwc.why, sizeof(fwc.why),
					 "not the display firmware these addresses were read from (\"%s\" is not at %#x)",
					 fwc_sig[i].text, fwc_sig[i].phys);
				return false;
			}
		}
	}
	fwc.ok = true;

	return true;
}

/* the slot is empty or ours; else its words are named */
static bool fwc_slot_free(uint32_t off, unsigned int words, uint32_t mark, char *why, size_t n)
{
	uint32_t w[FWC_SHM_CM_WORDS], a = fwc.shm + off, hs, hn;
	unsigned int i;
	bool zero = true;

	if (off < FWC_SHM_HDMIRX_END || off + 4 * words > FWC_SHM_WINDOW_END) {
		snprintf(why, n, "slot %#x is outside the free part of the receiver's window", off);
		return false;
	}
	/*
	 * The firmware's allocator lies below the slots and grows upwards; a slot it has reached may be handed out by it
	 * (measured on the HY310 18.10.2026: one page given, the break at +0x33000, the slots three pages above). Read at
	 * every write, not once: the break moves while the firmware runs. The break moves in whole pages (morecore rounds
	 * to pages, and a class of small blocks takes a page of its own; Mythos 19.10.2026): once it stands at the start
	 * of the slot's page, the next allocation takes that page, so the slot is free only while the break is below it.
	 */
	if (!fwc.io->rd(fwc.shm + FWC_SMM_HEAD + 4 * 47, &hs) || !fwc.io->rd(fwc.shm + FWC_SMM_HEAD + 4 * 45, &hn)) {
		snprintf(why, n, "/dev/mem: cannot read the firmware's allocator at %#x", fwc.shm + FWC_SMM_HEAD);
		return false;
	}
	if (hs != fwc.shm + FWC_SMM_HEAD) {
		snprintf(why, n, "the firmware's allocator is not where it was read (start %#x) -- nothing written", hs);
		return false;
	}
	if (hn >= (off & ~0xfffu) - FWC_SMM_HEAD) {
		snprintf(why, n, "the firmware's allocator has grown over the slot at %#x (break %#x) -- nothing written", a, hs + hn);
		return false;
	}
	for (i = 0; i < words; i++) {
		if (!fwc.io->rd(a + 4 * i, &w[i])) {
			snprintf(why, n, "/dev/mem: cannot read %#x", a + 4 * i);
			return false;
		}
		zero &= !w[i];
	}
	if (w[words - 2] == mark && w[words - 1] == ~mark)
		return true;
	if (zero)
		return true;
	snprintf(why, n, "the slot at %#x is somebody else's (%08x %08x %08x ...) -- nothing written", a, w[0], w[1], w[2]);

	return false;
}

static bool fwc_slot_put(uint32_t off, const uint32_t *w, unsigned int words, uint32_t mark)
{
	uint32_t a = fwc.shm + off;
	unsigned int i;

	for (i = 0; i < words - 2; i++)
		if (!fwc.io->wr(a + 4 * i, w[i]))
			return false;

	return fwc.io->wr(a + 4 * (words - 2), mark) && fwc.io->wr(a + 4 * (words - 1), ~mark);
}

static void fwc_sleep_ms(unsigned int ms)
{
	struct timespec ts = { .tv_sec = ms / 1000, .tv_nsec = (long)(ms % 1000) * 1000000L };

	nanosleep(&ts, NULL);
}

/* ---- white balance ---- */

/* how many of the six fields differ by more than one step from what is wanted; -1: the registers cannot be read */
static int fwc_wb_off(void)
{
	unsigned int i;
	int bad = 0;

	for (i = 0; i < FWC_WB_N; i++) {
		uint32_t reg, w;
		unsigned int sh, got, want = fwc_wb_expect(i, fwc.wb[i]);
		int d;

		fwc_wb_field(i, &reg, &sh);
		if (!fwc.io->rd(reg, &w))
			return -1;
		got = w >> sh & 0xfffu;
		d = (int)got - (int)want;
		bad += d > 1 || d < -1;
	}

	return bad;
}

static void fwc_wb_text(char *out, size_t n)
{
	snprintf(out, n, "%d %d %d %d %d %d", fwc.wb[0], fwc.wb[1], fwc.wb[2], fwc.wb[3], fwc.wb[4], fwc.wb[5]);
}

/* send the six wanted values and look at the registers; returns false and says why when it did not take */
static bool fwc_wb_send(char *msg, size_t n)
{
	uint32_t blk[FWC_SHM_WB_WORDS], arg;
	unsigned int ms, i;
	char err[160];
	int bad = 0;

	fwc.wb_applied = false;
	if (!fwc_probe()) {
		snprintf(msg, n, "%s", fwc.why);
		return false;
	}
	if (!fwc_slot_free(FWC_SHM_WB, FWC_SHM_WB_WORDS, FWC_MARK_WB, err, sizeof(err))) {
		snprintf(msg, n, "%s", err);
		return false;
	}
	for (i = 0; i < FWC_WB_N; i++)
		blk[i] = (uint32_t)fwc.wb[i];
	if (!fwc_slot_put(FWC_SHM_WB, blk, FWC_SHM_WB_WORDS, FWC_MARK_WB)) {
		snprintf(msg, n, "/dev/mem: the slot at %#x cannot be written", fwc.shm + FWC_SHM_WB);
		return false;
	}
	arg = fwc.shm + FWC_SHM_WB;
	if (!fwc.io->call(FWC_RPC_WB, &arg, 1, err, sizeof(err))) {
		snprintf(msg, n, "%s", err);
		return false;
	}
	fwc.sends_wb++;
	for (ms = 0;; ms += 20) {
		bad = fwc_wb_off();
		if (bad <= 0 || ms >= FWC_VERIFY_MS)
			break;
		fwc_sleep_ms(20);
	}
	fwc_wb_text(fwc.last, sizeof(fwc.last));
	if (bad < 0) {
		snprintf(msg, n, "sent, the registers cannot be read back");
		fwc.wb_applied = true;	/* the call went through; nothing to compare with */
		return true;
	}
	if (bad) {
		snprintf(msg, n, "sent, but %d of 6 registers differ from the values after %u ms", bad, ms);
		return false;
	}
	snprintf(msg, n, "registers read back, %u ms", ms);
	fwc.wb_applied = true;

	return true;
}

/* ---- colour management ---- */

static bool fwc_cm_read(unsigned int e, int *mag, bool *neg)
{
	uint32_t reg, w, fr;
	unsigned int sh, bit;

	fwc_cm_field(e, &reg, &sh);
	if (!fwc.io->rd(reg, &w))
		return false;
	*mag = (int)(w >> sh & 0xffu);
	fwc_cm_sign(e, &reg, &bit);
	if (!fwc.io->rd(reg, &fr))
		return false;
	*neg = fr >> bit & 1u;

	return true;
}

static bool fwc_base_load(void)
{
	char line[1024], *p, *end;
	unsigned int e;
	FILE *f;

	if (!fwc.base_path)
		return false;
	f = fopen(fwc.base_path, "r");
	if (!f)
		return false;
	if (!fgets(line, sizeof(line), f) || strncmp(line, "h713-tv cm-base 1", 17) || !fgets(line, sizeof(line), f)) {
		fclose(f);
		return false;
	}
	fclose(f);
	p = line;
	for (e = 0; e < FWC_CM_N; e++) {
		long x = strtol(p, &end, 10);

		if (end == p || x < FWC_NEG_ZERO || x > FWC_CM_MAX)
			return false;
		fwc.cm_base[e] = (int)x;
		p = end;
	}
	fwc.cm_base_ok = true;

	return true;
}

static void fwc_base_save(void)
{
	char tmp[256];
	unsigned int e;
	FILE *f;

	if (!fwc.base_path)
		return;
	snprintf(tmp, sizeof(tmp), "%s.new", fwc.base_path);
	f = fopen(tmp, "w");
	if (!f) {
		warn("colour          %s: %s -- the firmware's own colour values are not kept over a restart of this program",
		     fwc.base_path, strerror(errno));
		return;
	}
	fputs("h713-tv cm-base 1\n", f);
	for (e = 0; e < FWC_CM_N; e++)
		fprintf(f, "%s%d", e ? " " : "", fwc.cm_base[e]);
	fputc('\n', f);
	if (fclose(f) || rename(tmp, fwc.base_path)) {
		warn("colour          %s: %s", fwc.base_path, strerror(errno));
		unlink(tmp);
	}
}

/* read what the registers hold now into the base and keep it: only for a moment when none of this program's steps is on them */
static bool fwc_base_take(char *why, size_t n)
{
	unsigned int e;

	for (e = 0; e < FWC_CM_N; e++) {
		int mag;
		bool neg;

		if (!fwc_cm_read(e, &mag, &neg)) {
			snprintf(why, n, "/dev/mem: the colour registers cannot be read");
			return false;
		}
		fwc.cm_base[e] = !neg ? mag : mag ? -mag : FWC_NEG_ZERO;
	}
	fwc.cm_base_ok = true;
	fwc_base_save();

	return true;
}

/* what the firmware itself holds in every entry, once: before this program has changed any */
static bool fwc_base_ensure(char *why, size_t n)
{
	if (fwc.cm_base_ok || fwc_base_load())
		return true;

	return fwc_base_take(why, n);
}

/* the value every entry should hold: the firmware's own, moved by the wanted step */
static int fwc_cm_eff(unsigned int e)
{
	int base = fwc.cm_base[e] == FWC_NEG_ZERO ? 0 : fwc.cm_base[e];

	return fwc_clamp(base + fwc.cm[e], -FWC_CM_MAX, FWC_CM_MAX);
}

/* the sign bit entry e should have: its value's sign, and for a zero the one the firmware had */
static bool fwc_cm_want_neg(unsigned int e)
{
	int eff = fwc_cm_eff(e);

	return eff ? eff < 0 : fwc.cm_base[e] < 0;
}

/* how many entries do not hold what is wanted (magnitude or sign); -1: the registers cannot be read */
static int fwc_cm_off(void)
{
	unsigned int e;
	int bad = 0;

	for (e = 0; e < FWC_CM_N; e++) {
		int mag, eff = fwc_cm_eff(e);
		bool neg;

		if (!fwc_cm_read(e, &mag, &neg))
			return -1;
		bad += mag != (eff < 0 ? -eff : eff) || (eff && neg != (eff < 0));
	}

	return bad;
}

/* set the sign bit of every entry whose sign is not the wanted one (before the call, as the vendor's HAL does) */
static bool fwc_cm_signs(void)
{
	unsigned int e;

	for (e = 0; e < FWC_CM_N; e++) {
		uint32_t reg, w;
		unsigned int bit;
		bool want = fwc_cm_want_neg(e);

		fwc_cm_sign(e, &reg, &bit);
		if (!fwc.io->rd(reg, &w))
			return false;
		if ((w >> bit & 1u) == (want ? 1u : 0u))
			continue;
		w = want ? w | 1u << bit : w & ~(1u << bit);
		if (!fwc.io->wr(reg, w))
			return false;
	}

	return true;
}

static bool fwc_cm_call(const int *mag, char *err, size_t en)
{
	uint32_t blk[FWC_SHM_CM_WORDS], args[2];
	unsigned int e;

	memset(blk, 0, sizeof(blk));
	for (e = 0; e < FWC_CM_N; e++)
		blk[e] = (uint32_t)mag[e];
	if (!fwc_slot_put(FWC_SHM_CM, blk, FWC_SHM_CM_WORDS, FWC_MARK_CM)) {
		snprintf(err, en, "/dev/mem: the slot at %#x cannot be written", fwc.shm + FWC_SHM_CM);
		return false;
	}
	args[0] = fwc.shm + FWC_SHM_CM;
	args[1] = FWC_CM_AXES;

	return fwc.io->call(FWC_RPC_CM, args, 2, err, en);
}

/*
 * Make the registers hold what is wanted. `repair`: the firmware may have changed
 * registers behind the back of its own cache, so the entries that are off are sent
 * one off first (else it would find nothing different and write nothing).
 */
static bool fwc_cm_send(bool repair, char *msg, size_t n)
{
	int mag[FWC_CM_N], off = 0, bad;
	unsigned int e, ms;
	char err[160];

	fwc.cm_applied = false;
	if (!fwc_probe()) {
		snprintf(msg, n, "%s", fwc.why);
		return false;
	}
	if (!fwc_slot_free(FWC_SHM_CM, FWC_SHM_CM_WORDS, FWC_MARK_CM, err, sizeof(err)) ||
	    !fwc_base_ensure(err, sizeof(err))) {
		snprintf(msg, n, "%s", err);
		return false;
	}
	if (!fwc_cm_signs()) {
		snprintf(msg, n, "/dev/mem: the sign bits cannot be written");
		return false;
	}
	for (e = 0; e < FWC_CM_N; e++) {
		int eff = fwc_cm_eff(e), m;
		bool neg;

		mag[e] = eff < 0 ? -eff : eff;
		if (repair && fwc_cm_read(e, &m, &neg) && m != mag[e]) {
			off++;
			mag[e] = mag[e] == FWC_CM_MAX ? FWC_CM_MAX - 1 : mag[e] + 1;
		}
	}
	if (off && !fwc_cm_call(mag, err, sizeof(err))) {	/* the nudge: the cache now differs from what comes next */
		snprintf(msg, n, "%s", err);
		return false;
	}
	for (e = 0; e < FWC_CM_N; e++) {
		int eff = fwc_cm_eff(e);

		mag[e] = eff < 0 ? -eff : eff;
	}
	if (!fwc_cm_call(mag, err, sizeof(err))) {
		snprintf(msg, n, "%s", err);
		return false;
	}
	fwc.sends_cm++;
	for (ms = 0;; ms += 20) {
		bad = fwc_cm_off();
		if (bad <= 0 || ms >= FWC_VERIFY_MS)
			break;
		fwc_sleep_ms(20);
	}
	snprintf(fwc.last, sizeof(fwc.last), "colour management, %d entries off after %u ms", bad < 0 ? 0 : bad, ms);
	if (bad < 0) {
		snprintf(msg, n, "sent, the registers cannot be read back");
		fwc.cm_applied = true;
		return true;
	}
	if (bad) {
		snprintf(msg, n, "sent, but %d of %d entries differ from the values after %u ms", bad, FWC_CM_N, ms);
		return false;
	}
	snprintf(msg, n, "registers read back, %u ms", ms);
	fwc.cm_applied = true;

	return true;
}

/* ---- names ---- */

/* the index of a name: 0..5 white balance, 6.. colour management entries; -1: not ours */
int fwc_key(const char *name)
{
	char key[48], w[48];
	unsigned int i;
	size_t j;

	for (j = 0; name[j] && j + 1 < sizeof(w); j++)
		w[j] = (char)tolower((unsigned char)name[j]) == '-' ? '_' : (char)tolower((unsigned char)name[j]);
	w[j] = '\0';
	for (i = 0; i < FWC_WB_N; i++)
		if (!strcmp(w, fwc_wb_name[i]))
			return (int)i;
	for (i = 0; i < FWC_CM_N; i++) {
		snprintf(key, sizeof(key), "cm_%s_%s", fwc_cm_axis[i / 3], fwc_cm_comp[i % 3]);
		if (!strcmp(w, key))
			return FWC_WB_N + (int)i;
		if (i % 3 == 1) {		/* "saturation" as well as "sat" */
			snprintf(key, sizeof(key), "cm_%s_saturation", fwc_cm_axis[i / 3]);
			if (!strcmp(w, key))
				return FWC_WB_N + (int)i;
		}
	}

	return -1;
}

static int fwc_axis(const char *name)
{
	unsigned int a;

	for (a = 0; a < FWC_CM_AXES; a++)
		if (!strcasecmp(name, fwc_cm_axis[a]))
			return (int)a;
	if (!strcasecmp(name, "yellow-green"))
		return 4;
	if (!strcasecmp(name, "blue-purple"))
		return 8;
	if (!strcasecmp(name, "skin"))
		return 2;
	if (!strcasecmp(name, "magenta"))
		return 9;
	if (name[0] >= '0' && name[0] <= '9' && atoi(name) < FWC_CM_AXES)
		return atoi(name);

	return -1;
}

/* "ctl set NAME VALUE" for a name of ours; the whole answer. A value is kept when the call went out, even if the
 * registers did not follow (the next send brings them); when nothing went out the old value stays. */
void fwc_set(struct reply *r, int idx, const char *value)
{
	char *end, msg[200], nm[48];
	long x = strtol(value, &end, 0);
	unsigned int sent;
	int old;
	bool ok;

	if (*end || end == value) {
		reply_fail(r, "\"%s\" is not a number", value);
		return;
	}
	if (idx < FWC_WB_N) {
		snprintf(nm, sizeof(nm), "%s", fwc_wb_name[idx]);
		if (x < 0 || x > FWC_WB_MAX) {
			reply_fail(r, "%s: %ld is outside 0..%d", nm, x, FWC_WB_MAX);
			return;
		}
		old = fwc.wb[idx];
		fwc.wb[idx] = (int)x;
		sent = fwc.sends_wb;
		ok = fwc_wb_send(msg, sizeof(msg));
		if (!ok && fwc.sends_wb == sent)
			fwc.wb[idx] = old;
	} else {
		idx -= FWC_WB_N;
		snprintf(nm, sizeof(nm), "cm_%s_%s", fwc_cm_axis[idx / 3], fwc_cm_comp[idx % 3]);
		if (x < -FWC_CM_MAX || x > FWC_CM_MAX) {
			reply_fail(r, "%s: %ld is outside -%d..%d", nm, x, FWC_CM_MAX, FWC_CM_MAX);
			return;
		}
		old = fwc.cm[idx];
		fwc.cm[idx] = (int)x;
		sent = fwc.sends_cm;
		ok = fwc_cm_send(false, msg, sizeof(msg));
		if (!ok && fwc.sends_cm == sent)
			fwc.cm[idx] = old;
	}
	if (ok)
		reply_add(r, "ok %s = %ld (%s)\n", nm, x, msg);
	else
		reply_fail(r, "%s = %ld: %s", nm, x, msg);
}

void fwc_get(struct reply *r, int idx)
{
	if (idx < FWC_WB_N)
		reply_add(r, "ok %s = %d\n", fwc_wb_name[idx], fwc.wb[idx]);
	else
		reply_add(r, "ok cm_%s_%s = %d\n", fwc_cm_axis[(idx - FWC_WB_N) / 3], fwc_cm_comp[(idx - FWC_WB_N) % 3],
			  fwc.cm[idx - FWC_WB_N]);
}

/*
 * "wb": show; "wb R G B RO GO BO": all six at once, one call; "wb reset": all 512.
 * One command for the settings page, whose two sliders move three gains together.
 */
void cmd_wb(struct reply *r, char **arg, unsigned int n)
{
	int v[FWC_WB_N], old[FWC_WB_N];
	char msg[200], t[64];
	unsigned int i, sent;
	bool ok;

	if (n == 0) {
		fwc_wb_text(t, sizeof(t));
		if (!fwc_probe())	/* "ok", not an error: the numbers are shown, and the page knows to hide itself */
			reply_add(r, "ok wb %s [not available: %s]\n", t, fwc.why);
		else
			reply_add(r, "ok wb %s -- R G B gain, R G B offset; 512 is neutral%s\n", t,
				  fwc.wb_applied ? " [on the registers]" : fwc_wb_neutral() ? "" : " [not applied]");
		return;
	}
	if (n == 1 && (!strcmp(arg[0], "reset") || !strcmp(arg[0], "neutral"))) {
		for (i = 0; i < FWC_WB_N; i++)
			v[i] = FWC_WB_NEUTRAL;
	} else if (n == FWC_WB_N) {
		for (i = 0; i < FWC_WB_N; i++) {
			char *end;
			long x = strtol(arg[i], &end, 0);

			if (*end || end == arg[i] || x < 0 || x > FWC_WB_MAX) {
				reply_fail(r, "wb: \"%s\" is not a number in 0..%d", arg[i], FWC_WB_MAX);
				return;
			}
			v[i] = (int)x;
		}
	} else {
		reply_fail(r, "wb needs six numbers (R G B gain, R G B offset, 0..%d, 512 neutral), or reset", FWC_WB_MAX);
		return;
	}
	memcpy(old, fwc.wb, sizeof(old));
	memcpy(fwc.wb, v, sizeof(v));
	sent = fwc.sends_wb;
	ok = fwc_wb_send(msg, sizeof(msg));
	if (!ok && fwc.sends_wb == sent)
		memcpy(fwc.wb, old, sizeof(old));
	fwc_wb_text(t, sizeof(t));
	if (ok)
		reply_add(r, "ok wb %s (%s)\n", t, msg);
	else
		reply_fail(r, "wb %s: %s", t, msg);
}

/*
 * "cm": the entries that are not neutral; "cm AXIS": one axis; "cm AXIS H S V": the three of an axis at once (one
 * call); "cm reset": all neutral. AXIS is a name (red lips skintone yellow yellow_green green cyan blue blue_purple
 * purple) or its number.
 */
void cmd_cm(struct reply *r, char **arg, unsigned int n)
{
	char msg[200];
	int a, v[3], old[3];
	unsigned int e, k, sent;
	bool ok;

	if (n == 0) {
		unsigned int shown = 0;

		for (e = 0; e < FWC_CM_N; e++)
			if (fwc.cm[e]) {
				if (!shown++)
					reply_add(r, "ok cm\n");
				reply_add(r, "  cm_%s_%s = %d\n", fwc_cm_axis[e / 3], fwc_cm_comp[e % 3], fwc.cm[e]);
			}
		if (!shown)
			reply_add(r, "ok cm all neutral (0 = as the picture mode has it)\n");
		return;
	}
	if (n == 1 && (!strcmp(arg[0], "reset") || !strcmp(arg[0], "neutral"))) {
		int keep[FWC_CM_N];

		memcpy(keep, fwc.cm, sizeof(keep));
		memset(fwc.cm, 0, sizeof(fwc.cm));
		if (!fwc.cm_base_ok && !fwc_cm_any() && !fwc_base_load()) {
			reply_add(r, "ok cm all neutral (nothing was changed since the start)\n");
			return;
		}
		sent = fwc.sends_cm;
		ok = fwc_cm_send(true, msg, sizeof(msg));
		if (!ok && fwc.sends_cm == sent)
			memcpy(fwc.cm, keep, sizeof(keep));
		if (ok)
			reply_add(r, "ok cm all neutral (%s)\n", msg);
		else
			reply_fail(r, "cm reset: %s", msg);
		return;
	}
	a = fwc_axis(arg[0]);
	if (a < 0) {
		reply_fail(r, "cm: no axis \"%s\" (red lips skintone yellow yellow_green green cyan blue blue_purple purple)", arg[0]);
		return;
	}
	if (n == 1) {
		reply_add(r, "ok cm %s hue %d sat %d value %d\n", fwc_cm_axis[a], fwc.cm[3 * a], fwc.cm[3 * a + 1],
			  fwc.cm[3 * a + 2]);
		return;
	}
	if (n != 4) {
		reply_fail(r, "cm AXIS needs hue, saturation and value (-%d..%d, 0 neutral)", FWC_CM_MAX, FWC_CM_MAX);
		return;
	}
	for (k = 0; k < 3; k++) {
		char *end;
		long x = strtol(arg[1 + k], &end, 0);

		if (*end || end == arg[1 + k] || x < -FWC_CM_MAX || x > FWC_CM_MAX) {
			reply_fail(r, "cm: \"%s\" is not a number in -%d..%d", arg[1 + k], FWC_CM_MAX, FWC_CM_MAX);
			return;
		}
		v[k] = (int)x;
	}
	for (k = 0; k < 3; k++) {
		old[k] = fwc.cm[3 * a + k];
		fwc.cm[3 * a + k] = v[k];
	}
	sent = fwc.sends_cm;
	ok = fwc_cm_send(false, msg, sizeof(msg));
	if (!ok && fwc.sends_cm == sent)
		for (k = 0; k < 3; k++)
			fwc.cm[3 * a + k] = old[k];
	if (!ok) {
		reply_fail(r, "cm %s: %s", fwc_cm_axis[a], msg);
	} else {
		reply_add(r, "ok cm %s hue %d sat %d value %d (%s)\n", fwc_cm_axis[a], v[0], v[1], v[2], msg);
	}
}

/*
 * A picture mode writes the firmware's own colour management values again, all of them and different ones for each mode
 * (measured 18.10.2026: standard to cinema changes 17 of the 36 entries). The base of "a step on the firmware's own value"
 * is therefore the base of the mode in force. So before a mode is sent the steps are taken off (the registers hold the old
 * base), and after it the registers are read as the new base and the steps are laid on again. Nothing of this happens
 * as long as no step was ever used: then the mode's own values are simply what shows.
 */
void fwc_mode_begin(void)
{
	int keep[FWC_CM_N];
	char msg[200];

	fwc.mode_open = false;
	if (!fwc.cm_base_ok && !fwc_base_load())
		return;
	if (!fwc_probe())
		return;
	memcpy(keep, fwc.cm, sizeof(keep));
	memset(fwc.cm, 0, sizeof(fwc.cm));
	if (fwc_cm_off() != 0 && !fwc_cm_send(true, msg, sizeof(msg)))
		warn("colour          before a picture mode: %s", msg);
	memcpy(fwc.cm, keep, sizeof(keep));
	fwc.mode_open = true;
}

/* a reason for "not available" is said once, not at every source change */
static void fwc_complain(const char *why, const char *what)
{
	static char said[200];

	if (!strcmp(said, what))
		return;
	snprintf(said, sizeof(said), "%s", what);
	warn("colour          after %s: %s", why, what);
}

/*
 * After the start, a "ctl resync", a picture mode or a source change: do the registers still hold what is wanted?
 * If not, send again. Reading six and thirty-six fields costs nothing; a send costs a call (~120 ms). Nothing is
 * asked of the firmware while everything is neutral and nothing was ever changed (except at the start, where the
 * white balance registers are looked at once: a restart of this program must not leave an old, unsaved setting standing).
 */
void fwc_sync(const char *why)
{
	bool start = !strcmp(why, "the start");
	bool wb_held = !fwc_wb_neutral() || fwc.sends_wb;
	bool cm_held = fwc_cm_any() || fwc.cm_base_ok || fwc_base_load();
	char msg[200];
	int bad;

	if (!start && !wb_held && !cm_held)
		return;
	if (!fwc_probe()) {
		if (wb_held || cm_held)
			fwc_complain(why, fwc.why);
		else if (start)
			info("colour          not available (%s) -- white balance and colour management are not offered", fwc.why);
		return;
	}
	bad = fwc_wb_off();
	if (bad > 0 || (bad < 0 && !fwc_wb_neutral())) {
		fwc.repairs++;
		if (fwc_wb_send(msg, sizeof(msg)))
			info("colour          white balance sent after %s: %d of 6 registers were off (%s)", why, bad < 0 ? 6 : bad, msg);
		else
			warn("colour          white balance after %s: %s", why, msg);
	} else if (bad == 0) {
		fwc.wb_applied = true;
	}
	if (cm_held) {
		if (!fwc_base_ensure(msg, sizeof(msg))) {
			warn("colour          colour management after %s: %s", why, msg);
			return;
		}
		bad = fwc_cm_off();
		if (bad > 0 || (bad < 0 && fwc_cm_any())) {
			fwc.repairs++;
			if (fwc_cm_send(true, msg, sizeof(msg)))
				info("colour          colour management sent after %s: %d of %d entries were off (%s)", why,
				     bad < 0 ? FWC_CM_N : bad, FWC_CM_N, msg);
			else
				warn("colour          colour management after %s: %s", why, msg);
		} else if (bad == 0) {
			fwc.cm_applied = true;
		}
	}
}

void fwc_mode_end(const char *why)
{
	char msg[200];

	if (fwc.mode_open) {
		fwc.mode_open = false;
		/* the registers hold the new mode's own values: that is the base now */
		if (!fwc_base_take(msg, sizeof(msg)))
			warn("colour          after %s: %s", why, msg);
	}
	fwc_sync(why);
}

/* status: one line each, from what is held (no hardware read) */
void fwc_status(struct reply *r)
{
	char t[64];
	unsigned int e, n = 0;

	for (e = 0; e < FWC_CM_N; e++)
		n += fwc.cm[e] != 0;
	fwc_wb_text(t, sizeof(t));
	reply_add(r, "white balance   %s (R G B gain, R G B offset; 512 neutral)%s\n", t,
		  fwc.wb_applied ? ", on the registers" : fwc_wb_neutral() ? "" : ", NOT applied");
	reply_add(r, "colour mgmt     %u entr%s changed%s\n", n, n == 1 ? "y" : "ies",
		  fwc.cm_applied ? ", on the registers" : n ? ", NOT applied" : "");
	if (!fwc.ok && fwc.why[0])
		reply_add(r, "                not available: %s\n", fwc.why);
	if (fwc.sends_wb || fwc.sends_cm)
		reply_add(r, "                sent %u white balance, %u colour management, %u repairs; last: %s\n", fwc.sends_wb,
			  fwc.sends_cm, fwc.repairs, fwc.last);
}

void fwc_init(void)
{
	unsigned int i;

	for (i = 0; i < FWC_WB_N; i++)
		fwc.wb[i] = FWC_WB_NEUTRAL;
	memset(fwc.cm, 0, sizeof(fwc.cm));
}

/* what the kept values (the file "werte") say, taken over at the start; have[] marks the ones the file named */
void fwc_adopt(const bool *wb_have, const int *wb, const bool *cm_have, const int *cm)
{
	unsigned int i;

	for (i = 0; i < FWC_WB_N; i++)
		if (wb_have[i])
			fwc.wb[i] = wb[i];
	for (i = 0; i < FWC_CM_N; i++)
		if (cm_have[i])
			fwc.cm[i] = cm[i];
	if (!fwc_wb_neutral() || fwc_cm_any()) {
		char t[64];
		unsigned int n = 0;

		fwc_wb_text(t, sizeof(t));
		for (i = 0; i < FWC_CM_N; i++)
			n += fwc.cm[i] != 0;
		info("saved           colour: white balance %s, colour management %u entr%s changed", t, n, n == 1 ? "y" : "ies");
	}
}

/* "KEY = VALUE" of the file "werte": 0 not ours, 1 taken (value in *out, entry in *idx), -1 ours but out of range */
int fwc_parse_kept(const char *key, long x, int *idx, int *out)
{
	int k = fwc_key(key);

	if (k < 0)
		return 0;
	if (k < FWC_WB_N ? (x < 0 || x > FWC_WB_MAX) : (x < -FWC_CM_MAX || x > FWC_CM_MAX))
		return -1;
	*idx = k;
	*out = (int)x;

	return 1;
}

/* the lines "ctl save" adds to the file: the six white balance values always, the colour entries that are not 0 */
size_t fwc_kept_lines(FILE *f, char *msg, size_t n, size_t l)
{
	unsigned int i;

	for (i = 0; i < FWC_WB_N; i++)
		fprintf(f, "%-11s = %d\n", fwc_wb_name[i], fwc.wb[i]);
	for (i = 0; i < FWC_CM_N; i++)
		if (fwc.cm[i])
			fprintf(f, "cm_%s_%s = %d\n", fwc_cm_axis[i / 3], fwc_cm_comp[i % 3], fwc.cm[i]);
	if (l + 1 < n) {
		char t[64];

		fwc_wb_text(t, sizeof(t));
		l += (size_t)snprintf(msg + l, n - l, " wb=%s", t);
		for (i = 0; i < FWC_CM_N; i++)
			if (fwc.cm[i] && l + 1 < n)
				l += (size_t)snprintf(msg + l, n - l, " cm_%s_%s=%d", fwc_cm_axis[i / 3], fwc_cm_comp[i % 3],
						      fwc.cm[i]);
	}

	return l;
}

/* "ctl list": the firmware's own controls, after the capture driver's */
void fwc_list(struct reply *r)
{
	for (unsigned int i = 0; i < FWC_WB_N; i++)
		reply_add(r, "  %-26s %d  (0..%d)\n", fwc_wb_name[i], fwc.wb[i], FWC_WB_MAX);
	reply_add(r, "  cm_AXIS_hue|sat|value      colour management, -%d..%d, 0 neutral (ctl cm)\n", FWC_CM_MAX, FWC_CM_MAX);
}
