#!/usr/bin/env python3
r"""
U-Boot Interrupt & Recovery Script for HY310.

Connects to the UART bridge (OrangePi TCP:9999) and:
1. Sends rapid keypresses to interrupt U-Boot during bootdelay (5s window)
2. Once at U-Boot prompt, can execute recovery commands

Usage from Windows:
  python uboot_interrupt.py                    # Just interrupt, drop to U-Boot prompt
  python uboot_interrupt.py --boot-usb         # Interrupt + boot from USB stick (recovery)
  python uboot_interrupt.py --cmd "printenv"   # Interrupt + run custom U-Boot command
  python uboot_interrupt.py --monitor          # Just monitor UART output (no interrupt)

Prerequisites:
  - UART bridge running on OrangePi (uart_bridge.py on port 9999)
  - HY310 must be rebooting or about to reboot (bootdelay window)

The HY310 must be rebooted FIRST (via SSH: ssh root@192.168.8.208 reboot),
then immediately run this script to catch the 5-second bootdelay window.

Typical recovery flow:
  1. ssh -i C:\Users\User\.ssh\id_ed25519 root@192.168.8.208 reboot
  2. python uboot_interrupt.py --boot-usb
"""

import socket
import time
import sys
import argparse
import threading
from typing import Optional

UART_HOST = "192.168.8.179"
UART_PORT = 9999

# U-Boot USB boot commands (loads known-good kernel from USB stick FAT32)
USB_BOOT_CMDS = [
    "usb start",
    "fatload usb 0:1 0x45000000 mboot32.00",
    "fatload usb 0:1 0x45400000 mboot32.01",
    "bootm 0x45000000",
]

# U-Boot recovery: flash stock boot_a back from boot_b
RESTORE_BOOT_A_CMDS = [
    "sunxi_flash read 45000000 boot_b",
    "sunxi_flash write 45000000 boot_a",
    "reset",
]


class UBootInterrupt:
    def __init__(self, host=UART_HOST, port=UART_PORT):
        self.host = host
        self.port = port
        self.sock: Optional[socket.socket] = None
        self.running = True
        self.at_prompt = False

    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(10)
        self.sock.connect((self.host, self.port))
        print(f"[+] Connected to UART bridge {self.host}:{self.port}")

        # Drain buffered data
        self.sock.settimeout(0.5)
        try:
            while True:
                d = self.sock.recv(4096)
                if not d:
                    break
        except socket.timeout:
            pass
        print("[+] Buffer drained, ready")

    def reader_thread(self):
        """Background thread to print all UART output."""
        if self.sock is None:
            return

        self.sock.settimeout(0.3)
        while self.running:
            try:
                data = self.sock.recv(4096)
                if data:
                    text = data.decode("utf-8", errors="replace")
                    sys.stdout.write(text)
                    sys.stdout.flush()
                    # Detect U-Boot prompt
                    if "=> " in text or "sunxi#" in text:
                        self.at_prompt = True
            except socket.timeout:
                continue
            except Exception:
                break

    def send(self, text):
        if self.sock is None:
            raise RuntimeError("UART socket is not connected")

        self.sock.sendall(text.encode())

    def send_line(self, cmd):
        """Send a command + carriage return."""
        self.send(cmd + "\r")
        time.sleep(0.3)

    def interrupt_uboot(self, timeout=15):
        """
        Send rapid keystrokes to interrupt U-Boot bootdelay.
        Returns True if U-Boot prompt detected within timeout.
        """
        print(f"[*] Sending interrupt keypresses for up to {timeout}s...")
        print("[*] (Reboot the HY310 now if not already rebooting)")

        start = time.time()
        while time.time() - start < timeout:
            # Send various keys that U-Boot recognizes as "any key"
            self.send(" ")
            self.send("\x1b")  # ESC
            self.send("\r")
            time.sleep(0.1)

            if self.at_prompt:
                print("\n[+] U-Boot prompt detected!")
                return True

        print(f"\n[-] Timeout after {timeout}s - no U-Boot prompt detected")
        return False

    def execute_commands(self, cmds):
        """Execute a sequence of U-Boot commands."""
        for cmd in cmds:
            print(f"[>] {cmd}")
            self.send_line(cmd)
            time.sleep(2)  # Wait for command to complete

    def monitor(self):
        """Just monitor UART output until Ctrl+C."""
        print("[*] Monitoring UART output (Ctrl+C to stop)...")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[*] Stopped monitoring")

    def run(self, mode="interrupt", custom_cmds=None):
        try:
            self.connect()

            # Start reader thread
            reader = threading.Thread(target=self.reader_thread, daemon=True)
            reader.start()

            if mode == "monitor":
                self.monitor()
                return

            # Interrupt U-Boot
            if self.interrupt_uboot():
                time.sleep(0.5)

                if mode == "boot-usb":
                    print("[*] Booting from USB stick (recovery)...")
                    self.execute_commands(USB_BOOT_CMDS)
                elif mode == "restore":
                    print("[*] Restoring boot_a from boot_b...")
                    self.execute_commands(RESTORE_BOOT_A_CMDS)
                elif mode == "custom" and custom_cmds:
                    print("[*] Executing custom commands...")
                    self.execute_commands(custom_cmds)
                else:
                    print("[*] At U-Boot prompt. Interactive mode.")
                    print("[*] Type commands (Ctrl+C to exit):")
                    try:
                        while True:
                            cmd = input()
                            self.send_line(cmd)
                    except (KeyboardInterrupt, EOFError):
                        pass

                # Wait a bit to see output
                time.sleep(3)
            else:
                print("[-] Could not interrupt U-Boot.")
                print("    Possible causes:")
                print("    - HY310 already booted past bootdelay")
                print("    - UART bridge not connected to correct serial port")
                print("    - HY310 not powered on / not rebooting")

        finally:
            self.running = False
            if self.sock:
                self.sock.close()


def main():
    parser = argparse.ArgumentParser(description="HY310 U-Boot Interrupt & Recovery")
    parser.add_argument(
        "--boot-usb",
        action="store_true",
        help="Interrupt U-Boot and boot from USB stick (recovery)",
    )
    parser.add_argument(
        "--restore",
        action="store_true",
        help="Restore boot_a from boot_b (factory recovery)",
    )
    parser.add_argument(
        "--cmd", nargs="+", help="Custom U-Boot commands to execute after interrupt"
    )
    parser.add_argument(
        "--monitor", action="store_true", help="Just monitor UART output (no interrupt)"
    )
    parser.add_argument(
        "--host", default=UART_HOST, help=f"UART bridge host (default: {UART_HOST})"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=UART_PORT,
        help=f"UART bridge port (default: {UART_PORT})",
    )

    args = parser.parse_args()

    tool = UBootInterrupt(args.host, args.port)

    if args.monitor:
        tool.run(mode="monitor")
    elif args.boot_usb:
        tool.run(mode="boot-usb")
    elif args.restore:
        tool.run(mode="restore")
    elif args.cmd:
        tool.run(mode="custom", custom_cmds=args.cmd)
    else:
        tool.run(mode="interrupt")


if __name__ == "__main__":
    main()
