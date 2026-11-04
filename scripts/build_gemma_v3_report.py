#!/usr/bin/env python3
"""Render v3 stage receipts without changing measurements or older reports.

Usage: .venv/bin/python scripts/build_gemma_v3_report.py [--max-stage G2]

Inputs: results/followup-v3-gemma-map/stages/G0.json ... G6.json.
Required stage keys: stage, status (or state), title, summary. Allowed status:
DESIGNED, RUNNING, MEASURED, BLOCKED, NOT_APPLICABLE, NOT_EVALUABLE, INVALID.
Optional keys: scope, verdict, rationale, limitations (list of strings),
sources/artifacts (lists of repository-relative existing file paths), metrics
(list of {name, value, unit, source}). An absent/null metric displays N/A.
Optional tables: [{title,columns:[{key,label,format?}],rows:[...],sources:[...],
caption}]. Column format='percent' expects a fractional rate; 'percent_ci'
expects [low,high]. Tables preserve explicit cluster/variant denominators.
MEASURED requires at least one raw source. BLOCKED may retain actual diagnostic
measurements; it never implies the stage's scientific claim was measured.

Figures: {id,title,kind,x,y,rows,sources,caption,unit,xlabel,ylabel,...}.
Kinds: bar/interval (x categorical, y numeric), line/scatter (x/y numeric),
heatmap (x/y categorical, value numeric). Optional series names a grouping key;
low/high name interval columns; unit='fraction' formats fractional rates as %;
reference is a numeric benchmark; vmin/vmax and center control heatmap scale.
An optional xlim=[lower,upper] explicitly sets a numeric horizontal domain.
All rows remain in source.json, including missing values and denominators.
Numeric null is missing, never zero. NaN/Inf, duplicate heatmap cells, invalid
intervals and unknown statuses fail. Empty figures are described as unavailable.
For blocked Holm claims, p=1 placeholders must be labeled in metric name/unit;
the renderer never computes tests or scientific verdicts from status/figures.

Outputs ONLY reports/followup-v3-gemma-map/RUN_README_SECTION.md and newly
rendered artifacts/followup-v3-gemma-map/figures/G*_{id}.{png,svg,source.json}.
The fragment uses root-relative repository links for parent README composition.
The source receipts include the exact input rows plus SHA256 of every source
and the stage snapshot. Run after stage writers finish, before upload snapshots.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm
from matplotlib.ticker import PercentFormatter
import numpy as np

PREFIX = "followup-v3-gemma-map"
STATUSES = {"DESIGNED", "RUNNING", "MEASURED", "BLOCKED", "NOT_APPLICABLE", "NOT_EVALUABLE", "INVALID"}
COLORS = ["#28649B", "#CB7837", "#9B5379", "#747D37", "#6B7280"]
STAGES = ["G0", "G1", "G2", "G3", "G4", "G5", "G6"]


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=lambda x: (_ for _ in ()).throw(ValueError(f"Nonfinite JSON: {x}")))


def source_path(root, value):
    path = (root / value).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError(f"Source missing or outside repository: {value}")
    return path


def receipt(root, path):
    path = source_path(root, path)
    return {"path": path.relative_to(root).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def number(value):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"Expected finite measurement or null: {value!r}")
    return float(value)


def escaped(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


def display(value):
    if value is None:
        return "N/A (미측정/누락)"
    if isinstance(value, float):
        number(value)
        return f"{value:.6g}"
    return escaped(value)


def table_cell(value, style=None):
    if value is None:
        return display(None)
    if style == "percent":
        return f"{number(value):.2%}"
    if style == "percent_ci":
        if len(value) != 2:
            raise ValueError("Interval table cell must contain two bounds")
        lo, hi = map(number, value)
        if lo is None or hi is None:
            return display(None)
        if lo > hi:
            raise ValueError("Reversed table interval")
        return f"[{lo:.2%}, {hi:.2%}]"
    return display(value)


def wrap(value, width=30):
    return "\n".join(textwrap.wrap(str(value), width=width))


def link(path, label=None):
    return f"[{label or path}]({path})"


def draw_figure(root, stage_path, stage, spec):
    ident = spec["id"]
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", ident):
        raise ValueError(f"Invalid figure id: {ident}")
    rows = spec.get("rows", [])
    sources = list(dict.fromkeys([stage_path.relative_to(root).as_posix(), *spec.get("sources", [])]))
    receipts = [receipt(root, s) for s in sources]
    if not rows:
        return None
    kind, x, y = spec["kind"], spec["x"], spec["y"]
    value_key = spec.get("value", "value") if kind == "heatmap" else y
    values = [number(r.get(value_key)) for r in rows]
    if not any(v is not None for v in values):
        return None
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "axes.spines.top": False, "axes.spines.right": False, "svg.hashsalt": "gemma-v3-report"})
    fig, ax = plt.subplots(figsize=(10.8, 5.5), layout="constrained")
    fraction = spec.get("unit") == "fraction"
    fmt = lambda v: f"{v:.1%}" if fraction else f"{v:.3g}"
    if kind == "heatmap":
        xs, ys = list(dict.fromkeys(str(r[x]) for r in rows)), list(dict.fromkeys(str(r[y]) for r in rows))
        matrix = np.full((len(ys), len(xs)), np.nan)
        seen = set()
        for r, v in zip(rows, values):
            cell = (ys.index(str(r[y])), xs.index(str(r[x])))
            if cell in seen:
                raise ValueError(f"Duplicate heatmap cell: {cell}")
            seen.add(cell)
            if v is not None:
                matrix[cell] = v
        fig.set_size_inches(max(9, len(xs)*1.2), max(4, len(ys)*.56+2))
        bounds = {k: spec[k] for k in ("vmin", "vmax") if k in spec}
        if "center" in spec:
            center = number(spec["center"])
            extent = max(abs(min(v for v in values if v is not None)-center), abs(max(v for v in values if v is not None)-center), 1e-9)
            norm = TwoSlopeNorm(vcenter=center, vmin=spec.get("vmin", center-extent), vmax=spec.get("vmax", center+extent))
            mesh = ax.imshow(matrix, cmap="PuOr_r", norm=norm, aspect="auto")
        else:
            mesh = ax.imshow(matrix, cmap="Blues", aspect="auto", **bounds)
        ax.set_xticks(range(len(xs)), [wrap(a, 18) for a in xs])
        ax.set_yticks(range(len(ys)), [wrap(a, 34) for a in ys])
        for (i,j), v in np.ndenumerate(matrix):
            rgba = mesh.cmap(mesh.norm(v)) if np.isfinite(v) else (1,1,1,1)
            luminance = .2126*rgba[0]+.7152*rgba[1]+.0722*rgba[2]
            ax.text(j, i, fmt(v) if np.isfinite(v) else "N/A", ha="center", va="center", color="white" if luminance < .48 else "#18212B")
        cb = fig.colorbar(mesh, ax=ax, shrink=.85)
        if fraction:
            cb.ax.yaxis.set_major_formatter(PercentFormatter(1))
        cb.set_label(spec.get("value_label", spec.get("unit", value_key)))
    elif kind in {"bar", "interval"}:
        fig.set_size_inches(10.8, max(4, len(rows)*.52+1.8))
        for i, (r, v) in enumerate(zip(rows, values)):
            if v is None:
                ax.text(.01, i, "N/A", transform=ax.get_yaxis_transform(), va="center")
                continue
            if kind == "bar":
                ax.barh(i, v, color=COLORS[0], height=.65)
            else:
                ax.plot(v, i, "o", color=COLORS[0], ms=6)
                lo, hi = number(r.get(spec.get("low", "low"))), number(r.get(spec.get("high", "high")))
                if (lo is None) != (hi is None):
                    raise ValueError("An interval requires both bounds or neither")
                if lo is not None:
                    if not lo <= v <= hi:
                        raise ValueError("Interval does not contain estimate")
                    ax.hlines(i, lo, hi, color=COLORS[0], linewidth=2)
            ax.annotate(fmt(v), (v, i), xytext=(6, 5), textcoords="offset points", fontsize=10)
        ax.set_yticks(range(len(rows)), [wrap(r[x], 38) for r in rows])
        ax.invert_yaxis()
        ax.axvline(0, color="#555D65", lw=.8)
        ax.margins(x=.18)
        if fraction:
            ax.xaxis.set_major_formatter(PercentFormatter(1))
        ax.set_xlabel(spec.get("ylabel", y))
        ax.xaxis.grid(True, alpha=.15)
    elif kind in {"line", "scatter"}:
        series_key = spec.get("series")
        groups = list(dict.fromkeys(str(r.get(series_key, "")) for r in rows)) if series_key else [""]
        for i, group in enumerate(groups):
            selected = [r for r in rows if not series_key or str(r.get(series_key, "")) == group]
            coordinates = [(number(r.get(x)), number(r.get(y))) for r in selected]
            # NaN breaks lines at missing observations; it is not a zero value.
            xx = [a if a is not None else np.nan for a,b in coordinates]
            yy = [b if b is not None else np.nan for a,b in coordinates]
            ax.plot(xx, yy, marker=["o", "s", "^", "D", "v"][i%5], linestyle="-" if kind == "line" else "none", color=COLORS[i%5], label=group or None, ms=4)
        if series_key:
            ax.legend(frameon=False, loc="upper left", bbox_to_anchor=(1.01,1))
        if fraction:
            ax.yaxis.set_major_formatter(PercentFormatter(1))
        ax.grid(alpha=.15)
        ax.set_xlabel(spec.get("xlabel", x))
        ax.set_ylabel(spec.get("ylabel", y))
    else:
        raise ValueError(f"Unknown figure kind: {kind}")
    if "reference" in spec:
        ref = number(spec["reference"])
        if ref is not None:
            (ax.axvline if kind in {"bar", "interval"} else ax.axhline)(ref, color="#555D65", linestyle="--", linewidth=1)
    if "xlim" in spec:
        ax.set_xlim(*spec["xlim"])
    ax.set_title(wrap(spec["title"], 78), loc="left", pad=14, fontsize=14)
    output = root / "artifacts" / PREFIX / "figures" / f"{stage}_{ident}"
    output.parent.mkdir(parents=True, exist_ok=True)
    for extension in ("png", "svg"):
        fig.savefig(output.with_suffix("."+extension), dpi=160, bbox_inches="tight", metadata={"Date": None} if extension == "svg" else None)
    plt.close(fig)
    sidecar = output.with_suffix(".source.json")
    sidecar.write_text(json.dumps({"schema_version":1, "stage":stage, "figure":spec, "sources":receipts, "missing_policy":"null remains missing; no statistical inference by renderer"}, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    return output.relative_to(root).as_posix()


def render(root: Path, max_stage="G6"):
    root = root.resolve()
    stage_dir = root / "results" / PREFIX / "stages"
    loaded = []
    for stage in STAGES[:STAGES.index(max_stage)+1]:
        path = stage_dir / f"{stage}.json"
        if not path.exists():
            loaded.append((stage, None, None))
            continue
        data = read_json(path)
        status = data.get("status", data.get("state"))
        if data.get("stage") != stage or status not in STATUSES:
            raise ValueError(f"Invalid stage identity/status: {path}")
        if data.get("status") and data.get("state") and data["status"] != data["state"]:
            raise ValueError(f"Contradictory state/status: {path}")
        if status == "MEASURED" and not data.get("sources"):
            raise ValueError(f"Measured stage requires raw sources: {path}")
        for src in [*data.get("sources", []), *data.get("artifacts", [])]:
            source_path(root, src)
        loaded.append((stage, data, path))
    lines = ["## Followup-v3 Gemma map — 실행 기록", "", "기존 pilot/v2 결과와 분리한 새 실행이다. 아래 상태는 단계별 실행 receipt를 따른다. 각 단계의 문구는 그 receipt의 기록 시점을 나타내며, 뒤 단계에서 갱신된 판정은 해당 단계에 따로 기록한다. **MEASURED는 해당 단계 산출물의 측정을 뜻하며 가설 지지를 뜻하지 않는다.** RUNNING/BLOCKED는 완료 결과가 아니며, 미측정 값은 0으로 채우지 않는다.", "", f"{link(f'reports/{PREFIX}/DESIGN.md', '설계')} · {link(f'configs/{PREFIX.replace("-", "_")}.json', '설정')}", "", "| 단계 | 상태 | 내용 |", "|---|---|---|"]
    for stage, data, path in loaded:
        lines.append(f"| {stage} | {data.get('status', data.get('state')) if data else 'DESIGNED (실행 receipt 없음)'} | {escaped(data.get('title', '')) if data else '미측정'} |")
    for stage, data, path in loaded:
        if data is None:
            continue
        status = data.get("status", data.get("state"))
        lines += ["", f"### {stage} · {data.get('title', stage)} — {status}", "", str(data.get("summary", "")), "", link(path.relative_to(root).as_posix(), "단계 원본 receipt")]
        for key, label in (("scope", "해석 범위"), ("verdict", "과학 판정"), ("rationale", "판정 근거")):
            if data.get(key):
                lines += ["", f"**{label}:** {data[key]}"]
        if data.get("metrics"):
            lines += ["", "| 측정 항목 | 값 | 단위/범위 | 원자료 |", "|---|---:|---|---|"]
            for m in data["metrics"]:
                src = m.get("source")
                if src:
                    source_path(root, src)
                lines.append(f"| {escaped(m['name'])} | {display(m.get('value'))} | {escaped(m.get('unit',''))} | {link(src) if src else '단계 receipt'} |")
        for table in data.get("tables", []):
            columns = table["columns"]
            for src in table.get("sources", []):
                source_path(root, src)
            lines += ["", f"**{table['title']}**", "", "| " + " | ".join(escaped(c.get("label", c["key"])) for c in columns) + " |", "| " + " | ".join("---" for c in columns) + " |"]
            for row in table["rows"]:
                lines.append("| " + " | ".join(table_cell(row.get(c["key"]), c.get("format")) for c in columns) + " |")
            if table.get("caption"):
                lines += ["", table["caption"]]
            if table.get("sources"):
                lines += ["", " · ".join(link(src) for src in table["sources"])]
        seen_ids = set()
        for spec in data.get("figures", []):
            if spec["id"] in seen_ids:
                raise ValueError(f"Duplicate figure id in {stage}: {spec['id']}")
            seen_ids.add(spec["id"])
            output = draw_figure(root, path, stage, spec)
            if output is None:
                lines += ["", f"**{spec['title']}:** 표시할 측정값 없음 (0으로 대체하지 않음)."]
            else:
                lines += ["", f"![{spec['title']}]({output}.svg)", "", spec.get("caption", ""), "", f"{link(output+'.png', 'PNG')} · {link(output+'.source.json', '정확한 그림 값·출처 SHA256')}"]
        if data.get("limitations"):
            lines += ["", "해석 제한:", "", *[f"- {s}" for s in data["limitations"]]]
        sources = list(dict.fromkeys([*data.get("sources", []), *data.get("artifacts", [])]))
        if sources:
            lines += ["", "원자료 및 산출물:", "", *[f"- {link(s)}" for s in sources]]
    destination = root / "reports" / PREFIX / "RUN_README_SECTION.md"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(lines).rstrip()+"\n", encoding="utf-8")
    return {"fragment": str(destination), "loaded_stages": [s for s,d,p in loaded if d is not None]}


def prepare_readiness_additions(root: Path):
    """Create a reviewable append-only payload; the stage owner merges it into G1."""
    root = root.resolve()
    summary_path = f"results/{PREFIX}/readiness_summary.json"
    summary = read_json(source_path(root, summary_path))
    audit_path = f"results/{PREFIX}/readiness_replay_audit.json"
    audit = read_json(source_path(root, audit_path))
    if summary.get("status") != "MEASURED_CONDITIONAL_READINESS_SUMMARY" or audit.get("status") != "PASS":
        raise ValueError("Readiness additions require completed diagnostic and passed raw replay")
    if audit.get("summary_sha256") != receipt(root, summary_path)["sha256"]:
        raise ValueError("Readiness replay refers to a different summary")
    for key, path in summary["source_paths"].items():
        if receipt(root, path)["sha256"] != summary["source_sha256"][key]:
            raise ValueError(f"Readiness source changed: {key}")
    rows = summary["rows"]
    if len(rows) != 16 or len({(r["model"], r["concept"], r["language"]) for r in rows}) != 16:
        raise ValueError("Readiness report requires all 16 unique model/concept/language cells")
    sources = [summary_path, audit_path, f"results/{PREFIX}/readiness_conditional_amendment.json", *[f"results/{PREFIX}/readiness_scores/{m}.json" for m in summary["models"]]]
    for src in sources:
        source_path(root, src)
    table_rows, figure_rows = [], []
    for row in rows:
        source_ci = row["source_cluster_bootstrap"]["ci95"]
        shared_ci = row["shared_reference_cluster_sensitivity"]["ci95"]
        table_rows.append({"model":row["model"], "concept":row["concept"], "language":row["language"], "accuracy":row["accuracy"], "n_variants":row["n_rows"], "n_sources":row["source_cluster_bootstrap"]["n_clusters"], "source_ci":source_ci, "n_shared":row["shared_reference_cluster_sensitivity"]["n_clusters"], "shared_ci":shared_ci, "conditional_flag":str(row["conditional_threshold_met"]), "shared_flag":str(row["shared_reference_threshold_met"])})
        figure_rows.append({"cell":f"{row['model']} / {row['concept']} / {row['language']}", "accuracy":row["accuracy"], "low":source_ci[0], "high":source_ci[1], "n_variants":row["n_rows"], "n_source_clusters":row["source_cluster_bootstrap"]["n_clusters"]})
    note = "고정 renderer·편의표집 source에 조건부인 진단이다. Source cluster 95% bootstrap CI는 독립 template 모집단 CI가 아니다. 같은 source의 변형을 함께 재표집하며, 공유 reference로 묶은 민감도 CI도 별도로 공개한다. 표의 조건부 기준(.75 정확도 및 CI 하한>.50)은 원래 strict renderer gate 또는 H1–H4의 적격성 통과를 뜻하지 않는다."
    columns = [{"key":k,"label":label,**({"format":style} if style else {})} for k,label,style in [("model","모델",None),("concept","개념",None),("language","언어",None),("accuracy","정확도","percent"),("n_variants","변형 수",None),("n_sources","source clusters",None),("source_ci","source 95% CI","percent_ci"),("n_shared","shared-reference clusters",None),("shared_ci","민감도 95% CI","percent_ci"),("conditional_flag","조건부 기준",None),("shared_flag","민감도 기준",None)]]
    payload = {"schema_version":1,"target_stage":"G1","merge_policy":"append figures/tables/sources/limitations; stage owner sets status and scientific interpretation", "sources":sources, "figures":[{"id":"readiness_conditional_accuracy","kind":"interval","title":"Conditional readiness accuracy — source-cluster bootstrap 95% CI","x":"cell","y":"accuracy","rows":figure_rows,"unit":"fraction","reference":.75,"xlim":[0,1],"ylabel":"Accuracy (conditional diagnostic)","sources":sources,"caption":"16 model/concept/language cells; dashed line: accuracy threshold .75 only. The separate lower-CI criterion is >.50. "+note}], "tables":[{"title":"조건부 readiness: 정확도·분모·cluster 민감도","columns":columns,"rows":table_rows,"sources":sources,"caption":note}], "limitations":[note]}
    destination = root / "results" / PREFIX / "report_inputs" / "G1_readiness_additions.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    return {"additions":str(destination),"cells":len(rows)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--max-stage", choices=STAGES, default="G6")
    parser.add_argument("--prepare-readiness", action="store_true", help="Write G1 additions from complete readiness sources, without rendering or mutating G1")
    args = parser.parse_args()
    print(json.dumps(prepare_readiness_additions(args.root) if args.prepare_readiness else render(args.root, args.max_stage), ensure_ascii=False))
