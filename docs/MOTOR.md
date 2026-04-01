# HY310 Keystone Motor Subsystem

## Status: PARTIAL — sysfs works, physical movement inconsistent, limit switch suspect

## Hardware

- **Driver**: `hy310-keystone-motor`
- Motor type: 4-phase stepper
- Control: GPIO-driven phases
- Limit switch: **PH14** (always reads LOW — possible hardware damage or wiring fault)

## Driver Design

- Work-queue based asynchronous movement
- Step tables configurable via DTS
- Sysfs interface exposed for user-space control

## Known Issues

1. **Limit switch PH14 always reads LOW**: The homing sequence cannot reliably detect the limit position. Either the switch is damaged or the wiring is incorrect. Do not run continuous homing loops without a software position limit to avoid mechanical damage.
2. **Physical movement inconsistent after boot homing**: Motor phases may not be in a known state after the homing attempt fails. A manual phase reset or power cycle may be required.

## Next Steps

1. Probe PH14 physically to determine if the limit switch is electrically connected
2. Add a maximum step count guard to the homing routine
3. Verify GPIO phase ordering against the motor datasheet
