# Followup v2 — frozen protocol

The original pilot is preserved at commit `127db6cdfb75d13b6ce70b4514ef82ed2f044bc0`. Its original README is copied to `reports/pilot-v1-README.md`; `results/followup-v2/preservation_before.json` records SHA256 hashes. No original measured values, mappings, data, or figures may be overwritten. Root README is an accumulating view.

This extension executes all five directions in the original next-experiments report and the analysis remedies. It remains a bounded mechanistic study, not a claim of universal neuron monosemanticity. Numerical settings are frozen in `configs/followup_v2.json` before new held-out observations.

| Stage | Execution and evaluation |
|---|---|
| F0 | Data oracle, leakage and shortcut audit; preserve old evidence; freeze protocol |
| F1 | Train five independent 20.7M decoders; keep initial/middle/final checkpoints. Calibrate three cached base model prompt formats on calibration only. Report D3/D4 task competence and response bias |
| F2 | Known SwiGLU neuron permutation: verify logits, exact correspondence and mapped intervention effects; wrong/random mappings as negative controls |
| F3 | Ten independent-seed pairs and three cross-family pairs; initial/middle/final trajectory; answer and statement-span positions. Activation, rank, expanded task semantic, sign semantic, shuffled labels, restricted/flexible layers, partial and one-to-many; 100 random mappings per pair |
| F4 | Single neurons and groups, zero/mean/opposite-label patch plus dose-response at two positions; D2 train/validation chooses causal weight, D4 tests effects. No candidate tuning from D3/D4 |
| F5 | Five directed independent-seed transplants and selective interpolation; aligned, random matched-size, naive parameter averaging, unchanged target. D2 selects configurations with retention guardrail; all frozen candidates measured on D4. Cross-family raw weight copying is structurally inapplicable |
| F6 | Global multiplicity correction; numerical replay; preservation check; final reports and stage uploads |

Training, calibration, discovery (D1), fitting (D2), activation test (D3) and causal/transfer test (D4) are separate. New data remove the previously identified arithmetic parity and bracket-count shortcuts and replace property-name equality logic. This does not establish absence of every possible shortcut. Three generation seeds are distributed within the new benchmark; they are not three independent benchmark families.

Each evaluation split has 24 shared wrapper clusters, balanced paired truth labels, and four concepts. The primary response score removes between-task mean differences and averages within-task correlations. Bootstrap/sign-flip uses wrappers, not neurons or all ten overlapping seed pairs as independent replicates. Report pair and seed variability; inference is conditional on the finite five trained models and this benchmark. Repeated random mappings address the original single-random-control limitation. Interim confidence intervals and unadjusted p values do not authorize significance claims; the full confirmatory family gets BH adjustment in F6.

Per-task capability requires accuracy at least 0.70 and Wilson 95% lower bound above 0.50 for both models; D4 is assessed separately. All task measurements are retained even if the gate fails, but low competence cannot falsify functional conservation. Checkpoint analyses use fixed final-D1 candidates to avoid changing the population mid-trajectory; initial/middle data are observational controls. A semantic fingerprint remains a finite task proxy. Its fit and final causal evaluation are independent.

Permutation is an exact positive control within one model, not evidence of independently learned conservation. Neuron transplantation across independent residual bases may fail even with useful activation alignment. Selective merging is tested for task gain and retention rather than described as circuit-preserving in advance. Retention on these four synthetic tasks is not general language ability preservation.

GPU operations run serially. Budget remains 8 GPU-hours including the original approximately 0.108 measured GPU wall-hours and 60GB additional disk. No paid service, global environment change, or unrelated process interruption. Stage results, code, source arrays, generated figures and reports are uploaded to the explicitly authorized repository after each stage; weights/caches are excluded. Failures and protocol amendments are retained, and interrupted execution never counts as a completed stage.
