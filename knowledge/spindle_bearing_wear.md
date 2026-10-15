# Spindle bearing wear — drive end

## What to look for

A failing drive-end spindle bearing typically produces a multi-signal mechanical signature. It rarely shows only one high reading.

## Typical symptoms

- **VIB_X_MM_S and VIB_Y_MM_S**: Both directions rise together; VIB_X often leads. The rise can be impulsive with sharp peaks when the rolling elements pass over a spall or pit.
- **BEARING_TEMP_C**: Gradual increase as friction grows. In severe cases the temperature can climb several degrees above the normal band.
- **ACOUSTIC_DB**: A high-pitched sound or grinding noise raises the acoustic emission well above the ambient machine noise.
- **MOTOR_CURRENT_A**: Small rise because the spindle motor works harder to maintain RPM against increased drag.
- **SPINDLE_RPM and LOAD_PCT**: Usually remain within normal setpoints because the control loop compensates.

## Why it matters

Bearing wear is one of the most time-critical spindle faults. An impulsive rise means material is coming off the races or rollers. Delaying action risks catastrophic secondary damage to the shaft, housing and finished parts.

## Recommended actions

1. Inspect the drive-end bearing and listen to the spindle with a stethoscope or contact microphone.
2. Capture a vibration spectrum and look for bearing defect frequencies (BPFO, BPFI, BSF, FTF).
3. Check lubrication condition, flow and spindle warm-up cycle.
4. If peaks continue to climb, schedule a controlled stop and bearing replacement before the next production run.
