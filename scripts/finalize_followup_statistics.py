"""One conservative confirmatory family; never refits a mapping on test data."""
import json,sys,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.followup_analysis import apply_global_bh,json_ready
run=ROOT/'results/followup-v2';tests={};sources={}
for relative in ('alignment/summary.json','causal_alignment/summary.json'):
    path=run/relative;obj=json.loads(path.read_text())
    if not obj['full_protocol_complete']:raise ValueError('Incomplete confirmatory family')
    for name,test in obj['confirmatory_tests'].items():
        if name in tests:raise ValueError('Duplicate hypothesis ID')
        tests[name]=test
    sources[relative]=hashlib.sha256(path.read_bytes()).hexdigest()
path=run/'transfers/summary.json';obj=json.loads(path.read_text())
if obj['status']!='COMPLETED' or len(obj['pairs'])!=5:raise ValueError('Incomplete transfer family')
tests['F5/aggregate/selected_minus_baseline']=obj['aggregate_selected_minus_baseline']
for pair,result in obj['pairs'].items():tests[f'F5/{pair}/selected_minus_baseline']=result['selected_minus_baseline']
sources['transfers/summary.json']=hashlib.sha256(path.read_bytes()).hexdigest()
result=apply_global_bh(tests)
result.update(source_sha256=sources,expected_family_size=110,scope='52 final F3 contrasts,52 F4 contrasts,5 directed F5 contrasts plus shared-wrapper F5 aggregate; no repeated checkpoint replication',limitations=['Shared models and outcomes make tests dependent; BH requires independence or suitable positive dependence.','CIs condition on the fixed five trained models and finite benchmark wrappers.','Task competence gates determine interpretation, not removal of unfavorable tests.','Checkpoint, dose, per-task and unselected transfer comparisons are descriptive.'])
if result['family_size']!=110:raise ValueError(f'Expected110 hypotheses, got{result["family_size"]}')
out=run/'statistics/global_tests.json';out.parent.mkdir(exist_ok=True)
text=json.dumps(json_ready(result),indent=2,ensure_ascii=False,allow_nan=False)+'\n'
if out.exists() and out.read_text()!=text:raise ValueError('Refusing changed global correction')
if not out.exists():out.write_text(text)
print(json.dumps({'family_size':result['family_size'],'finite_pvalue_count':result['finite_pvalue_count'],'q_below_05':sum(t['qvalue'] is not None and t['qvalue']<.05 for t in result['tests'].values())}))
