// SPDX-License-Identifier: GPL-3.0-only
// Differential driver: runs UxPlay's own fairplay_setup/handshake/decrypt (lib/fairplay_playfair.c,
// lib/playfair/*.c) on random handshakes and prints them in the format of playfair_vectors.txt:
//   p1 <mode> <message1> <reply1>
//   case <mode> <message3> <reply2> <ekey> <key>
// Build (tests/differential.rs does this): cc -O2 -I$UXPLAY/lib uxplay_driver.c $UXPLAY/lib/fairplay_playfair.c
//   $UXPLAY/lib/playfair/*.c -lm;  run: ./driver <cases per mode> <seed>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "fairplay.h"

static uint64_t rng;
static uint8_t next_byte(void) {  // splitmix64, one byte per step
    uint64_t z = (rng += 0x9e3779b97f4a7c15ULL);
    z = (z ^ (z >> 30)) * 0xbf58476d1ce4e5b9ULL;
    z = (z ^ (z >> 27)) * 0x94d049bb133111ebULL;
    return (uint8_t)(z ^ (z >> 31));
}

static void hex(const unsigned char *p, size_t n) {
    putchar(' ');
    for (size_t i = 0; i < n; i++) printf("%02x", p[i]);
}

static void die(const char *what, int mode) {
    fprintf(stderr, "%s failed (mode %d)\n", what, mode);
    exit(1);
}

int main(int argc, char **argv) {
    if (argc != 3) {
        fprintf(stderr, "usage: %s <cases per mode> <seed>\n", argv[0]);
        return 2;
    }
    long cases = strtol(argv[1], NULL, 10);
    rng = strtoull(argv[2], NULL, 0);
    for (int mode = 0; mode < 4; mode++) {
        // A sender's message 1: FPLY 03 01 01, length 4, then 02 00 <mode> bb.
        unsigned char m1[16] = {0x46, 0x50, 0x4c, 0x59, 0x03, 0x01, 0x01, 0x00,
                                0x00, 0x00, 0x00, 0x04, 0x02, 0x00, (unsigned char)mode, 0xbb};
        unsigned char r1[142];
        fairplay_t *fp = fairplay_init(NULL);
        if (fairplay_setup(fp, m1, r1) != 0) die("fairplay_setup", mode);
        fairplay_destroy(fp);
        printf("p1 %d", mode);
        hex(m1, 16);
        hex(r1, 142);
        putchar('\n');
        for (long c = 0; c < cases; c++) {
            // A sender's message 3: FPLY 03 01 03, length 0x98, the mode, then random bytes.
            unsigned char m3[164] = {0x46, 0x50, 0x4c, 0x59, 0x03, 0x01, 0x03, 0x00, 0x00, 0x00, 0x00, 0x98};
            m3[12] = (unsigned char)mode;
            for (int i = 13; i < 164; i++) m3[i] = next_byte();
            unsigned char ekey[72], r2[32], key[16];
            for (int i = 0; i < 72; i++) ekey[i] = next_byte();
            fp = fairplay_init(NULL);
            if (fairplay_setup(fp, m1, r1) != 0) die("fairplay_setup", mode);
            if (fairplay_handshake(fp, m3, r2) != 0) die("fairplay_handshake", mode);
            if (fairplay_decrypt(fp, ekey, key) != 0) die("fairplay_decrypt", mode);
            fairplay_destroy(fp);
            printf("case %d", mode);
            hex(m3, 164);
            hex(r2, 32);
            hex(ekey, 72);
            hex(key, 16);
            putchar('\n');
        }
    }
    return 0;
}
