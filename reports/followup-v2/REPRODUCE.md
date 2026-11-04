# Followup-v2 reproduction and stage publication

The original pilot remains at commit `127db6cdfb75d13b6ce70b4514ef82ed2f044bc0`. The followup uses new data, new independent seeds, and separate output paths. Never rerun training or fitting into a preserved result directory with altered inputs.

To inspect published numerical evidence without model weights, install the project dependencies and run:

```bash
python scripts/validate_followup_results.py --require-complete --output /tmp/followup-replay.json
```

Raw data are also published in `data/followup-v2.tar.gz`. The validator can reconstruct the deterministic dataset and checks stored hashes. Raw measurements include row identities, model coordinates, full-answer likelihood margins, token lengths, sign routes, and intervention effects. Original large weights remain local; training and model manifests pin their hashes and public model revisions.

For a new experiment reproduction, create a separate project checkout/workspace and keep its `results/followup-v2` empty. Install dependencies in its own virtual environment; download pinned base models using `scripts/prepare_models.py` so local paths refer to that workspace. Generate and freeze data with `src.followup_data.generate_dataset` and `freeze_dataset`. The following is the execution order used here (invoke the project's Python environment):

```bash
python scripts/run_followup_training.py
python -m src.followup_calibration_runner --resume --batch-size 32
python scripts/build_followup_stages.py F1 --render
python -m src.followup_runner discover
python -m src.followup_runner positive
python scripts/build_followup_stages.py F2 --render
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python -m src.followup_alignment_runner fit
python -m src.followup_runner heldout
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python -m src.followup_alignment_runner evaluate
python scripts/build_followup_stages.py F3 --render
python -m src.followup_runner causal-fit
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python -m src.followup_alignment_runner causal-fit
python -m src.followup_runner causal-test
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python -m src.followup_alignment_runner causal-evaluate
python scripts/build_followup_stages.py F4 --render
python -m src.followup_transfer --device cuda
python scripts/build_followup_stages.py F5 --render
python scripts/finalize_followup_statistics.py
python scripts/validate_followup_results.py --require-complete --output results/followup-v2/replay_audit.json
```

The supplementary analyses below are outside the 110-test primary family. The larger hard-stress set was motivated by the small post-hoc D3 split, then frozen and published before model measurement. It reuses training-length bracket strings and D3 wrapper styles while excluding all original bracket strings and adjacent mismatch cues:

```bash
python -m src.followup_stress --split D3
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python -m src.followup_proxy_ablation
python -m src.followup_hard_stress freeze
python -m src.followup_hard_stress evaluate --batch-size 16
# Only after complete primary D4 measurements and the map freeze:
python -m src.followup_stress --split D4
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python -m src.followup_causal_diagnostics
```

Run GPU commands serially. Hard-stress uses original checkpoints and calibration locks without retraining. Neither its outcomes nor supplementary diagnostics change a primary mapping, threshold, or selected transplant policy.

After all primary and supplementary measurements finish, perform the final CPU checks and reporting. These commands use the already installed project environment (for example, `.venv/bin/python` in place of `python`). The dependence sensitivity retains the same 110 original p-values and primary BH results; BY is a post-hoc robustness check, not another hypothesis family or a repair for invalid sign-flip assumptions or construct confounds. [SciPy documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.false_discovery_control.html)

```bash
python scripts/finalize_followup_statistics.py
python scripts/followup_dependence_sensitivity.py
python -m pytest -q --junitxml=results/followup-v2/tests_final.xml
python scripts/validate_followup_results.py --require-complete --output results/followup-v2/replay_audit.json
```

Create `results/followup-v2/final_audit.json` from those actual test/replay outputs, rather than entering an assumed test count. For example:

```bash
python - <<'PY'
import json
from pathlib import Path
import xml.etree.ElementTree as ET
run = Path('results/followup-v2')
cases = list(ET.parse(run/'tests_final.xml').getroot().iter('testcase'))
failed = sum(case.find('failure') is not None for case in cases)
errors = sum(case.find('error') is not None for case in cases)
skipped = sum(case.find('skipped') is not None for case in cases)
passed = len(cases) - failed - errors - skipped
replay = json.loads((run/'replay_audit.json').read_text())
assert passed > 0 and failed == errors == 0
assert replay['status'] in ('COMPLETE', 'PASS_COMPLETE') and replay['complete']
assert not replay['errors'] and replay['exit_code'] == 0
audit = {'status': 'PASS_COMPLETE',
         'tests': {'passed': passed, 'failed': failed, 'errors': errors, 'skipped': skipped,
                   'source': 'results/followup-v2/tests_final.xml'},
         'replay': replay, 'limitations': []}
(run/'final_audit.json').write_text(json.dumps(audit, indent=2) + '\n')
PY
```

A separately executed portable-archive audit can be attached as `archive_replay`; a local pass does not imply that excluded weights, legacy PNGs or intervention restart chunks were checked in the published archive. Keep its explicit preservation and fallback coverage.

The final adapter also requires a completed `results/followup-v2/scientific_review.json`: `status: "REVIEWED"`, `overall_verdict`, and exactly four `questions` with `id`, `question`, `verdict`, `rationale`, `evidence` (existing repository paths), and `scope`. Write these answers after reviewing the actual results. Do not derive scientific verdicts from the number of significant tests or blindly carry them into a new reproduction. Accepted verdicts are `SUPPORTED`, `NOT SUPPORTED`, `INCONCLUSIVE`, and `NOT_APPLICABLE`.

```bash
python scripts/build_followup_final.py --render
```

This command refuses to write F6 until all F0–F5 measured snapshots, 110-test correction, dependence sensitivity, complete audit/replay, 18 hard-stress evaluations, 26 causal-orientation diagnostics, matched proxy ablation, five transfer pairs, and the scientific review are present. It generates `report_inputs/F6.json`, the F6 snapshot and reports. Final displays add validated global q-values to F3/F4/F5 without modifying their saved primary measurements or historical stage snapshots. Recorded GPU-bearing stage wall intervals are summed once from saved runtime receipts; they are not GPU utilization or active-kernel time.

D2 causal collection can overlap CPU-only F3 fitting in wall time, but only one GPU process is active. D3 model measurements begin after the complete F3 freeze; D4 measurements begin after the complete F4 freeze. The eight measured interventions remain in raw arrays; primary F4 scoring uses only zero/mean/patch. Identical no-op and duplicate-dose controls are retained as diagnostics.

`scripts/build_followup_stages.py` reads measured files to generate stage snapshots. `src.followup_reporting` creates tables, SVG/PNG figures and exact source/value JSON. The root README is composed from `reports/followup-v2/README_SECTION.md` followed by the byte-preserved original `reports/pilot-v1-README.md`. Current-session uploads use the connected GitHub tool after each stage. Standalone publication is:

```bash
python scripts/publish_followup_github.py F3 --require-upload
```

It uses an existing `GH_TOKEN`/`GITHUB_TOKEN` from the environment without saving credentials. Without credentials it writes `QUEUED_NOT_UPLOADED`; that is not upload completion. The publisher always preserves the existing GitHub tree, excludes weights/caches, uses non-forced branch updates, and refuses a changed remote head. Raw per-intervention restart chunks are omitted because completed `effects.npz` plus baseline margins reconstruct every intervention margin exactly; chunks remain locally for recovery.

Statistical replay verifies saved arrays and calculations, not the historical chronology of execution. A passing test or exact permutation control does not establish cross-model semantic or causal conservation. Five trained models and manually authored wrappers limit population-level generalization.
