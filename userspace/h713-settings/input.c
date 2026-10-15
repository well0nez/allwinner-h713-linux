// SPDX-License-Identifier: GPL-2.0
/*
 * The remote's keys for the page. The launcher starts its entries detached and lets go of the remote's devices, so a page
 * that is opened from it reads them itself - the same two as h713-keys: the Bluetooth remote (1d5a:c081) and the IR
 * receiver (input name "sunxi-ir") - and holds them alone (EVIOCGRAB) while it is open: Kodi under cage gets no key from the
 * page's navigation, and nothing happens twice. h713-keys and h713-power see nothing meanwhile, so what they would do with
 * the keys that matter is done here: volume, mute and focus by the row's own commands, Power by h713-power's datagram.
 */
#define _GNU_SOURCE
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/input.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <sys/un.h>

#include "settings.h"

#define MAXDEV 6

static int fd[MAXDEV], nfd;
static bool grabbed;
static double stamp_ms;		/* the kernel's time (CLOCK_REALTIME) of the key input_key returned last: the gate HL starts here */

double input_stamp(void)
{
	double t = stamp_ms;

	stamp_ms = 0;
	return t;
}

static bool read_line(const char *path, char *out, size_t n)
{
	FILE *f = fopen(path, "r");

	out[0] = '\0';
	if (!f)
		return false;
	if (fgets(out, (int)n, f))
		out[strcspn(out, "\n")] = '\0';
	fclose(f);
	return out[0] != '\0';
}

/* the event nodes of the stock remote, by the sysfs the way h713-keys finds them */
static void discover(void)
{
	const char *sys = getenv("H713_SETTINGS_SYS");
	char base[200], p[512], name[64], vendor[16], product[16];
	struct dirent *e;
	DIR *d;

	snprintf(base, sizeof(base), "%s/class/input", sys && *sys ? sys : "/sys");
	d = opendir(base);
	while (d && (e = readdir(d)) && nfd < MAXDEV) {
		bool ble, ir;

		if (strncmp(e->d_name, "event", 5))
			continue;
		snprintf(p, sizeof(p), "%s/%s/device/id/vendor", base, e->d_name);
		read_line(p, vendor, sizeof(vendor));
		snprintf(p, sizeof(p), "%s/%s/device/id/product", base, e->d_name);
		read_line(p, product, sizeof(product));
		snprintf(p, sizeof(p), "%s/%s/device/name", base, e->d_name);
		read_line(p, name, sizeof(name));
		ble = !strcmp(vendor, "1d5a") && !strcmp(product, "c081");
		ir = !strcmp(name, "sunxi-ir");
		if (!ble && !ir)
			continue;
		snprintf(p, sizeof(p), "%s/%s", getenv("H713_SETTINGS_DEV") ? getenv("H713_SETTINGS_DEV") : "/dev/input", e->d_name);
		if ((fd[nfd] = open(p, O_RDONLY | O_NONBLOCK | O_CLOEXEC)) >= 0)
			nfd++;
	}
	if (d)
		closedir(d);
}

/* the devices to hold: H713_SETTINGS_INPUT = a comma-separated list of files (the tests: FIFOs, which cannot be grabbed) */
int input_open(void)
{
	const char *list = getenv("H713_SETTINGS_INPUT");

	if (list && *list) {
		char buf[512], *save = NULL;

		snprintf(buf, sizeof(buf), "%s", list);
		for (char *p = strtok_r(buf, ",", &save); p && nfd < MAXDEV; p = strtok_r(NULL, ",", &save))
			if ((fd[nfd] = open(p, O_RDONLY | O_NONBLOCK | O_CLOEXEC)) >= 0)
				nfd++;
		return nfd;
	}
	discover();
	for (int i = 0; i < nfd; i++)
		if (ioctl(fd[i], EVIOCGRAB, 1)) {
			fprintf(stderr, "h713-settings: the remote's device cannot be held: %s\n", strerror(errno));
			input_close();
			return 0;	/* a page the keys of which Kodi would share is worse than none */
		}
	grabbed = nfd > 0;
	return nfd;
}

void input_close(void)
{
	for (int i = 0; i < nfd; i++) {
		if (grabbed)
			ioctl(fd[i], EVIOCGRAB, 0);
		close(fd[i]);
	}
	nfd = 0;
	grabbed = false;
}

/* the key names of the kernel: what h713-keys reads (docs/tools/h713-keys.md). Menu (KEY_COMPOSE since the rule, KEY_MENU) is
 * recognised and has no meaning on the page. */
static int map(int code, int value)
{
	switch (code) {			/* the arrows go on repeating: a held key moves on */
	case KEY_UP:
		return KE_UP;
	case KEY_DOWN:
		return KE_DOWN;
	case KEY_LEFT:
		return KE_LEFT;
	case KEY_RIGHT:
		return KE_RIGHT;
	}
	if (value != 1)
		return 0;		/* the rest counts on the press, not on the repeat */
	switch (code) {
	case KEY_ENTER:			/* the remote's OK since 70-h713-remote.rules: a client (cage, Kodi) gets no code above 247 */
	case 352:			/* KEY_OK: the same key without the rule */
	case 353:			/* KEY_SELECT: the Bluetooth remote's "Menu Pick" without it */
		return KE_OK;
	case KEY_BACK:
		return KE_BACK;
	case KEY_HOMEPAGE:
		return KE_HOME;
	case KEY_POWER:
		return KE_POWER;
	case KEY_VOLUMEUP:
		return KE_VOL_UP;
	case KEY_VOLUMEDOWN:
		return KE_VOL_DOWN;
	case KEY_MUTE:
		return KE_MUTE;
	case KEY_F4:
		return KE_FOCUS_UP;
	case KEY_F5:
		return KE_FOCUS_DOWN;
	}
	return 0;
}

int input_key(int timeout_ms)
{
	struct pollfd p[MAXDEV];

	for (int i = 0; i < nfd; i++)
		p[i] = (struct pollfd){ fd[i], POLLIN, 0 };
	if (!nfd) {
		if (timeout_ms > 0)
			usleep((useconds_t)timeout_ms * 1000);
		return KE_NONE;
	}
	if (poll(p, (nfds_t)nfd, timeout_ms) <= 0)
		return KE_NONE;
	for (int i = 0; i < nfd; i++) {
		struct input_event ev;

		if (!(p[i].revents & POLLIN))
			continue;
		if (read(fd[i], &ev, sizeof(ev)) == (ssize_t)sizeof(ev) && ev.type == EV_KEY) {
			int k = map(ev.code, ev.value);

			if (k) {
				stamp_ms = ev.time.tv_sec * 1e3 + ev.time.tv_usec / 1e3;
				return k;
			}
		}
	}
	return KE_NONE;
}

/* the press the page cannot take: h713-power's countdown (the datagram h713-keys sends for a Power press with its launcher open) */
void input_power(void)
{
	const char *path = getenv("H713_SETTINGS_POWER");
	struct sockaddr_un a = { .sun_family = AF_UNIX };
	int s = socket(AF_UNIX, SOCK_DGRAM | SOCK_CLOEXEC, 0);

	snprintf(a.sun_path, sizeof(a.sun_path), "%s", path && *path ? path : "/run/h713-power.sock");
	if (s >= 0) {
		if (sendto(s, "short", 5, MSG_NOSIGNAL, (struct sockaddr *)&a, sizeof(a)) < 0)
			fprintf(stderr, "h713-settings: h713-power does not answer (%s) - the Power press is lost\n", strerror(errno));
		close(s);
	}
}
