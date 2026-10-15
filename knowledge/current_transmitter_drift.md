# Motor-current transmitter drift

## What to look for

A drifting current transmitter or a loose terminal in the motor-current signal path reports a load change that the machine itself does not feel.

## Typical symptoms

- **MOTOR_CURRENT_A**: Rises or falls smoothly over a few days while the physical load is unchanged.
- **SPINDLE_LOAD_PCT**: Stays flat, within a few percent of the long-term average. The controller has no real load to fight.
- **VIB_X_MM_S and VIB_Y_MM_S**: Remain inside the normal baseline window.
- **BEARING_TEMP_C and ACOUSTIC_DB**: Not elevated.
- **FEED_RATE_MM_MIN and SPINDLE_RPM**: Match the programme and show normal variation.

## Why it matters

Instrument drift can look like an over-current alarm and trigger unnecessary maintenance. Labeling it as an instrumentation issue avoids false positives and keeps the maintenance team focused on real mechanical faults.

## Recommended actions

1. Verify the motor-current reading against a handheld current clamp or VFD display.
2. Check terminations and shielding on the current-signal cable.
3. Calibrate or replace the transmitter.
4. Mark the event as instrumentation drift in the label bank so future runs suppress similar patterns.
