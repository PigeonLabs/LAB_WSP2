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

D2 causal collection can overlap CPU-only F3 fitting in wall time, but only one GPU process is active. D3 model measurements begin after the complete F3 freeze; D4 measurements begin after the complete F4 freeze. The eight measured interventions remain in raw arrays; primary F4 scoring uses only zero/mean/patch. Identical no-op and duplicate-dose controls are retained as diagnostics.

`scripts/build_followup_stages.py` reads measured files to generate stage snapshots. `src.followup_reporting` creates tables, SVG/PNG figures and exact source/value JSON. The root README is composed from `reports/followup-v2/README_SECTION.md` followed by the byte-preserved original `reports/pilot-v1-README.md`. Current-session uploads use the connected GitHub tool after each stage. Standalone publication is:

```bash
python scripts/publish_followup_github.py F3 --require-upload
```

It uses an existing `GH_TOKEN`/`GITHUB_TOKEN` from the environment without saving credentials. Without credentials it writes `QUEUED_NOT_UPLOADED`; that is not upload completion. The publisher always preserves the existing GitHub tree, excludes weights/caches, uses non-forced branch updates, and refuses a changed remote head. Raw per-intervention restart chunks are omitted because completed `effects.npz` plus baseline margins reconstruct every intervention margin exactly; chunks remain locally for recovery.

Statistical replay verifies saved arrays and calculations, not the historical chronology of execution. A passing test or exact permutation control does not establish cross-model semantic or causal conservation. Five trained models and manually authored wrappers limit population-level generalization.
