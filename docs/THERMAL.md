# HY310 Thermal Subsystem

## Status: WORKING

## THS (Thermal Sensor)

- **Address**: `0x02009400`
- **Driver**: `sun8i-thermal`
- **Zones**: 2
  - CPU thermal: ~65°C typical
  - GPU thermal: ~66°C typical
- **SID calibration**: offset `0x14`, 8 bytes

## Board Thermal Management

The `hy310-board-mgr` driver handles board-level thermal and power management:

- Fan PWM control
- USB power GPIO
- NTC thermistor via LRADC
- Power LED / status LED
- Fan power GPIO
- Power hold
- DC-in detect
- Charge-OK signal
- Battery GPADC
- NTC sensors

The stock `pwm_fan` driver was the reference for this functionality.
