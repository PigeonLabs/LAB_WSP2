# Followup-v2 research critique

측정 완료 여부, 과제 능력, 대조군 회복, 가설 지지를 구분합니다. 아래 한계는 각 단계의 저장된 증거와 함께 읽어야 합니다.

## F0 — 새 benchmark와 기존 결과 보존

상태: MEASURED; 판정: SUPPORTED.

- Task grammars shared across splits despite distinct wrappers.
- Logic AST family is finite; numeric arithmetic restricted to addition.
- Invalid bracket arrangements can have local order cues; multiset balance does not establish recursive parsing.
- Generation seeds do not substitute for model seeds.
- 24 prompt wrappers are manually authored and not random draws from all language.

[측정과 원본](F0_REPORT.md)

## F1 — 5개 독립 초기화 학습과 calibration 전용 형식 선택

상태: MEASURED; 판정: INCONCLUSIVE.

- Calibration format-selection scores are optimistic and are not final generalization estimates.
- Wilson intervals are operational competence gates; they do not replace wrapper-cluster research intervals.
- Five initialization seeds still represent one small architecture and one training distribution.
- No D3 or D4 measurement is loaded by this stage builder.

[측정과 원본](F1_REPORT.md)

## F2 — 정확한 뉴런 순열의 양성 대조군

상태: MEASURED; 판정: SUPPORTED.

- constructed within-model permutation symmetry; not independently learned conservation
- Recovery fraction uses 32 candidate neurons; correlations use 768 input examples.
- Logit equality uses the stored absolute plus relative tolerance, not absolute tolerance alone.
- A constructed within-model permutation is not independent seed evidence.
- Only the registered control and selected neuron/position coverage are tested.

[측정과 원본](F2_REPORT.md)

## F3 — 독립 시드·이종 계열의 두 위치 정렬과 학습 궤적

상태: MEASURED; 판정: INCONCLUSIVE.

- Five seeds produce ten dependent pairs, not ten independent replications.
- Final-D1 candidate selection and final-D2 maps are reused across checkpoint trajectories.
- Expanded semantic labels remain input-task/subtype truth-contrast proxies with UNKNOWN permitted.
- Final q values use the single110-member global BH family. Raw p values and original primary measurements are preserved.
- A positive response correlation does not establish equal causal roles.
- Cross-family prompts use calibration-selected formats: Qwen fourshot, Smol default, OLMo explicit. The target statement and row identity are shared, but prefix contexts differ; this is a calibrated-use comparison, not an identical-full-context test. Native character-span alignment does not remove the prefix confound.
- All three pretrained families fall below the0.70 calibration competence threshold. D3 competence must be judged separately; low-competence failures cannot establish absence of functional conservation.
- Overall syntax accuracy above the operational competence threshold does not prove recursive parsing or structural understanding. The posthoc no-adjacent-mismatch stratum is small and content-confounded; its gap is not a controlled causal effect.
- Syntax shortcut findings do not substitute for separate construct validation of comparison, negation, or arithmetic. Frozen primary mappings, thresholds and tests are unchanged.

[측정과 원본](F3_REPORT.md)

## F4 — 단일·그룹 뉴런 인과 정렬과 dose-response

상태: MEASURED; 판정: SUPPORTED (정답 위치의 등록된 truth-oriented 개입효과 상관 개선에 한정; 넓은 기능 보존은 판단 불가).

고정 D2 절차를 새 D4 문항에 적용했을 때, 독립 시드 answer 위치의 combined−semantic 차이는 single +0.05870 (95% wrapper CI [+0.04763, +0.06991]), group +0.06778 (95% wrapper CI [+0.05201, +0.08372])였다. 원래 110개 검정군의 BH에서 양의 pair 효과는 single 8/10, group 4/10이고, 사후 BY 민감도에서는 7/10, 4/10이다. 이 사실은 정답 방향으로 정의된 zero/mean/patch 효과의 대응 지표에 한정한 개선을 지지한다. 위 cohort CI는 고정 모델·공유 wrapper에 조건부인 기술적 구간이며 다중검정 보정 구간이 아니다. Group span 차이는 +0.00161 (95% wrapper CI [-0.00997, +0.01340])로 일관된 span 개선을 보이지 않는다. Tiny single-answer fit 6/10과 공개 single-answer fit 3/3은 인과 가중치 1을 선택했으므로 의미·인과 정보의 시너지를 입증하지 않는다. 같은 정답끼리 비교한 tiny answer의 절대 상관은 single 0.01726, group 0.03797로 더 약하며, view 간 감소를 별도의 확증적 차이 검정으로 취급하지 않는다. Activation 기준선 대비 비교는 사후 보충 분석이다. 넓은 의미의 인과 기능 보존·회로 동등성·이식 유용성은 여전히 판단 불가다.

[최종 검토 원본](../../results/followup-v2/scientific_review.json)

- All model pairs sharing a seed are dependent; inference is conditional on the observed model collection.
- Groups contain fixed D1 candidates; the results do not imply full circuit recovery.
- Zero/mean/patch can alter activation distributions; dose response is supplementary.
- Exact-zero or constant effects are not evidence of causal agreement.
- No D4 outcome changes the frozen maps or D2-selected mixing weights.
- Cross-family causal comparisons retain each calibration-selected prompt format: Qwen fourshot, Smol default, OLMo explicit. The same target statements have different prefix contexts. Character-span alignment cannot remove this context confound; conclusions concern calibrated-use conditions, not identical full inputs.
- Pretrained calibration competence is below0.70. D4 competence is evaluated independently; low competence cannot falsify conservation of a function not established in the tested model.
- Saved D4 by-task results split into all pairs and pairs passing both operational task gates. Descriptive only: no new confidence intervals, p-values, refits or primary-family changes. Eligibility conditions on D4 outcomes; different subsets and missing-wrapper support must not be treated as a controlled causal comparison. Passing the syntax accuracy gate does not establish recursive or structural understanding.
- The primary F4 comparison omitted an activation-based causal matching baseline. This separate gap check was added after some tiny-model D4 outcomes had been observed. Both activation_raw and activation_task_centered maps were fitted only on the first12 D2 wrappers; fitting read no D4 values. Raw activation follows the F3 raw-correlation matching family; task-centered activation is an additional control. Both are retained without selecting a winner. The comparison is descriptive and posthoc: no new p/q/CI, no110-family change, no automatic conservation support. Means equally weight finite observed pair means; missing pair/wrapper coverage must be compared. Shared-model pairs are dependent.
- Same frozen maps and zero/mean/patch effects, viewed as truth-oriented, yes-oriented, and within-label correlations. This is an exploratory answer-bias diagnostic, not a new primary endpoint or refit. Different views can have different identifiable cell support; attenuation is consistent with answer-orientation confounding but does not prove its exclusive cause. Undefined views remain N/A.

[측정과 원본](F4_REPORT.md)

## F5 — 뉴런 이식과 선택적 보간 병합

상태: MEASURED; 판정: NOT SUPPORTED (선택 정책의 유용한 전이 개선은 확립되지 않음).

선택 정책의 D4 목표 과제 평균 변화는 +0.1042 percentage points, 95% wrapper CI [0, +0.3125] percentage points, p=q=1이었다. 한 쌍의 한 wrapper에서 192문항 중 정답 한 개가 늘었고 네 쌍은 정책을 선택하지 않았다. 유용한 전이 개선이 확립되지 않았다는 판정이며 효과가 정확히 0이거나 모든 병합이 불가능하다는 뜻은 아니다. Naive 50% 전체 평균은 comparison 정확도를 41.15–45.31 percentage points 낮췄고, alpha=1은 donor 전체 교체이므로 병합 성공으로 해석하지 않는다.

[최종 검토 원본](../../results/followup-v2/scientific_review.json)

- D2 jointly selects task, mapping, and interpolation weight; its gains are in-sample.
- Random donors preserve target units/group size but not donor activation magnitude.
- Native parameter interpolation does not establish circuit-preserving model merging.
- Naive alpha=1 replaces the target with the full donor; it is not evidence of successful model merging. The alpha0.5 failure is a descriptive observed control, not a universal impossibility result.
- Directed pairs reuse seeds; pair tests are descriptive and not five independent replications.

[측정과 원본](F5_REPORT.md)

## F6 — 전역 보정·재현 검증과 최종 연구 판정

상태: MEASURED; 판정: INCONCLUSIVE.

- Five trained seeds share one architecture/training distribution; overlapping pairs are dependent. Wrapper uncertainty is conditional on observed models, not unseen-seed population uncertainty.
- All110 predeclared tests share one BH family. Conditional pair effects and cohort confidence intervals are not independent replications; exploratory proxy, stress, and orientation diagnostics are outside that family.
- Posthoc BY sensitivity reuses the same110 original p-values; it does not replace primary BH, create new hypotheses, or repair invalid individual p-values, wrapper sign-flip assumptions, low competence or construct confounds.
- Qwen fourshot, Smol default and OLMo explicit retain different prompt-prefix contexts. Shared target statements and native span alignment do not create identical full-context comparisons.
- An operational accuracy/Wilson gate does not validate the intended construct. Syntax results can reflect remaining local cues; the posthoc small D3 stratum and new hard set have different content.
- New hard cases were frozen before their inference but designed after D3 observation; they remain exploratory, not a new confirmatory test or evidence of recursive parsing.
- Truth-oriented, yes-oriented and within-label causal views can differ in identifiable support. Attenuation is not proof that answer bias exclusively caused the original association.
- The four-dimensional versus expanded proxy comparison uses the samefollowup-v2 evidence and was requested after D3; it cannot explain every historical pilot-v1 to followup-v2 change.
- Native neuron transplantation and parameter interpolation do not establish whole-circuit-preserving model merging.
- Sum of saved serial model-stage wall intervals, including CPU/IO/transfer overhead. An upper wall-duration accounting for recorded GPU-bearing stages, not GPU utilization, active kernel time, or complete project elapsed time. CPU statistical analysis and reporting are excluded. Training is counted once via aggregate runtime; its per-seed manifests are not added again.
- Named followup directories, including local checkpoints and restart chunks; excludes preexisting base-model caches and unrelated workspace files. This is the saved accounting snapshot, not a promise that later report generation consumes zero additional bytes.
- Peak Torch allocated memory measures the framework allocator, not total physical device usage or GPU utilization.
- Only listed present files, archived member bytes, and saved README were verified; omitted weights/PNGs were not verified.
- 배포 아카이브 replay 상태는 COMPLETE이며, 검증 파일 245개·생략 파일 16개의 범위를 따로 기록했다.
- Saved-artifact replay does not establish historical execution chronology or independently regenerate excluded model weights.
- The archive replay used a relocated publication-shaped copy, not a fresh GitHub download. Final remote Git blob integrity is checked separately after publication.
- Archive coverage explicitly omits six original weight files and ten legacy PNGs; original raw dataset bytes are checked through tar members, and the original README through its saved copy.
- Saved-artifact replay does not regenerate excluded model weights, independently rerun training, or establish historical execution chronology.
- Inference is conditional on fixed models, selected native units, and authored wrapper clusters; shared model pairs are dependent.
- Saved D4 by-task results split into all pairs and pairs passing both operational task gates. Descriptive only: no new confidence intervals, p-values, refits or primary-family changes. Eligibility conditions on D4 outcomes; different subsets and missing-wrapper support must not be treated as a controlled causal comparison. Passing the syntax accuracy gate does not establish recursive or structural understanding.
- The primary F4 comparison omitted an activation-based causal matching baseline. This separate gap check was added after some tiny-model D4 outcomes had been observed. Both activation_raw and activation_task_centered maps were fitted only on the first12 D2 wrappers; fitting read no D4 values. Raw activation follows the F3 raw-correlation matching family; task-centered activation is an additional control. Both are retained without selecting a winner. The comparison is descriptive and posthoc: no new p/q/CI, no110-family change, no automatic conservation support. Means equally weight finite observed pair means; missing pair/wrapper coverage must be compared. Shared-model pairs are dependent.

[측정과 원본](F6_REPORT.md)

## 새 hard syntax 보충 검증

- Post-hoc motivated by D3 local-cue weakness; fresh outcomes do not make it preregistered primary evidence.
- Valid strings need suitable closing runs, so their structural distribution differs from the original syntax corpus.
- Equal5..8pair length range prevents longer strings being the sole explanation; depth distribution can still differ.
- Removing adjacent type mismatches does not remove every finite-state/local cue or prove recursive parsing.
- Wrappers were already inspected in D3; only content/outcomes are new.
- All18 confidence intervals are descriptive wrapper-cluster bootstrap intervals conditional on fixed models; no global claims are inferred from overlap or individual exploratory p-values.
- Balanced true/false pairs make chance accuracy50%; yes preference and true/false accuracy can still be highly asymmetric. Ties count as incorrect.
- Different calibration-selected prefix contexts remain for Qwen, Smol and OLMo; matched target content does not mean identical full prompts.
- Original D3 and the hard set differ in content and structural distribution. Their difference is not a controlled causal effect or proof of recursive parsing.

[전체 측정과 출처](HARD_STRESS_REPORT.md)

