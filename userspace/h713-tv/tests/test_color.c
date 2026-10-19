/* SPDX-License-Identifier: GPL-2.0 */
/*
 * h713-tv's white balance and colour management, on the host: main.c and color.c are compiled into this file and
 * the machinery that reaches the hardware (/dev/mem, /dev/cpu_comm, the board file) is replaced by a made-up display
 * firmware that does what the real one was measured to do (BERICHT of the media side project, parts 1 and 2):
 *
 *   SetWhiteBalance      one word, the block of six; every word that is not 0xFFFF goes through the curve of
 *                        pq_custom.TSE into its register field
 *   SetColorManagement   two words, the block and the number of axes; only the entries that differ from the firmware's
 *                        cache are written, as 8-bit magnitudes into their fields
 *
 * What is checked: the numbers the registers get for a wanted value (the 0x8cc of the wall test), that all six
 * white balance words are sent every time and none is 0xFFFF, that the colour management is a step on the firmware's
 * own value (and 0 gives it back, sign bit included), that the firmware's own values survive a restart of the program,
 * that a firmware that forgot is told again (and that its cache would have hidden it), that nothing is written
 * outside the two slots and the sign bits, that a slot that is somebody's is left alone, that a firmware this was not
 * written for is not touched, and the file "werte" (save, read, a bad line).
 *
 *   test_color      exit 0 when every case passed
 */
#define main h713_tv_main
#include "../main.c"
#undef main
#include "../color.c"

static int failed;

static void check(bool ok, const char *what)
{
	printf("%s %s\n", ok ? "ok  " : "FAIL", what);
	if (!ok)
		failed++;
}

/* ---- the made-up machine: a sparse memory of 32-bit words, and a firmware behind two calls ---- */

static char base_file[] = "/tmp/h713-tv-test-color-XXXXXX";

#define MEM_MAX 4096
static struct { uint32_t a, v; } mem[MEM_MAX];
static unsigned int nmem;
static struct { uint32_t a, v; } wlog[MEM_MAX];	/* every write by the program */
static unsigned int nwlog;
static unsigned int calls_wb, calls_cm;
static uint32_t last_wb_block[8];
static uint32_t last_cm_args[2];
static bool all_six_ok = true;		/* no white balance block ever carried 0xFFFF */
static uint32_t fw_cache[FWC_CM_N];	/* the firmware's cache of what it wrote */
static bool fail_call;			/* the call itself fails */
static bool no_region;

static uint32_t *slot(uint32_t a)
{
	unsigned int i;

	for (i = 0; i < nmem; i++)
		if (mem[i].a == a)
			return &mem[i].v;
	mem[nmem].a = a;
	mem[nmem].v = 0;

	return &mem[nmem++].v;
}

static void put(uint32_t a, uint32_t v)
{
	*slot(a) = v;
}

static uint32_t get(uint32_t a)
{
	return *slot(a);
}

static void put_field(uint32_t reg, unsigned int sh, uint32_t v)
{
	put(reg, (get(reg) & ~(0xfffu << sh)) | (v & 0xfffu) << sh);
}

static void put_text(uint32_t a, const char *s)
{
	size_t i;

	for (i = 0; i <= strlen(s); i++) {
		uint32_t w = get((a + (uint32_t)i) & ~3u), sh = 8 * ((a + (uint32_t)i) & 3);

		put((a + (uint32_t)i) & ~3u, (w & ~(0xffu << sh)) | (uint32_t)(unsigned char)s[i] << sh);
	}
}

/* what the board holds in the colour registers before anybody changes them */
static const int cm_default[FWC_CM_N] = {
	147, 0, 0,	/* red: hue 147 (a value the board's TSE puts there) */
	0, 0, 0,
	0, 0, 0,
	0, 90, 0,	/* yellow: saturation 90 */
	0, 0, 0,  0, 0, 0,  0, 0, 0,  0, 0, 0,  0, 0, 0,  0, 0, 0,  0, 0, 0,  0, 0, 0,
};

static void put_cm_regs(void)
{
	unsigned int e;

	for (e = 0; e < FWC_CM_N; e++) {
		uint32_t reg;
		unsigned int sh;

		fwc_cm_field(e, &reg, &sh);
		put(reg, (get(reg) & ~(0xffu << sh)) | (uint32_t)cm_default[e] << sh);
	}
	put(FWC_REG_CM_FLAGS, 0x60626161u);	/* the bits the board has: none of the sign bits of the yellow axis */
	put(FWC_REG_CM_FLAGS + 4, 0x60626060u);
	put(FWC_REG_CM_FLAGS + 8, 0x60606060u);
}

/* the picture mode's own colour values (the vendor's per-mode script): the board's table for standard, another for cinema */
static int cm_cinema[FWC_CM_N];

static void make_cinema(void)
{
	unsigned int e;

	for (e = 0; e < FWC_CM_N; e++)
		cm_cinema[e] = cm_default[e];
	cm_cinema[0] = 150;		/* red hue */
	cm_cinema[1] = 20;		/* red saturation */
	cm_cinema[9] = 10;		/* yellow hue */
	cm_cinema[10] = 70;		/* yellow saturation */
	cm_cinema[19] = 44;		/* cyan saturation */
	cm_cinema[32] = 3;		/* an entry that standard has at 0 */
}

static int regs_seen_by_script[FWC_CM_N];	/* what the registers held when the script ran */

/* SetPictureMode: the script writes the magnitudes of all 36 entries (not the signs, not the firmware's cache) */
static void firmware_mode(const int *table)
{
	unsigned int e;

	for (e = 0; e < FWC_CM_N; e++) {
		uint32_t reg;
		unsigned int sh;

		fwc_cm_field(e, &reg, &sh);
		regs_seen_by_script[e] = (int)(get(reg) >> sh & 0xff);
		put(reg, (get(reg) & ~(0xffu << sh)) | (uint32_t)table[e] << sh);
	}
}

static void machine_reset(void)
{
	unsigned int i;

	memset(mem, 0, sizeof(mem));
	nmem = nwlog = 0;
	calls_wb = calls_cm = 0;
	all_six_ok = true;
	fail_call = no_region = false;
	memset(fw_cache, 0, sizeof(fw_cache));
	unlink(base_file);	/* the firmware's own values of the last run are not this machine's */
	put(FWC_SHM_BASE + FWC_SHM_MAGIC1, FWC_SHM_MAGIC);
	put(FWC_SHM_BASE + FWC_SHM_MAGIC2, FWC_SHM_MAGIC);
	put(FWC_SHM_BASE + FWC_SMM_HEAD + 4 * 47, FWC_SHM_BASE + FWC_SMM_HEAD);	/* the HY310 18.10.2026: break at +0x33000 */
	put(FWC_SHM_BASE + FWC_SMM_HEAD + 4 * 45, 0x6000);
	for (i = 0; i < sizeof(fwc_sig) / sizeof(fwc_sig[0]); i++)
		put_text(fwc_sig[i].phys, fwc_sig[i].text);
	put(FWC_REG_WB_D4, 0);
	put(FWC_REG_WB_D8, 0);
	put(FWC_REG_WB_DC, 0x08000800);
	put(FWC_REG_WB_E0, 0x08000000);
	put_cm_regs();
}

/* the firmware forgets what it was told (a restart of the display, a picture mode's script): registers back, cache stays */
static void firmware_forgets(void)
{
	put(FWC_REG_WB_D4, 0);
	put(FWC_REG_WB_D8, 0);
	put(FWC_REG_WB_DC, 0x08000800);
	put(FWC_REG_WB_E0, 0x08000000);
	put_cm_regs();
}

static bool m_rd(uint32_t phys, uint32_t *v)
{
	*v = get(phys);
	return true;
}

static bool m_wr(uint32_t phys, uint32_t v)
{
	wlog[nwlog].a = phys;
	wlog[nwlog++].v = v;
	put(phys, v);
	return true;
}

static bool m_call(uint32_t id, const uint32_t *args, unsigned int n, char *err, size_t en)
{
	unsigned int i;

	if (fail_call) {
		snprintf(err, en, "RPC %#x: Connection timed out", id);
		return false;
	}
	if (id == FWC_RPC_WB && n == 1) {
		calls_wb++;
		for (i = 0; i < 8; i++)
			last_wb_block[i] = get(args[0] + 4 * i);
		for (i = 0; i < FWC_WB_N; i++) {
			uint32_t reg;
			unsigned int sh;

			all_six_ok &= last_wb_block[i] != 0xFFFF;
			if (last_wb_block[i] == 0xFFFF)
				continue;
			fwc_wb_field(i, &reg, &sh);
			put_field(reg, sh, fwc_wb_expect(i, (int)last_wb_block[i]));
		}
		return true;
	}
	if (id == FWC_RPC_CM && n == 2) {
		calls_cm++;
		last_cm_args[0] = args[0];
		last_cm_args[1] = args[1];
		for (i = 0; i < FWC_CM_N; i++) {
			uint32_t v = get(args[0] + 4 * i), reg;
			unsigned int sh;

			if (v == fw_cache[i])
				continue;		/* the firmware writes only what differs from its cache */
			fw_cache[i] = v;
			fwc_cm_field(i, &reg, &sh);
			put(reg, (get(reg) & ~(0xffu << sh)) | (v & 0xff) << sh);
		}
		return true;
	}
	snprintf(err, en, "unknown call %#x", id);
	return false;
}

static bool m_region(uint32_t *base, uint32_t *size)
{
	if (no_region)
		return false;
	*base = FWC_SHM_BASE;
	*size = FWC_SHM_SIZE;
	return true;
}

static const struct fwc_io fake = { .rd = m_rd, .wr = m_wr, .call = m_call, .region = m_region };

/* a new run of the program on the same machine: the program's state is gone, the machine's and the base file stay */
static void program_starts(void)
{
	memset(&fwc, 0, sizeof(fwc));
	fwc.memfd = -1;
	fwc.io = &fake;
	fwc.base_path = base_file;
	fwc_init();
}

static void reply_clear(struct reply *r)
{
	r->len = 0;
	r->failed = false;
	r->buf[0] = '\0';
}

static int cm_mag(unsigned int e)
{
	uint32_t reg;
	unsigned int sh;

	fwc_cm_field(e, &reg, &sh);
	return (int)(get(reg) >> sh & 0xff);
}

static bool cm_neg(unsigned int e)
{
	uint32_t reg;
	unsigned int bit;

	fwc_cm_sign(e, &reg, &bit);
	return get(reg) >> bit & 1;
}

static bool regs_are_stock(void)
{
	return get(FWC_REG_WB_D4) == 0 && get(FWC_REG_WB_D8) == 0 && get(FWC_REG_WB_DC) == 0x08000800 &&
	       get(FWC_REG_WB_E0) == 0x08000000;
}

/* every magnitude and every flag word as the board had them (the board has sign bits set on entries of 0, too) */
static bool cm_is_default(void)
{
	unsigned int e;
	bool ok = true;

	for (e = 0; e < FWC_CM_N; e++)
		ok &= cm_mag(e) == cm_default[e];

	return ok && get(FWC_REG_CM_FLAGS) == 0x60626161u && get(FWC_REG_CM_FLAGS + 4) == 0x60626060u &&
	       get(FWC_REG_CM_FLAGS + 8) == 0x60606060u;
}

/* every write the program made lies in a slot or is a sign bit word */
static bool writes_only_in_slots(void)
{
	unsigned int i;

	for (i = 0; i < nwlog; i++) {
		uint32_t a = wlog[i].a;
		bool in_wb = a >= FWC_SHM_BASE + FWC_SHM_WB && a < FWC_SHM_BASE + FWC_SHM_WB + 4 * FWC_SHM_WB_WORDS;
		bool in_cm = a >= FWC_SHM_BASE + FWC_SHM_CM && a < FWC_SHM_BASE + FWC_SHM_CM + 4 * FWC_SHM_CM_WORDS;
		bool flags = a >= FWC_REG_CM_FLAGS && a < FWC_REG_CM_FLAGS + 12;

		if (!in_wb && !in_cm && !flags)
			return false;
	}

	return true;
}

int main(void)
{
	struct reply r;
	char *args[6];
	struct saved_values sv;
	unsigned int repairs0;
	int fd = mkstemp(base_file);

	if (fd < 0) {
		perror("mkstemp");
		return 1;
	}
	close(fd);
	unlink(base_file);	/* the test's own file, made above; the program creates it again when it needs it */

	/* ---- the numbers ---- */
	check(fwc_wb_expect(0, 512) == 0x800 && fwc_wb_expect(1, 512) == 0x800 && fwc_wb_expect(2, 512) == 0x800,
	      "gain 512 is 1.0: 0x800");
	check(fwc_wb_expect(1, 563) == 0x8cc, "G gain 563 is 0x8cc (the value of the wall test)");
	check(fwc_wb_expect(0, 480) == 0x780 && fwc_wb_expect(0, 256) == 0x400 && fwc_wb_expect(0, 0) == 0,
	      "gain below 512 is 4 x the value");
	check(fwc_wb_expect(2, 1023) == 0xfff, "gain 1023 is the top: 0xfff");
	check(fwc_wb_expect(3, 512) == 0 && fwc_wb_expect(4, 0) == 0x800 && fwc_wb_expect(5, 1023) == 0x7ff,
	      "offset 512 is 0, 0 is -2048 (0x800), 1023 is 2047");
	check(fwc_key("wb_r_gain") == 0 && fwc_key("WB_B_OFFSET") == 5 && fwc_key("cm_red_hue") == FWC_WB_N &&
	      fwc_key("cm_yellow_sat") == FWC_WB_N + 3 * 3 + 1 && fwc_key("cm_yellow_saturation") == FWC_WB_N + 3 * 3 + 1 &&
	      fwc_key("cm_yellow_green_value") == FWC_WB_N + 3 * 4 + 2 && fwc_key("cm_blue_purple_hue") == FWC_WB_N + 3 * 8,
	      "the names find their entries, also the two-word axes");
	check(fwc_key("brightness") < 0 && fwc_key("cm_yellow") < 0 && fwc_key("cm_yellow_gain") < 0 && fwc_key("wb_gain") < 0,
	      "other names (the V4L2 controls) are not ours");
	check(fwc_axis("yellow") == 3 && fwc_axis("yellow-green") == 4 && fwc_axis("9") == 9 && fwc_axis("magenta") == 9 &&
	      fwc_axis("pink") < 0, "axes by name and number");
	{
		uint32_t reg;
		unsigned int sh, bit;

		fwc_cm_field(3 * 3, &reg, &sh);
		check(reg == 0x0514035c && sh == 16, "yellow hue is 0x0514035c[23:16]");
		fwc_cm_field(3 * 3 + 1, &reg, &sh);
		check(reg == 0x05140360 && sh == 24, "yellow saturation is 0x05140360[31:24]");
		fwc_cm_field(3 * 11 + 2, &reg, &sh);
		check(reg == 0x05140430 && sh == 16, "the last entry is 0x05140430[23:16]");
		fwc_cm_sign(3 * 3, &reg, &bit);
		check(reg == 0x05140300 && bit == 1, "the sign of yellow hue is bit 1 of 0x05140300");
		fwc_cm_sign(3 * 0 + 2, &reg, &bit);
		check(reg == 0x05140300 && bit == 27, "the sign of red value is bit 27 (the first axis is the top byte)");
		fwc_cm_sign(3 * 9 + 1, &reg, &bit);
		check(reg == 0x05140308 && bit == 18, "the sign of purple saturation is bit 18 of the third word");
	}

	/* ---- white balance ---- */
	machine_reset();
	program_starts();
	reply_clear(&r);
	fwc_set(&r, fwc_key("wb_g_gain"), "563");
	check(!r.failed && strstr(r.buf, "ok wb_g_gain = 563") && calls_wb == 1, "set wb_g_gain 563: one call, ok");
	check(last_wb_block[0] == 512 && last_wb_block[1] == 563 && last_wb_block[2] == 512 && last_wb_block[3] == 512 &&
	      last_wb_block[4] == 512 && last_wb_block[5] == 512, "the block holds all six values: the five neutral ones too");
	check(last_wb_block[6] == FWC_MARK_WB && last_wb_block[7] == ~FWC_MARK_WB, "and the mark");
	check((get(FWC_REG_WB_DC) & 0xfff) == 0x8cc && (get(FWC_REG_WB_DC) >> 16 & 0xfff) == 0x800, "the registers: G 0x8cc, R untouched");
	check(fwc.wb_applied, "applied");
	reply_clear(&r);
	args[0] = "480"; args[1] = "492"; args[2] = "512"; args[3] = "512"; args[4] = "512"; args[5] = "512";
	cmd_wb(&r, args, 6);
	check(!r.failed && calls_wb == 2, "wb 480 492 512 ...: one call for six values");
	check((get(FWC_REG_WB_DC) >> 16 & 0xfff) == 0x780 && (get(FWC_REG_WB_DC) & 0xfff) == 0x7b0 &&
	      (get(FWC_REG_WB_E0) >> 16 & 0xfff) == 0x800, "R 0x780, G 0x7b0, B 0x800");
	reply_clear(&r);
	args[0] = "reset";
	cmd_wb(&r, args, 1);
	check(!r.failed && regs_are_stock() && fwc_wb_neutral(), "wb reset: the stock words, all 512");
	check(all_six_ok, "no block ever carried 0xFFFF");
	reply_clear(&r);
	fwc_set(&r, 0, "1024");
	check(r.failed && calls_wb == 3, "1024 is refused without a call");
	reply_clear(&r);
	fwc_set(&r, 0, "-1");
	check(r.failed && calls_wb == 3, "-1 is refused without a call");
	reply_clear(&r);
	fwc_set(&r, 0, "red");
	check(r.failed && calls_wb == 3, "a word is refused without a call");
	reply_clear(&r);
	args[0] = "1"; args[1] = "2";
	cmd_wb(&r, args, 2);
	check(r.failed && calls_wb == 3, "wb with two numbers is refused");
	reply_clear(&r);
	cmd_wb(&r, args, 0);
	check(!r.failed && strstr(r.buf, "ok wb 512 512 512 512 512 512"), "wb alone shows the six");
	check(writes_only_in_slots(), "everything written lies in the two slots");

	/* the hardware cannot be reached: nothing is held that cannot be carried out */
	fail_call = true;
	reply_clear(&r);
	fwc_set(&r, 1, "600");
	check(r.failed && fwc.wb[1] == 512, "a call that does not go out leaves the old value");
	fail_call = false;

	/* a slot that is somebody's */
	machine_reset();
	program_starts();
	put(FWC_SHM_BASE + FWC_SHM_WB + 8, 0x12345678);
	reply_clear(&r);
	fwc_set(&r, 1, "600");
	check(r.failed && strstr(r.buf, "somebody else's") && fwc.wb[1] == 512 && calls_wb == 0 && nwlog == 0,
	      "a slot with foreign words and no mark of ours is not written, no call, the old value stays");
	check(get(FWC_SHM_BASE + FWC_SHM_WB + 8) == 0x12345678, "and the foreign word is still there");
	put(FWC_SHM_BASE + FWC_SHM_WB + 8, 0);
	machine_reset();
	program_starts();
	put(FWC_SHM_BASE + FWC_SHM_CM + 4, 0x1);
	reply_clear(&r);
	fwc_set(&r, fwc_key("cm_yellow_hue"), "20");
	check(r.failed && strstr(r.buf, "somebody else's") && calls_cm == 0 && nwlog == 0 && fwc.cm[9] == 0,
	      "the same for the colour management slot");

	/* the firmware's allocator has grown up to a slot */
	machine_reset();
	program_starts();
	put(FWC_SHM_BASE + FWC_SMM_HEAD + 4 * 45, FWC_SHM_WB - FWC_SMM_HEAD + 0x100);
	reply_clear(&r);
	fwc_set(&r, 1, "600");
	check(r.failed && strstr(r.buf, "grown over the slot") && calls_wb == 0 && nwlog == 0 && fwc.wb[1] == 512,
	      "an allocator whose break is past the slot: not written, no call, the old value stays");
	put(FWC_SHM_BASE + FWC_SMM_HEAD + 4 * 45, FWC_SHM_WB - FWC_SMM_HEAD);
	reply_clear(&r);
	fwc_set(&r, 1, "600");
	check(!r.failed && calls_wb == 1, "a break exactly at the slot leaves it free");
	machine_reset();
	program_starts();
	put(FWC_SHM_BASE + FWC_SMM_HEAD + 4 * 47, 0);
	reply_clear(&r);
	fwc_set(&r, 1, "600");
	check(r.failed && strstr(r.buf, "not where it was read") && calls_wb == 0 && nwlog == 0,
	      "an allocator that is not where it was read: refused");

	/* the backlight PWM block of the receiver is never touched */
	machine_reset();
	program_starts();
	put(FWC_SHM_BASE + 0x37100, 5);
	put(FWC_SHM_BASE + 0x37104, 1);
	reply_clear(&r);
	fwc_set(&r, 1, "600");
	check(!r.failed && get(FWC_SHM_BASE + 0x37100) == 5 && get(FWC_SHM_BASE + 0x37104) == 1,
	      "with the backlight PWM words at +0x37100 in place, they stay");
	args[0] = "yellow"; args[1] = "5"; args[2] = "5"; args[3] = "5";
	cmd_cm(&r, args, 4);
	check(!r.failed && get(FWC_SHM_BASE + 0x37100) == 5 && get(FWC_SHM_BASE + 0x37104) == 1, "... also after a colour management call");

	/* ---- not the firmware this was written for ---- */
	machine_reset();
	program_starts();
	put(fwc_sig[1].phys, 0x58585858);
	reply_clear(&r);
	fwc_set(&r, 1, "563");
	check(r.failed && strstr(r.buf, "not the display firmware") && calls_wb == 0 && nwlog == 0 && fwc.wb[1] == 512,
	      "another firmware: refused, no call, nothing written");
	fwc_sync("the start");
	check(calls_wb == 0 && calls_cm == 0 && nwlog == 0, "and the start does not touch it either");
	machine_reset();
	program_starts();
	put(FWC_SHM_BASE + FWC_SHM_MAGIC2, 0);
	reply_clear(&r);
	fwc_set(&r, 1, "563");
	check(r.failed && strstr(r.buf, "no cpu_comm transport") && calls_wb == 0, "no cpu_comm transport: refused");

	/* ---- colour management: a step on the firmware's own value ---- */
	machine_reset();
	program_starts();
	reply_clear(&r);
	fwc_set(&r, fwc_key("cm_yellow_hue"), "60");
	check(!r.failed && calls_cm == 1 && last_cm_args[1] == FWC_CM_AXES && last_cm_args[0] == FWC_SHM_BASE + FWC_SHM_CM,
	      "cm_yellow_hue 60: one call with the block and 12 axes");
	check(cm_mag(9) == 60 && !cm_neg(9), "yellow hue 60 in the register");
	check(cm_mag(10) == 90 && cm_mag(0) == 147, "the other entries are as the board had them (yellow sat 90, red hue 147)");
	check(get(FWC_SHM_BASE + FWC_SHM_CM + 4 * 10) == 90 && get(FWC_SHM_BASE + FWC_SHM_CM + 4 * 0) == 147,
	      "the block carries the board's own values for what was not touched");
	check(fwc.cm_base_ok && fwc.cm_base[10] == 90, "the firmware's own values were read first");
	reply_clear(&r);
	fwc_set(&r, fwc_key("cm_yellow_sat"), "10");
	check(!r.failed && cm_mag(10) == 100, "yellow saturation +10 on 90 is 100");
	reply_clear(&r);
	fwc_set(&r, fwc_key("cm_yellow_sat"), "-20");
	check(!r.failed && cm_mag(10) == 70 && !cm_neg(10), "-20 on 90 is 70, no sign");
	reply_clear(&r);
	fwc_set(&r, fwc_key("cm_yellow_sat"), "-100");
	check(!r.failed && cm_mag(10) == 10 && cm_neg(10), "-100 on 90 is -10: magnitude 10 and the sign bit");
	reply_clear(&r);
	fwc_set(&r, fwc_key("cm_yellow_hue"), "-60");
	check(!r.failed && cm_mag(9) == 60 && cm_neg(9), "hue -60 on 0: magnitude 60, sign bit set");
	reply_clear(&r);
	fwc_set(&r, fwc_key("cm_yellow_hue"), "60");
	check(!r.failed && cm_mag(9) == 60 && !cm_neg(9), "and back to +60: the sign bit is cleared again");
	reply_clear(&r);
	fwc_set(&r, fwc_key("cm_red_hue"), "255");
	check(!r.failed && cm_mag(0) == 255 && !cm_neg(0), "red hue +255 on 147 clamps to 255");
	reply_clear(&r);
	fwc_set(&r, fwc_key("cm_red_hue"), "256");
	check(r.failed, "256 is outside the range");
	reply_clear(&r);
	args[0] = "cyan"; args[1] = "5"; args[2] = "-5"; args[3] = "7";
	cmd_cm(&r, args, 4);
	check(!r.failed && cm_mag(18) == 5 && cm_mag(19) == 5 && cm_neg(19) && cm_mag(20) == 7 && calls_cm == 8,
	      "cm cyan 5 -5 7: three entries, one call");
	reply_clear(&r);
	args[0] = "yellow";
	cmd_cm(&r, args, 1);
	check(!r.failed && strstr(r.buf, "ok cm yellow hue 60 sat -100 value 0"), "cm yellow shows the wanted steps");
	reply_clear(&r);
	cmd_cm(&r, args, 0);
	check(!r.failed && strstr(r.buf, "cm_yellow_hue = 60") && strstr(r.buf, "cm_cyan_sat = -5") && !strstr(r.buf, "cm_green"),
	      "cm alone lists the changed ones");
	reply_clear(&r);
	args[0] = "reset";
	cmd_cm(&r, args, 1);
	check(!r.failed && cm_is_default(), "cm reset: every magnitude and sign bit as the board had it");
	check(writes_only_in_slots(), "the colour management wrote only its slot and the sign bits");
	check(access(base_file, F_OK) == 0, "the firmware's own values are kept in a file");

	/* a restart of the program: the registers hold an old step, the base comes from the file, not from the registers */
	reply_clear(&r);
	fwc_set(&r, fwc_key("cm_yellow_hue"), "60");
	program_starts();
	check(cm_mag(9) == 60, "(the registers still hold the step)");
	reply_clear(&r);
	args[0] = "reset";
	cmd_cm(&r, args, 1);
	check(!r.failed && cm_is_default(), "after a restart, cm reset gives the board's own value, not the step");

	/* a restart with nothing kept: the registers hold an old step, the start brings them back */
	reply_clear(&r);
	fwc_set(&r, fwc_key("cm_yellow_hue"), "60");
	program_starts();
	fwc_sync("the start");
	check(cm_is_default(), "the start puts the board's own colour back when nothing is kept");

	/* ---- the firmware forgets ---- */
	reply_clear(&r);
	fwc_set(&r, fwc_key("cm_yellow_hue"), "60");
	fwc_set(&r, fwc_key("wb_g_gain"), "563");
	calls_cm = calls_wb = 0;
	repairs0 = fwc.repairs;
	fwc_sync("a resync");
	check(calls_cm == 0 && calls_wb == 0, "everything in place: a check sends nothing");
	firmware_forgets();
	check(cm_mag(9) == 0 && (get(FWC_REG_WB_DC) & 0xfff) == 0x800, "(the firmware has forgotten both)");
	fwc_sync("a resync");
	check(calls_wb == 1 && (get(FWC_REG_WB_DC) & 0xfff) == 0x8cc, "the white balance is sent again");
	check(calls_cm == 2 && cm_mag(9) == 60, "the colour management is sent twice (one off first) and is back");
	check(fwc.repairs == repairs0 + 2, "two repairs are counted");

	/* the cache would have hidden it */
	firmware_forgets();
	{
		int mag[FWC_CM_N];
		unsigned int e;
		char err[100];

		for (e = 0; e < FWC_CM_N; e++) {
			int eff = fwc_cm_eff(e);

			mag[e] = eff < 0 ? -eff : eff;
		}
		calls_cm = 0;
		fwc_cm_call(mag, err, sizeof(err));
		check(calls_cm == 1 && cm_mag(9) == 0, "without the nudge the firmware finds nothing different and writes nothing");
	}
	fwc_sync("a source change");
	check(cm_mag(9) == 60, "with it, the change is written");

	/* ---- a picture mode writes the firmware's own colour: the base is the base of the mode in force ---- */
	make_cinema();
	machine_reset();
	program_starts();
	reply_clear(&r);
	fwc_set(&r, fwc_key("cm_yellow_hue"), "60");
	fwc_set(&r, fwc_key("cm_red_sat"), "-20");
	fwc_mode_begin();
	check(cm_is_default(), "before the mode is sent, the steps are off: the registers hold the standard base");
	firmware_mode(cm_cinema);
	check(cm_mag(9) == 10 && cm_mag(1) == 20, "(the cinema script has written its own values over them)");
	fwc_mode_end("a preset");
	check(cm_mag(9) == 70 && cm_mag(1) == 0 && !cm_neg(1), "cinema: yellow hue 10 + 60 = 70, red saturation 20 - 20 = 0");
	check(cm_mag(10) == 70 && cm_mag(0) == 150 && cm_mag(19) == 44 && cm_mag(32) == 3,
	      "the rest is cinema's own, not standard's (yellow saturation 70 and not 90)");
	check(fwc.cm_base[10] == 70 && fwc.cm_base[9] == 10, "the base is cinema's now");
	reply_clear(&r);
	args[0] = "reset";
	cmd_cm(&r, args, 1);
	check(!r.failed && cm_mag(9) == 10 && cm_mag(1) == 20 && cm_mag(10) == 70, "cm reset in cinema gives cinema's own values");
	fwc_set(&r, fwc_key("cm_yellow_hue"), "-30");
	fwc_mode_begin();
	firmware_mode(cm_default);
	fwc_mode_end("a picture mode");
	check(cm_mag(9) == 30 && cm_neg(9) && cm_mag(10) == 90, "and back to standard: its own base (yellow hue 0 - 30, saturation 90)");
	args[0] = "reset";
	cmd_cm(&r, args, 1);
	check(cm_is_default(), "reset in standard: the board's table, signs and all");

	/* no step ever used: the mode's values stand and nothing is sent */
	machine_reset();
	program_starts();
	calls_cm = 0;
	fwc_mode_begin();
	firmware_mode(cm_cinema);
	fwc_mode_end("a preset");
	check(calls_cm == 0 && cm_mag(10) == 70 && !fwc.cm_base_ok && access(base_file, F_OK) != 0,
	      "without a step ever used: no call, no base, cinema's own values show");

	/* the start of a new run, a step kept, the registers still holding the old mode's base plus the step */
	machine_reset();
	program_starts();
	reply_clear(&r);
	fwc_set(&r, fwc_key("cm_yellow_hue"), "60");
	program_starts();
	fwc.cm[9] = 60;			/* what fwc_adopt() takes from the file werte */
	fwc_mode_begin();
	check(cm_mag(9) == 0, "a restart: the step is taken off before the mode is sent (the base comes from the file)");
	firmware_mode(cm_cinema);
	fwc_mode_end("a preset");
	check(cm_mag(9) == 70 && cm_mag(10) == 70 && fwc.cm_base[9] == 10, "and laid on cinema's base");
	{
		bool clean = true;
		unsigned int e;

		for (e = 0; e < FWC_CM_N; e++)
			clean &= regs_seen_by_script[e] == cm_default[e];
		check(clean, "the script found the registers clean (the board's own values), not the steps");
	}

	/* ---- the start: neutral, nothing kept ---- */
	machine_reset();
	program_starts();
	fwc_sync("the start");
	check(calls_wb == 0 && calls_cm == 0 && nwlog == 0, "neutral and nothing kept: the start sends nothing and writes nothing");
	put(FWC_REG_WB_DC, 0x08000900);	/* a setting left standing by an earlier run */
	program_starts();
	fwc_sync("the start");
	check(calls_wb == 1 && regs_are_stock(), "an old, unsaved setting in the registers is taken back at the start");
	fwc_sync("a source change");
	check(calls_wb == 1, "a later check with everything in place sends nothing");

	/* ---- the file werte ---- */
	machine_reset();
	program_starts();
	reply_clear(&r);
	fwc_set(&r, fwc_key("wb_r_gain"), "480");
	fwc_set(&r, fwc_key("wb_b_offset"), "530");
	fwc_set(&r, fwc_key("cm_yellow_hue"), "60");
	fwc_set(&r, fwc_key("cm_green_sat"), "-15");
	{
		char path[] = "/tmp/h713-tv-test-werte-XXXXXX", msg[600] = "";
		FILE *f;
		int wfd = mkstemp(path);

		f = fdopen(wfd, "w");
		fprintf(f, "brightness  = 50\n");
		fwc_kept_lines(f, msg, sizeof(msg), 0);
		fclose(f);
		check(strstr(msg, "wb=480 512 512 512 512 530") && strstr(msg, "cm_yellow_hue=60") && strstr(msg, "cm_green_sat=-15"),
		      "save names the six and the changed entries in its answer");
		memset(&sv, 0, sizeof(sv));
		sv.path = path;
		saved_read(&sv);
		check(sv.wb_have[0] && sv.wb[0] == 480 && sv.wb_have[5] && sv.wb[5] == 530 && sv.wb_have[1] && sv.wb[1] == 512,
		      "read back: all six white balance values");
		check(sv.cm_have[9] && sv.cm[9] == 60 && sv.cm_have[3 * 5 + 1] && sv.cm[3 * 5 + 1] == -15, "read back: the two colour steps");
		check(!sv.cm_have[0] && !sv.cm_have[10], "and no more than those");
		check(sv.have[0] && sv.value[0] == 50, "the nine controls are read as before");
		program_starts();
		fwc_adopt(sv.wb_have, sv.wb, sv.cm_have, sv.cm);
		check(fwc.wb[0] == 480 && fwc.wb[5] == 530 && fwc.cm[9] == 60 && fwc.cm[3 * 5 + 1] == -15 && fwc.cm[0] == 0,
		      "adopted at the start");
		firmware_forgets();
		calls_wb = calls_cm = 0;
		fwc_sync("the start");
		check(calls_wb == 1 && calls_cm == 2 && (get(FWC_REG_WB_DC) >> 16 & 0xfff) == 0x780 && cm_mag(9) == 60,
		      "the start puts the kept values on the registers");
		check(cm_mag(16) == 15 && cm_neg(16), "(green saturation: -15 on 0 is magnitude 15 with the sign bit)");
		unlink(path);
	}
	{
		char path[] = "/tmp/h713-tv-test-bad-XXXXXX";
		FILE *f;
		int wfd = mkstemp(path);

		f = fdopen(wfd, "w");
		fprintf(f, "wb_r_gain = 5000\ncm_red_hue = 300\nwb_g_gain = abc\ncm_cyan_value = 9\nwb_b_gain = 600\n");
		fclose(f);
		memset(&sv, 0, sizeof(sv));
		sv.path = path;
		saved_read(&sv);
		check(!sv.wb_have[0] && !sv.cm_have[0] && !sv.wb_have[1], "values out of range or no numbers are dropped one by one");
		check(sv.cm_have[3 * 6 + 2] && sv.cm[3 * 6 + 2] == 9 && sv.wb_have[2] && sv.wb[2] == 600, "and the good ones around them stay");
		unlink(path);
	}

	/* status shows the state */
	machine_reset();
	program_starts();
	reply_clear(&r);
	fwc_set(&r, 1, "563");
	reply_clear(&r);
	fwc_status(&r);
	check(strstr(r.buf, "white balance   512 563 512 512 512 512") && strstr(r.buf, "on the registers") &&
	      strstr(r.buf, "colour mgmt     0 entries changed"), "status: both lines");

	unlink(base_file);
	printf("%s: %d failed\n", failed ? "FAILED" : "PASSED", failed);

	return failed ? 1 : 0;
}
