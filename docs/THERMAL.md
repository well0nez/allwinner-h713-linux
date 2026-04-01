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


## Fan Tachometer

The fan speed is read via **hrtimer GPIO-DAT register polling** on PH17 (GPIO 241)
at 100us intervals. This is the only working method on the H713 SoC.

GPIO-IRQ was extensively tested but does not work on H713 extended PH pins (PH11-PH19):
- IRQ registers correctly via  + 
- Pin value toggles visibly (fan pulses confirmed via GPIO reads)
- But the EINT hardware controller never fires the interrupt (counter stays 0)
- Confirmed by multiple independent investigations
- Stock kernel appears to use IRQ but may have vendor-specific EINT init we lack

The hrtimer polling approach reads the PIO DAT register directly via 
bypassing the GPIO subsystem (because  on H713 can alter the pin
function and break the input path). RPM is calculated from edge transitions counted
over 1-second intervals. Typical readings: 2500-2600 RPM at normal operation.

Fan stall detection is active: if RPM drops below threshold for multiple cycles,
the system triggers emergency shutdown (stock behavior).
