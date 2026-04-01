#!/usr/bin/env python3
"""
Compare U-Boot DTB vs Mainline DTB.
Extracts all properties from both DTBs into CSV format,
then produces a diff report showing:
  - Missing nodes/properties in our mainline DTB
  - Mismatched values between stock and mainline
  - Properties that exist in mainline but not in stock

Usage:
  python3 compare_dtb.py <uboot_dtb.dts> <mainline_dtb.dts>

Output:
  - uboot_dtb_extract.csv
  - mainline_dtb_extract.csv
  - dtb_comparison_report.csv
"""

import sys
import re
import csv
from pathlib import Path
from collections import OrderedDict


def parse_dts(filepath):
    """Parse a DTS file into a flat dict of node_path -> {property: value}"""
    text = Path(filepath).read_text(errors="replace")

    entries = []  # list of (node_path, property_name, value, line_number)
    node_stack = []
    current_path = "/"

    for lineno, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()

        # Skip empty lines and comments
        if not stripped or stripped.startswith("//") or stripped.startswith("/*"):
            continue

        # Track node entry
        # Match: "nodename {" or "nodename@addr {"
        node_match = re.match(r"^([a-zA-Z0-9_@#,.-]+)\s*\{", stripped)
        if node_match:
            name = node_match.group(1)
            node_stack.append(name)
            current_path = "/" + "/".join(node_stack)
            entries.append((current_path, "__NODE__", "exists", lineno))
            continue

        # Track node exit
        if stripped.startswith("};") or stripped == "}":
            if node_stack:
                node_stack.pop()
                current_path = "/" + "/".join(node_stack) if node_stack else "/"
            continue

        # Parse property = value;
        prop_match = re.match(r"^([a-zA-Z0-9_#,.+-]+)\s*=\s*(.+?)\s*;", stripped)
        if prop_match:
            prop_name = prop_match.group(1)
            prop_value = prop_match.group(2).strip()
            entries.append((current_path, prop_name, prop_value, lineno))
            continue

        # Parse boolean property (no value)
        bool_match = re.match(r"^([a-zA-Z0-9_#,.+-]+)\s*;", stripped)
        if bool_match:
            prop_name = bool_match.group(1)
            entries.append((current_path, prop_name, "<boolean>", lineno))
            continue

    return entries


def extract_gpio_info(value):
    """Try to decode GPIO references from property values"""
    # Match patterns like <0x23 0x0b 0x03 0x01 0x00 0x00 0x01>
    hex_match = re.findall(r"<(0x[0-9a-fA-F]+(?:\s+0x[0-9a-fA-F]+)*)>", value)
    if hex_match:
        return hex_match
    return None


def write_csv(entries, filepath):
    """Write parsed entries to CSV"""
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["node_path", "property", "value", "line", "gpio_decode"])
        for node_path, prop, value, line in entries:
            gpio = extract_gpio_info(value)
            gpio_str = str(gpio) if gpio else ""
            writer.writerow([node_path, prop, value, line, gpio_str])
    print(f"  Written: {filepath} ({len(entries)} entries)")


def compare_dtbs(stock_entries, mainline_entries):
    """Compare two DTB extracts and produce a report"""
    # Build lookup dicts
    stock_dict = {}
    for path, prop, value, line in stock_entries:
        key = f"{path}::{prop}"
        stock_dict[key] = (value, line)

    mainline_dict = {}
    for path, prop, value, line in mainline_entries:
        key = f"{path}::{prop}"
        mainline_dict[key] = (value, line)

    report = []

    # Find items in stock but missing in mainline
    for key, (value, line) in stock_dict.items():
        if key not in mainline_dict:
            path, prop = key.split("::", 1)
            report.append(
                {
                    "status": "MISSING_IN_MAINLINE",
                    "node_path": path,
                    "property": prop,
                    "stock_value": value,
                    "mainline_value": "",
                    "stock_line": line,
                    "mainline_line": "",
                    "note": "Present in U-Boot DTB but absent in mainline DTB",
                }
            )

    # Find items in mainline but not in stock
    for key, (value, line) in mainline_dict.items():
        if key not in stock_dict:
            path, prop = key.split("::", 1)
            report.append(
                {
                    "status": "EXTRA_IN_MAINLINE",
                    "node_path": path,
                    "property": prop,
                    "stock_value": "",
                    "mainline_value": value,
                    "stock_line": "",
                    "mainline_line": line,
                    "note": "Present in mainline DTB but absent in U-Boot DTB",
                }
            )

    # Find mismatches
    for key in stock_dict:
        if key in mainline_dict:
            stock_val, stock_line = stock_dict[key]
            main_val, main_line = mainline_dict[key]
            if stock_val != main_val:
                path, prop = key.split("::", 1)
                report.append(
                    {
                        "status": "VALUE_MISMATCH",
                        "node_path": path,
                        "property": prop,
                        "stock_value": stock_val,
                        "mainline_value": main_val,
                        "stock_line": stock_line,
                        "mainline_line": main_line,
                        "note": "Both exist but values differ",
                    }
                )

    return report


def main():
    if len(sys.argv) < 3:
        print("Usage: python3 compare_dtb.py <uboot_dtb.dts> <mainline_dtb.dts>")
        print("  Produces CSV extracts and comparison report")
        sys.exit(1)

    stock_dts = sys.argv[1]
    mainline_dts = sys.argv[2]

    print(f"Parsing stock U-Boot DTB: {stock_dts}")
    stock_entries = parse_dts(stock_dts)
    print(f"  Found {len(stock_entries)} entries")

    print(f"Parsing mainline DTB: {mainline_dts}")
    mainline_entries = parse_dts(mainline_dts)
    print(f"  Found {len(mainline_entries)} entries")

    # Write CSV extracts
    stock_csv = Path(stock_dts).stem + "_extract.csv"
    mainline_csv = Path(mainline_dts).stem + "_extract.csv"
    write_csv(stock_entries, stock_csv)
    write_csv(mainline_entries, mainline_csv)

    # Compare
    print("\nComparing...")
    report = compare_dtbs(stock_entries, mainline_entries)

    # Write comparison report
    report_file = "dtb_comparison_report.csv"
    with open(report_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "status",
                "node_path",
                "property",
                "stock_value",
                "mainline_value",
                "stock_line",
                "mainline_line",
                "note",
            ],
        )
        writer.writeheader()
        for row in sorted(report, key=lambda r: (r["status"], r["node_path"])):
            writer.writerow(row)

    # Summary
    missing = sum(1 for r in report if r["status"] == "MISSING_IN_MAINLINE")
    extra = sum(1 for r in report if r["status"] == "EXTRA_IN_MAINLINE")
    mismatch = sum(1 for r in report if r["status"] == "VALUE_MISMATCH")

    print(f"\n=== Comparison Report: {report_file} ===")
    print(f"  MISSING in mainline:  {missing}")
    print(f"  EXTRA in mainline:    {extra}")
    print(f"  VALUE MISMATCH:       {mismatch}")
    print(f"  Total differences:    {len(report)}")

    # Print critical findings
    print("\n=== Critical Mismatches (GPIO/Power/Clock related) ===")
    critical_keywords = [
        "gpio",
        "power",
        "fan",
        "usb",
        "led",
        "pwm",
        "panel",
        "backlight",
        "bl_en",
        "standby",
        "hold",
        "vdd",
        "vcc",
        "clk",
        "clock",
        "mmc",
        "sdc",
        "wlan",
        "wifi",
        "rfkill",
    ]
    for row in report:
        path_prop = (row["node_path"] + row["property"]).lower()
        if any(kw in path_prop for kw in critical_keywords):
            print(f"  [{row['status']}] {row['node_path']} :: {row['property']}")
            if row["stock_value"]:
                print(f"    Stock:    {row['stock_value'][:120]}")
            if row["mainline_value"]:
                print(f"    Mainline: {row['mainline_value'][:120]}")


if __name__ == "__main__":
    main()
