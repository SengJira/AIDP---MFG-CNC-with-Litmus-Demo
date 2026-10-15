# Label Bank cross-machine transfer

## What is the Label Bank?

The Label Bank is a reusable library of confirmed findings. Each entry contains the signal pattern, the feature profile and the root-cause category that an engineer assigned.

## How it works

1. An operator reviews anomalous events on one machine.
2. Confirmed events are written to `labels` and promoted to `label_bank`.
3. When a sister machine — such as CNC-02 — starts showing a similar pattern, the seeded detection run loads the Label Bank and uses it to:
   - Raise scores for windows that match a confirmed mechanical fault profile.
   - Suppress events that match a dismissed or instrumentation pattern.

## Transfer rules

- **Mechanical and Process/Utility labels can be promoted** and transferred across similar equipment.
- **Instrumentation labels should not be promoted** because they depend on the specific transmitter and wiring of the source machine.
- Feature profiles are compared using simple distance metrics between signal means, standard deviations and smoothness indicators.
