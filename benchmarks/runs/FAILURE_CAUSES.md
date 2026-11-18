# Why each model fails: points lost by cause

Every lost effective point of each vague-prompt run, put down to one cause by `python -m roaddraft.eval causes` (`roaddraft.eval.causes`: the rules are in its docstring). **Standard**: a drafting convention not applied, with no failed attempt at it; *confirmed* where the same model's explicit run earned it back when told (a standard it lost even when told counts as reasoning). **Tool use**: the tools did not do what the model meant (a command that failed and never worked, lettering typed as plain text, doubled output, the fault budget). **Reasoning**: the tools did what the model asked, but what it asked for was wrong. **Budget**: out of steps, time, context or output, or a provider error. hard-pilots is pass or fail, so a failed pilot takes one cause; with no explicit run of the pilot and no tool fault it is unresolved.

## `d1-test`

| Run | Effective | Lost | Standard (confirmed) | Tool use | Reasoning | Budget | Unresolved | Paired |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `e3-d1-test-gpt-6-astra-codex-medium-single-vague-v3` | 96.6 | 3.4 | 3.3 | 0.0 | 0.1 | 0.0 | 0.0 | no |
| `e3-d1-test-claude-opus-5-5-claude-code-medium-single-vague-v3` | 95.5 | 4.5 | 4.3 | 0.0 | 0.2 | 0.0 | 0.0 | no |
| `e3-d1-test-gpt-6.1-terra-codex-medium-single-vague-v3` | 92.8 | 7.2 | 6.4 | 0.7 | 0.1 | 0.0 | 0.0 | no |
| `e3-d1-test-nemotron-3.5-super-vl-single-vague-v3` | 82.4 | 17.6 | 15.6 | 0.4 | 1.6 | 0.0 | 0.0 | no |
| `e3-d1-test-gemma-4-31b-single-vague-v3` | 80.1 | 19.9 | 17.4 | 0.1 | 2.4 | 0.0 | 0.0 | no |
| `e3-d1-test-qwen3.6-35b-a3b-single-vague-v3` | 76.3 | 23.7 | 21.7 | 1.2 | 0.8 | 0.0 | 0.0 | no |
| `e3-d1-test-gpt-6-luna-codex-medium-single-vague-v3` | 76.1 | 23.9 | 17.1 (17.1) | 3.0 | 3.9 | 0.0 | 0.0 | yes |
| `e3-d1-test-claude-sonnet-5-5-claude-code-medium-single-vague-v3` | 76.0 | 24.0 | 21.4 | 2.4 | 0.2 | 0.0 | 0.0 | no |
| `e3-d1-test-gpt-oss-120b-single-vague-v3` | 70.3 | 29.7 | 26.3 | 0.7 | 2.7 | 0.0 | 0.0 | no |
| `e3-d1-test-gemma-4-12b-q8-lms-single-vague-v3` | 67.2 | 32.8 | 10.9 (10.9) | 3.8 | 18.0 | 0.0 | 0.0 | yes |
| `e3-d1-test-glm-5.3-single-vague-v3` | 66.5 | 33.5 | 32.1 | 0.6 | 0.8 | 0.0 | 0.0 | no |
| `e3-d1-test-mistral-small-4-single-vague-v3` | 64.0 | 36.0 | 28.5 | 3.5 | 4.0 | 0.0 | 0.0 | no |
| `e3-d1-test-qwen3.5-9b-q4km-lms-single-vague-v3` | 62.6 | 37.4 | 16.1 (16.1) | 5.3 | 16.1 | 0.0 | 0.0 | yes |
| `e3-d1-test-glm-4.6v-flash-q4km-lms-single-vague-v3` | 25.2 | 74.8 | 5.3 (5.3) | 35.0 | 34.5 | 0.0 | 0.0 | yes |

## `d1-real`

| Run | Effective | Lost | Standard (confirmed) | Tool use | Reasoning | Budget | Unresolved | Paired |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `e3-d1-real-gpt-6.1-terra-codex-medium-single-vague-v3` | 90.5 | 9.5 | 8.6 | 0.0 | 0.8 | 0.0 | 0.0 | no |
| `e3-d1-real-claude-opus-5-5-claude-code-medium-single-vague-v3` | 86.7 | 13.3 | 10.7 | 0.0 | 2.6 | 0.0 | 0.0 | no |
| `e3-d1-real-gemma-4-31b-single-vague-cost5-v3` | 76.8 | 23.2 | 20.3 | 1.5 | 1.4 | 0.0 | 0.0 | no |
| `e3-d1-real-claude-sonnet-5-5-claude-code-medium-single-vague-v3` | 75.1 | 24.9 | 17.8 | 2.7 | 4.4 | 0.0 | 0.0 | no |
| `e3-d1-real-gpt-6-luna-codex-medium-single-vague-v3` | 71.8 | 28.2 | 13.3 (13.3) | 3.8 | 11.2 | 0.0 | 0.0 | yes |
| `e3-d1-real-qwen3.6-35b-a3b-single-vague-cost5-v3` | 70.5 | 29.5 | 21.6 | 4.1 | 3.8 | 0.0 | 0.0 | no |
| `e3-d1-real-qwen3.5-9b-q4km-lms-single-vague-v3` | 59.7 | 40.3 | 11.1 (11.1) | 6.8 | 22.5 | 0.0 | 0.0 | yes |
| `e3-d1-real-gemma-4-12b-q8-lms-single-vague-v3` | 59.0 | 41.0 | 8.2 (8.2) | 8.8 | 24.0 | 0.0 | 0.0 | yes |
| `e3-d1-real-glm-4.6v-flash-q4km-lms-single-vague-v3` | 13.6 | 86.4 | 2.2 (2.2) | 51.6 | 31.6 | 1.0 | 0.0 | yes |

## `d1-test-hard`

| Run | Effective | Lost | Standard (confirmed) | Tool use | Reasoning | Budget | Unresolved | Paired |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `e3-d1-test-hard-claude-opus-5-5-claude-code-medium-single-vague-v3` | 93.7 | 6.3 | 5.3 (5.3) | 0.0 | 1.0 | 0.0 | 0.0 | yes |
| `e3-d1-test-hard-gpt-6.1-terra-codex-medium-single-vague-v3` | 92.9 | 7.1 | 4.9 (4.9) | 1.2 | 1.0 | 0.0 | 0.0 | yes |
| `e3-d1-test-hard-claude-sonnet-5-5-claude-code-medium-single-vague-v3` | 54.5 | 45.5 | 32.8 (32.8) | 5.1 | 7.5 | 0.0 | 0.0 | yes |
| `e3-d1-test-hard-gpt-6-luna-codex-medium-single-vague-v3` | 43.2 | 56.8 | 31.2 (31.2) | 14.3 | 10.5 | 0.7 | 0.0 | yes |
| `e3-d1-test-hard-qwen3.6-35b-a3b-single-vague-cost5-v3` | 41.7 | 58.3 | 46.5 | 8.3 | 3.5 | 0.0 | 0.0 | no |
| `e3-d1-test-hard-qwen3.5-9b-q4km-lms-single-vague-v3` | 9.4 | 90.6 | 56.3 | 20.7 | 10.6 | 3.0 | 0.0 | no |
| `e3-d1-test-hard-gemma-4-12b-q8-lms-single-vague-v3` | 3.0 | 97.0 | 75.4 | 16.2 | 4.4 | 1.0 | 0.0 | no |

## `d1-real-hard`

| Run | Effective | Lost | Standard (confirmed) | Tool use | Reasoning | Budget | Unresolved | Paired |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `e3-d1-real-hard-claude-opus-5-5-claude-code-medium-single-vague-v3` | 77.6 | 22.4 | 16.1 (16.1) | 2.1 | 4.2 | 0.0 | 0.0 | yes |
| `e3-d1-real-hard-gpt-6.1-terra-codex-medium-single-vague-v3` | 72.1 | 27.9 | 14.8 (14.8) | 11.6 | 1.5 | 0.0 | 0.0 | yes |
| `e3-d1-real-hard-gpt-6-luna-codex-medium-single-vague-v3` | 51.1 | 48.9 | 31.3 (31.3) | 13.3 | 4.3 | 0.0 | 0.0 | yes |
| `e3-d1-real-hard-claude-sonnet-5-5-claude-code-medium-single-vague-v3` | 50.8 | 49.2 | 27.8 (27.8) | 17.4 | 4.0 | 0.0 | 0.0 | yes |
| `e3-d1-real-hard-qwen3.6-35b-a3b-single-vague-cost5-v3` | 50.6 | 49.4 | 40.3 | 7.1 | 1.9 | 0.0 | 0.0 | no |
| `e3-d1-real-hard-gemma-4-12b-q8-lms-single-vague-v3` | 37.5 | 62.5 | 35.7 | 24.2 | 2.5 | 0.0 | 0.0 | no |
| `e3-d1-real-hard-qwen3.5-9b-q4km-lms-single-vague-v3` | 33.5 | 66.5 | 44.1 | 14.9 | 7.5 | 0.0 | 0.0 | no |

## `hard-pilots`

| Run | Effective | Lost | Standard (confirmed) | Tool use | Reasoning | Budget | Unresolved | Paired |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `e3-hard-pilots-claude-opus-5-5-claude-code-medium-single-vague-v3` | 40.2 | 59.8 | 15.2 (15.2) | 10.7 | 33.9 | 0.0 | 0.0 | yes |
| `e3-hard-pilots-gpt-6.1-terra-codex-medium-single-vague-v3` | 28.6 | 71.4 | 12.5 (12.5) | 26.8 | 32.1 | 0.0 | 0.0 | yes |
| `e3-hard-pilots-claude-sonnet-5-5-claude-code-medium-single-vague-v3` | 24.1 | 75.9 | 12.5 (12.5) | 7.1 | 56.3 | 0.0 | 0.0 | yes |
| `e3-hard-pilots-glm-5.3-single-vague-cost5-text-v3` | 11.8 | 88.2 | 0.0 | 29.4 | 0.0 | 17.6 | 41.2 | no |
| `e3-hard-pilots-qwen3.6-35b-a3b-single-vague-v3` | 8.0 | 92.0 | 0.0 | 34.8 | 0.0 | 12.5 | 44.6 | no |
| `e3-hard-pilots-nemotron-3.5-super-vl-single-vague-v3` | 4.5 | 95.5 | 0.0 | 9.8 | 0.0 | 8.0 | 77.7 | no |
| `e3-hard-pilots-gpt-oss-120b-single-vague-cost5-text-v3` | 3.9 | 96.1 | 0.0 | 21.6 | 0.0 | 0.0 | 74.5 | no |
| `e3-hard-pilots-gpt-oss-120b-single-vague-text-v3` | 3.4 | 96.6 | 0.0 | 24.7 | 0.0 | 0.0 | 71.9 | no |
| `e3-hard-pilots-gpt-6-luna-codex-medium-single-vague-v3` | 2.7 | 97.3 | 2.7 (2.7) | 19.6 | 75.0 | 0.0 | 0.0 | yes |
| `e3-hard-pilots-mistral-small-4-single-vague-v3` | 2.7 | 97.3 | 0.0 | 27.7 | 0.0 | 0.9 | 68.8 | no |
| `e3-hard-pilots-gemma-4-31b-single-vague-v3` | 1.8 | 98.2 | 0.0 | 29.5 | 0.0 | 2.7 | 66.1 | no |
| `e3-hard-pilots-gemma-4-26b-a4b-single-vague-v3` | 0.9 | 99.1 | 0.0 | 32.1 | 0.0 | 26.8 | 40.2 | no |
| `e3-hard-pilots-qwen3.5-9b-q4km-lms-single-vague-v3` | 0.9 | 99.1 | 0.9 (0.9) | 43.8 | 46.4 | 8.0 | 0.0 | yes |
| `e3-hard-pilots-gemma-4-12b-q8-lms-single-vague-v3` | 0.0 | 100.0 | 0.0 | 32.1 | 13.4 | 13.4 | 41.1 | yes |

Points are per task, averaged over the run's tasks; each row's causes add up to its lost points. k = 1 everywhere. Per-run detail (sub-causes, task types, example tasks) is in each run's `report/causes.md`.
