/* SPDX-License-Identifier: GPL-2.0 */
/*
 * Which display stack h713-tv runs on (docs/tools/h713-tv.md, "The clean stack"), without a device: main.c is compiled
 * into this file and the decision is asked directly. What is checked: a capture node's name belongs to the vendor stack,
 * to the clean one or to neither; the node -d names decides, and a name of neither (or one that could not be read)
 * keeps the vendor path and its old failure; without -d the vendor's node wins when it is there, the clean one is taken
 * only without it, and with neither the vendor path stays, message for message; each stack names its own DRM driver
 * and capture node; the two names stay apart in the 15 characters QUERYCAP carries.
 *
 *   test_stack     exit 0 when every case passed
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

int main(void)
{
	/* the names */
	check(stack_of_v4l2_name("sun50i-h713-hdmirx") == STACK_VENDOR, "sun50i-h713-hdmirx is the vendor stack's node");
	check(stack_of_v4l2_name("h713-hdmirx-clean") == STACK_CLEAN, "h713-hdmirx-clean is the clean stack's node");
	check(stack_of_v4l2_name("cedrus") < 0, "cedrus is neither");
	check(stack_of_v4l2_name("sun50i-h713-hdm") < 0, "a truncated name is neither (sysfs carries the whole name)");
	check(stack_of_v4l2_name("") < 0, "an empty name is neither");

	/* -d names a node: its name decides */
	check(stack_decide(true, STACK_CLEAN, false, false) == STACK_CLEAN, "-d on the clean node: clean");
	check(stack_decide(true, STACK_VENDOR, false, false) == STACK_VENDOR, "-d on the vendor node: vendor");
	check(stack_decide(true, -1, false, true) == STACK_VENDOR,
	      "-d on a node of neither: the vendor path, which refuses that node as it always did");
	check(stack_decide(true, STACK_VENDOR, false, true) == STACK_VENDOR,
	      "-d decides even when the search would find the clean node (the udev instance is the node)");

	/* no -d: the search */
	check(stack_decide(false, -1, false, false) == STACK_VENDOR, "nothing found: the vendor path and its old failure");
	check(stack_decide(false, -1, true, false) == STACK_VENDOR, "the vendor node alone: vendor");
	check(stack_decide(false, -1, false, true) == STACK_CLEAN, "the clean node (or h713_drm) alone: clean");
	check(stack_decide(false, -1, true, true) == STACK_VENDOR, "both: the vendor's, as before the clean stack existed");

	/* what each stack then looks for */
	stack = STACK_VENDOR;
	check(!strcmp(stack_drm(), "sun50i-h713-afbd") && !strcmp(stack_v4l2(), "sun50i-h713-hdmirx"),
	      "vendor: sun50i-h713-afbd and sun50i-h713-hdmirx");
	stack = STACK_CLEAN;
	check(!strcmp(stack_drm(), "h713-drm") && !strcmp(stack_v4l2(), "h713-hdmirx-clean"),
	      "clean: h713-drm and h713-hdmirx-clean");
	stack = STACK_VENDOR;

	/* QUERYCAP's driver[16] confirms the node by 15 characters: the two must differ there */
	check(strncmp(V4L2_DRIVER, V4L2_DRIVER_CLEAN, sizeof(((struct v4l2_capability *)0)->driver) - 1) != 0,
	      "the two capture names differ within QUERYCAP's 15 characters");

	printf(failed ? "FAILED: %d\n" : "all passed\n", failed);
	return failed ? 1 : 0;
}
