/* mipslog -- den MIPS-elog-Ring (Modus 1) auslesen.
 *
 * Adressen aus display.bin reversiert:
 *   Ring          phys 0x4B272D9C, 102400 Bytes
 *   Schreibzeiger phys 0x4B48C2A8   (Offset im Ring)
 *   Lesezeiger    phys 0x4B48C2A4
 *   Overflow      phys 0x4B48C2A1
 *
 * dump  = alles ausgeben, Lesezeiger NICHT anfassen (Boot-Historie)
 * tail  = fortlaufend, Lesezeiger nachziehen
 */
#define _GNU_SOURCE
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#define RING_PHYS 0x4B272D9CUL
#define RING_SIZE 102400UL
#define CTL_PHYS  0x4B48C000UL      /* Seitenanfang, Zeiger liegen als Offset drin */
#define OFF_WR    (0x4B48C2A8UL - CTL_PHYS)
#define OFF_RD    (0x4B48C2A4UL - CTL_PHYS)
#define OFF_OVF   (0x4B48C2A1UL - CTL_PHYS)

static volatile uint8_t *ctl;
static volatile uint8_t *ring;
static uint32_t rd32(unsigned o) { return *(volatile uint32_t *)(ctl + o); }
static void     wr32(unsigned o, uint32_t v) { *(volatile uint32_t *)(ctl + o) = v; }

static void emit(uint32_t from, uint32_t to)
{
	uint32_t i;
	for (i = from; i != to; i = (i + 1) % RING_SIZE) {
		uint8_t c = ring[i];
		putchar((c == '\n' || c == '\t' || (c >= 0x20 && c < 0x7f)) ? c : '.');
	}
	fflush(stdout);
}

int main(int argc, char **argv)
{
	int fd = open("/dev/mem", O_RDWR | O_SYNC);
	const char *mode = argc > 1 ? argv[1] : "state";
	uint32_t w, r;

	if (fd < 0) { perror("/dev/mem"); return 1; }
	ctl  = mmap(NULL, 0x1000, PROT_READ | PROT_WRITE, MAP_SHARED, fd, CTL_PHYS);
	ring = mmap(NULL, RING_SIZE, PROT_READ, MAP_SHARED, fd, RING_PHYS & ~0xfffUL);
	if (ctl == MAP_FAILED || ring == MAP_FAILED) { perror("mmap"); return 1; }
	ring += (RING_PHYS & 0xfff);

	w = rd32(OFF_WR); r = rd32(OFF_RD);
	if (!strcmp(mode, "state")) {
		printf("write=%u read=%u overflow=%u\n", w, r, ctl[OFF_OVF]);
		return 0;
	}
	if (!strcmp(mode, "dump")) {          /* Boot-Historie, Lesezeiger unangetastet */
		fprintf(stderr, "-- Ring 0..%u, Lesezeiger bleibt bei %u --\n", w, r);
		emit(0, w);
		putchar('\n');
		return 0;
	}
	if (!strcmp(mode, "tail")) {
		for (;;) {
			w = rd32(OFF_WR);
			r = rd32(OFF_RD);
			if (w != r) { emit(r, w); wr32(OFF_RD, w); }
			usleep(200000);
		}
	}
	fprintf(stderr, "usage: mipslog state|dump|tail\n");
	return 2;
}
