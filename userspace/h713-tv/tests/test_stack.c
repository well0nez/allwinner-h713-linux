/* SPDX-License-Identifier: GPL-2.0 */
/*
 * Which display stack h713-tv runs on (docs/tools/h713-tv.md, "The clean stack"), without a device: main.c is compiled
 * into this file and the decision is asked directly. What is checked: a capture node's name belongs to the vendor stack,
 * to the clean one or to neither; the node -d names decides, and a name of neither (or one that could not be read)
 * keeps the vendor path and its old failure; without -d the vendor's node wins when it is there, the clean one is taken
 * only without it, and with neither the vendor path stays, message for message; each stack names its own DRM driver
 * and capture node; QUERYCAP confirms a node per stack: the vendor's by the 15 characters of its driver field, the
 * clean one's by driver "h713_drm" and card "h713-hdmirx-clean" (clean 8e24be3), and neither takes the other's.
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

static struct v4l2_capability cap_of(const char *driver, const char *card)
{
	struct v4l2_capability c;

	memset(&c, 0, sizeof(c));
	strncpy((char *)c.driver, driver, sizeof(c.driver) - 1);
	strncpy((char *)c.card, card, sizeof(c.card) - 1);
	return c;
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

	/* QUERYCAP: what each stack takes as its node */
	{
		struct v4l2_capability vendor = cap_of("sun50i-h713-hdm", "sun50i-h713-hdmirx");
		struct v4l2_capability clean = cap_of("h713_drm", "h713-hdmirx-clean");
		struct v4l2_capability clean_old = cap_of("h713-hdmirx-cle", "H713 HDMI receiver (clean)");
		struct v4l2_capability other_card = cap_of("h713_drm", "something-else");
		struct v4l2_capability cedrus = cap_of("cedrus", "cedrus");

		stack = STACK_VENDOR;
		check(capture_cap_matches(&vendor), "vendor: the truncated driver \"sun50i-h713-hdm\" is the node");
		check(!capture_cap_matches(&clean) && !capture_cap_matches(&cedrus),
		      "vendor: neither h713_drm's node nor cedrus");
		stack = STACK_CLEAN;
		check(capture_cap_matches(&clean), "clean: driver h713_drm, card h713-hdmirx-clean is the node");
		check(!capture_cap_matches(&vendor), "clean: not the vendor's node");
		check(!capture_cap_matches(&other_card), "clean: h713_drm with another card is not the node");
		check(!capture_cap_matches(&clean_old), "clean: the QUERYCAP before 8e24be3 is not taken");
		check(!capture_cap_matches(&cedrus), "clean: not cedrus");
		stack = STACK_VENDOR;
	}

	printf(failed ? "FAILED: %d\n" : "all passed\n", failed);
	return failed ? 1 : 0;
}
