#!/usr/bin/env python3
"""Post-hoc BH/BY dependence sensitivity for the completed, fixed 110-test family.

CPU-only: reads p-values already measured by the primary protocol. Never loads
models, reruns tests, fits mappings, drops hypotheses, or edits primary results.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import scipy
from scipy.stats import false_discovery_control

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_FAMILY_SIZE = 110
ALPHA = .05
SCIPY_REFERENCE = "https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.false_discovery_control.html"


def adjust_with_missing(pvalues):
    """Preserve missing outputs while retaining their slots in both corrections.

    Missing p-values are supplied as 1 only to the full-family correction, not
    presented as observed measurements. Reject malformed/nonfinite inputs.
    """
    pvalues = list(pvalues)
    if not pvalues:
        raise ValueError("Cannot adjust an empty hypothesis family")
    for value in pvalues:
        if value is None:
            continue
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.integer, np.floating)):
            raise ValueError("p-values must be finite numbers in [0, 1] or None")
        if not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError("p-values must be finite numbers in [0, 1] or None")
    supplied = np.array([1. if value is None else value for value in pvalues], dtype=np.float64)
    bh = false_discovery_control(supplied, method="bh")
    by = false_discovery_control(supplied, method="by")
    return {"bh": [None if p is None else float(q) for p, q in zip(pvalues, bh)],
            "by": [None if p is None else float(q) for p, q in zip(pvalues, by)],
            "family_size": len(pvalues), "undefined_count": sum(p is None for p in pvalues),
            "harmonic_factor": float(sum(1. / i for i in range(1, len(pvalues) + 1)))}


def sensitivity(payload, source_sha256):
    """Verify archived BH independently, then add a separate BY sensitivity."""
    tests = payload.get("tests")
    if not isinstance(tests, dict) or len(tests) != EXPECTED_FAMILY_SIZE:
        raise ValueError("Completed original family must contain exactly 110 tests")
    names = sorted(tests)
    if payload.get("family_size") != EXPECTED_FAMILY_SIZE or payload.get("expected_family_size") != EXPECTED_FAMILY_SIZE:
        raise ValueError("Original family_size and expected_family_size must both be 110")
    if payload.get("family") != names:
        raise ValueError("Original family names/order do not match its complete test dictionary")
    if any("pvalue" not in tests[name] or "qvalue" not in tests[name] for name in names):
        raise ValueError("Every original hypothesis needs explicit pvalue and qvalue, including None")
    pvalues = [tests[name]["pvalue"] for name in names]
    adjusted = adjust_with_missing(pvalues)
    finite_count = EXPECTED_FAMILY_SIZE - adjusted["undefined_count"]
    if payload.get("finite_pvalue_count") != finite_count:
        raise ValueError("Original finite_pvalue_count disagrees with its p-values")
    rows, differences = {}, []
    for name, p, q_bh, q_by in zip(names, pvalues, adjusted["bh"], adjusted["by"]):
        original_q = tests[name]["qvalue"]
        if p is None:
            if original_q is not None:
                raise ValueError(f"Undefined p-value must retain undefined original q-value: {name}")
        else:
            if isinstance(original_q, bool) or not isinstance(original_q, (int, float)) or not math.isfinite(original_q):
                raise ValueError(f"Invalid original BH q-value: {name}")
            difference = abs(original_q - q_bh)
            differences.append(difference)
            if not math.isclose(original_q, q_bh, rel_tol=1e-12, abs_tol=1e-12):
                raise ValueError(f"Original BH differs from independent SciPy replay: {name}")
            if q_by + 1e-12 < q_bh:
                raise AssertionError("BY unexpectedly less conservative than BH")
        rows[name] = {"pvalue": p, "q_bh_primary": original_q, "q_bh_scipy": q_bh, "q_by_scipy": q_by,
                      "undefined_slot_retained": p is None,
                      "bh_reject": None if p is None else bool(q_bh < ALPHA),
                      "by_reject": None if p is None else bool(q_by < ALPHA)}
    bh_names = [name for name in names if rows[name]["bh_reject"] is True]
    by_names = [name for name in names if rows[name]["by_reject"] is True]
    return {"analysis": "posthoc_dependence_sensitivity", "preregistered_primary": False,
            "primary_results_changed": False, "additional_hypotheses": 0,
            "refits_or_new_model_calls": False, "new_pvalues_computed": False,
            "source": "results/followup-v2/statistics/global_tests.json", "source_sha256": source_sha256,
            "family_size": EXPECTED_FAMILY_SIZE, "finite_pvalue_count": finite_count,
            "undefined_pvalue_count": adjusted["undefined_count"], "family": names,
            "multiplicity_policy": "Exact original 110 slots; None supplied as 1 only for adjustment; reported p and adjusted q remain None",
            "alpha": ALPHA, "rejection_rule": "adjusted q strictly below 0.05",
            "methods": {"bh": "Benjamini-Hochberg", "by": "Benjamini-Yekutieli"},
            "by_harmonic_factor": adjusted["harmonic_factor"],
            "independent_bh_verification": {"passed": True, "library": "scipy.stats.false_discovery_control",
                                             "scipy_version": scipy.__version__,
                                             "maximum_absolute_difference": max(differences, default=0.0),
                                             "absolute_tolerance": 1e-12, "relative_tolerance": 1e-12},
            "rejections": {"bh": {"count": len(bh_names), "names": bh_names},
                           "by": {"count": len(by_names), "names": by_names},
                           "bh_only": {"count": len(set(bh_names) - set(by_names)),
                                       "names": sorted(set(bh_names) - set(by_names))}},
            "tests": rows, "reference": SCIPY_REFERENCE,
            "limitations": [
                "Post-hoc sensitivity, not a replacement for the preregistered primary BH family.",
                "BH requires independence or suitable positive dependence; BY accommodates arbitrary dependence among valid p-values.",
                "Validity of each original p-value and exchangeability/symmetry assumptions of wrapper sign flips remain necessary.",
                "BY does not repair invalid p-values, pseudoreplication, finite-model generalization, low competence, construct validity, or outcome-driven analysis.",
                "Shared models and outcomes remain shared; the number of independent trained models does not increase."]}


def render_report(result):
    rejected = result["rejections"]
    lines = ["# followup-v2: 의존성에 대한 다중검정 민감도 분석", "",
             "이 분석은 **사후 보충 민감도 분석**이다. 사전 정의된 110개 가설·원래 p-value·주 분석 BH 결과를 변경하지 않았다. 모델 실행, 정렬 재학습, 추가 가설 검정은 하지 않았다.", "",
             f"원래 110개 가설 중 유효한 p-value는 {result['finite_pvalue_count']}개, 정의되지 않은 p-value는 {result['undefined_pvalue_count']}개다. 정의되지 않은 항목은 다중검정 계산 안에서만 p=1 자리로 유지하고 공개 p/q는 `null`로 남겼다.", "",
             "| 보정 | q < 0.05 기각 수 | 역할 |", "|---|---:|---|",
             f"| BH | {rejected['bh']['count']} | 기존 주 분석의 독립 재계산 |",
             f"| BY | {rejected['by']['count']} | 임의 의존성에 대한 사후 민감도 |", "",
             f"SciPy로 재계산한 BH는 원래 값과 일치했다(최대 절대 차이 {result['independent_bh_verification']['maximum_absolute_difference']:.3g}). BY는 같은 110개 p-value에 조화합 계수 {result['by_harmonic_factor']:.8f}를 적용한다.", "",
             "## 기각된 가설 ID", "",
             "### BH와 BY 모두에서 기각", ""]
    lines.extend([f"- `{name}`" for name in rejected["by"]["names"]] or ["없음."])
    lines.extend(["", "### BH에서만 기각", ""])
    lines.extend([f"- `{name}`" for name in rejected["bh_only"]["names"]] or ["없음."])
    lines.extend(["", "## 해석의 제한", "",
                  "공유 모델과 출력 때문에 검정들이 서로 의존한다. BH는 독립성 또는 적절한 양의 의존성이 필요하며, BY는 유효한 p-value 사이의 임의 의존성을 허용하는 더 보수적인 보정이다. [SciPy 공식 문서](" + SCIPY_REFERENCE + ")", "",
                  "그러나 개별 p-value의 타당성과 wrapper sign-flip의 교환가능성·대칭성 가정은 여전히 필요하다. BY는 잘못된 p-value, 유사 반복의 독립 표본 처리, 적은 학습 seed 수, 낮은 과제 능력, 측정 개념의 부적절성이나 결과를 본 뒤의 설계 변경을 고치지 않는다. 두 보정에서 기각되더라도 인과적·의미적 보존의 모든 전제 조건이 충족된다는 뜻은 아니다.", "",
                  "## 추적 정보", "",
                  "- [원래 110개 검정](../../results/followup-v2/statistics/global_tests.json)",
                  "- [전체 BH/BY 값과 가설 ID](../../results/followup-v2/statistics/dependence_sensitivity.json)",
                  f"- 원본 SHA256: `{result['source_sha256']}`",
                  f"- SciPy 버전: `{result['independent_bh_verification']['scipy_version']}`", ""])
    return "\n".join(lines)


def run(source, output, report):
    source, output, report = Path(source), Path(output), Path(report)
    # Reading happens before directory creation, so missing primary evidence
    # cannot create a misleading placeholder result or a report of fake values.
    payload_bytes = source.read_bytes()
    digest = hashlib.sha256(payload_bytes).hexdigest()
    result = sensitivity(json.loads(payload_bytes), digest)
    json_text = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    report_text = render_report(result)
    if source.read_bytes() != payload_bytes:
        raise RuntimeError("Primary source changed during sensitivity calculation")
    for path, text in ((output, json_text), (report, report_text)):
        if path.resolve() == source.resolve():
            raise ValueError("Refusing to write over the primary source")
        if path.exists() and path.read_text() != text:
            raise ValueError(f"Refusing to overwrite changed sensitivity evidence: {path}")
    for path, text in ((output, json_text), (report, report_text)):
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            with path.open("x", encoding="utf-8") as stream:
                stream.write(text)
    print(json.dumps({"family_size": result["family_size"], "bh_rejected": result["rejections"]["bh"]["count"],
                      "by_rejected": result["rejections"]["by"]["count"], "source_sha256": digest}))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "results/followup-v2/statistics/global_tests.json")
    parser.add_argument("--output", type=Path, default=ROOT / "results/followup-v2/statistics/dependence_sensitivity.json")
    parser.add_argument("--report", type=Path, default=ROOT / "reports/followup-v2/DEPENDENCE_SENSITIVITY.md")
    args = parser.parse_args(argv)
    run(args.source, args.output, args.report)


if __name__ == "__main__":
    main()
