import copy
import unittest

import numpy as np

from src.data import CONCEPTS, SPLITS, _balanced, generate_dataset, validate_dataset
from src.statistics import cluster_bootstrap, fdr_bh, paired_randomization_test, safe_correlation


class DatasetTests(unittest.TestCase):
    def setUp(self):
        self.dataset = generate_dataset(seed=7, per_concept=24)

    def test_reproducible_balanced_and_disjoint(self):
        self.assertEqual(self.dataset, generate_dataset(seed=7, per_concept=24))
        self.assertNotEqual(self.dataset, generate_dataset(seed=8, per_concept=24))
        result = validate_dataset(self.dataset)
        self.assertFalse(result["cross_split_leakage"])
        self.assertEqual([result["splits"][s]["n"] for s in SPLITS], [96]*5)
        self.assertEqual(len({result["splits"][s]["sha256"] for s in SPLITS}), 5)
        self.assertEqual([result["splits"][s]["clusters"] for s in SPLITS], [6]*5)

    def test_shared_wrappers_are_resampled_jointly(self):
        for rows in self.dataset.values():
            for wrapper in {r["template"] for r in rows}:
                same_wrapper = [r for r in rows if r["template"] == wrapper]
                self.assertEqual(len({r["group_id"] for r in same_wrapper}), 1)
                self.assertEqual({r["concept"] for r in same_wrapper}, set(CONCEPTS))
        altered = copy.deepcopy(self.dataset)
        altered["D1"][0]["group_id"] = "spurious-independent-cluster"
        with self.assertRaisesRegex(ValueError, "Shared wrapper"):
            validate_dataset(altered)

    def test_truth_labels_are_correct(self):
        for rows in self.dataset.values():
            for r in rows:
                if r["concept"] == "arithmetic":
                    statement = r["prompt"][slice(*r["span"])]
                    a, _, b, _, result = statement.rstrip(".").split()
                    self.assertEqual(int(a)+int(b) == int(result), bool(r["label"]))
                elif r["concept"] == "comparison":
                    a, b = r["numeric_tuple"]
                    self.assertEqual((a>b) if "greater than" in r["prompt"] else (a<b), bool(r["label"]))
                elif r["concept"] == "syntax":
                    brackets = r["prompt"].split("The brackets ")[1].split(" are balanced.")[0]
                    self.assertEqual(_balanced(brackets), bool(r["label"]))
                else:
                    statement = r["prompt"][slice(*r["span"])]
                    property_fact = statement.split("one property, ")[1].split(".")[0]
                    property_query = statement.split(" has ")[-1].rstrip(".")
                    self.assertEqual(property_fact != property_query, bool(r["label"]))

    def test_injected_leak_is_rejected(self):
        altered = copy.deepcopy(self.dataset)
        altered["D4"][0]["prompt"] = altered["D3"][0]["prompt"]
        altered["D4"][0]["span"] = [0, 1]
        with self.assertRaisesRegex(ValueError, "leakage"):
            validate_dataset(altered)

    def test_unequal_training_size(self):
        ds = generate_dataset(per_concept={s: 128 if s == "train" else 12 for s in SPLITS})
        self.assertEqual(len(ds["train"]), 512)
        self.assertEqual(len(ds["D4"]), 48)

    def test_matched_controls_preserve_task_and_wrapper(self):
        for rows in self.dataset.values():
            pairs = {}
            for row in rows:
                pairs.setdefault(row["pair_id"], []).append(row)
            for pair in pairs.values():
                a, b = pair
                self.assertEqual(a["concept"], b["concept"])
                self.assertEqual(a["template"], b["template"])
                self.assertEqual(a["content_key"], b["content_key"])
                self.assertEqual(a["correct"], b["foil"])
                self.assertNotEqual(a["prompt"], b["prompt"])

    def test_known_syntax_shortcut_is_measured_not_hidden(self):
        # This diagnoses a limitation; it does not strengthen the benchmark claim.
        for rows in self.dataset.values():
            for row in rows:
                if row["concept"] == "syntax":
                    text = row["prompt"].split("The brackets ")[1].split(" are balanced.")[0]
                    count_only = sum(c in "([{" for c in text) == sum(c in ")]}" for c in text)
                    self.assertEqual(count_only, bool(row["label"]))


class StatisticsTests(unittest.TestCase):
    def test_cluster_estimand_does_not_weight_prompt_count(self):
        result = cluster_bootstrap([0]*100 + [10], ["a"]*100+["b"], n_boot=200, seed=3)
        self.assertEqual(result["mean"], 5)
        self.assertEqual(result["n_clusters"], 2)
        self.assertEqual(result["ci"], [0, 10])

    def test_exact_sign_flip_and_zero_effect(self):
        groups = [str(i) for i in range(8)]
        result = paired_randomization_test([1]*8, [0]*8, groups)
        self.assertEqual(result["pvalue"], 2/256)
        self.assertEqual(paired_randomization_test([1]*8, [1]*8, groups)["pvalue"], 1)

    def test_missing_clusters_and_nonfinite(self):
        self.assertIsNone(cluster_bootstrap([1, 2], ["x", "x"])["ci"])
        with self.assertRaises(ValueError):
            cluster_bootstrap([np.nan], ["x"])

    def test_bh_preserves_original_order(self):
        np.testing.assert_allclose(fdr_bh([.04, .001, .03, .8]), [.0533333333, .004, .0533333333, .8])

    def test_constant_and_tied_correlations(self):
        self.assertIsNone(safe_correlation([1, 1, 1], [1, 2, 3]))
        self.assertAlmostEqual(safe_correlation([1, 1, 3, 4], [4, 4, 2, 1], "spearman"), -1)
        self.assertAlmostEqual(safe_correlation([1, 2, 3], [2, 4, 6]), 1)


if __name__ == "__main__":
    unittest.main()
