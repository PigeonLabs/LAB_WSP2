# Engine and E1 evidence audit

Audit scope: pilot-v1 E1 measured artifacts and the current E2–E4 engine. This is a post-run implementation/evidence audit, not a new confirmatory analysis. No measured arrays, mappings, or alignment methods were edited after D3 was observed. Later E2–E4 outcomes are outside this audit's initial numerical scope.

## Checks passed

- `validate_dataset` confirms 6,144 train examples and 512 examples in each of D1–D4, balanced 64/64 truth labels per concept for each evaluation split. Exact prompts, wrapper templates, unordered operand pairs, and content keys are disjoint across splits.
- All D1/D2/D3 saved row IDs for seed11, seed29, untrained11, and untrained29 equal their corresponding dataset order. All 12 product matrices are finite and shape `(512, 64)`; selected layers are `[1, 2, 3, 4]`, with 16 candidates per layer.
- Every trained and untrained E1 method's reported mean was recomputed from its frozen source/target map and saved D3 activation matrix and matched the saved metric. No independent algorithm is claimed for this check: it verifies artifact consistency with the estimand implemented by the engine.
- Seeds 11 and 29 each completed 1,200 planned steps; initial parameter hashes differ, and both final hashes differ from their respective initial hashes. These are independently initialized 20,718,080-parameter models, not fine-tuned copies of one pretrained checkpoint.
- Training accepts only records marked train. Candidate selection uses D1; mapping methods and descriptive partial thresholds use D2; D3 only supplies response evaluation. Alignment maps are serialized before analysis loads D3 arrays. D3 activation collection occurs before mapping analysis, but no D3 values enter any fit operation.
- The common answer-token prefix correction is applied consistently to capture and intervention. Teacher-forced scoring still includes the full original correct and foil continuations. This avoids a trivial byte-tokenizer shared-space cancellation at the last MLP layer. FP32 inference and FP64 analysis are used.
- Core integration tests cover full multi-token scoring, padding invariance, shared-prefix boundary, independent initialization, identity intervention, complete matched donors, output storage, and changed-config resume rejection.

## E1 interpretation must be conservative

| D3 task | Seed 11 accuracy | Seed 29 accuracy |
|---|---:|---:|
| arithmetic | 0.4844 | 0.5078 |
| comparison | 0.8203 | 0.6797 |
| negation | 0.6797 | 0.4922 |
| syntax | 0.9141 | 0.9141 |

Arithmetic is approximately chance in both models, and negation is approximately chance for seed29. The main metric pools all four tasks; it is **not a competence-conditioned metric**. Reporting the capability table explicitly is therefore necessary. Correspondence failure on these weak tasks cannot reject conservation of a function that was not demonstrably learned.

Trained activation matching exceeds one fixed random map by **0.366346**, with cluster bootstrap 95% CI **[0.295642, 0.443003]**, exact two-sided p **0.03125**, and within-pair BH q **0.052083**. The corrected result does not pass q < .05.

The untrained control is particularly important: activation matching exceeds its fixed random map by **0.135443**, q **0.039062**, despite **0.5 accuracy on every task for both untrained models**. Thus positive held-out activation alignment can arise from shared input statistics and architecture before task learning. It is not sufficient evidence of conserved learned neuron functions. No direct preregistered trained-versus-untrained difference-in-differences test is present; their individually selected candidate sets also differ. H1 should remain **INCONCLUSIVE**.

Semantic minus activation matching is **-0.069521**, CI **[-0.098566, -0.040462]**, q **0.052083**. This pilot does not demonstrate semantic matching superiority. An interval excluding zero and q above .05 are not contradictory: these are different inferential procedures with only six clusters.

## Important statistical and scientific limitations

1. **One random matching realization:** the random baseline uses seed1729 once per model pair. Cluster intervals condition on that fixed map and do not include random-mapping uncertainty. A future preregistered run should average multiple matching seeds and expose its null distribution. The present maps must not be replaced after seeing D3.
2. **Only six wrapper clusters:** all concepts sharing a wrapper are clustered jointly, correctly avoiding 24-cluster pseudoreplication. The minimum attainable exact two-sided sign-flip p is 0.03125. Bootstrap intervals are exploratory and cannot establish robustness across natural-language domains.
3. **Multiplicity scope:** BH correction is applied within one model-pair comparison family, not globally across every experiment/model pair. Reports should not present pair-local q as study-wide control.
4. **Truth contrast is not unique semantic identity:** fingerprints encode true-versus-false responses within four synthetic task categories. They do not identify primary functions independent of truth, output yes/no bias, surface grammar, or token cues. Atlas primary function labels remain UNKNOWN.
5. **Shared task grammar and shortcuts:** split-disjoint wrapper wording does not eliminate shared arithmetic syntax, property-token equality, or bracket-count shortcuts. Common yes/no answer alternatives can align generic output-choice effects in E4. See [data design limitations](DATA_DESIGN_LIMITATIONS.md).
6. **Weak weight baseline:** `weight_similarity` is a concatenated local gate/up/down cosine heuristic in the original residual bases. It is not global Git Re-Basin and does not optimize residual-stream permutation constraints. Cross-layer matches also lack a structural permutation interpretation.
7. **Partial threshold is descriptive:** shuffled individual D2 rows create a row-max null threshold. The shuffle does not preserve full matched-pair/wrapper dependence; coverage from it is not a calibrated neuron-level significance claim. No neuron-level p-values are asserted.
8. **Selected candidate population:** half the candidates are D1 contrast-selected and half random. Reported quality applies to this chosen candidate mixture, not all native neurons. One-to-many quality and one-to-one quality have different matched-pair weighting and coverage.
9. **Two training seeds only:** one independent-trained model pair is insufficient for a seed-population stability estimate. Early/middle checkpoints are saved but their functional evolution is not analyzed in this engine.
10. **Observation scope:** capture uses the model-specific final shared-context token before answer divergence. It does not yet compare character-span pooled measurements; tokenizer-length sensitivity is recorded but not statistically controlled. Persisted down-projection contribution is its norm, not the full residual vector.
11. **Natural-language atlas missing:** no separate public natural-language corpus activations are collected by this engine. The measured atlas consists entirely of controlled synthetic tasks.
12. **E4 scope:** zero, mean, and within-model opposite-label patching are present; scaling is tested at hook level but not a measured dose-response study. D4 contains new wrappers/examples, not a new task family. Mean and patch interventions can still be off-distribution. E4 normalizes by D2 fit margin standard deviation; correlations are scalar-scale invariant, so this normalization does not independently demonstrate scale robustness.
13. **Controls not interchangeable:** the E4 shifted-task control disrupts task/row correspondence. It is not an independently trained mismatched-model-family control. Untrained causal controls are not included in the current runner.

## Resume and preservation audit

Low-level `collect_model` verifies a signature including model identity, dataset, selection count, precision, and boundary policy. `collect_causal` verifies data/config/source-manifest identity. However, at audit time `runner.collect` returned immediately on any existing manifest, bypassing these low-level checks. Likewise both analysis entrypoints return existing metrics without source hash comparison. This can reuse stale artifacts if inputs/config are changed under the same run directory. It does not invalidate the fresh pilot-v1 execution whose raw IDs and settings were checked above.

Recommended infrastructure correction: validate current source/config signatures before skipping in the runner and analyses; reject mismatches and require a new versioned run directory. This is a resume safety repair, not a change to the measured methods. Mid-training restart from optimizer state is not implemented: completed training is reusable, while an incomplete initial checkpoint raises rather than silently overwriting. `--resume` must not be described as arbitrary-step training continuation.

## Evidence

- [Trained E1 metrics](../results/pilot-v1/E1/trained/metrics.json), [untrained metrics](../results/pilot-v1/E1/untrained/metrics.json).
- [Trained frozen mappings](../results/pilot-v1/E1/trained/frozen_mappings.json), [trained matched-neuron rows](../results/pilot-v1/E1/trained/matches.csv).
- [Seed11 collection manifest](../results/pilot-v1/collections/seed11/manifest.json), [seed29 collection manifest](../results/pilot-v1/collections/seed29/manifest.json).
- [Experiment implementation](../src/experiment.py), [training implementation](../src/training.py), [runner](../src/runner.py), [integration tests](../tests/test_experiment.py).
