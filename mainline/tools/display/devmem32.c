/*
 * devmem32 -- read 32-bit MMIO registers on the H713 target.
 *
 * Why this exists at all: on arm64 you cannot read device registers through
 * /dev/mem with od or dd. The read() path is gated by valid_phys_addr_range(),
 * which requires memblock_is_map_memory(), and MMIO is not memory -- every read
 * returns -EFAULT on a perfectly healthy board. Only mmap() works, and
 * CONFIG_STRICT_DEVMEM permits exactly that. The shipping Debian rootfs has no
 * busybox, no devmem2 and no python3, so there was nothing on the target that
 * could do it.
 *
 * Freestanding and static on purpose: no libc, raw syscalls, a couple of KiB.
 * That makes it small enough to base64 onto the board over the serial console
 * when there is no network yet, which is exactly the situation it is for.
 *
 * Build (see tools/display/README or the handoff doc):
 *   clang --target=aarch64-linux-gnu -nostdlib -static -ffreestanding -Os \
 *         -fno-stack-protector -fuse-ld=lld -Wl,-e,_start \
 *         -o devmem32 devmem32.c
 *
 * Usage on target (root):
 *   ./devmem32                 the display handoff register set, with expected
 *                              values from the 2026-08-07 project-0x34 run
 *   ./devmem32 0x05600178 ...  arbitrary addresses
 */

typedef unsigned long u64;
typedef unsigned int u32;

#define SYS_openat 56
#define SYS_close  57
#define SYS_write  64
#define SYS_mmap   222
#define SYS_exit   93

#define AT_FDCWD   -100
#define O_RDONLY   0
#define O_SYNC     0x101000
#define PROT_READ  1
#define MAP_SHARED 1
#define PAGE       4096UL

static long sys(long n, long a, long b, long c, long d, long e, long f)
{
	register long x8 __asm__("x8") = n;
	register long x0 __asm__("x0") = a;
	register long x1 __asm__("x1") = b;
	register long x2 __asm__("x2") = c;
	register long x3 __asm__("x3") = d;
	register long x4 __asm__("x4") = e;
	register long x5 __asm__("x5") = f;

	__asm__ volatile("svc #0"
			 : "+r"(x0)
			 : "r"(x8), "r"(x1), "r"(x2), "r"(x3), "r"(x4), "r"(x5)
			 : "memory", "cc");
	return x0;
}

static void out(const char *s, unsigned n) { sys(SYS_write, 1, (long)s, n, 0, 0, 0); }

static void puts_(const char *s)
{
	unsigned n = 0;
	while (s[n])
		n++;
	out(s, n);
}

static void hex(u64 v, int digits)
{
	char b[17];
	int i;

	for (i = digits - 1; i >= 0; i--) {
		b[i] = "0123456789abcdef"[v & 0xf];
		v >>= 4;
	}
	out(b, digits);
}

/* Counts are decimal. The first version printed "0 of 0c changed". */
static void dec(u64 v)
{
	char b[21];
	int i = 20;

	if (!v) {
		out("0", 1);
		return;
	}
	while (v) {
		b[--i] = (char)('0' + (v % 10));
		v /= 10;
	}
	out(b + i, 20 - i);
}

/* The registers that must survive for the U-Boot frame to survive. */
static const struct { u64 addr; u32 want; const char *what; } regs[] = {
	{ 0x058c0014, 0xb8002300, "display PLL, N+1=36" },
	{ 0x0525c000, 0x02f80550, "mixer H/V total" },
	{ 0x0524c000, 0x00fc0202, "DE/OSD control" },
	{ 0x0528008c, 0x00000000, "layer X origin" },
	{ 0x05280084, 0x02d00500, "layer size" },
	{ 0x05600140, 0x03001901, "AFBD control" },
	{ 0x05600170, 0x00001400, "AFBD stride" },
	{ 0x05600178, 0x6c100000, "AFBD source address" },
	{ 0x05140054, 0x40000080, "display route" },
	{ 0x051c0014, 0x18000005, "LVDS PHY" },
	{ 0x051c0028, 0x1f300030, "LVDS PHY mid" },
	{ 0x05700000, 0xfff11111, "TVTOP" },
};

static u64 parse_hex(const char *s, int *ok)
{
	u64 v = 0;
	int any = 0;

	if (s[0] == '0' && (s[1] == 'x' || s[1] == 'X'))
		s += 2;
	while (*s) {
		int d;

		if (*s >= '0' && *s <= '9')
			d = *s - '0';
		else if (*s >= 'a' && *s <= 'f')
			d = *s - 'a' + 10;
		else if (*s >= 'A' && *s <= 'F')
			d = *s - 'A' + 10;
		else
			break;
		v = (v << 4) | (u64)d;
		any = 1;
		s++;
	}
	*ok = any;
	return v;
}

void _start(void)
{
	long argc;
	char **argv;
	int fd, i, bad = 0, n;

	/* argc/argv straight off the stack: no libc start-up ran. */
	__asm__ volatile("ldr %0, [sp]\n\tadd %1, sp, #8"
			 : "=r"(argc), "=r"(argv));

	fd = (int)sys(SYS_openat, AT_FDCWD, (long)"/dev/mem",
		      O_RDONLY | O_SYNC, 0, 0, 0);
	if (fd < 0) {
		puts_("cannot open /dev/mem (run as root)\n");
		sys(SYS_exit, 2, 0, 0, 0, 0, 0);
	}

	n = (argc > 1) ? (int)argc - 1 : (int)(sizeof(regs) / sizeof(regs[0]));

	for (i = 0; i < n; i++) {
		u64 addr, base, off, map;
		u32 got, want = 0;
		int have_want = 0, ok = 1;

		if (argc > 1) {
			addr = parse_hex(argv[i + 1], &ok);
			if (!ok) {
				puts_("bad address\n");
				continue;
			}
		} else {
			addr = regs[i].addr;
			want = regs[i].want;
			have_want = 1;
		}

		base = addr & ~(PAGE - 1);
		off = addr & (PAGE - 1);
		map = (u64)sys(SYS_mmap, 0, PAGE, PROT_READ, MAP_SHARED,
			       fd, (long)base);
		if ((long)map < 0 && (long)map > -4096) {
			puts_("0x");
			hex(addr, 8);
			puts_("  MMAP FAILED\n");
			bad++;
			continue;
		}

		got = *(volatile u32 *)(map + off);

		puts_("0x");
		hex(addr, 8);
		puts_("  ");
		hex(got, 8);
		if (have_want) {
			puts_("  want ");
			hex(want, 8);
			puts_("  ");
			puts_(regs[i].what);
			if (got != want) {
				puts_("   <-- CHANGED");
				bad++;
			}
		}
		puts_("\n");
	}

	if (argc <= 1) {
		puts_("\n");
		dec((u64)bad);
		puts_(" of ");
		dec((u64)n);
		puts_(" changed\n");
	}

	sys(SYS_close, fd, 0, 0, 0, 0, 0);
	sys(SYS_exit, bad ? 1 : 0, 0, 0, 0, 0, 0);
}
