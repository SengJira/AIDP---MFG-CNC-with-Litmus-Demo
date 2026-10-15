# Coolant filter restriction and chip blockage

## What to look for

A restricted coolant filter, blocked chip conveyor or clogged nozzle creates a process/utility signature rather than a mechanical spindle fault.

## Typical symptoms

- **COOLANT_FLOW_LPM**: Falls below the normal band. The drop may be gradual as a paper filter loads with fines, or sudden if a chip clogs a nozzle.
- **COOLANT_PRESSURE_BAR**: Often rises as the pump tries to push the same volume through a smaller opening, or falls if the pump cavitates.
- **BEARING_TEMP_C**: Can rise because the same coolant also removes heat from the spindle. Flow is therefore more important than pressure alone.
- **ACOUSTIC_DB**: May increase because of pump or fluid noise.
- **VIB_X_MM_S and VIB_Y_MM_S**: Usually stay in the normal range unless coolant starvation causes thermal distortion.

## Why it matters

Running with low coolant flow causes heat build-up, tool wear and poor surface finish. In extreme cases it can lead to thermal seizure of the spindle or fire in the cutting zone.

## Recommended actions

1. Check the coolant filter delta-pressure or service timer.
2. Inspect chip drag, conveyors and tank for blockages.
3. Verify coolant concentration and temperature; foaming lowers effective flow.
4. Clean or replace the filter element and confirm flow returns to the normal band.
