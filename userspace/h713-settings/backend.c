// SPDX-License-Identifier: GPL-2.0
/*
 * The way to the tools: a ctl socket (one line, one answer, hang up - h713-tv, h713-warp), a program run for its
 * output or started and left, and a "key = value" file of /etc/h713 changed in place. No shell anywhere.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <sys/un.h>
#include <sys/wait.h>

#include "settings.h"

const char *p_tv, *p_warp, *p_etc, *p_bin;
char reply[2048];

/* the answer's first word decides: "ok ..." or "error ..." */
bool ctl(const char *sock, const char *line, char *out, size_t n)
{
	struct sockaddr_un addr = { .sun_family = AF_UNIX };
	struct timeval tmo = { 3, 0 };
	size_t len = 0;
	ssize_t got;
	int fd = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);

	out[0] = '\0';
	snprintf(addr.sun_path, sizeof(addr.sun_path), "%s", sock);
	if (fd < 0)
		return false;
	setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tmo, sizeof(tmo));
	setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &tmo, sizeof(tmo));
	if (connect(fd, (struct sockaddr *)&addr, sizeof(addr)) || send(fd, line, strlen(line), MSG_NOSIGNAL) < 0) {
		snprintf(out, n, "error %s: %s", sock, strerror(errno));
		close(fd);
		return false;
	}
	while (len + 1 < n && (got = recv(fd, out + len, n - len - 1, 0)) > 0)
		len += (size_t)got;
	out[len] = '\0';
	close(fd);
	return !strncmp(out, "ok", 2);
}

static bool say(const char *sock, const char *fmt, va_list ap)
{
	char line[160];

	vsnprintf(line, sizeof(line) - 1, fmt, ap);
	strcat(line, "\n");
	return ctl(sock, line, reply, sizeof(reply));
}

bool tv(const char *fmt, ...)
{
	va_list ap;
	bool ok;

	va_start(ap, fmt);
	ok = say(p_tv, fmt, ap);
	va_end(ap);
	return ok;
}

bool warp(const char *fmt, ...)
{
	va_list ap;
	bool ok;

	va_start(ap, fmt);
	ok = say(p_warp, fmt, ap);
	va_end(ap);
	return ok;
}

/* the tool by its name, or under p_bin (the tests' stand-ins) */
static void exec_tool(const char *const *argv)
{
	char path[256];
	int nul = open("/dev/null", O_RDONLY);

	if (nul >= 0)
		dup2(nul, 0);		/* a tool never reads the page's keys */

	if (p_bin && *p_bin) {
		snprintf(path, sizeof(path), "%s/%s", p_bin, argv[0]);
		execv(path, (char *const *)argv);
	} else {
		execvp(argv[0], (char *const *)argv);
	}
	_exit(127);
}

/* run a program and collect what it prints (stdout and stderr), at most timeout_ms; its exit status, -1 not run */
int run(const char *const *argv, char *out, size_t n, int timeout_ms)
{
	struct timespec t0, t;
	int p[2], status = 0, left = timeout_ms;
	size_t len = 0;
	pid_t pid;

	out[0] = '\0';
	if (pipe2(p, O_CLOEXEC))
		return -1;
	pid = fork();
	if (pid < 0) {
		close(p[0]);
		close(p[1]);
		return -1;
	}
	if (!pid) {
		dup2(p[1], 1);
		dup2(p[1], 2);
		exec_tool(argv);
	}
	close(p[1]);
	clock_gettime(CLOCK_MONOTONIC, &t0);
	for (;;) {
		struct pollfd pf = { p[0], POLLIN, 0 };
		ssize_t got;

		if (left <= 0 || poll(&pf, 1, left) <= 0) {
			kill(pid, SIGKILL);
			status = -1;
			break;
		}
		got = read(p[0], out + len, len + 1 < n ? n - len - 1 : 0);
		if (got <= 0)
			break;
		len += (size_t)got;
		out[len] = '\0';
		clock_gettime(CLOCK_MONOTONIC, &t);
		left = timeout_ms - (int)((t.tv_sec - t0.tv_sec) * 1000 + (t.tv_nsec - t0.tv_nsec) / 1000000);
	}
	close(p[0]);
	if (waitpid(pid, &status, 0) < 0)
		return -1;
	return WIFEXITED(status) ? WEXITSTATUS(status) : -1;
}

/* started, not waited for; the caller finds out with waitpid. Its output goes nowhere, its errors to ours. */
int spawn(const char *const *argv)
{
	pid_t pid = fork();

	if (pid < 0)
		return -1;
	if (!pid) {
		int nul = open("/dev/null", O_WRONLY);

		if (nul >= 0)
			dup2(nul, 1);
		exec_tool(argv);
	}
	return pid;
}

const char *etc(const char *name)
{
	static char path[4][256];
	static int i;

	i = (i + 1) & 3;
	snprintf(path[i], sizeof(path[i]), "%s/%s", p_etc, name);
	return path[i];
}

/* --- "key = value" files: read a key, change one line in place (comments and the other keys stay) --------- */

static char *slurp(const char *file, size_t *len)
{
	FILE *f = fopen(file, "r");
	char *b = NULL;
	long n;

	if (!f)
		return NULL;
	fseek(f, 0, SEEK_END);
	n = ftell(f);
	rewind(f);
	if (n >= 0 && n < (1 << 20) && (b = malloc((size_t)n + 1))) {
		*len = fread(b, 1, (size_t)n, f);
		b[*len] = '\0';
	}
	fclose(f);
	return b;
}

/* the line's key if it is "key = value" (leading blanks allowed), the value without its comment */
static bool split(char *line, char **key, char **val)
{
	char *c = strchr(line, '#'), *eq;

	if (c)
		*c = '\0';
	eq = strchr(line, '=');
	if (!eq)
		return false;
	*eq = '\0';
	*key = line + strspn(line, " \t");
	for (char *e = eq; e > *key && (e[-1] == ' ' || e[-1] == '\t'); e--)
		e[-1] = '\0';
	*val = eq + 1 + strspn(eq + 1, " \t");
	for (char *e = *val + strlen(*val); e > *val && (e[-1] == ' ' || e[-1] == '\t' || e[-1] == '\n' || e[-1] == '\r'); e--)
		e[-1] = '\0';
	return **key;
}

bool conf_get(const char *file, const char *key, char *out, size_t n)
{
	size_t len = 0;
	char *buf = slurp(file, &len), *save = NULL, *line;
	bool found = false;

	out[0] = '\0';
	if (!buf)
		return false;
	for (line = strtok_r(buf, "\n", &save); line; line = strtok_r(NULL, "\n", &save)) {
		char *k, *v;

		if (split(line, &k, &v) && !strcmp(k, key)) {
			snprintf(out, n, "%s", v);
			found = true;		/* the last one wins, as in the daemons */
		}
	}
	free(buf);
	return found;
}

bool conf_set(const char *file, const char *key, const char *val)
{
	char tmp[300], want[160];
	size_t len = 0;
	char *buf = slurp(file, &len), *p;
	struct stat st = { .st_mode = 0644 };
	int last = -1, no = 0;
	FILE *f;
	int fd;

	snprintf(tmp, sizeof(tmp), "%s.new", file);
	snprintf(want, sizeof(want), "%s = %s", key, val);
	/* the last line of the key is the one that counts for the daemons (conf_get), so it is the one changed */
	for (p = buf; p && *p; no++) {
		char *eol = strchr(p, '\n'), line[512], *k, *v;
		size_t l = eol ? (size_t)(eol - p) : strlen(p);

		snprintf(line, sizeof(line), "%.*s", (int)l, p);
		if (split(line, &k, &v) && !strcmp(k, key))
			last = no;
		p += l + (eol ? 1 : 0);
	}
	stat(file, &st);
	fd = open(tmp, O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC, st.st_mode & 0777);
	f = fd >= 0 ? fdopen(fd, "w") : NULL;
	if (!f) {
		free(buf);
		return false;
	}
	for (p = buf, no = 0; p && *p; no++) {
		char *eol = strchr(p, '\n');
		size_t l = eol ? (size_t)(eol - p) : strlen(p);

		if (no == last)
			fprintf(f, "%s\n", want);
		else
			fprintf(f, "%.*s\n", (int)l, p);
		p += l + (eol ? 1 : 0);
	}
	if (last < 0)
		fprintf(f, "%s\n", want);
	free(buf);
	fflush(f);
	fsync(fd);
	if (fclose(f) || rename(tmp, file)) {
		unlink(tmp);
		return false;
	}
	return true;
}
