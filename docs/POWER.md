# HY310 Power Management Subsystem

## Status: WORKING (reboot, poweroff, watchdog, power domains)

## Reboot / Poweroff

- **Reboot**: working via sunxi-wdt watchdog reset
- **Poweroff**: working

## Watchdog

| Watchdog | Address    | Compatible    |
|----------|------------|---------------|
| Main WDT | 0x02051000 | sun6i-a31-wdt |
| R_WDOG   | 0x07020400 | --            |

Note: Main watchdog is at 0x02051000, NOT 0x030090a0 (H6 address). Do not copy H6 DTS.

## ARISC (OpenRISC)

- ARISC firmware (arisc.fex) is loaded by U-Boot before kernel hand-off
- Handles low-level power sequencing on behalf of the ARM side

## Power Domains

Driver: allwinner,tv303-pmu at 0x07001000

| Domain   | Description     |
|----------|-----------------|
| pd_gpu   | GPU             |
| pd_tvfe  | TV frontend     |
| pd_tvcap | TV capture      |
| pd_ve    | Video engine    |
| pd_av1   | AV1 decoder     |

## Boot Arguments

    panic=5             # auto-reboot 5s after kernel panic
    clk_ignore_unused   # required -- clock parent management not yet complete

clk_ignore_unused must remain until the clock tree is fully described and all parent
relationships are correct in the DTS/CCF. Removing it prematurely will cause random
clocks to be gated and break peripherals.
