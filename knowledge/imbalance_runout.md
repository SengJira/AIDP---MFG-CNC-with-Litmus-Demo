# Imbalance, toolholder runout and alignment

## What to look for

Rotor imbalance, worn toolholder taper, poor alignment or a recent tool change can create a smooth, broad vibration rise. The signature is different from bearing spall because it lacks sharp, impulsive peaks.

## Typical symptoms

- **VIB_X_MM_S and VIB_Y_MM_S**: Both directions rise smoothly over hours or days. The ratio between X and Y usually stays fairly constant.
- **BEARING_TEMP_C**: May increase slightly because of the extra cyclic load, but less than during true bearing degradation.
- **ACOUSTIC_DB**: Rises gradually; the sound is a low-frequency rumble or hum rather than a sharp grinding noise.
- **SPINDLE_RPM and SPINDLE_LOAD_PCT**: Often normal and steady.
- **COOLANT_FLOW_LPM and COOLANT_PRESSURE_BAR**: Typically unaffected.

## Why it matters

Imbalance and runout wear bearings and tool seats faster, but they usually evolve more slowly than an internal bearing spall. Urgency is lower, but ignoring them turns a cheap balancing or toolholder job into an expensive bearing replacement later.

## Recommended actions

1. Review recent tool changes, collet swaps or crash events.
2. Check tool concentricity and runout with a dial indicator.
3. Perform a balance run or ask the spindle vendor for field balancing.
4. Inspect the toolholder taper and spindle nose for nicks or contamination.
