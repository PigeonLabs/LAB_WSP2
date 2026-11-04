# F4 posthoc activation-based causal matching controls

The primary F4 comparison omitted an activation-based causal matching baseline. This separate gap check was added after some tiny-model D4 outcomes had been observed. Both activation_raw and activation_task_centered maps were fitted only on the first12 D2 wrappers; fitting read no D4 values. Raw activation follows the F3 raw-correlation matching family; task-centered activation is an additional control. Both are retained without selecting a winner. The comparison is descriptive and posthoc: no new p/q/CI, no110-family change, no automatic conservation support. Means equally weight finite observed pair means; missing pair/wrapper coverage must be compared. Shared-model pairs are dependent.

Cell format: **mean [available pairs/total pairs; valid wrapper cells/possible wrapper cells]**. Undefined values remain N/A. These are conditional descriptive cohort summaries, not independent replication or new confidence intervals.

| Cohort / unit / position | Semantic | Combined | Random | Raw activation | Task-centered activation |
|---|---:|---:|---:|---:|---:|
| cross_family/group/answer | -0.0391 [3/3; 72/72] | 0.0551 [3/3; 72/72] | -0.0121 [3/3; 72/72] | -0.0210 [3/3; 72/72] | -0.0297 [3/3; 72/72] |
| cross_family/group/span | 0.0028 [3/3; 72/72] | 0.0865 [3/3; 72/72] | -0.0002 [3/3; 72/72] | -0.0568 [3/3; 72/72] | 0.0318 [3/3; 72/72] |
| cross_family/single/answer | -0.0264 [3/3; 72/72] | 0.0435 [3/3; 72/72] | -0.0005 [3/3; 72/72] | -0.0209 [3/3; 72/72] | -0.0277 [3/3; 72/72] |
| cross_family/single/span | -0.0023 [3/3; 72/72] | 0.0880 [3/3; 72/72] | -0.0009 [3/3; 72/72] | -0.0035 [3/3; 72/72] | -0.0240 [3/3; 72/72] |
| independent_seeds/group/answer | 0.0144 [10/10; 240/240] | 0.0822 [10/10; 240/240] | 0.0162 [10/10; 240/240] | 0.0111 [10/10; 240/240] | 0.0267 [10/10; 240/240] |
| independent_seeds/group/span | -0.0017 [10/10; 240/240] | -0.0001 [10/10; 240/240] | 0.0014 [10/10; 240/240] | 0.0015 [10/10; 240/240] | -0.0095 [10/10; 240/240] |
| independent_seeds/single/answer | 0.0033 [10/10; 240/240] | 0.0620 [10/10; 240/240] | -0.0004 [10/10; 240/240] | 0.0114 [10/10; 240/240] | 0.0038 [10/10; 240/240] |
| independent_seeds/single/span | -0.0083 [10/10; 240/240] | 0.0034 [10/10; 240/240] | -0.0002 [10/10; 240/240] | 0.0059 [10/10; 240/240] | -0.0016 [10/10; 240/240] |

## Interpretation limits

- The original comparison answers only combined-versus-semantic matching. It cannot by itself establish superiority to activation matching; this missing baseline is acknowledged rather than retrospectively preregistered.
- Raw and task-centered controls remain separately visible, including unfavorable or undefined outcomes. No outcome selects the preferred control.
- Task competence and construct validity remain distinct. Passing the syntax gate does not establish recursive understanding; consult the hard-stress evidence.
- Per-model calibration prefixes differ across pretrained families. These controls do not remove the context, response-orientation, or finite-model-generalization limitations.

## Source measurements and frozen maps

- [results/followup-v2/supplemental_causal_activation/summary.json](../../results/followup-v2/supplemental_causal_activation/summary.json)
- [results/followup-v2/supplemental_causal_activation/fit_manifest.json](../../results/followup-v2/supplemental_causal_activation/fit_manifest.json)
- [results/followup-v2/supplemental_causal_activation/seed101_seed211/single/eval.json](../../results/followup-v2/supplemental_causal_activation/seed101_seed211/single/eval.json)
- [results/followup-v2/supplemental_causal_activation/seed101_seed211/group/eval.json](../../results/followup-v2/supplemental_causal_activation/seed101_seed211/group/eval.json)
- [results/followup-v2/supplemental_causal_activation/seed101_seed307/single/eval.json](../../results/followup-v2/supplemental_causal_activation/seed101_seed307/single/eval.json)
- [results/followup-v2/supplemental_causal_activation/seed101_seed307/group/eval.json](../../results/followup-v2/supplemental_causal_activation/seed101_seed307/group/eval.json)
- [results/followup-v2/supplemental_causal_activation/seed101_seed401/single/eval.json](../../results/followup-v2/supplemental_causal_activation/seed101_seed401/single/eval.json)
- [results/followup-v2/supplemental_causal_activation/seed101_seed401/group/eval.json](../../results/followup-v2/supplemental_causal_activation/seed101_seed401/group/eval.json)
- [results/followup-v2/supplemental_causal_activation/seed101_seed503/single/eval.json](../../results/followup-v2/supplemental_causal_activation/seed101_seed503/single/eval.json)
- [results/followup-v2/supplemental_causal_activation/seed101_seed503/group/eval.json](../../results/followup-v2/supplemental_causal_activation/seed101_seed503/group/eval.json)
- [results/followup-v2/supplemental_causal_activation/seed211_seed307/single/eval.json](../../results/followup-v2/supplemental_causal_activation/seed211_seed307/single/eval.json)
- [results/followup-v2/supplemental_causal_activation/seed211_seed307/group/eval.json](../../results/followup-v2/supplemental_causal_activation/seed211_seed307/group/eval.json)
- [results/followup-v2/supplemental_causal_activation/seed211_seed401/single/eval.json](../../results/followup-v2/supplemental_causal_activation/seed211_seed401/single/eval.json)
- [results/followup-v2/supplemental_causal_activation/seed211_seed401/group/eval.json](../../results/followup-v2/supplemental_causal_activation/seed211_seed401/group/eval.json)
- [results/followup-v2/supplemental_causal_activation/seed211_seed503/single/eval.json](../../results/followup-v2/supplemental_causal_activation/seed211_seed503/single/eval.json)
- [results/followup-v2/supplemental_causal_activation/seed211_seed503/group/eval.json](../../results/followup-v2/supplemental_causal_activation/seed211_seed503/group/eval.json)
- [results/followup-v2/supplemental_causal_activation/seed307_seed401/single/eval.json](../../results/followup-v2/supplemental_causal_activation/seed307_seed401/single/eval.json)
- [results/followup-v2/supplemental_causal_activation/seed307_seed401/group/eval.json](../../results/followup-v2/supplemental_causal_activation/seed307_seed401/group/eval.json)
- [results/followup-v2/supplemental_causal_activation/seed307_seed503/single/eval.json](../../results/followup-v2/supplemental_causal_activation/seed307_seed503/single/eval.json)
- [results/followup-v2/supplemental_causal_activation/seed307_seed503/group/eval.json](../../results/followup-v2/supplemental_causal_activation/seed307_seed503/group/eval.json)
- [results/followup-v2/supplemental_causal_activation/seed401_seed503/single/eval.json](../../results/followup-v2/supplemental_causal_activation/seed401_seed503/single/eval.json)
- [results/followup-v2/supplemental_causal_activation/seed401_seed503/group/eval.json](../../results/followup-v2/supplemental_causal_activation/seed401_seed503/group/eval.json)
- [results/followup-v2/supplemental_causal_activation/qwen_smol/single/eval.json](../../results/followup-v2/supplemental_causal_activation/qwen_smol/single/eval.json)
- [results/followup-v2/supplemental_causal_activation/qwen_smol/group/eval.json](../../results/followup-v2/supplemental_causal_activation/qwen_smol/group/eval.json)
- [results/followup-v2/supplemental_causal_activation/qwen_olmo/single/eval.json](../../results/followup-v2/supplemental_causal_activation/qwen_olmo/single/eval.json)
- [results/followup-v2/supplemental_causal_activation/qwen_olmo/group/eval.json](../../results/followup-v2/supplemental_causal_activation/qwen_olmo/group/eval.json)
- [results/followup-v2/supplemental_causal_activation/smol_olmo/single/eval.json](../../results/followup-v2/supplemental_causal_activation/smol_olmo/single/eval.json)
- [results/followup-v2/supplemental_causal_activation/smol_olmo/group/eval.json](../../results/followup-v2/supplemental_causal_activation/smol_olmo/group/eval.json)
