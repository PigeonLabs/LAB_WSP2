# followup-v2 reporting contract

`python -m src.followup_reporting [--max-stage F0...F6]` reads `results/followup-v2/stages/F0.json` through `F6.json`. It writes only `reports/followup-v2/` and `artifacts/followup-v2/figures/`. It never changes the root README or any pilot-v1 output. The parent may prepend `README_SECTION.md` to the root README after preserving the previous version.

Each stage accepts:

- `id`, `title`, `status`, `question`, `verdict`, `rationale`.
- `metrics`: objects with `name`, `value`, optional `ci`, `unit`, `model_pair`, `model`, `method`, `task`, `split`, `n`, `n_clusters`, `source`.
- `comparisons`: `name`, `estimate` (or `effect`), `ci`, `pvalue`, `qvalue`, `correction_scope`, `source`.
- `competence_gate`: a structured description of the competence requirement and observed status; no threshold is inferred by reporting.
- `limitations`: plain strings; `next_action`: plain string.
- `artifacts`: objects `{label, path}` or relative file paths.
- `figures`: explicit chart specifications described below.

`PENDING`, `RUNNING`, `MEASURED`, `BLOCKED`, `FAILED`, `INCONCLUSIVE`, `NOT_APPLICABLE`, `COMPLETE`, `PASS`, `PARTIAL`, and `PLANNED` are accepted execution states. Verdicts are `SUPPORTED`, `NOT SUPPORTED`, `INCONCLUSIVE`, or `NOT_APPLICABLE`. An unfinished stage cannot claim `SUPPORTED`. Missing stages remain visibly pending; missing measurements are not zero-filled.

## Figure specification

All kinds share `id`, `title`, `kind`, optional `note`, and `source` (a repository-relative source path or list). `rows` may be embedded in the stage snapshot. Without embedded rows, JSON sources use `records_key` for a dotted object path; CSV is read directly. Sources must exist. If no source is supplied, the saved stage JSON is the exact source. Figure sidecar JSON stores source SHA256 values and the plotted rows.

- `line` / `scatter`: `x`, `y` name row fields, optional `series`, `xlabel`, `ylabel`, `xlim`, `ylim`, `yscale`, `reference` (horizontal baseline).
- `interval` / `bar`: `label`, `value`, `ci` name row fields (defaults `label`, `value`, `ci`); `xlabel` / `unit`; optional `xlim`. Intervals are rendered only when present.
- `heatmap`: `row`, `column`, `value` name row fields (defaults `model`, `task`, `value`); optional `row_order`, `column_order`, `vmin`, `vmax`, `percent`, `rotation`, `xlabel`, `ylabel`, `unit`. Duplicate cells fail explicitly. Missing combinations appear `N/A`, never an invented zero.

When explicit figure specifications are absent, numerical metrics sharing a name and unit are plotted together as intervals. A singleton metric stays in the table. Values are not pooled across model pairs, seeds, tasks, or incompatible units. Automatic charts use the stage snapshot as their source; metric-level sources remain linked in the detailed report.

## Scientific boundary

The renderer never assigns statistical significance from confidence-interval overlap or selects a preferred method. The stage author supplies verdicts, their scope, competence eligibility, and correction family. Model/task/seed variation, null-matching variation, and intervention effects require distinct records and labels. A positive control proves only the stated engineering recovery property; it must not be reported as independent-model semantic conservation. Transplant and merge outcomes must include competence and collateral-task behavior, not only a favorable target metric.
