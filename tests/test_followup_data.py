import copy
import json
import re
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from src.followup_data import (CONCEPTS, SPLITS, WRAPPERS, generate_dataset,
                               validate_dataset, freeze_dataset, load_dataset, oracle)


def independent_logic(text, assignment):
    tokens=re.findall(r'NOT|AND|OR|XOR|[PQRSTUVWX]|[()]',text)
    cursor=0
    def parse():
        nonlocal cursor
        token=tokens[cursor];cursor+=1
        if token=='NOT': return not parse()
        if token!='(': return assignment[token]
        left=parse();op=tokens[cursor];cursor+=1;right=parse()
        assert tokens[cursor]==')';cursor+=1
        return (left and right) if op=='AND' else (left or right) if op=='OR' else (left != right)
    result=parse()
    assert cursor==len(tokens)
    return result


class FollowupDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.small=generate_dataset(train_size=192,eval_size=192)
        cls.full=generate_dataset()

    def test_default_counts_groups_and_seeds(self):
        manifest=validate_dataset(self.full)
        self.assertEqual(manifest['splits']['train']['n'],16384)
        for split in SPLITS:
            rows=self.full[split]
            self.assertEqual(len({r['group_id'] for r in rows}),24)
            self.assertEqual(len({r['generation_seed'] for r in rows}),3)
            self.assertLess(max(len(r['prompt'].encode()) for r in rows),180)
            if split!='train':
                self.assertEqual(len(rows),768)
                self.assertEqual(set(Counter((r['concept'],r['group_id'],r['label']) for r in rows).values()),{4})
                for concept in CONCEPTS:
                    for group in {r['group_id'] for r in rows}:
                        self.assertEqual(len({r['generation_seed'] for r in rows if r['concept']==concept and r['group_id']==group}),3)

    def test_semantic_truth_from_text_independent_oracles(self):
        for rows in self.full.values():
            for r in rows:
                text=r['statement'];concept=r['concept']
                if concept=='arithmetic':
                    a,b,c=map(int,re.fullmatch(r'(\d+) plus (\d+) equals (\d+)\.',text).groups())
                    truth=(a+b==c)
                elif concept=='comparison':
                    a,op,b=re.fullmatch(r'(\d+) is (greater|less) than (\d+)\.',text).groups()
                    truth=int(a)>int(b) if op=='greater' else int(a)<int(b)
                elif concept=='negation':
                    assignment_text,query=text.split('. Claim: ')
                    assignment={v:(value=='T') for v,value in re.findall(r'([PQRSTUVWX])=([TF])',assignment_text)}
                    truth=independent_logic(query.removesuffix(' evaluates to T.'),assignment)
                else:
                    brackets=text.removeprefix('The bracket sequence ').removesuffix(' is well-formed.')
                    old=None
                    while old!=brackets:
                        old=brackets
                        for pair in ('()','[]','{}'): brackets=brackets.replace(pair,'')
                    truth=(brackets=='')
                self.assertEqual(truth,bool(r['label']))
                self.assertEqual(truth,oracle(r))

    def test_pairwise_shortcut_balance(self):
        for rows in self.full.values():
            pairs={}
            for r in rows: pairs.setdefault(r['pair_id'],[]).append(r)
            for pair in pairs.values():
                a,b=pair
                self.assertEqual(a['label']+b['label'],1)
                self.assertEqual(a['correct'],b['foil'])
                if a['concept']=='syntax':
                    x,y=a['semantic']['brackets'],b['semantic']['brackets']
                    self.assertEqual(Counter(x),Counter(y))
                    self.assertEqual([c in '([{' for c in x],[c in '([{' for c in y])
                elif a['concept']=='arithmetic':
                    x,y=a['semantic']['claimed_sum'],b['semantic']['claimed_sum']
                    self.assertEqual(x%2,y%2);self.assertEqual(len(str(x)),len(str(y)))
                elif a['concept']=='negation':
                    self.assertEqual(sum(a['semantic']['assignment'].values()),sum(b['semantic']['assignment'].values()))

    def test_all_wrappers_are_full_distinct_instructions(self):
        wrappers=[w for values in WRAPPERS.values() for w in values]
        self.assertEqual(len(wrappers),144);self.assertEqual(len(set(wrappers)),144)
        self.assertTrue(all(w.count('{s}')==1 for w in wrappers))

    def test_deterministic_and_new_seed(self):
        self.assertEqual(self.small,generate_dataset(train_size=192,eval_size=192))
        other=generate_dataset(seeds=(10,20,30),train_size=192,eval_size=192)
        self.assertNotEqual(self.small['D3'],other['D3'])

    def test_immutable_freeze_and_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            freeze_dataset(self.small,tmp)
            freeze_dataset(self.small,tmp)
            self.assertEqual(load_dataset(tmp),self.small)
            changed=generate_dataset(seeds=(10,20,30),train_size=192,eval_size=192)
            with self.assertRaises(FileExistsError): freeze_dataset(changed,tmp)
            path=Path(tmp)/'D3.jsonl';path.write_text(path.read_text()+'\n')
            with self.assertRaisesRegex(ValueError,'hash mismatch'): load_dataset(tmp)

    def test_corrupt_label_or_prompt_is_rejected(self):
        broken=copy.deepcopy(self.small);broken['D3'][0]['label']=1-broken['D3'][0]['label']
        with self.assertRaisesRegex(ValueError,'oracle'): validate_dataset(broken)
        broken=copy.deepcopy(self.small);broken['D4'][0]['prompt']='changed prompt'
        with self.assertRaises(ValueError): validate_dataset(broken)

    def test_cross_split_numeric_tuples_are_disjoint_across_tasks(self):
        seen={}
        for split,rows in self.full.items():
            for r in rows:
                if r['numeric_tuple'] is not None:
                    key=tuple(r['numeric_tuple'])
                    self.assertIn(seen.setdefault(key,split),(split,))


if __name__=='__main__': unittest.main()
