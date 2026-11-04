"""Immutable follow-up probes with new content, wrappers and explicit semantic oracles.

This module never reads or modifies pilot-v1 data. Wrappers are shared across tasks
and form the statistical grouping unit. More wrappers do not create new task grammars.
"""
from __future__ import annotations
import hashlib
import itertools
import json
import random
from collections import Counter
from pathlib import Path

VERSION = 'followup-v2'
SPLITS = ('train', 'calibration', 'D1', 'D2', 'D3', 'D4')
CONCEPTS = ('arithmetic', 'comparison', 'negation', 'syntax')
DEFAULT_SEEDS = (2718, 3141, 5772)

# Written as full natural instructions rather than differentiating templates by IDs.
# All questions ask for truth of the claim: no question negates the requested answer.
WRAPPERS = {
 'train': [
 '{s} Is this true?', 'Check this: {s} Is it correct?', 'Claim: {s} Does it hold?',
 'Decide yes or no. {s} Is the claim true?', '{s} Is that accurate?', 'Judge this claim: {s} Correct?',
 'Statement: {s} Is it valid?', '{s} Can you confirm this claim?', 'Evaluate: {s} Is it right?',
 'Read this claim. {s} Is it true?', '{s} Is the statement correct?', 'Assess: {s} Does the claim hold?',
 'Please check: {s} True?', '{s} Is the assertion accurate?', 'Fact check: {s} Correct?',
 'Here is a claim: {s} Should it be accepted?', '{s} Is this statement valid?', 'Consider the claim {s} Is it true?',
 'Answer yes if this is true: {s} Is it?', '{s} Does this assertion hold?', 'Verify: {s} Is the claim accurate?',
 'Determine the truth of this claim: {s} Is it true?', '{s} Would you mark this correct?', 'Your claim to judge: {s} Is it correct?'],
 'calibration': [
 'Test statement: {s} Is it correct?', '{s} Does the statement hold?', 'Check the assertion {s} Is it true?',
 'Please assess the following: {s} Correct?', '{s} Is this claim right?', 'Determine whether the following is true: {s} Is it?',
 'I propose this claim: {s} Is it accurate?', '{s} Can this claim be confirmed?', 'Your question is whether this is true: {s} Is it?',
 'For verification: {s} Is it correct?', '{s} Is that claim valid?', 'Judge the statement below. {s} Is it accurate?',
 'Take this assertion: {s} Does it hold?', '{s} Is this fact stated correctly?', 'Evaluate the truth of: {s} Is it true?',
 'Would this claim pass a check? {s} Is it correct?', '{s} Should this statement be accepted?', 'Please verify the assertion: {s} Is it true?',
 'Assess the truth of this: {s} Correct?', '{s} Can you affirm this statement?', 'Review the claim: {s} Is it right?',
 'Decide whether to accept this claim: {s} Is it true?', '{s} Is the proposed statement accurate?', 'Check for correctness: {s} Is it valid?'],
 'D1': [
 'A student claims: {s} Is the student correct?', '{s} Would this assertion be true?', 'Inspect this claim: {s} Does it hold?',
 'Please judge the truth here: {s} Is it true?', '{s} Is this proposed fact correct?', 'Can the following claim be accepted? {s} Is it valid?',
 'An exercise states: {s} Is that correct?', '{s} Does the claim withstand checking?', 'Decide the truth value: {s} Is it true?',
 'Examine this statement: {s} Correct?', '{s} Is the given assertion right?', 'A learner writes: {s} Is that accurate?',
 'Look at this claim: {s} Can you confirm it?', '{s} Would the statement pass as correct?', 'The assertion to assess is: {s} True?',
 'For a truth check, consider: {s} Is it correct?', '{s} Is the above claim valid?', 'A proposed answer says: {s} Is it right?',
 'Check the reasoning outcome: {s} Is this true?', '{s} Do the facts support this assertion?', 'Please evaluate this claim for truth: {s} Is it true?',
 'Treat this as a claim to verify: {s} Correct?', '{s} Should the claim receive a yes?', 'Test the assertion: {s} Does it hold?'],
 'D2': [
 'An examiner asks about this claim: {s} Is it true?', '{s} Does this deserve a correct mark?', 'Review this assertion carefully: {s} Is it valid?',
 'Find whether this claim holds: {s} Does it?', '{s} Is the supplied statement true?', 'Here is an assertion for checking: {s} Correct?',
 'A colleague proposes: {s} Is the proposal accurate?', '{s} Can the assertion be accepted?', 'Please determine if this claim is true: {s} Is it?',
 'Consider this proposed fact: {s} Is it right?', '{s} Is the stated claim sound?', 'Make a truth judgment: {s} Is it true?',
 'A worksheet contains: {s} Is it correct?', '{s} Is the assertion given here accurate?', 'Judge correctness here: {s} Is it correct?',
 'The following is asserted: {s} Does it hold?', '{s} Can this statement be verified as true?', 'Please decide the truth of this assertion: {s} True?',
 'Assess this proposed statement: {s} Is it valid?', '{s} Should we affirm the claim?', 'A note claims: {s} Is that right?',
 'Verify the supplied claim: {s} Is it accurate?', '{s} Would you accept the assertion as true?', 'Give a verdict on this claim: {s} Correct?'],
 'D3': [
 'A teacher is checking this: {s} Is the claim correct?', '{s} Would the claim be judged true?', 'Investigate this assertion: {s} Does it hold?',
 'Please inspect the claim for correctness: {s} Is it right?', '{s} Is this a true statement?', 'An answer key proposes: {s} Is it accurate?',
 'The claim under review is: {s} Is it true?', '{s} Could we confirm the assertion?', 'Decide if the proposed fact is true: {s} Is it?',
 'Someone wrote this statement: {s} Is it valid?', '{s} Does the given claim hold?', 'A reviewer must check: {s} Is it correct?',
 'Look closely at this assertion: {s} Is it accurate?', '{s} Is the claim as written true?', 'Determine if this assertion holds: {s} Does it?',
 'For assessment, the claim is: {s} Correct?', '{s} Can we endorse this statement as true?', 'A problem suggests: {s} Is the suggestion correct?',
 'Check whether the statement is true: {s} Is it?', '{s} Does this assertion merit agreement?', 'Here is the claim to examine: {s} Is it right?',
 'Please decide whether the claim is accurate: {s} Is it?', '{s} Is this assertion valid as stated?', 'A proposed solution states: {s} Is that true?'],
 'D4': [
 'A final claim needs checking: {s} Is it true?', '{s} Would a careful check confirm this?', 'Inspect the proposed fact: {s} Is it correct?',
 'Please evaluate correctness: {s} Is the claim valid?', '{s} Is that a correct assertion?', 'A reader proposes this statement: {s} Is it right?',
 'Consider the assertion under test: {s} Does it hold?', '{s} Can the stated claim be affirmed?', 'Determine if the following claim is accurate: {s} Is it?',
 'For review, someone claims: {s} Is that true?', '{s} Does this statement merit a yes?', 'A test presents this claim: {s} Is it correct?',
 'Check this proposed answer for truth: {s} Is it true?', '{s} Is the statement given here valid?', 'Your judgment is requested: {s} Is the claim right?',
 'Please assess whether this assertion holds: {s} Does it?', '{s} Could this claim be marked correct?', 'An exercise proposes the claim: {s} Is it accurate?',
 'Read the assertion and judge it: {s} True?', '{s} Is the proposed claim valid?', 'Verify the truth of this statement: {s} Is it true?',
 'A statement has been submitted: {s} Should it be accepted?', '{s} Is this accurate as a claim?', 'Judge the assertion supplied here: {s} Is it correct?']}


def _digest(value):
 return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _bracket_valid(text):
 stack=[]
 close={')':'(', ']':'[', '}':'{'}
 for ch in text:
  if ch in '([{': stack.append(ch)
  elif ch not in close or not stack or stack.pop()!=close[ch]: return False
 return not stack


def _eval_ast(ast, assignment):
 if isinstance(ast, str): return bool(assignment[ast])
 op=ast[0]
 if op=='NOT': return not _eval_ast(ast[1], assignment)
 a,b=_eval_ast(ast[1], assignment),_eval_ast(ast[2], assignment)
 return {'AND': a and b, 'OR': a or b, 'XOR': a != b}[op]


def _print_ast(ast):
 if isinstance(ast,str): return ast
 if ast[0]=='NOT': return f'NOT {_print_ast(ast[1])}'
 return f'({_print_ast(ast[1])} {ast[0]} {_print_ast(ast[2])})'


def oracle(record):
 """Evaluate ground truth from structured semantic fields; never trust label."""
 c,m=record['concept'],record['semantic']
 if c=='arithmetic': return m['a']+m['b']==m['claimed_sum']
 if c=='comparison': return m['a']>m['b'] if m['relation']=='greater' else m['a']<m['b']
 if c=='negation': return _eval_ast(m['ast'],m['assignment'])
 if c=='syntax': return _bracket_valid(m['brackets'])
 raise ValueError(f'Unsupported concept {c}')


def _make_pair(concept, rng, seen, split):
 for attempt in range(100000):
  if concept=='arithmetic':
   a,b=rng.randrange(128),rng.randrange(128)
   key=[concept,sorted((a,b))]
   total=a+b
   # Same parity AND same decimal width. Broad offsets, never +/-1.
   wrongs=[v for v in range(256) if v!=total and v%2==total%2 and len(str(v))==len(str(total))]
   wrong=rng.choice(wrongs)
   semantics=[{'a':a,'b':b,'claimed_sum':wrong},{'a':a,'b':b,'claimed_sum':total}]
   statements=[f'{a} plus {b} equals {m["claimed_sum"]}.' for m in semantics]
  elif concept=='comparison':
   width=rng.choice((1,2,3)); low,high={1:(0,10),2:(10,100),3:(100,128)}[width]
   a,b=rng.sample(range(low,high),2)
   relation=rng.choice(('greater','less'))
   key=[concept, sorted((a,b))]
   truth=(a>b) if relation=='greater' else (a<b)
   semantics=[{'a':a if truth==bool(label) else b,'b':b if truth==bool(label) else a,'relation':relation} for label in (0,1)]
   statements=[f'{m["a"]} is {relation} than {m["b"]}.' for m in semantics]
  elif concept=='negation':
   variables=rng.sample(list('PQRSTUVWX'),3)
   leaves=[['NOT',v] if rng.random()<.5 else v for v in variables]
   # Every Boolean query contains explicit negation, with nonnumeric variable names.
   negated_index=rng.randrange(3);leaves[negated_index]=['NOT',variables[negated_index]]
   if rng.random()<.5: ast=[rng.choice(('AND','OR','XOR')),leaves[0],[rng.choice(('AND','OR','XOR')),leaves[1],leaves[2]]]
   else: ast=[rng.choice(('AND','OR','XOR')),[rng.choice(('AND','OR','XOR')),leaves[0],leaves[1]],leaves[2]]
   if rng.random()<.3: ast=['NOT',ast]
   assignments=[dict(zip(variables,bits)) for bits in itertools.product((False,True), repeat=3)]
   # Opposite labels, identical True/False counts remove assignment-count shortcut.
   candidates=[(x,y) for x in assignments for y in assignments if not _eval_ast(ast,x) and _eval_ast(ast,y) and sum(x.values())==sum(y.values())]
   if not candidates: continue
   false_assignment,true_assignment=rng.choice(candidates)
   key=[concept,ast,variables,[false_assignment,true_assignment]]
   semantics=[{'ast':ast,'assignment':x,'variable_order':variables} for x in (false_assignment,true_assignment)]
   statements=[', '.join(f'{v}={"T" if m["assignment"][v] else "F"}' for v in variables)+f'. Claim: {_print_ast(ast)} evaluates to T.' for m in semantics]
  else:
   stack=[];chars=[]
   for _ in range(rng.choice((5,6,7,8))):
    left,right=rng.choice((('(',')'),('[',']'),('{','}')));chars.append(left);stack.append(right)
    while stack and rng.random()<.5: chars.append(stack.pop())
   chars.extend(reversed(stack)); valid=''.join(chars)
   key=[concept,valid]
   closing_positions=[i for i,ch in enumerate(valid) if ch in ')]}']
   swaps=[(i,j) for i in closing_positions for j in closing_positions if i<j and valid[i]!=valid[j]]
   if not swaps: continue
   i,j=rng.choice(swaps);invalid_chars=list(valid)
   invalid_chars[i],invalid_chars[j]=invalid_chars[j],invalid_chars[i]
   invalid=''.join(invalid_chars)
   if _bracket_valid(invalid): raise AssertionError('Closing-type swap unexpectedly valid')
   semantics=[{'brackets':invalid},{'brackets':valid}]
   statements=[f'The bracket sequence {m["brackets"]} is well-formed.' for m in semantics]
  digest=_digest(key)
  if digest in seen[concept]: continue
  if concept in ('arithmetic','comparison'):
   numeric_key=tuple(sorted((semantics[0]['a'],semantics[0]['b'])))
   if numeric_key in seen['numeric'] and seen['numeric'][numeric_key]!=split: continue
   seen['numeric'][numeric_key]=split
  seen[concept].add(digest)
  return semantics,statements,key
 raise ValueError(f'Content pool exhausted for {concept}')


def generate_dataset(seeds=DEFAULT_SEEDS, train_size=16384, eval_size=768):
 """Generate old-schema-compatible rows; sizes are TOTAL rows, not per-concept.

 Eval size must be a positive multiple of 192 (4 concepts *24 wrappers *2 labels).
 Train size must be divisible by8. Three seeds govern independent content streams;
 seeds are represented within every split and are not model initialization seeds.
 """
 seeds=tuple(int(s) for s in seeds)
 if len(seeds)!=3 or len(set(seeds))!=3: raise ValueError('Exactly three distinct generation seeds required')
 if train_size<192 or train_size%8 or eval_size<192 or eval_size%192: raise ValueError('train_size divisible by8 >=192; eval_size divisible by192 >=192')
 if train_size//8+5*eval_size//8>4200: raise ValueError('Requested sizes exceed conservative unique content budget')
 rngs={s:random.Random(s) for s in seeds};seen={c:set() for c in CONCEPTS};seen['numeric']={};dataset={}
 for split_index,split in enumerate(SPLITS):
  size=train_size if split=='train' else eval_size
  n_pairs=size//8;rows=[]
  for concept_index,concept in enumerate(CONCEPTS):
   for pair_index in range(n_pairs):
    wrapper_index=pair_index%24
    generation_seed=seeds[(pair_index//24+wrapper_index+concept_index+split_index)%3]
    semantics,statements,key=_make_pair(concept,rngs[generation_seed],seen,split)
    pair_id=f'{VERSION}:{split}:{concept}:{pair_index:05d}'
    for label in (0,1):
     statement=statements[label];template=WRAPPERS[split][wrapper_index];prompt=template.format(s=statement)
     start=prompt.index(statement)
     rows.append({'id':f'{pair_id}:{label}','split':split,'concept':concept,'prompt':prompt,
      'correct':' yes' if label else ' no','foil':' no' if label else ' yes','label':label,
      'template_id':f'{split}:wrapper:t{wrapper_index:02d}','group_id':f'{split}:wrapper:t{wrapper_index:02d}',
      'template':template,'pair_id':pair_id,'numeric_tuple':sorted((semantics[label]['a'],semantics[label]['b'])) if concept in ('arithmetic','comparison') else None,
      'content_key':key,'span':[start,start+len(statement)],'statement':statement,'semantic':semantics[label],
      'generation_seed':generation_seed,'source':VERSION})
  random.Random(_digest([seeds,split,'row-order'])).shuffle(rows);dataset[split]=rows
 validate_dataset(dataset)
 return dataset


def validate_dataset(dataset):
 if set(dataset)!=set(SPLITS): raise ValueError('Expected six splits train/calibration/D1/D2/D3/D4')
 owners={k:{} for k in ('prompt','template','content_key','numeric_tuple')};ids=set();summary={};max_bytes=0;offsets=[]
 for split in SPLITS:
  rows=dataset[split];pairs={};labels=Counter();groups={};seeds=Counter()
  for row in rows:
   if row['id'] in ids or row['split']!=split: raise ValueError('Duplicate ID or wrong split')
   ids.add(row['id']);concept=row['concept'];label=row['label']
   if label not in (0,1) or oracle(row)!=bool(label): raise ValueError('Semantic oracle disagrees with truth label')
   if row['correct']!=(' yes' if label else ' no') or row['foil']!=(' no' if label else ' yes'): raise ValueError('Wrong continuations')
   start,end=row['span']
   if row['prompt'][start:end]!=row['statement']: raise ValueError('Wrong statement span')
   if row['prompt']!=row['template'].format(s=row['statement']): raise ValueError('Prompt/template mismatch')
   if row['group_id']!=row['template_id']: raise ValueError('Must cluster shared wrappers across concepts')
   nbytes=len(row['prompt'].encode());max_bytes=max(max_bytes,nbytes)
   if nbytes>250: raise ValueError('Prompt exceeds 250 byte budget')
   pairs.setdefault(row['pair_id'],[]).append(row);labels[(concept,row['group_id'],label)]+=1;seeds[row['generation_seed']]+=1
   groups.setdefault(row['group_id'],set()).add(concept)
   for field in owners:
    if row[field] is None: continue
    token=_digest(row[field]);prior=owners[field].get(token)
    if prior is not None and prior!=split: raise ValueError(f'Cross-split {field} overlap')
    owners[field][token]=split
  if len({r['prompt'] for r in rows})!=len(rows): raise ValueError('Duplicate prompt within split')
  if len(groups)!=24 or any(c!=set(CONCEPTS) for c in groups.values()): raise ValueError('Must cover all four tasks in24 shared wrapper clusters')
  for concept,group,label in labels:
   if labels[concept,group,0]!=labels[concept,group,1]: raise ValueError('Labels not balanced per task-wrapper')
  for pair in pairs.values():
   if len(pair)!=2 or {r['label'] for r in pair}!={0,1}: raise ValueError('Invalid donor pair')
   a,b=sorted(pair,key=lambda r:r['label'])
   if any(a[k]!=b[k] for k in ('group_id','concept','content_key','generation_seed')): raise ValueError('Mismatched pair metadata')
   if a['concept']=='arithmetic':
    x,y=a['semantic']['claimed_sum'],b['semantic']['claimed_sum'];offsets.append(x-y)
    if x%2!=y%2 or len(str(x))!=len(str(y)) or abs(x-y)<=1: raise ValueError('Arithmetic shortcut balance failed')
   elif a['concept']=='comparison':
    if a['semantic']['a']!=b['semantic']['b'] or a['semantic']['b']!=b['semantic']['a']: raise ValueError('Comparison donor must reverse operands')
    if len(str(a['semantic']['a']))!=len(str(a['semantic']['b'])): raise ValueError('Comparison digit-length shortcut')
   elif a['concept']=='negation':
    if a['semantic']['ast']!=b['semantic']['ast'] or sum(a['semantic']['assignment'].values())!=sum(b['semantic']['assignment'].values()): raise ValueError('Logic query/count mismatch')
   else:
    x,y=a['semantic']['brackets'],b['semantic']['brackets']
    if Counter(x)!=Counter(y): raise ValueError('Bracket multiset shortcut')
    if [ch in '([{' for ch in x]!=[ch in '([{' for ch in y]: raise ValueError('Bracket opening-closing skeleton mismatch')
  summary[split]={'n':len(rows),'sha256':_digest(rows),'clusters':24,'generation_seeds':dict(seeds),
                  'concept_counts':dict(Counter(r['concept'] for r in rows)), 'max_prompt_bytes':max(len(r['prompt'].encode()) for r in rows)}
 return {'version':VERSION,'splits':summary,'max_prompt_bytes':max_bytes,'cross_split_leakage':False,
  'grouping':'24 shared wrappers, sampled jointly across concepts','arithmetic_false_offsets':{'min':min(offsets),'max':max(offsets),'unique':len(set(offsets))},
  'shortcut_checks':{'arithmetic_pair_parity_and_width_equal':True,'comparison_operand_width_equal':True,'logic_pair_true_count_equal':True,'syntax_pair_character_multiset_equal':True,'syntax_pair_open_close_skeleton_equal':True},
  'limitations':['Task grammars shared across splits despite distinct wrappers.','Logic AST family is finite; numeric arithmetic restricted to addition.','Invalid bracket arrangements can have local order cues; multiset balance does not establish recursive parsing.','Generation seeds do not substitute for model seeds.','24 prompt wrappers are manually authored and not random draws from all language.']}


def freeze_dataset(dataset, directory='data/followup-v2'):
 """Write once. Identical bytes are resumable; any divergent existing file fails."""
 directory=Path(directory);manifest=validate_dataset(dataset)
 files={f'{split}.jsonl':''.join(json.dumps(r,sort_keys=True,separators=(',',':'))+'\n' for r in rows) for split,rows in dataset.items()}
 manifest['file_sha256']={name:hashlib.sha256(text.encode()).hexdigest() for name,text in files.items()}
 files['manifest.json']=json.dumps(manifest,sort_keys=True,indent=2)+'\n'
 # Preflight every existing target before any write.
 for name,text in files.items():
  path=directory/name
  if path.exists() and path.read_text()!=text: raise FileExistsError(f'Immutable dataset differs: {path}')
 directory.mkdir(parents=True,exist_ok=True)
 for name,text in files.items():
  path=directory/name
  if not path.exists():
   with path.open('x') as handle: handle.write(text)
 return manifest


def load_dataset(directory='data/followup-v2'):
 directory=Path(directory);manifest=json.loads((directory/'manifest.json').read_text());dataset={}
 for split in SPLITS:
  name=f'{split}.jsonl';payload=(directory/name).read_bytes()
  if hashlib.sha256(payload).hexdigest()!=manifest['file_sha256'][name]: raise ValueError(f'Frozen data hash mismatch: {name}')
  dataset[split]=[json.loads(line) for line in payload.decode().splitlines()]
 checked=validate_dataset(dataset)
 if checked['splits']!=manifest['splits']:
  # JSON object keys stringify seed integers; normalize both sides.
  if json.loads(json.dumps(checked['splits']))!=manifest['splits']: raise ValueError('Manifest metadata mismatch')
 return dataset
