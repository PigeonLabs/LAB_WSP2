# F5 — all24 frozen transfer conditions per directed pair

All120 D4 condition evaluations are shown, including unselected activation/semantic transfers, all three random maps, and naive full-parameter averaging. D2 alone selects the deployed policy. Unselected D4 conditions are descriptive and cannot change that policy or create new tests. Accuracy changes below are percentage points relative to the untouched target.

For naive full-parameter averaging, alpha=1 is full donor replacement. It is not successful merging. Sparse aligned transfer modifies only the registered native units; it is not whole-circuit preservation.

## seed101_to_seed211

D2 target task: **arithmetic**. Frozen selected policy: **semantic__alpha_0.25**. Task row counts: arithmetic=192, comparison=192, negation=192, syntax=192.

[Frozen D2 policy](../../results/followup-v2/transfers/seed101_to_seed211/policy.json) · [Pair summary](../../results/followup-v2/transfers/seed101_to_seed211/summary.json) · [All raw D4 margins](../../results/followup-v2/transfers/seed101_to_seed211/D4_margins.npz)

| Condition | Alpha | D2 selected | arithmetic | comparison | negation | syntax | Target change (pp) | Comparison change (pp) |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| Untouched target | — | NO | 56.25% | 93.23% | 73.44% | 84.38% |0.0000|0.0000|
| activation | 0 | NO | 56.25% | 93.23% | 73.44% | 84.38% | +0.0000 | +0.0000 |
| activation | 0.25 | NO | 56.25% | 93.23% | 72.92% | 84.38% | +0.0000 | +0.0000 |
| activation | 0.5 | NO | 56.25% | 93.23% | 72.92% | 84.38% | +0.0000 | +0.0000 |
| activation | 1 | NO | 56.25% | 93.23% | 72.92% | 84.38% | +0.0000 | +0.0000 |
| semantic | 0 | NO | 56.25% | 93.23% | 73.44% | 84.38% | +0.0000 | +0.0000 |
| semantic | 0.25 | YES | 56.77% | 93.23% | 73.44% | 84.38% | +0.5208 | +0.0000 |
| semantic | 0.5 | NO | 56.77% | 93.23% | 73.44% | 84.38% | +0.5208 | +0.0000 |
| semantic | 1 | NO | 56.77% | 93.23% | 73.44% | 84.90% | +0.5208 | +0.0000 |
| random_seed17 | 0 | NO | 56.25% | 93.23% | 73.44% | 84.38% | +0.0000 | +0.0000 |
| random_seed17 | 0.25 | NO | 56.25% | 93.23% | 72.92% | 84.38% | +0.0000 | +0.0000 |
| random_seed17 | 0.5 | NO | 55.73% | 93.23% | 72.92% | 84.38% | -0.5208 | +0.0000 |
| random_seed17 | 1 | NO | 55.73% | 93.23% | 72.92% | 84.38% | -0.5208 | +0.0000 |
| random_seed31 | 0 | NO | 56.25% | 93.23% | 73.44% | 84.38% | +0.0000 | +0.0000 |
| random_seed31 | 0.25 | NO | 56.25% | 93.23% | 72.92% | 84.38% | +0.0000 | +0.0000 |
| random_seed31 | 0.5 | NO | 56.25% | 93.23% | 72.92% | 84.38% | +0.0000 | +0.0000 |
| random_seed31 | 1 | NO | 56.25% | 93.23% | 72.92% | 84.38% | +0.0000 | +0.0000 |
| random_seed47 | 0 | NO | 56.25% | 93.23% | 73.44% | 84.38% | +0.0000 | +0.0000 |
| random_seed47 | 0.25 | NO | 56.25% | 93.23% | 72.92% | 84.38% | +0.0000 | +0.0000 |
| random_seed47 | 0.5 | NO | 56.25% | 93.23% | 72.92% | 84.38% | +0.0000 | +0.0000 |
| random_seed47 | 1 | NO | 56.25% | 93.23% | 72.92% | 84.38% | +0.0000 | +0.0000 |
| naive_average | 0 | NO | 56.25% | 93.23% | 73.44% | 84.38% | +0.0000 | +0.0000 |
| naive_average | 0.25 | NO | 59.90% | 93.75% | 72.92% | 84.90% | +3.6458 | +0.5208 |
| naive_average | 0.5 | NO | 50.00% | 50.00% | 50.00% | 50.00% | -6.2500 | -43.2292 |
| naive_average (full donor replacement) | 1 | NO | 58.85% | 93.23% | 74.48% | 88.54% | +2.6042 | +0.0000 |

The original donor/target before-and-after parameter hashes are recorded in the pair summary. These descriptive conditions do not choose a new policy from D4.

## seed211_to_seed307

D2 target task: **negation**. Frozen selected policy: **NONE (untouched target)**. Task row counts: arithmetic=192, comparison=192, negation=192, syntax=192.

[Frozen D2 policy](../../results/followup-v2/transfers/seed211_to_seed307/policy.json) · [Pair summary](../../results/followup-v2/transfers/seed211_to_seed307/summary.json) · [All raw D4 margins](../../results/followup-v2/transfers/seed211_to_seed307/D4_margins.npz)

| Condition | Alpha | D2 selected | arithmetic | comparison | negation | syntax | Target change (pp) | Comparison change (pp) |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| Untouched target | — | YES | 58.85% | 93.75% | 75.52% | 89.06% |0.0000|0.0000|
| activation | 0 | NO | 58.85% | 93.75% | 75.52% | 89.06% | +0.0000 | +0.0000 |
| activation | 0.25 | NO | 58.85% | 93.75% | 75.52% | 89.06% | +0.0000 | +0.0000 |
| activation | 0.5 | NO | 58.85% | 93.75% | 75.52% | 89.06% | +0.0000 | +0.0000 |
| activation | 1 | NO | 58.85% | 93.75% | 75.52% | 89.06% | +0.0000 | +0.0000 |
| semantic | 0 | NO | 58.85% | 93.75% | 75.52% | 89.06% | +0.0000 | +0.0000 |
| semantic | 0.25 | NO | 58.85% | 93.75% | 76.04% | 89.06% | +0.5208 | +0.0000 |
| semantic | 0.5 | NO | 58.85% | 93.75% | 76.04% | 89.06% | +0.5208 | +0.0000 |
| semantic | 1 | NO | 58.85% | 93.75% | 76.04% | 89.06% | +0.5208 | +0.0000 |
| random_seed17 | 0 | NO | 58.85% | 93.75% | 75.52% | 89.06% | +0.0000 | +0.0000 |
| random_seed17 | 0.25 | NO | 58.85% | 93.75% | 75.52% | 89.06% | +0.0000 | +0.0000 |
| random_seed17 | 0.5 | NO | 58.85% | 93.75% | 75.52% | 89.06% | +0.0000 | +0.0000 |
| random_seed17 | 1 | NO | 58.85% | 93.75% | 75.52% | 89.06% | +0.0000 | +0.0000 |
| random_seed31 | 0 | NO | 58.85% | 93.75% | 75.52% | 89.06% | +0.0000 | +0.0000 |
| random_seed31 | 0.25 | NO | 58.85% | 93.75% | 75.52% | 89.06% | +0.0000 | +0.0000 |
| random_seed31 | 0.5 | NO | 58.85% | 93.75% | 75.52% | 89.06% | +0.0000 | +0.0000 |
| random_seed31 | 1 | NO | 58.85% | 93.75% | 75.52% | 89.06% | +0.0000 | +0.0000 |
| random_seed47 | 0 | NO | 58.85% | 93.75% | 75.52% | 89.06% | +0.0000 | +0.0000 |
| random_seed47 | 0.25 | NO | 58.85% | 93.75% | 75.52% | 89.06% | +0.0000 | +0.0000 |
| random_seed47 | 0.5 | NO | 58.85% | 93.75% | 75.52% | 89.06% | +0.0000 | +0.0000 |
| random_seed47 | 1 | NO | 58.85% | 93.75% | 75.52% | 89.06% | +0.0000 | +0.0000 |
| naive_average | 0 | NO | 58.85% | 93.75% | 75.52% | 89.06% | +0.0000 | +0.0000 |
| naive_average | 0.25 | NO | 60.42% | 94.27% | 77.08% | 86.98% | +1.5625 | +0.5208 |
| naive_average | 0.5 | NO | 50.00% | 51.56% | 50.00% | 50.00% | -25.5208 | -42.1875 |
| naive_average (full donor replacement) | 1 | NO | 56.25% | 93.23% | 73.44% | 84.38% | -2.0833 | -0.5208 |

The original donor/target before-and-after parameter hashes are recorded in the pair summary. These descriptive conditions do not choose a new policy from D4.

## seed307_to_seed401

D2 target task: **comparison**. Frozen selected policy: **NONE (untouched target)**. Task row counts: arithmetic=192, comparison=192, negation=192, syntax=192.

[Frozen D2 policy](../../results/followup-v2/transfers/seed307_to_seed401/policy.json) · [Pair summary](../../results/followup-v2/transfers/seed307_to_seed401/summary.json) · [All raw D4 margins](../../results/followup-v2/transfers/seed307_to_seed401/D4_margins.npz)

| Condition | Alpha | D2 selected | arithmetic | comparison | negation | syntax | Target change (pp) | Comparison change (pp) |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| Untouched target | — | YES | 71.88% | 95.31% | 79.17% | 90.10% |0.0000|0.0000|
| activation | 0 | NO | 71.88% | 95.31% | 79.17% | 90.10% | +0.0000 | +0.0000 |
| activation | 0.25 | NO | 71.88% | 95.31% | 79.17% | 90.10% | +0.0000 | +0.0000 |
| activation | 0.5 | NO | 71.88% | 95.31% | 79.17% | 90.10% | +0.0000 | +0.0000 |
| activation | 1 | NO | 71.88% | 95.31% | 79.69% | 90.10% | +0.0000 | +0.0000 |
| semantic | 0 | NO | 71.88% | 95.31% | 79.17% | 90.10% | +0.0000 | +0.0000 |
| semantic | 0.25 | NO | 71.88% | 95.31% | 79.17% | 90.10% | +0.0000 | +0.0000 |
| semantic | 0.5 | NO | 71.88% | 95.31% | 79.17% | 90.10% | +0.0000 | +0.0000 |
| semantic | 1 | NO | 71.88% | 95.31% | 79.17% | 90.10% | +0.0000 | +0.0000 |
| random_seed17 | 0 | NO | 71.88% | 95.31% | 79.17% | 90.10% | +0.0000 | +0.0000 |
| random_seed17 | 0.25 | NO | 71.88% | 95.31% | 79.17% | 90.10% | +0.0000 | +0.0000 |
| random_seed17 | 0.5 | NO | 71.88% | 95.31% | 79.17% | 90.10% | +0.0000 | +0.0000 |
| random_seed17 | 1 | NO | 71.88% | 95.31% | 79.17% | 90.10% | +0.0000 | +0.0000 |
| random_seed31 | 0 | NO | 71.88% | 95.31% | 79.17% | 90.10% | +0.0000 | +0.0000 |
| random_seed31 | 0.25 | NO | 71.88% | 95.31% | 79.17% | 90.10% | +0.0000 | +0.0000 |
| random_seed31 | 0.5 | NO | 71.88% | 95.31% | 79.17% | 90.10% | +0.0000 | +0.0000 |
| random_seed31 | 1 | NO | 71.88% | 95.31% | 79.17% | 90.10% | +0.0000 | +0.0000 |
| random_seed47 | 0 | NO | 71.88% | 95.31% | 79.17% | 90.10% | +0.0000 | +0.0000 |
| random_seed47 | 0.25 | NO | 71.88% | 95.31% | 79.17% | 90.10% | +0.0000 | +0.0000 |
| random_seed47 | 0.5 | NO | 71.88% | 95.31% | 79.17% | 90.10% | +0.0000 | +0.0000 |
| random_seed47 | 1 | NO | 71.88% | 95.31% | 79.17% | 90.10% | +0.0000 | +0.0000 |
| naive_average | 0 | NO | 71.88% | 95.31% | 79.17% | 90.10% | +0.0000 | +0.0000 |
| naive_average | 0.25 | NO | 65.10% | 93.75% | 80.73% | 90.10% | -1.5625 | -1.5625 |
| naive_average | 0.5 | NO | 50.00% | 50.00% | 53.65% | 52.60% | -45.3125 | -45.3125 |
| naive_average (full donor replacement) | 1 | NO | 58.85% | 93.75% | 75.52% | 89.06% | -1.5625 | -1.5625 |

The original donor/target before-and-after parameter hashes are recorded in the pair summary. These descriptive conditions do not choose a new policy from D4.

## seed401_to_seed503

D2 target task: **arithmetic**. Frozen selected policy: **NONE (untouched target)**. Task row counts: arithmetic=192, comparison=192, negation=192, syntax=192.

[Frozen D2 policy](../../results/followup-v2/transfers/seed401_to_seed503/policy.json) · [Pair summary](../../results/followup-v2/transfers/seed401_to_seed503/summary.json) · [All raw D4 margins](../../results/followup-v2/transfers/seed401_to_seed503/D4_margins.npz)

| Condition | Alpha | D2 selected | arithmetic | comparison | negation | syntax | Target change (pp) | Comparison change (pp) |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| Untouched target | — | YES | 54.69% | 91.15% | 68.23% | 89.58% |0.0000|0.0000|
| activation | 0 | NO | 54.69% | 91.15% | 68.23% | 89.58% | +0.0000 | +0.0000 |
| activation | 0.25 | NO | 55.21% | 91.15% | 68.23% | 89.58% | +0.5208 | +0.0000 |
| activation | 0.5 | NO | 55.73% | 91.15% | 68.23% | 89.58% | +1.0417 | +0.0000 |
| activation | 1 | NO | 55.73% | 91.15% | 68.23% | 89.58% | +1.0417 | +0.0000 |
| semantic | 0 | NO | 54.69% | 91.15% | 68.23% | 89.58% | +0.0000 | +0.0000 |
| semantic | 0.25 | NO | 55.21% | 91.15% | 68.23% | 89.58% | +0.5208 | +0.0000 |
| semantic | 0.5 | NO | 55.21% | 91.15% | 68.23% | 89.58% | +0.5208 | +0.0000 |
| semantic | 1 | NO | 55.21% | 91.15% | 68.23% | 89.58% | +0.5208 | +0.0000 |
| random_seed17 | 0 | NO | 54.69% | 91.15% | 68.23% | 89.58% | +0.0000 | +0.0000 |
| random_seed17 | 0.25 | NO | 55.21% | 91.15% | 68.23% | 89.58% | +0.5208 | +0.0000 |
| random_seed17 | 0.5 | NO | 55.73% | 91.15% | 68.23% | 89.58% | +1.0417 | +0.0000 |
| random_seed17 | 1 | NO | 55.73% | 91.15% | 67.71% | 89.58% | +1.0417 | +0.0000 |
| random_seed31 | 0 | NO | 54.69% | 91.15% | 68.23% | 89.58% | +0.0000 | +0.0000 |
| random_seed31 | 0.25 | NO | 55.21% | 91.15% | 68.23% | 89.58% | +0.5208 | +0.0000 |
| random_seed31 | 0.5 | NO | 55.73% | 91.15% | 68.23% | 89.58% | +1.0417 | +0.0000 |
| random_seed31 | 1 | NO | 55.73% | 91.15% | 68.23% | 89.58% | +1.0417 | +0.0000 |
| random_seed47 | 0 | NO | 54.69% | 91.15% | 68.23% | 89.58% | +0.0000 | +0.0000 |
| random_seed47 | 0.25 | NO | 55.21% | 91.15% | 68.23% | 89.58% | +0.5208 | +0.0000 |
| random_seed47 | 0.5 | NO | 55.73% | 91.15% | 68.23% | 89.58% | +1.0417 | +0.0000 |
| random_seed47 | 1 | NO | 55.73% | 91.15% | 68.23% | 89.58% | +1.0417 | +0.0000 |
| naive_average | 0 | NO | 54.69% | 91.15% | 68.23% | 89.58% | +0.0000 | +0.0000 |
| naive_average | 0.25 | NO | 58.33% | 91.15% | 71.88% | 90.10% | +3.6458 | +0.0000 |
| naive_average | 0.5 | NO | 50.00% | 50.00% | 50.00% | 50.00% | -4.6875 | -41.1458 |
| naive_average (full donor replacement) | 1 | NO | 71.88% | 95.31% | 79.17% | 90.10% | +17.1875 | +4.1667 |

The original donor/target before-and-after parameter hashes are recorded in the pair summary. These descriptive conditions do not choose a new policy from D4.

## seed503_to_seed101

D2 target task: **arithmetic**. Frozen selected policy: **NONE (untouched target)**. Task row counts: arithmetic=192, comparison=192, negation=192, syntax=192.

[Frozen D2 policy](../../results/followup-v2/transfers/seed503_to_seed101/policy.json) · [Pair summary](../../results/followup-v2/transfers/seed503_to_seed101/summary.json) · [All raw D4 margins](../../results/followup-v2/transfers/seed503_to_seed101/D4_margins.npz)

| Condition | Alpha | D2 selected | arithmetic | comparison | negation | syntax | Target change (pp) | Comparison change (pp) |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| Untouched target | — | YES | 58.85% | 93.23% | 74.48% | 88.54% |0.0000|0.0000|
| activation | 0 | NO | 58.85% | 93.23% | 74.48% | 88.54% | +0.0000 | +0.0000 |
| activation | 0.25 | NO | 58.33% | 93.23% | 74.48% | 88.54% | -0.5208 | +0.0000 |
| activation | 0.5 | NO | 58.33% | 93.23% | 73.96% | 88.54% | -0.5208 | +0.0000 |
| activation | 1 | NO | 58.33% | 93.23% | 73.96% | 88.54% | -0.5208 | +0.0000 |
| semantic | 0 | NO | 58.85% | 93.23% | 74.48% | 88.54% | +0.0000 | +0.0000 |
| semantic | 0.25 | NO | 58.33% | 93.23% | 74.48% | 88.54% | -0.5208 | +0.0000 |
| semantic | 0.5 | NO | 58.33% | 93.23% | 73.96% | 88.54% | -0.5208 | +0.0000 |
| semantic | 1 | NO | 58.33% | 93.23% | 73.96% | 88.54% | -0.5208 | +0.0000 |
| random_seed17 | 0 | NO | 58.85% | 93.23% | 74.48% | 88.54% | +0.0000 | +0.0000 |
| random_seed17 | 0.25 | NO | 58.33% | 93.23% | 74.48% | 88.54% | -0.5208 | +0.0000 |
| random_seed17 | 0.5 | NO | 58.33% | 93.23% | 73.96% | 88.54% | -0.5208 | +0.0000 |
| random_seed17 | 1 | NO | 58.33% | 93.23% | 73.96% | 88.54% | -0.5208 | +0.0000 |
| random_seed31 | 0 | NO | 58.85% | 93.23% | 74.48% | 88.54% | +0.0000 | +0.0000 |
| random_seed31 | 0.25 | NO | 58.33% | 93.23% | 74.48% | 88.54% | -0.5208 | +0.0000 |
| random_seed31 | 0.5 | NO | 58.33% | 93.23% | 73.96% | 88.54% | -0.5208 | +0.0000 |
| random_seed31 | 1 | NO | 58.33% | 93.23% | 73.96% | 88.54% | -0.5208 | +0.0000 |
| random_seed47 | 0 | NO | 58.85% | 93.23% | 74.48% | 88.54% | +0.0000 | +0.0000 |
| random_seed47 | 0.25 | NO | 58.33% | 93.23% | 74.48% | 88.54% | -0.5208 | +0.0000 |
| random_seed47 | 0.5 | NO | 58.33% | 93.23% | 73.96% | 88.54% | -0.5208 | +0.0000 |
| random_seed47 | 1 | NO | 58.33% | 93.23% | 73.96% | 88.54% | -0.5208 | +0.0000 |
| naive_average | 0 | NO | 58.85% | 93.23% | 74.48% | 88.54% | +0.0000 | +0.0000 |
| naive_average | 0.25 | NO | 54.17% | 89.06% | 74.48% | 85.94% | -4.6875 | -4.1667 |
| naive_average | 0.5 | NO | 50.00% | 50.00% | 50.00% | 50.00% | -8.8542 | -43.2292 |
| naive_average (full donor replacement) | 1 | NO | 54.69% | 91.15% | 68.23% | 89.58% | -4.1667 | -2.0833 |

The original donor/target before-and-after parameter hashes are recorded in the pair summary. These descriptive conditions do not choose a new policy from D4.

