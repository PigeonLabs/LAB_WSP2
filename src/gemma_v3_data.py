"""Closed-test v3 engineering data; no model calls and no v2 data reuse.

Engineering has 32 scenarios but ONLY FOUR shared template lineages. It cannot
support independent-template inference. Readiness needs a genuinely new source
catalog and an engineering prompt freeze receipt; this module never invents
independence by renaming templates. Test/OOD generation is deliberately absent.
"""
from __future__ import annotations
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import random
import re

VERSION = 'gemma-v3-engineering-v1'
SEED = 20261104
CONCEPTS = ('negation', 'ownership_coreference', 'temporal_order', 'numeric_comparison')
LANGUAGES = ('en', 'ko')
ROOT = Path(__file__).resolve().parents[1]
NAMES_EN = ('Mina', 'Yuna', 'Sua', 'Jiu', 'Haru', 'Nari', 'Sena', 'Ara')
NAMES_KO = ('민아', '유나', '수아', '지우', '하루', '나리', '세나', '아라')
OTHER_EN = ('Junho', 'Minho', 'Jiho', 'Taeo', 'Siu', 'Jaeho', 'Seho', 'Yuno')
OTHER_KO = ('준호', '민호', '지호', '태오', '시우', '재호', '세호', '윤오')
THIRD_EN = ('Sora', 'Bora', 'Dara', 'Mira', 'Rina', 'Jina', 'Hana', 'Yuri')
THIRD_KO = ('소라', '보라', '다라', '미라', '리나', '지나', '하나', '유리')
OBJECTS_EN = ('umbrella', 'pencil', 'bag', 'wallet', 'notebook', 'towel', 'glove', 'balloon')
OBJECTS_KO = ('우산', '연필', '가방', '지갑', '공책', '수건', '장갑', '풍선')


def digest(value):
    raw = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(raw).hexdigest()


def _render(concept, names, obj, values, state, lexical, language):
    a, b, c = names
    if concept == 'negation':
        yes, no = (a, b) if state else (b, a)
        if language == 'en':
            context = (f'{yes} carries the {obj}. {no} does not carry the {obj}.' if not lexical else
                       f'The {obj} is carried by {yes}. The {obj} is not carried by {no}.')
            claim = f'{a} carries the {obj}.'
        else:
            context = (f'{yes}는 {obj}을 들고 있다. {no}는 {obj}을 들고 있지 않다.' if not lexical else
                       f'{obj}을 들고 있는 사람은 {yes}다. {no}는 {obj}을 들고 있지 않다.')
            claim = f'{a}는 {obj}을 들고 있다.'
    elif concept == 'ownership_coreference':
        first, last = (a, c) if state else (c, a)
        if language == 'en':
            context = (f'{first} gave the {obj} to {b}. Then {b} gave it to {last}.' if not lexical else
                       f'The {obj} passed from {first} to {b}. Afterward, {b} handed it to {last}.')
            claim = f'{c} owns the {obj} now.'
        else:
            context = (f'{first}는 {obj}을 {b}에게 주었다. 그다음 {b}는 그것을 {last}에게 주었다.' if not lexical else
                       f'{obj}은 {first}에게서 {b}에게 넘어갔다. 이후 {b}는 그것을 {last}에게 넘겼다.')
            claim = f'현재 {obj}의 주인은 {c}다.'
    elif concept == 'temporal_order':
        first, last = (a, c) if state else (c, a)
        if language == 'en':
            context = (f'{first} arrived before {b}. {b} arrived before {last}.' if not lexical else
                       f'{b} arrived after {first}. {last} arrived after {b}.')
            claim = f'{a} arrived before {c}.'
        else:
            context = (f'{first}는 {b}보다 먼저 도착했다. {b}는 {last}보다 먼저 도착했다.' if not lexical else
                       f'{b}는 {first}보다 나중에 도착했다. {last}는 {b}보다 나중에 도착했다.')
            claim = f'{a}는 {c}보다 먼저 도착했다.'
    elif concept == 'numeric_comparison':
        lo, hi = sorted(values)
        x, y = (hi, lo) if state else (lo, hi)
        if language == 'en':
            context = (f'{a} has {x} tokens. {b} has {y} tokens.' if not lexical else
                       f'Token counts: {a}={x}, {b}={y}.')
            claim = f'{a} has more tokens than {b}.'
        else:
            context = (f'{a}의 토큰 수는 {x}개이다. {b}의 토큰 수는 {y}개이다.' if not lexical else
                       f'토큰 기록: {a}={x}개, {b}={y}개.')
            claim = f'{a}의 토큰 수는 {b}보다 많다.'
    else:
        raise ValueError('Unknown concept')
    return context, claim


def _fullmatch(pattern, text):
    match = re.fullmatch(pattern, text)
    if match is None:
        raise ValueError('Unrecognized or corrupted controlled-language sentence')
    return match.groups()


def oracle(context, claim, concept, language, lexical):
    """Parse displayed facts and query; never consult stored semantic_state."""
    n = r'([^ .,:=]+)'
    if concept == 'negation':
        if language == 'en':
            q, obj = _fullmatch(n + r' carries the ' + n + r'\.', claim)
            if not lexical:
                yes, o1, no, o2 = _fullmatch(n+r' carries the '+n+r'\. '+n+r' does not carry the '+n+r'\.', context)
            else:
                o1, yes, o2, no = _fullmatch(r'The '+n+r' is carried by '+n+r'\. The '+n+r' is not carried by '+n+r'\.', context)
        else:
            q, obj = _fullmatch(n+r'는 '+n+r'을 들고 있다\.', claim)
            if not lexical:
                yes, o1, no, o2 = _fullmatch(n+r'는 '+n+r'을 들고 있다\. '+n+r'는 '+n+r'을 들고 있지 않다\.', context)
            else:
                o1, yes, no, o2 = _fullmatch(n+r'을 들고 있는 사람은 '+n+r'다\. '+n+r'는 '+n+r'을 들고 있지 않다\.', context)
        if o1 != obj or o2 != obj or yes == no or q not in (yes, no):
            raise ValueError('Ambiguous negation facts')
        return q == yes
    if concept == 'ownership_coreference':
        if language == 'en':
            q, obj = _fullmatch(n+r' owns the '+n+r' now\.', claim)
            if not lexical:
                first, o, middle, repeated, last = _fullmatch(n+r' gave the '+n+r' to '+n+r'\. Then '+n+r' gave it to '+n+r'\.', context)
            else:
                o, first, middle, repeated, last = _fullmatch(r'The '+n+r' passed from '+n+r' to '+n+r'\. Afterward, '+n+r' handed it to '+n+r'\.', context)
        else:
            obj, q = _fullmatch(r'현재 '+n+r'의 주인은 '+n+r'다\.', claim)
            if not lexical:
                first, o, middle, repeated, last = _fullmatch(n+r'는 '+n+r'을 '+n+r'에게 주었다\. 그다음 '+n+r'는 그것을 '+n+r'에게 주었다\.', context)
            else:
                o, first, middle, repeated, last = _fullmatch(n+r'은 '+n+r'에게서 '+n+r'에게 넘어갔다\. 이후 '+n+r'는 그것을 '+n+r'에게 넘겼다\.', context)
        if o != obj or middle != repeated or len({first, middle, last}) != 3 or q not in (first, middle, last):
            raise ValueError('Broken transfer/coreference chain')
        return q == last
    if concept == 'temporal_order':
        if language == 'en':
            q1, q2 = _fullmatch(n+r' arrived before '+n+r'\.', claim)
            x1, y1, x2, y2 = _fullmatch(n+r' arrived '+('after' if lexical else 'before')+r' '+n+r'\. '+n+r' arrived '+('after' if lexical else 'before')+r' '+n+r'\.', context)
        else:
            q1, q2 = _fullmatch(n+r'는 '+n+r'보다 먼저 도착했다\.', claim)
            word = '나중에' if lexical else '먼저'
            x1, y1, x2, y2 = _fullmatch(n+r'는 '+n+r'보다 '+word+r' 도착했다\. '+n+r'는 '+n+r'보다 '+word+r' 도착했다\.', context)
        edges = [(y1, x1), (y2, x2)] if lexical else [(x1, y1), (x2, y2)]
        nodes = {v for edge in edges for v in edge}
        if len(nodes) != 3 or q1 == q2 or not {q1, q2} <= nodes or edges[0][1] != edges[1][0]:
            raise ValueError('Broken temporal chain')
        reachable = {q1}
        for _ in range(3):
            reachable |= {v for u, v in edges if u in reachable}
        return q2 in reachable
    if concept == 'numeric_comparison':
        if language == 'en':
            q1, q2 = _fullmatch(n+r' has more tokens than '+n+r'\.', claim)
            pattern = n+r' has (\d+) tokens\. '+n+r' has (\d+) tokens\.' if not lexical else r'Token counts: '+n+r'=(\d+), '+n+r'=(\d+)\.'
        else:
            q1, q2 = _fullmatch(n+r'의 토큰 수는 '+n+r'보다 많다\.', claim)
            pattern = n+r'의 토큰 수는 (\d+)개이다\. '+n+r'의 토큰 수는 (\d+)개이다\.' if not lexical else r'토큰 기록: '+n+r'=(\d+)개, '+n+r'=(\d+)개\.'
        a, x, b, y = _fullmatch(pattern, context)
        if a == b or set((a,b)) != set((q1,q2)) or x == y:
            raise ValueError('Ambiguous numeric comparison')
        counts = {a:int(x), b:int(y)}
        return counts[q1] > counts[q2]
    raise ValueError('Unsupported semantic grammar')


def package_prompt(context, claim, language, answer_code):
    true_code, false_code = ('A','B') if not answer_code else ('B','A')
    if language == 'en':
        prompt = f'{context}\nStatement: {claim}\nUse {true_code} for a true statement and {false_code} for a false statement.\nAnswer:'
        completions = [f' {true_code}. The statement is true.', f' {false_code}. The statement is false.']
    else:
        prompt = f'{context}\n진술: {claim}\n진술이 참이면 {true_code}, 거짓이면 {false_code}로 답하십시오.\n답:'
        completions = [f' {true_code}. 이 진술은 참이다.', f' {false_code}. 이 진술은 거짓이다.']
    return prompt, completions


def build_engineering(seed=SEED):
    rng = random.Random(seed);rows = []
    for concept in CONCEPTS:
        for index in range(8):
            family = f'E-{concept}-{index:02d}'
            values = rng.sample(range(11,100),2)
            for state, lexical, code, language in itertools.product((0,1),(0,1),(0,1),LANGUAGES):
                names = (NAMES_EN[index],OTHER_EN[index],THIRD_EN[index]) if language=='en' else (NAMES_KO[index],OTHER_KO[index],THIRD_KO[index])
                obj = OBJECTS_EN[index] if language=='en' else OBJECTS_KO[index]
                context, claim = _render(concept,names,obj,values,state,lexical,language)
                prompt, completions = package_prompt(context,claim,language,code)
                suffix = f's{state}-l{lexical}-c{code}-{language}'
                row = dict(id=family+'-'+suffix, family_id=family, source_id=family,
                           lineage_id='engineering-template-v1/'+concept,
                           template_id=f'{concept}/lex{lexical}/{language}', grammar_id='controlled-v1/'+concept,
                           split='engineering',concept=concept,language=language,
                           semantic_state=state,label=state,lexical=lexical,answer_code=code,
                           context=context,claim=claim,prompt=prompt,completions=completions,
                           canonical_proposition_ids=['statement_true','statement_false'],
                           correct_index=0 if state else 1,span=[0,len(context)],
                           pair_id=f'{family}-l{lexical}-c{code}-{language}',
                           counterfactual_donor_id=f'{family}-s{1-state}-l{lexical}-c{code}-{language}',
                           lexical_donor_id=f'{family}-s{state}-l{1-lexical}-c{code}-{language}',
                           source_provenance='newly authored controlled-language engineering grammar; not a sampled independent document',
                           facts=dict(names=list(names),object=obj,numeric_values=values),
                           causal_selected=lexical==index%2)
                row['correct']=completions[row['correct_index']];row['foil']=completions[1-row['correct_index']]
                row['prompt_sha256']=digest(prompt.encode());row['content_sha256']=digest([context,claim])
                rows.append(row)
    validate_records(rows,expected_families=32,expected_split='engineering')
    return rows


def validate_records(rows,expected_families=None,expected_split=None):
    if not rows:raise ValueError('Empty dataset')
    ids={r['id']:r for r in rows}
    if len(ids)!=len(rows):raise ValueError('Repeated row ID')
    families={};signatures={};prompts=set()
    for row in rows:
        if row['split'] in ('test','ood'):raise ValueError('Test and OOD remain closed')
        if expected_split and row['split']!=expected_split:raise ValueError('Wrong split')
        if row['grammar_id']!='controlled-v1/'+row['concept']:raise ValueError('New source grammar requires an independently tested oracle')
        if oracle(row['context'],row['claim'],row['concept'],row['language'],row['lexical'])!=bool(row['semantic_state']):raise ValueError('Text oracle disagrees with semantic state')
        prompt, completions=package_prompt(row['context'],row['claim'],row['language'],row['answer_code'])
        if row['prompt']!=prompt or row['completions']!=completions:raise ValueError('Prompt/code/completion mismatch')
        correct=0 if row['semantic_state'] else 1
        if row['correct_index']!=correct or row['label']!=row['semantic_state'] or row['correct']!=completions[correct] or row['foil']!=completions[1-correct]:raise ValueError('Answer mismatch')
        if row['span']!=[0,len(row['context'])]:raise ValueError('Invalid semantic span')
        if row['prompt_sha256']!=digest(prompt.encode()) or row['content_sha256']!=digest([row['context'],row['claim']]):raise ValueError('Text hash mismatch')
        if prompt in prompts:raise ValueError('Repeated prompt')
        prompts.add(prompt);families.setdefault(row['family_id'],[]).append(row)
        # All variants of one known rendering grammar share ancestry, even if a
        # caller gives the examples different lineage IDs or story wrappers.
        signatures.setdefault(row['grammar_id'],set()).add(row['lineage_id'])
        for donor_key,factor in [('counterfactual_donor_id','semantic_state'),('lexical_donor_id','lexical')]:
            donor=ids.get(row[donor_key])
            if donor is None:raise ValueError('Missing paired donor')
            for key in ('family_id','concept','language','answer_code','lexical','semantic_state'):
                if key!=factor and donor[key]!=row[key]:raise ValueError('Donor changes an unintended factor')
            if donor[factor]!=1-row[factor]:raise ValueError('Donor does not flip exactly the intended factor')
    expected=set(itertools.product((0,1),(0,1),(0,1),LANGUAGES))
    for family,items in families.items():
        if len(items)!=16 or {(r['semantic_state'],r['lexical'],r['answer_code'],r['language']) for r in items}!=expected:raise ValueError('Incomplete factorial family')
        if len({(r['lineage_id'],r['concept'],r['source_id']) for r in items})!=1:raise ValueError('Family provenance changes across variants')
        if sum(bool(r['causal_selected']) for r in items)!=8:raise ValueError('Need eight causal cells')
        if {(r['semantic_state'],r['answer_code'],r['language']) for r in items if r['causal_selected']}!=set(itertools.product((0,1),(0,1),LANGUAGES)):raise ValueError('Causal subset loses a primary stratum')
    if expected_families is not None and len(families)!=expected_families:raise ValueError('Family count mismatch')
    if any(len(lineages)!=1 for lineages in signatures.values()):raise ValueError('Shared grammar falsely assigned independent lineages')
    counts={c:len({r['lineage_id'] for r in rows if r['concept']==c}) for c in CONCEPTS}
    return dict(rows=len(rows),scenario_families=len(families),lineage_clusters=len({r['lineage_id'] for r in rows}),lineages_per_concept=counts,
                independent_template_generalization_gate='FAIL_INSUFFICIENT_LINEAGES',
                minimum_required_test_lineages_per_concept=40,
                inference_scope='Engineering only; scenario substitutions are not independent template samples',
                source_ids=sorted({r['source_id'] for r in rows}),lineage_ids=sorted({r['lineage_id'] for r in rows}),grammar_ids=sorted(signatures),
                prompt_sha256=sorted(r['prompt_sha256'] for r in rows),content_sha256=sorted({r['content_sha256'] for r in rows}))


def build_readiness(source_records, engineering_manifest, prompt_freeze_receipt):
    """Validate a supplied independent catalog only; never synthesize R from E.

    Current four-grammar bank has no reserved independent readiness templates.
    Thus reusing it fails BLOCKED_DATA_GATE, irrespective of renamed source IDs.
    A future catalog needs genuinely new grammars and tested oracle extensions.
    """
    if not prompt_freeze_receipt or prompt_freeze_receipt.get('status')!='FROZEN_ENGINEERING_PROMPT':raise ValueError('Readiness remains sealed until engineering prompt freeze')
    if prompt_freeze_receipt.get('engineering_data_sha256')!=engineering_manifest['data_sha256']:raise ValueError('Prompt freeze receipt does not bind engineering data')
    if prompt_freeze_receipt.get('prompt_packager_sha256')!=prompt_packager_hash():raise ValueError('Prompt code changed after freeze')
    if not source_records:raise ValueError('BLOCKED_DATA_GATE: independent readiness source catalog unavailable')
    checked=validate_records(source_records,64,'readiness')
    old=engineering_manifest['validation']
    for key in ('source_ids','lineage_ids','grammar_ids','prompt_sha256','content_sha256'):
        if set(checked[key]) & set(old[key]):raise ValueError('BLOCKED_DATA_GATE: engineering/readiness lineage or content leakage: '+key)
    return source_records


def prompt_packager_hash():
    import inspect
    return digest(inspect.getsource(package_prompt).encode())


def freeze_engineering(output_dir, seed=SEED):
    rows=build_engineering(seed);validation=validate_records(rows,32,'engineering')
    raw=''.join(json.dumps(row,ensure_ascii=False,sort_keys=True)+'\n' for row in rows).encode()
    manifest=dict(version=VERSION,split='engineering',seed=seed,data_sha256=digest(raw),
                  source_code_sha256=digest(Path(__file__).read_bytes()),prompt_packager_sha256=prompt_packager_hash(),validation=validation,
                  other_splits_generated=False,readiness_status='BLOCKED_DATA_GATE_PENDING_INDEPENDENT_CATALOG_AND_PROMPT_FREEZE',
                  test_opened=False,ood_opened=False,limitations=['Four shared content/rendering grammar lineages, not32 independent source templates.','Only controlled-language statement truth is validated; no free-text fluency or universal semantic oracle.','No claim of absence of all lexical shortcuts; all four factors and donor pairs are explicit.'])
    directory=Path(output_dir);directory.mkdir(parents=True,exist_ok=True)
    for path,payload in [(directory/'engineering.jsonl',raw),(directory/'engineering_manifest.json',(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode())]:
        if path.exists() and path.read_bytes()!=payload:raise FileExistsError('Refusing to overwrite frozen engineering evidence: '+str(path))
    for path,payload in [(directory/'engineering.jsonl',raw),(directory/'engineering_manifest.json',(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode())]:
        if not path.exists():path.write_bytes(payload)
    return manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,default=ROOT/'data/followup-v3-gemma-map');args=parser.parse_args()
    manifest=freeze_engineering(args.output)
    print(json.dumps({k:manifest[k] for k in ['data_sha256','readiness_status','test_opened','ood_opened']}))


if __name__=='__main__':main()
