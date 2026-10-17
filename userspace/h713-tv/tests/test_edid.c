/* SPDX-License-Identifier: GPL-2.0 */
/*
 * h713-tv's EDID without Deep Colour, on the host: main.c is compiled into this file and edid_strip_dc() is run on
 * made-up EDIDs of the shape the vendor's file has (a base block with one detailed timing, a CTA extension with a video
 * data block, audio, speakers, the HDMI vendor block and, for the 2.0 half, the HDMI Forum vendor block). What is
 * checked: every Deep Colour bit of both vendor blocks goes, Supports_AI, DVI_Dual, the maximum TMDS clock, the
 * SCDC flags and every other byte stay, the extension's checksum is right, a second run finds nothing (a restart of
 * h713-tv publishes nothing again), the block is found after edid_prune() moved it, and a vendor block that is too
 * short, is somebody else's or reaches past the extension is not touched.
 *
 *   test_edid      exit 0 when every case passed
 */
#define main h713_tv_main
#include "../main.c"
#undef main

static int failed;

static void check(bool ok, const char *what)
{
	printf("%s %s\n", ok ? "ok  " : "FAIL", what);
	if (!ok)
		failed++;
}

static unsigned int sum128(const uint8_t *b)
{
	unsigned int i, s = 0;

	for (i = 0; i < 128; i++)
		s += b[i];
	return s & 0xff;
}

static unsigned int bytes_differ(const uint8_t *a, const uint8_t *b, unsigned int n)
{
	unsigned int i, d = 0;

	for (i = 0; i < n; i++)
		d += a[i] != b[i];
	return d;
}

/* the offsets inside the extension the builder fills in, for the checks */
struct shape {
	unsigned int hdmi;	/* the HDMI vendor block's header byte */
	unsigned int forum;	/* the HDMI Forum vendor block's header byte, 0: none */
	unsigned int dc;	/* the flags byte of the HDMI vendor block */
	unsigned int tmds;	/* ... its maximum TMDS clock byte */
	unsigned int dc420;	/* the Forum block's YCbCr 4:2:0 Deep Colour byte */
	unsigned int scdc;	/* ... its SCDC flags byte */
	unsigned int vdb;	/* the video data block's header byte */
};

enum { WITH_FORUM = 1, SHORT_HDMI = 2, FOREIGN = 4 };

/*
 * A 256-byte EDID: base block (1.3, one 1920x1080p60 timing, one extension), CTA 861 extension revision 3 with
 * video (6 VICs), audio, speaker, HDMI vendor block, optionally the HDMI Forum block, a block of Dolby Vision's shape
 * (extended tag, whose bytes at the flag offsets are 0xff), a vendor block of somebody else's (tag 3, 0xff at the
 * flag offsets), and a detailed timing.
 */
static struct shape build(uint8_t *edid, uint8_t hdmi_flags, uint8_t dc420, unsigned int opt)
{
	static const uint8_t header[8] = { 0x00, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0x00 };
	uint8_t *ext = edid + 128;
	struct shape s = { 0 };
	unsigned int i = 4;

	memset(edid, 0, 256);
	memcpy(edid, header, sizeof(header));
	edid[8] = 0x52; edid[9] = 0x74;			/* manufacturer "TST" */
	edid[18] = 1; edid[19] = 3;			/* EDID 1.3 */
	edid[0x14] = 0x81;				/* digital */
	memcpy(edid + 54, edid_panel_timings[1].dtd, 12);
	edid[54 + 12] = 0x80; edid[54 + 13] = 0x10; edid[54 + 14] = 0x40; edid[54 + 15] = 0x00;
	edid[0x7e] = 1;
	edid[127] = (uint8_t)(-(int)sum128(edid));

	ext[0] = 0x02;
	ext[1] = 0x03;
	ext[3] = 0xf1;
	s.vdb = i;
	ext[i++] = 0x40 | 6;
	ext[i++] = 0x90; ext[i++] = 0x04; ext[i++] = 0x1f; ext[i++] = 0x13; ext[i++] = 0x14; ext[i++] = 0x05;
	ext[i++] = 0x20 | 3;
	ext[i++] = 0x09; ext[i++] = 0x7f; ext[i++] = 0x07;
	ext[i++] = 0x80 | 3;
	ext[i++] = 0x01; ext[i++] = 0x00; ext[i++] = 0x00;
	s.hdmi = i;
	if (opt & SHORT_HDMI) {
		ext[i++] = 0x60 | 5;			/* the physical address and no flags */
		ext[i++] = 0x03; ext[i++] = 0x0c; ext[i++] = 0x00; ext[i++] = 0x10; ext[i++] = 0x00;
	} else {
		ext[i++] = 0x60 | 7;
		ext[i++] = 0x03; ext[i++] = 0x0c; ext[i++] = 0x00; ext[i++] = 0x10; ext[i++] = 0x00;
		s.dc = i;
		ext[i++] = hdmi_flags;
		s.tmds = i;
		ext[i++] = 0x44;			/* 340 MHz */
	}
	if (opt & WITH_FORUM) {
		s.forum = i;
		ext[i++] = 0x60 | 7;
		ext[i++] = 0xd8; ext[i++] = 0x5d; ext[i++] = 0xc4; ext[i++] = 0x01;
		ext[i++] = 0x78;			/* 600 MHz */
		s.scdc = i;
		ext[i++] = 0x80;			/* SCDC present */
		s.dc420 = i;
		ext[i++] = dc420;
	}
	ext[i++] = 0xe0 | 11;				/* extended tag 1, OUI 46 d0 00, a Dolby Vision shape */
	ext[i++] = 0x01; ext[i++] = 0x46; ext[i++] = 0xd0; ext[i++] = 0x00;
	memset(ext + i, 0xff, 7);
	i += 7;
	if (opt & FOREIGN) {
		ext[i++] = 0x60 | 8;			/* somebody else's vendor block */
		ext[i++] = 0x11; ext[i++] = 0x22; ext[i++] = 0x33;
		memset(ext + i, 0xff, 5);
		i += 5;
	}
	ext[2] = (uint8_t)i;				/* the detailed timing starts here */
	memcpy(ext + i, edid + 54, 18);
	ext[127] = (uint8_t)(-(int)sum128(ext));
	return s;
}

int main(void)
{
	uint8_t orig[256], e[256], a[256], b[256], have[16];
	char list[96];
	struct shape s;
	unsigned int n, i;

	/* the vendor's shape: AI, DC_36bit, DC_30bit, DC_Y444 in the HDMI block, the 1.4 half */
	s = build(orig, 0xb8, 0, 0);
	check(sum128(orig + 128) == 0 && sum128(orig) == 0, "the made-up EDID has two good checksums");
	memcpy(e, orig, 256);
	n = edid_strip_dc(e, list, sizeof(list));
	check(n == 3 && !strcmp(list, " DC_Y444 DC_30bit DC_36bit"), "HDMI block 0xb8: three Deep Colour bits cleared, named");
	check(e[128 + s.dc] == 0x80, "... Supports_AI stays, the flags are 0x80");
	check(e[128 + s.tmds] == 0x44, "... the maximum TMDS clock is untouched (340 MHz)");
	check(sum128(e + 128) == 0, "... the extension's checksum is right");
	check(bytes_differ(orig, e, 256) == 2, "... two bytes differ: the flags and the checksum");
	check(!memcmp(orig, e, 128), "... the base block is the same");
	check(!strcmp(list + 1, "DC_Y444 DC_30bit DC_36bit"), "... the names read well for the journal");
	check(edid_strip_dc(e, list, sizeof(list)) == 0 && list[0] == '\0', "a second run finds nothing: a restart publishes nothing again");
	memcpy(a, e, 256);
	edid_strip_dc(a, NULL, 0);
	check(!memcmp(a, e, 256), "... and changes nothing (also without a list)");

	/* all four bits, and the two that are not Deep Colour */
	build(orig, 0xf9, 0, 0);
	memcpy(e, orig, 256);
	n = edid_strip_dc(e, list, sizeof(list));
	check(n == 4 && strstr(list, "DC_48bit") && e[128 + s.dc] == 0x81, "0xf9: all four bits go, Supports_AI and DVI_Dual stay (0x81)");
	check(sum128(e + 128) == 0, "... checksum right");

	/* the 2.0 half: the HDMI block and the Forum block */
	s = build(orig, 0xb8, 0x07, WITH_FORUM);
	memcpy(e, orig, 256);
	n = edid_strip_dc(e, list, sizeof(list));
	check(n == 6 && strstr(list, "DC_36bit_420") && strstr(list, "DC_30bit_420") && strstr(list, "DC_48bit_420"),
	      "both vendor blocks: six bits, the three 4:2:0 ones named");
	check(e[128 + s.dc420] == 0x00, "... the 4:2:0 Deep Colour byte is 0");
	check(e[128 + s.scdc] == 0x80 && e[128 + s.forum + 5] == 0x78, "... SCDC present and the maximum TMDS character rate (600 MHz) are untouched");
	check(sum128(e + 128) == 0 && bytes_differ(orig, e, 256) == 3, "... checksum right, three bytes differ (two flags, the checksum)");
	/* only the Forum block offers it */
	build(orig, 0x80, 0x02, WITH_FORUM);
	memcpy(e, orig, 256);
	check(edid_strip_dc(e, list, sizeof(list)) == 1 && !strcmp(list, " DC_36bit_420") && sum128(e + 128) == 0,
	      "only DC_36bit_420 offered: that one goes, checksum right");

	/* a 2.0 EDID that offers nothing */
	build(orig, 0x80, 0x00, WITH_FORUM);
	memcpy(e, orig, 256);
	check(edid_strip_dc(e, list, sizeof(list)) == 0 && !memcmp(orig, e, 256), "an EDID without Deep Colour stays byte for byte");

	/* what is not an HDMI sink with a CTA extension */
	build(orig, 0xb8, 0x07, WITH_FORUM);
	memcpy(e, orig, 256);
	e[0x7e] = 0;
	check(edid_strip_dc(e, list, sizeof(list)) == 0, "no extension in the base block: nothing");
	memcpy(e, orig, 256);
	e[128] = 0x70;
	check(edid_strip_dc(e, list, sizeof(list)) == 0 && e[128 + 6] == orig[128 + 6], "an extension that is not CTA (0x70): nothing");
	memcpy(e, orig, 256);
	e[128 + 2] = 3;
	check(edid_strip_dc(e, list, sizeof(list)) == 0, "a detailed timing offset below 4 (no data blocks): nothing");

	/* a vendor block that is too short, or somebody else's, is not touched */
	s = build(orig, 0xb8, 0x07, WITH_FORUM | SHORT_HDMI);
	memcpy(e, orig, 256);
	n = edid_strip_dc(e, list, sizeof(list));
	check(n == 3 && e[128 + s.forum] == orig[128 + s.forum] && bytes_differ(orig, e, 256) == 2,
	      "an HDMI block with no flags byte (length 5): the next block's header is not read as flags; only the Forum bits go");
	s = build(orig, 0xb8, 0x07, WITH_FORUM | FOREIGN);
	memcpy(e, orig, 256);
	n = edid_strip_dc(e, list, sizeof(list));
	check(n == 6 && bytes_differ(orig, e, 256) == 3, "a vendor block of somebody else's (0xff at the flag offsets) and a Dolby Vision shaped block: untouched");
	for (i = 128 + s.vdb; i < 128 + 120; i++)
		if (orig[i] != e[i] && i != 128 + s.dc && i != 128 + s.dc420)
			break;
	check(i == 128 + 120, "... every other byte of the data blocks is the same");

	/* a block that claims to reach past the extension: skipped, nothing written out of it */
	memcpy(e, orig, 256);
	memset(e + 128 + 4, 0, 123);
	e[128 + 2] = 126;
	e[128 + 120] = 0x60 | 31;
	e[128 + 121] = 0x03; e[128 + 122] = 0x0c; e[128 + 123] = 0x00; e[128 + 126] = 0xff;
	memcpy(a, e, 256);
	check(edid_strip_dc(e, list, sizeof(list)) == 0 && !memcmp(a, e, 256), "a vendor block whose length runs past the extension: skipped");

	/* the list is cut, not overrun, when the buffer is small */
	build(orig, 0xf8, 0x07, WITH_FORUM);
	memcpy(e, orig, 256);
	{
		char tiny[12];

		n = edid_strip_dc(e, tiny, sizeof(tiny));
		check(n == 7 && strlen(tiny) < sizeof(tiny) && sum128(e + 128) == 0, "a list buffer of 12 bytes: cut, never overrun; seven bits all the same");
	}

	/* the words of the journal and of the answer */
	{
		char note[128];

		edid_dc_say(note, sizeof(note), 2, " DC_Y444 DC_30bit");
		check(!strcmp(note, "without deep colour (DC_Y444 DC_30bit)"), "edid_dc_say: \"without deep colour (names)\"");
		edid_dc_say(note, sizeof(note), 0, "");
		check(note[0] == '\0', "edid_dc_say: nothing to say, nothing said");
	}

	/* edid_prune() moves the vendor block; edid_strip_dc() finds it, in either order */
	memset(have, 0xff, sizeof(have));
	have[5 / 8] &= (uint8_t)~(1 << (5 % 8));		/* VIC 5 the table lacks: the last video descriptor goes */
	s = build(orig, 0xb8, 0x07, WITH_FORUM);
	memcpy(a, orig, 256);
	check(edid_prune(a, have, NULL, 0) == 1, "(set-up) edid_prune() takes VIC 5 out: the vendor blocks move up by one");
	check(edid_strip_dc(a, NULL, 0) == 6 && sum128(a + 128) == 0, "... then edid_strip_dc() still finds both and the checksum is right");
	memcpy(b, orig, 256);
	check(edid_strip_dc(b, NULL, 0) == 6 && edid_prune(b, have, NULL, 0) == 1 && sum128(b + 128) == 0,
	      "the other order: the same");
	check(!memcmp(a, b, 256), "... and both orders give the same 256 bytes");
	check(a[128 + s.dc - 1] == 0x80 && a[128 + s.dc420 - 1] == 0x00, "... flags 0x80 and 4:2:0 byte 0 at their moved places");
	check(edid_strip_dc(a, NULL, 0) == 0, "... and what goes out is clean");

	/* the four-block form of replug: the second EDID starts at byte 256 of the image */
	{
		uint8_t img[512];

		build(img, 0xb8, 0, 0);
		build(img + 256, 0xb8, 0x07, WITH_FORUM);
		check(edid_strip_dc(img, NULL, 0) == 3 && edid_strip_dc(img + 256, NULL, 0) == 6 &&
		      sum128(img + 128) == 0 && sum128(img + 256 + 128) == 0,
		      "the four-block image: each EDID is cleaned on its own, two good checksums");
	}

	printf("%s: %d failed\n", failed ? "FAILED" : "PASSED", failed);
	return failed ? 1 : 0;
}
