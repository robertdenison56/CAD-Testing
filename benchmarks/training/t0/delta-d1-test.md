# e3-d1-test-qwen3.5-9b-q4km-lms-single-vague-t0-pin1 minus e3-d1-test-qwen3.5-9b-q4km-lms-single-vague-pin1

Set `d1-test`, paired on the 100 tasks both ran. Run: qwen/qwen3.5-9b · single · vague · system extra conventions-v1@89b9a471. Base: qwen/qwen3.5-9b · single · vague.

**Effective +2.7 (-4.5 to +9.8, 95%), not separated from zero**: 61.6 to 64.3. Tasks at 100: 22 to 33 (15 gained, 4 lost).

**Not like for like:**

- system_extra: conventions-v1@89b9a471 against None

| task type | tasks | base | run | gap | 95% | better / worse / same | base at 100 | run at 100 | gained / lost |
|---|---:|---:|---:|---:|---|---|---:|---:|---|
| stationing | 6 | 86.8 | 67.1 | -19.7 | -48.5 to -1.8 | 1 / 5 / 0 | 0 | 0 | +0 / -0 |
| annotate-sheet | 7 | 66.4 | 46.9 | -19.6 | -49.6 to +11.4 | 3 / 4 / 0 | 0 | 0 | +0 / -0 |
| layer-setup | 6 | 100.0 | 83.3 | -16.7 | -50.0 to +0.0 | 0 / 1 / 5 | 6 | 5 | +0 / -1 |
| attach-reference | 7 | 100.0 | 85.7 | -14.3 | -42.9 to +0.0 | 0 / 1 / 6 | 7 | 6 | +0 / -1 |
| create-alignment | 6 | 79.8 | 66.7 | -13.1 | -50.0 to +10.7 | 1 / 1 / 4 | 4 | 4 | +1 / -1 |
| pavement | 6 | 60.1 | 49.5 | -10.5 | -41.3 to +9.5 | 2 / 1 / 3 | 0 | 0 | +0 / -0 |
| pavement-widths | 6 | 27.8 | 19.4 | -8.3 | -22.2 to +0.0 | 0 / 2 / 4 | 0 | 0 | +0 / -0 |
| annotate-base | 7 | 52.7 | 53.8 | +1.1 | -25.9 to +18.7 | 4 / 1 / 2 | 0 | 0 | +0 / -0 |
| curve-callouts | 6 | 68.6 | 71.6 | +2.9 | -41.2 to +50.0 | 1 / 1 / 4 | 0 | 1 | +1 / -0 |
| plan-sheet | 6 | 28.2 | 41.6 | +13.4 | -41.8 to +64.0 | 3 / 2 / 1 | 0 | 0 | +0 / -0 |
| sheet-setup | 6 | 11.6 | 26.2 | +14.6 | -11.7 to +41.0 | 4 / 2 / 0 | 0 | 0 | +0 / -0 |
| curve-table | 6 | 50.3 | 65.7 | +15.4 | +5.8 to +24.0 | 4 / 0 / 2 | 0 | 3 | +3 / -0 |
| bearings | 7 | 66.4 | 87.1 | +20.7 | +5.7 to +42.9 | 5 / 0 / 2 | 0 | 3 | +3 / -0 |
| pavement-edges | 6 | 76.2 | 100.0 | +23.8 | +0.0 to +57.1 | 2 / 0 / 4 | 4 | 6 | +2 / -0 |
| draw-alignment | 6 | 68.8 | 93.8 | +25.0 | +0.0 to +37.5 | 5 / 1 / 0 | 1 | 5 | +5 / -1 |
| title-block | 6 | 35.6 | 68.1 | +32.4 | -1.4 to +66.2 | 4 / 2 / 0 | 0 | 0 | +0 / -0 |
| **all** | 100 | 61.6 | 64.3 | +2.7 | -4.5 to +9.8 | 39 / 24 / 37 | 22 | 33 | +15 / -4 |
