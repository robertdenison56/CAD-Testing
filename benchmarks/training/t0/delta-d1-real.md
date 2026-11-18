# e3-d1-real-qwen3.5-9b-q4km-lms-single-vague-t0-pin1 minus e3-d1-real-qwen3.5-9b-q4km-lms-single-vague-pin1

Set `d1-real`, paired on the 100 tasks both ran. Run: qwen/qwen3.5-9b · single · vague · system extra conventions-v1@89b9a471. Base: qwen/qwen3.5-9b · single · vague.

**Effective +5.2 (-1.6 to +11.4, 95%), not separated from zero**: 60.0 to 65.3. Tasks at 100: 25 to 26 (6 gained, 5 lost).

**Not like for like:**

- system_extra: conventions-v1@89b9a471 against None

| task type | tasks | base | run | gap | 95% | better / worse / same | base at 100 | run at 100 | gained / lost |
|---|---:|---:|---:|---:|---|---|---:|---:|---|
| real-stationing | 5 | 84.2 | 64.7 | -19.4 | -49.1 to -1.6 | 0 / 3 / 2 | 0 | 0 | +0 / -0 |
| real-draw-alignment | 25 | 98.5 | 80.0 | -18.5 | -36.0 to -4.0 | 1 / 5 / 19 | 24 | 20 | +1 / -5 |
| real-title-block | 5 | 46.4 | 42.4 | -4.0 | -12.0 to +0.0 | 0 / 1 / 4 | 1 | 1 | +0 / -0 |
| real-sheet-setup | 5 | 61.8 | 59.5 | -2.3 | -6.8 to +0.0 | 0 / 1 / 4 | 0 | 0 | +0 / -0 |
| real-attach-reference | 5 | 75.0 | 80.0 | +5.0 | +0.0 to +15.0 | 1 / 0 / 4 | 0 | 1 | +1 / -0 |
| real-curve-table | 5 | 78.1 | 89.6 | +11.5 | +1.1 to +21.9 | 3 / 1 / 1 | 0 | 1 | +1 / -0 |
| real-bearings | 5 | 62.0 | 75.0 | +13.0 | -39.0 to +56.0 | 4 / 1 / 0 | 0 | 2 | +2 / -0 |
| real-construction-callouts | 25 | 31.0 | 44.7 | +13.7 | +2.2 to +25.6 | 11 / 5 / 9 | 0 | 0 | +0 / -0 |
| real-annotate-sheet | 5 | 65.1 | 86.2 | +21.1 | +11.5 to +30.4 | 5 / 0 / 0 | 0 | 0 | +0 / -0 |
| real-plan-sheet | 5 | 10.8 | 36.3 | +25.5 | -1.2 to +57.3 | 3 / 1 / 1 | 0 | 0 | +0 / -0 |
| real-alignment-data | 5 | 37.2 | 71.3 | +34.0 | +13.1 to +55.0 | 4 / 0 / 1 | 0 | 0 | +0 / -0 |
| real-callouts | 5 | 32.9 | 76.8 | +43.8 | -4.7 to +88.5 | 3 / 1 / 1 | 0 | 1 | +1 / -0 |
| **all** | 100 | 60.0 | 65.3 | +5.2 | -1.6 to +11.4 | 35 / 19 / 46 | 25 | 26 | +6 / -5 |
