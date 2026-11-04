from copy import deepcopy
import hashlib
import json

import numpy as np
import pytest
from scipy.stats import false_discovery_control

from scripts.followup_dependence_sensitivity import adjust_with_missing, sensitivity, run


def family_with_missing():
    values = [.001, .02] + [None] * 108
    bh = false_discovery_control(np.array([1 if p is None else p for p in values]), method="bh")
    tests = {f"H{i:03d}": {"pvalue": p, "qvalue": None if p is None else float(q)}
             for i, (p, q) in enumerate(zip(values, bh))}
    return {"family": sorted(tests), "family_size": 110, "expected_family_size": 110,
            "finite_pvalue_count": 2, "tests": tests}


def test_known_unsorted_bh_and_by_against_scipy():
    p = [.5, .6, .1, .001]
    adjusted = adjust_with_missing(p)
    assert np.allclose(adjusted["bh"], [.6, .6, .2, .004])
    assert np.allclose(adjusted["by"], false_discovery_control(p, method="by"))
    assert np.allclose(adjusted["by"], [1, 1, 5 / 12, 1 / 120])


def test_missing_slots_preserve_full_110_family_and_undefined_outputs():
    original = family_with_missing()
    before = deepcopy(original)
    result = sensitivity(original, "source-hash")
    assert original == before
    assert result["family_size"] == 110 and result["undefined_pvalue_count"] == 108
    assert result["tests"]["H000"]["q_bh_scipy"] == pytest.approx(.11)
    assert result["tests"]["H000"]["q_by_scipy"] == pytest.approx(.11 * sum(1 / i for i in range(1, 111)))
    for name in result["family"][2:]:
        assert result["tests"][name]["pvalue"] is None
        assert result["tests"][name]["q_bh_scipy"] is None
        assert result["tests"][name]["q_by_scipy"] is None
    # Dropping missing tests would produce .002; preserving all110 gives .11.
    assert result["rejections"]["bh"]["count"] == 0


def test_rejects_incomplete_family_and_wrong_archived_bh():
    payload = family_with_missing()
    incomplete = deepcopy(payload)
    incomplete["tests"].pop("H109")
    with pytest.raises(ValueError, match="exactly 110"):
        sensitivity(incomplete, "hash")
    payload["tests"]["H000"]["qvalue"] = .002
    with pytest.raises(ValueError, match="independent SciPy"):
        sensitivity(payload, "hash")


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -.1, 1.1, True, "0.2"])
def test_rejects_invalid_pvalues_instead_of_treating_as_missing(bad):
    with pytest.raises(ValueError, match="finite numbers"):
        adjust_with_missing([.2, bad, None])


def test_missing_source_creates_no_fake_result(tmp_path):
    output = tmp_path / "statistics" / "dependence_sensitivity.json"
    report = tmp_path / "reports" / "DEPENDENCE_SENSITIVITY.md"
    with pytest.raises(FileNotFoundError):
        run(tmp_path / "global_tests.json", output, report)
    assert not output.exists() and not report.exists()
    assert not output.parent.exists() and not report.parent.exists()


def test_source_unchanged_and_source_hash_replayed(tmp_path):
    source = tmp_path / "global_tests.json"
    payload = family_with_missing()
    source.write_text(json.dumps(payload))
    before = source.read_bytes()
    output, report = tmp_path / "sensitivity.json", tmp_path / "report.md"
    result = run(source, output, report)
    assert source.read_bytes() == before
    assert result["source_sha256"] == hashlib.sha256(before).hexdigest()
    assert run(source, output, report) == result
    assert "사후" in report.read_text()
