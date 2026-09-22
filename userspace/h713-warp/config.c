/* SPDX-License-Identifier: GPL-2.0 */
#define _GNU_SOURCE		/* accept4, strtok_r, O_CLOEXEC */
/*
 * /etc/h713/warp.conf (design AP2d M2) -- the same "key = value", "#" comment,
 * read-once-at-start format as /etc/h713/tv.conf, and the same file is the
 * save target of "ctl keystone set|nudge|reset": a keystone the user set has
 * to survive a reboot, which is the whole point of the vendor's persist.*
 * properties. It is rewritten whole into warp.conf.new, fsync'd and renamed
 * over, so a power cut leaves either the old file or the new one. Nine keys
 * and nothing else: tl_x tl_y tr_x tr_y bl_x bl_y br_x br_y, integer
 * per-mille 0..1000, POSITIVE INWARD, named by the physical corner as the
 * picture stands on the wall (matrix.c has the slot derivation), and
 * "warp = on|off", the state to come up in. An unknown key or an unreadable
 * value is named in the journal and ignored, so a typo does not silently
 * become a corner of 0.
 */
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <unistd.h>
#include <sys/stat.h>

#include "warp.h"

static char *trim(char *s)
{
	size_t n;

	while (*s == ' ' || *s == '\t' || *s == '\r' || *s == '\n')
		s++;
	n = strlen(s);
	while (n && (s[n - 1] == ' ' || s[n - 1] == '\t' || s[n - 1] == '\r' ||
		     s[n - 1] == '\n'))
		s[--n] = '\0';

	return s;
}

static bool parse_permille(const char *val, int *out)
{
	char *end;
	long x;

	errno = 0;
	x = strtol(val, &end, 10);
	if (end == val || *end || errno || x < 0 || x > 1000)
		return false;
	*out = (int)x;

	return true;
}

void conf_read(struct warp_conf *c)
{
	char line[256];
	unsigned int n = 0;
	FILE *f;

	c->present = false;
	c->start_on = false;
	c->zoom = 100;
	memset(c->v, 0, sizeof(c->v));

	f = fopen(c->path, "r");
	if (!f) {
		if (errno != ENOENT)
			warn("%s: %s -- the defaults apply (all corners 0, warp = off)",
			     c->path, strerror(errno));
		return;
	}
	c->present = true;
	while (fgets(line, sizeof(line), f)) {
		char *key, *val, *hash;
		int k, value;

		n++;
		hash = strchr(line, '#');
		if (hash)
			*hash = '\0';
		key = trim(line);
		if (!*key)
			continue;
		val = strpbrk(key, "= \t");
		if (!val) {
			warn("%s:%u: \"%s\" without a value -- ignored", c->path, n, key);
			continue;
		}
		*val++ = '\0';
		while (*val == ' ' || *val == '\t' || *val == '=')
			val++;
		val = trim(val);
		if (!strcasecmp(key, "zoom")) {
			int z = atoi(val);

			if (z >= 10 && z <= 100)
				c->zoom = z;
			else
				warn("%s:%u: zoom = \"%s\" is not 10..100 percent -- 100",
				     c->path, n, val);
			continue;
		}
		if (!strcasecmp(key, "warp")) {
			if (!strcasecmp(val, "on"))
				c->start_on = true;
			else if (!strcasecmp(val, "off"))
				c->start_on = false;
			else
				warn("%s:%u: warp = \"%s\" unknown (on off) -- off",
				     c->path, n, val);
			continue;
		}
		k = warp_key_by_name(key);
		if (k < 0) {
			warn("%s:%u: unknown key \"%s\" -- ignored (tl_x .. br_y, zoom, warp)",
			     c->path, n, key);
			continue;
		}
		if (!parse_permille(val, &value)) {
			warn("%s:%u: %s = \"%s\" is not a per-mille value 0..1000 -- dropped",
			     c->path, n, key, val);
			continue;
		}
		c->v[k] = value;
	}
	fclose(f);
	{
		int before[WARP_KEYS];

		memcpy(before, c->v, sizeof(before));
		warp_clamp(c->v);
		if (memcmp(before, c->v, sizeof(before)))
			warn("%s: two opposite corners asked for more than the picture's width or height -- clamped the vendor's way",
			     c->path);
	}
}

/* The file as the daemon writes it. Its comment block is part of the
 * contract: the corner names are the wall's, not the vendor's slots.
 */
bool conf_write(const struct warp_conf *c, char *why, size_t n)
{
	char tmp[200], dir[200], *slash;
	int fd, i;
	FILE *f;

	if (strlen(c->path) + 5 >= sizeof(tmp)) {
		snprintf(why, n, "%s: path too long", c->path);
		return false;
	}
	snprintf(tmp, sizeof(tmp), "%s.new", c->path);
	fd = open(tmp, O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC, 0644);
	if (fd < 0 && errno == ENOENT) {
		snprintf(dir, sizeof(dir), "%s", c->path);
		slash = strrchr(dir, '/');
		if (slash && slash != dir) {
			*slash = '\0';
			if (!mkdir(dir, 0755) || errno == EEXIST)
				fd = open(tmp, O_WRONLY | O_CREAT | O_TRUNC |
					  O_CLOEXEC, 0644);
		}
	}
	if (fd < 0) {
		snprintf(why, n, "%s: %s", tmp, strerror(errno));
		return false;
	}
	f = fdopen(fd, "w");
	if (!f) {
		snprintf(why, n, "%s: %s", tmp, strerror(errno));
		close(fd);
		unlink(tmp);
		return false;
	}
	fprintf(f, "# h713-warp: the keystone, written by \"h713-warp ctl keystone\".\n"
		"# Eight inward offsets in per-mille of the panel, 0..1000, 0 = the\n"
		"# corner untouched, larger pulls that corner towards the centre.\n"
		"# The names are the PHYSICAL corners as the picture stands on the\n"
		"# wall: tl = top left, tr = top right, bl = bottom left, br =\n"
		"# bottom right. x of a corner is limited by the corner at the other\n"
		"# end of its row, y by the one at the other end of its column, so\n"
		"# the picture can never be pulled past its own width or height.\n"
		"# All eight at 0 is the identity: the GPU is not started at all and\n"
		"# h713-tv shows the capture ring exactly as it does without this\n"
		"# service.\n");
	for (i = 0; i < WARP_KEYS; i++)
		fprintf(f, "%-5s = %d\n", warp_key_name[i], c->v[i]);
	fprintf(f, "\n# The screen zoom in percent (100 = none): every corner pulled in by\n# (100 - zoom) * 5 per-mille on top of the eight above.\nzoom  = %d\n", c->zoom);
	fprintf(f, "\n# The state to come up in.\nwarp  = %s\n",
		c->start_on ? "on" : "off");
	if (fflush(f) || fsync(fileno(f)) || fclose(f)) {
		snprintf(why, n, "%s: %s", tmp, strerror(errno));
		unlink(tmp);
		return false;
	}
	if (rename(tmp, c->path)) {
		snprintf(why, n, "%s: %s", c->path, strerror(errno));
		unlink(tmp);
		return false;
	}
	why[0] = '\0';

	return true;
}
