"""Deterministic, split-disjoint controlled tasks. Labels mean statement truth.

These are synthetic task probes, not a representative natural-language corpus.
The semantic concept label is distinct from the positive/negative truth label.
"""
from __future__ import annotations

import hashlib
import json
import random
from collections import Counter
from pathlib import Path

SPLITS = ("train", "D1", "D2", "D3", "D4")
CONCEPTS = ("arithmetic", "comparison", "negation", "syntax")
VERSION = "controlled-truth-v1"

# Entire templates, not only their identifiers, are held out by split.
WRAPPERS = {
    "train": ("{statement} Is this true? Answer:", "Check the claim: {statement} Correct?", "Decide yes or no: {statement} Response:", "Determine whether this is true: {statement} Answer:", "Is this statement correct? {statement} Answer:", "Read the statement. {statement} Is it true?"),
    "D1": ("Claim: {statement} Is the claim correct?", "Consider: {statement} True?", "Assess this statement: {statement} Valid?", "Judge the following: {statement} Is it correct?", "Please check: {statement} Is this accurate?", "Fact check: {statement} Confirmed?"),
    "D2": ("Evaluate the assertion '{statement}' Answer yes or no:", "Does this hold: {statement} Answer:", "Is the following accurate? {statement} Reply:", "Given the assertion {statement} Is it true?", "Check if this is right: {statement} Reply:", "Can we accept the statement {statement} Answer:"),
    "D3": ("A student writes: {statement} Should we accept it?", "Verify this assertion: {statement} Is it right?", "Would you mark this correct: {statement} Answer:", "An examiner presents: {statement} Is this correct?", "We need a truth judgment. {statement} Is it true?", "Assess this proposed answer: {statement} Correct?"),
    "D4": ("Your task is to judge: {statement} Is that so?", "Someone proposes: {statement} Can you confirm?", "Review this proposed fact: {statement} Is it valid?", "A colleague says: {statement} Is the claim accurate?", "Examine this assertion carefully: {statement} Does it hold?", "Please give a verdict: {statement} Is that correct?"),
}


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def _balanced(s):
    stack = []
    closing = {")": "(", "]": "[", "}": "{"}
    for ch in s:
        if ch in "([{":
            stack.append(ch)
        elif not stack or stack.pop() != closing[ch]:
            return False
    return not stack


def _syntax_pool(n, rng):
    output, seen = [], set()
    while len(output) < n:
        stack, chars = [], []
        for _ in range(7):
            left, right = rng.choice((("(", ")"), ("[", "]"), ("{", "}")))
            chars.append(left)
            stack.append(right)
            while stack and rng.random() < 0.55:
                chars.append(stack.pop())
        chars.extend(reversed(stack))
        valid = "".join(chars)
        if valid in seen:
            continue
        # Replace one closing symbol with an opening symbol, preserving length.
        pos = next(i for i, c in enumerate(valid) if c in ")]}")
        invalid = valid[:pos] + "(" + valid[pos + 1:]
        seen.add(valid)
        output.append((valid, invalid))
    return output


def generate_dataset(seed=1729, per_concept=64):
    """Return balanced matched pairs in each split; `per_concept` includes both labels.

    For larger training sets pass a mapping, e.g. {'train': 512, 'D1': 64, ...}.
    All operand pairs are sampled from the same 0..63 domain without replacement.
    """
    counts = {s: per_concept[s] if isinstance(per_concept, dict) else per_concept for s in SPLITS}
    if any(not isinstance(n, int) or n < 6 or n % 2 for n in counts.values()):
        raise ValueError("Each split requires an even per_concept count >= 6")
    total_pairs = sum(counts.values()) // 2
    if total_pairs > 2016:
        raise ValueError("Requested size exceeds unique unordered numeric-pair pool (2016)")
    rng = random.Random(seed)
    numeric = [(a, b) for a in range(64) for b in range(a + 1, 64)]
    rng.shuffle(numeric)
    # Reverse half the pairs independently of split so comparisons are not one-sided.
    numeric = [(b, a) if rng.random() < .5 else (a, b) for a, b in numeric]
    entities = [(f"object_{a}", f"property_{b}") for a in range(64) for b in range(64)]
    rng.shuffle(entities)
    syntax = _syntax_pool(total_pairs, rng)
    dataset, offset = {}, 0
    for split in SPLITS:
        records = []
        for j in range(counts[split] // 2):
            a, b = numeric[offset + j]
            entity, prop = entities[offset + j]
            valid, invalid = syntax[offset + j]
            for concept in CONCEPTS:
                template_index = j % len(WRAPPERS[split])
                template = WRAPPERS[split][template_index]
                pair_id = f"{split}:{concept}:{j:05d}"
                for label in (0, 1):
                    if concept == "arithmetic":
                        statement = f"{a} plus {b} equals {a + b if label else a + b + (1 if j % 2 else -1)}."
                    elif concept == "comparison":
                        relation = "greater" if bool(a > b) == bool(label) else "less"
                        statement = f"{a} is {relation} than {b}."
                    elif concept == "negation":
                        query_prop = f"property_{(int(prop.split('_')[1]) + 1) % 64}" if label else prop
                        statement = f"{entity} has exactly one property, {prop}. It is false that {entity} has {query_prop}."
                    else:
                        statement = f"The brackets {valid if label else invalid} are balanced."
                    prompt = template.format(statement=statement)
                    start = prompt.index(statement)
                    records.append({"id": f"{pair_id}:{label}", "split": split, "concept": concept,
                        "prompt": prompt, "correct": " yes" if label else " no",
                        "foil": " no" if label else " yes", "label": label,
                        "template_id": f"{split}:{concept}:t{template_index}",
                        # The same wrapper appears in all concepts: resample it jointly.
                        "group_id": f"{split}:wrapper:t{template_index}",
                        "template": template, "pair_id": pair_id,
                        "numeric_tuple": [a, b] if concept in ("arithmetic", "comparison") else None,
                        "content_key": [entity, prop] if concept == "negation" else valid if concept == "syntax" else [a, b],
                        "span": [start, start + len(statement)], "source": VERSION})
        rng.shuffle(records)
        dataset[split] = records
        offset += counts[split] // 2
    validate_dataset(dataset)
    return dataset


def validate_dataset(dataset):
    if set(dataset) != set(SPLITS):
        raise ValueError("Expected train, D1, D2, D3, D4 splits")
    owners = {key: {} for key in ("prompt", "template", "numeric_tuple", "content_key")}
    summaries, ids = {}, set()
    for split, rows in dataset.items():
        labels, pairs, groups, wrapper_groups = Counter(), {}, set(), {}
        for row in rows:
            if row["split"] != split or row["id"] in ids:
                raise ValueError("Wrong split field or duplicate record ID")
            ids.add(row["id"])
            if row["label"] not in (0, 1) or row["correct"] != (" yes" if row["label"] else " no"):
                raise ValueError("Invalid truth label or continuation")
            if row["correct"] == row["foil"]:
                raise ValueError("Identical answer candidates")
            start, end = row["span"]
            if not (0 <= start < end <= len(row["prompt"])):
                raise ValueError("Invalid character span")
            labels[(row["concept"], row["label"])] += 1
            pairs.setdefault(row["pair_id"], []).append(row["label"])
            groups.add(row["group_id"])
            previous_group = wrapper_groups.setdefault(row["template"], row["group_id"])
            if previous_group != row["group_id"]:
                raise ValueError("Shared wrapper must stay in one statistical cluster across concepts")
            for key in owners:
                value = row[key]
                if value is None:
                    continue
                # Treat reversed numeric operands as the same combination.
                if key == "numeric_tuple":
                    value = sorted(value)
                token = _hash(value)
                prior = owners[key].get(token)
                if prior is not None and prior != split:
                    raise ValueError(f"Cross-split {key} leakage between {prior} and {split}")
                owners[key][token] = split
        if any(sorted(labels_) != [0, 1] for labels_ in pairs.values()):
            raise ValueError("Every matched pair must contain one true and one false record")
        if any(labels[c, 0] != labels[c, 1] or labels[c, 0] == 0 for c in CONCEPTS):
            raise ValueError("Missing concept or unbalanced truth labels")
        if len({r["prompt"] for r in rows}) != len(rows):
            raise ValueError("Duplicate prompt inside split")
        summaries[split] = {"n": len(rows), "sha256": _hash(rows), "clusters": len(groups),
                            "counts": {c: {str(y): labels[c, y] for y in (0, 1)} for c in CONCEPTS}}
    return {"version": VERSION, "splits": summaries, "cross_split_leakage": False,
            "template_disjoint": True, "unordered_operand_tuple_disjoint": True,
            "grouping_scheme": "shared-wrapper-across-concepts-v2",
            "limitations": ["Synthetic task probes; natural-language atlas requires a separate corpus.",
                "Six shared wrapper clusters per split, not 24 independent concept-wrapper clusters; intervals are exploratory.",
                "Truth contrast is not evidence of a uniquely monosemantic neuron.",
                "Negation assumes the stated property fact and uses synthetic entity/property names.",
                "Negation can be solved by property-token equality; adjacent numeric property names provide a shortcut.",
                "Invalid syntax examples have unequal opening/closing counts; bracket counting is a shortcut.",
                "Held-out wrapper wording changes but underlying semantic task grammar is shared."]}


def save_dataset(dataset, directory):
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True)
    manifest = validate_dataset(dataset)
    for split, rows in dataset.items():
        (path / f"{split}.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    (path / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    return manifest
