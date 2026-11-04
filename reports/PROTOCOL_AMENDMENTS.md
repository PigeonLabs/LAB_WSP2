# Protocol amendments and execution record

This record distinguishes implementation repairs from outcome-driven method changes. Original measured arrays and frozen mappings are retained.

## Before held-out measurements

- Actual GPU access required approved execution outside the sandbox. Read-only checks found RTX PRO 6000 Blackwell Max-Q 96 GB. No driver, desktop process, or global environment was modified.
- Project execution uses PyTorch 2.15.0+cu132 from an existing environment through a project-local `.pth`, plus locally installed SciPy/NumPy. The initial environment probe also tested another existing PyTorch 2.14.1+cu130 installation; that was not the experiment interpreter.
- E1 used two independently initialized 20,718,080-parameter models, six layers, 1,200 training steps, and 6,144 synthetic training prompts. No shared pretrained checkpoint was used.
- Per model, four relative-depth layers and 16 candidates per layer were fixed, half D1 contrast-selected and half randomly sampled. E4 uses one functional and one random candidate per layer: eight neurons/model. This reduces the recommended initial scale; conclusions apply only to these candidates.
- Shared wrapper templates were correctly identified as six statistical clusters, not 24 concept-by-wrapper clusters. Prompts, labels, and split membership did not change. Training-era JSONL files remain in `data/pilot-v1`; corrected grouping metadata is separately saved in `data/pilot-v1-cluster-corrected`.
- Hook integration tests identified and repaired incomplete matched-donor subsets, the exact-zero sign bin, and the byte tokenizer's common-answer-space boundary. The final boundary includes the common token prefix of correct/foil answers before intervention. Full original continuation probabilities are still scored.
- Inference and causal effects use FP32; statistical summaries use FP64. BF16 is limited to E1 training.

## After D3 observations

- E3 deliberately reuses E1/E2 source measurements to compare methods on the same examples. It is not an independent replication of E1/E2.
- A late reproducibility audit found unordered concept iteration in the seeded label-shuffle control. Sorting fixes future runs. Archived controls and all original results are retained; reported historical metrics are replayable from saved mappings. See [correction details](REPRODUCIBILITY_CORRECTION.md). This is not evidence for selecting the most favorable random control.
- Natural-language atlas, statement-span diagnostics, and competence-stratified analyses are supplementary audits using fixed existing neuron selections. They do not select candidates, tune matching, or replace D3/D4 primary outcomes. They are labeled post hoc where applicable.
- Resume safety was strengthened with source signatures and manifest checks. This changes reuse behavior, not the measured alignment method.

## Scientific scope

No test-set-driven retraining, new candidate selection, threshold optimization, or replacement of an unfavorable primary result was performed. A redesigned confirmatory study requires new held-out data and a separate run version. Some MASTER extensions (new task-family generalization, learned checkpoint function trajectories, strong global permutation/optimal transport baselines, multiple random matching seeds, full dose-response, circuit transplantation) remain future work and are not represented as completed measurements.

## Publication

The user's explicit request authorizes automatic uploads to PigeonLabs/LAB_WSP2 despite MASTER's generic default against automatic pushes. This run uses the connected GitHub API with fast-forward updates and expected-head checks. Model weights, package caches, and credentials are excluded; measured arrays, configurations, source, data archives, figures, and reports are included.

The standalone publisher accepts GH_TOKEN/GITHUB_TOKEN without persisting it. Without such credentials it records `QUEUED_NOT_UPLOADED` for the connected publisher; a queue receipt is never an upload confirmation.
