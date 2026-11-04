"""Post-hoc, descriptive shortcut stress readout of already-saved margins.

No model loading, fitting, test re-selection, inferential tests or primary-result
changes occur here. --split D3 never inspects D4 measurements. D4 requires its own
explicit invocation after causal collection completes.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import numpy as np

from .followup_data import CONCEPTS, oracle

ROOT=Path(__file__).resolve().parents[1]
LOCAL_MISMATCHES={'(]','(}','[)','[}','{)','{]'}


def sha_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def adjacent_type_mismatch(brackets):
    return any(brackets[i:i+2] in LOCAL_MISMATCHES for i in range(len(brackets)-1))


def max_stack_depth(brackets):
    depth=maximum=0
    for char in brackets:
        depth += 1 if char in '([{' else -1
        if depth<0:raise ValueError('Expected valid opening-closing skeleton')
        maximum=max(maximum,depth)
    if depth!=0:raise ValueError('Unbalanced opening-closing skeleton')
    return maximum


def pair_strata(rows):
    """Cuts fixed in this exploratory script, applied to complete pairs only."""
    pairs={}
    for row in rows:
        if row['concept'] not in ('arithmetic','syntax'):continue
        if bool(row['label'])!=oracle(row):raise ValueError('Semantic truth mismatch')
        pairs.setdefault(row['pair_id'],[]).append(row)
    result={}
    for pair_id,pair in pairs.items():
        if len(pair)!=2 or {r['label'] for r in pair}!={0,1}:raise ValueError('Stress strata require complete opposite-label donor pairs')
        false,true=sorted(pair,key=lambda r:r['label'])
        concept=true['concept']
        if false['concept']!=concept or false['group_id']!=true['group_id']:raise ValueError('Pair metadata disagree')
        if concept=='syntax':
            bad,good=false['semantic']['brackets'],true['semantic']['brackets']
            if Counter(bad)!=Counter(good) or [x in '([{' for x in bad]!=[x in '([{' for x in good]:raise ValueError('Frozen syntax pair controls broken')
            if adjacent_type_mismatch(good):raise ValueError('A valid sequence cannot contain an adjacent type mismatch')
            cue='adjacent_mismatch_present' if adjacent_type_mismatch(bad) else 'no_adjacent_mismatch'
            depth=max_stack_depth(good)
            fields={'syntax/local_cue':cue,'syntax/max_depth':str(depth),'syntax/cue_by_depth':f'{cue}/depth_{depth}'}
            features={'false_has_adjacent_mismatch':cue=='adjacent_mismatch_present','valid_max_stack_depth':depth,'bracket_pairs':len(good)//2}
        else:
            original=true['semantic']['claimed_sum'];wrong=false['semantic']['claimed_sum']
            if original%2!=wrong%2 or len(str(original))!=len(str(wrong)):raise ValueError('Frozen arithmetic pair controls broken')
            distance=abs(wrong-original);offset='near_abs_offset_le_10' if distance<=10 else 'far_abs_offset_gt_10'
            carry='ones_carry' if true['semantic']['a']%10+true['semantic']['b']%10>=10 else 'no_ones_carry'
            fields={'arithmetic/false_offset':offset,'arithmetic/carry':carry,'arithmetic/offset_by_carry':f'{offset}/{carry}'}
            features={'false_offset':wrong-original,'false_absolute_offset':distance,'ones_carry':carry=='ones_carry'}
        result[pair_id]={'concept':concept,'row_ids':[false['id'],true['id']],'group_id':true['group_id'],'strata':fields,'features':features}
    return result


def summarize_model(margins, measured_ids, canonical_rows, pairs):
    margins=np.asarray(margins,float);ids=[str(x) for x in measured_ids]
    if margins.shape!=(len(ids),) or not np.isfinite(margins).all() or len(set(ids))!=len(ids):raise ValueError('One finite margin per unique row ID required')
    lookup={r['id']:r for r in canonical_rows}
    if set(ids)!=set(lookup):raise ValueError('Stress readout requires the full frozen split; no selective row filtering')
    values=dict(zip(ids,margins.tolist()));buckets={}
    for pair_id,pair in pairs.items():
        record={'pair_id':pair_id,'row_ids':pair['row_ids'],'margins':[values[r] for r in pair['row_ids']],'group_id':pair['group_id']}
        for axis,group in pair['strata'].items():buckets.setdefault(axis,{}).setdefault(group,[]).append(record)
    output={}
    for axis,groups in buckets.items():
        output[axis]={}
        for group,records in sorted(groups.items()):
            measured=np.asarray([r['margins'] for r in records]);correct=measured>0
            pair_accuracy=correct.mean(axis=1)
            wrapper_means={wrapper:float(np.mean([pair_accuracy[i] for i,r in enumerate(records) if r['group_id']==wrapper])) for wrapper in sorted({r['group_id'] for r in records})}
            output[axis][group]={'n_pairs':len(records),'n_rows':int(measured.size),'n_true':len(records),'n_false':len(records),
                'accuracy_pair_balanced':float(pair_accuracy.mean()),'correct_rows':int(correct.sum()),
                'accuracy_true_rows':float(correct[:,1].mean()),'accuracy_false_rows':float(correct[:,0].mean()),
                'pairs_both_correct':int(correct.all(axis=1).sum()),'pairs_neither_correct':int((~correct).all(axis=1).sum()),
                'tie_rows':int((measured==0).sum()),'n_wrappers':len(wrapper_means),
                'accuracy_wrapper_equal_descriptive':float(np.mean(list(wrapper_means.values()))),
                'pair_ids':[r['pair_id'] for r in records]}
    return output


def read_split(root,split):
    directory=root/'data/followup-v2';manifest=json.loads((directory/'manifest.json').read_text());path=directory/f'{split}.jsonl'
    if sha_file(path)!=manifest['file_sha256'][path.name]:raise ValueError('Frozen split byte hash mismatch')
    rows=[json.loads(line) for line in path.read_text().splitlines()]
    if any(r['split']!=split for r in rows):raise ValueError('Mixed split rows')
    return rows,{'manifest_sha256':sha_file(directory/'manifest.json'),'split_file_sha256':sha_file(path),'path':str(path.relative_to(root))}


def run_stress(root=ROOT,split='D3'):
    root=Path(root).resolve()
    if split not in ('D3','D4'):raise ValueError('Only explicit D3 or D4 saved-margin analysis is supported')
    cfg=json.loads((root/'configs/followup_v2.json').read_text());names=[f'seed{s}' for s in cfg['training']['seeds']]+['qwen','smol','olmo']
    rows,data_source=read_split(root,split);pairs=pair_strata(rows);models={};missing=[];sources={}
    for name in names:
        directory=root/'results/followup-v2'/('collections/'+name+'/final/D3' if split=='D3' else 'causal/'+name+'/D4')
        manifest_path=directory/'manifest.json'
        if not manifest_path.is_file():missing.append(name);continue
        manifest=json.loads(manifest_path.read_text());filename='measurements.npz' if split=='D3' else 'effects.npz';hashkey='measurements_sha256' if split=='D3' else 'effects_sha256';path=directory/filename
        if sha_file(path)!=manifest[hashkey]:raise ValueError(f'{name}: measurement checksum mismatch')
        with np.load(path,allow_pickle=False) as arrays:
            lookup={r['id']:r for r in rows};ids=arrays['row_ids'].astype(str).tolist()
            if any(i not in lookup for i in ids):raise ValueError('Unknown measurement ID')
            for key,field in [('labels','label'),('concepts','concept'),('groups','group_id')]:
                if not np.array_equal(arrays[key],np.asarray([lookup[i][field] for i in ids])):raise ValueError(f'{name}: metadata mismatch {key}')
            models[name]=summarize_model(arrays['margins'],ids,rows,pairs)
        lock=root/'results/followup-v2/calibration'/name/'lock.json'
        sources[name]={'path':str(path.relative_to(root)),'sha256':sha_file(path),'manifest_sha256':sha_file(manifest_path),
                       'prompt_variant':json.loads(lock.read_text())['variant'] if lock.is_file() else 'UNKNOWN'}
    return {'analysis':'exploratory_shortcut_stress_v1','split':split,'status':'COMPLETE_DESCRIPTIVE' if not missing else 'PARTIAL_DESCRIPTIVE',
      'posthoc':True,'primary_results_changed':False,'fits_or_new_model_calls':False,'pvalues_computed':False,
      'cuts_selected_after_D3_observed':True,'data_source':data_source,'sources':sources,'models':models,'missing_models':missing,
      'pair_features':pairs,'definitions':{'pair_balanced_accuracy':'Mean of the two correct-minus-foil-margin>0 indicators within each pair, then equal mean over pairs; ties incorrect.',
        'syntax_local_cue':'Whether the FALSE pair member contains any adjacent mismatched open-close pair: (], (}, [), [}, {), {]. Both true and false rows stay in its assigned stratum.',
        'syntax_depth':'Maximum stack depth of the VALID pair member; same untyped skeleton for its false donor.',
        'arithmetic_offset':'Absolute false claimed sum minus true sum, near<=10 versus far>10.',
        'carry':'Whether operand ones digits sum to at least10; not a claim about all carries.'},
      'limitations':['All cuts are exploratory, chosen after D3 was known; no confirmatory p-values or causal cue-use claim.',
        'No adjacent mismatch removes this one local cue; it does not prove recursive parsing and other local or finite-state cues may remain.',
        'Strata differ in content, depth, model competence and sample support; accuracy differences are not controlled causal effects.',
        'Arithmetic parity/digit-length controls hold within pairs, but value frequency, operand magnitude and other digit patterns remain possible cues.',
        'Reported pair-weighted accuracies retain balanced labels; wrapper-equal descriptive averages are supplementary.',
        'Models can use different calibration-locked prompt variants; cross-model differences cannot be attributed solely to shortcut use.',
        'No future thresholds, model settings, primary mappings or inclusion rules are selected from this readout.']}


def _table(result,axis,labels):
    models=result['models'];parts=['| Model | '+' | '.join(label for key,label in labels)+' |','|---|'+'---:|'*len(labels)]
    for name,groups in models.items():
        values=[]
        for key,label in labels:
            item=groups.get(axis,{}).get(key)
            values.append(f"{100*item['accuracy_pair_balanced']:.1f}% (n={item['n_rows']})" if item else 'N/A (n=0)')
        parts.append('| '+name+' | '+' | '.join(values)+' |')
    return '\n'.join(parts)


def render_report(results):
    text=['# 후속 데이터의 탐색적 shortcut 스트레스 분석','',
      '**D3 결과를 이미 확인한 뒤 정의한 사후 분석이다.** 새로운 모델 호출이나 정렬 학습 없이 저장된 정답–오답 후보 로그확률 차이만 다시 집계했다. 주 분석, verdict, 데이터, 후보 뉴런, 정렬 및 하이퍼파라미터를 변경하지 않는다. p값이나 유의성 주장은 제공하지 않는다.','',
      '각 stratum은 참·거짓 donor pair 전체를 함께 포함한다. 표의 정확도는 pair마다 두 문항의 정확도를 평균한 뒤 pair들을 동일 가중으로 평균한 값이며, n은 문항 수다. margin=0은 오답으로 센다. 서로 다른 stratum의 점수 차이는 문항 난도·내용·깊이 등의 차이를 포함하므로 특정 단서를 사용했다는 인과적 증거가 아니다.','']
    for result in results:
        split=result['split'];models=result['models']
        tiny=[groups['syntax/local_cue'] for name,groups in models.items() if name.startswith('seed')]
        finding=''
        if tiny and all('no_adjacent_mismatch' in group and 'adjacent_mismatch_present' in group for group in tiny):
            present=[x['adjacent_mismatch_present']['accuracy_pair_balanced'] for x in tiny]
            absent=[x['no_adjacent_mismatch']['accuracy_pair_balanced'] for x in tiny]
            n_present=tiny[0]['adjacent_mismatch_present']['n_rows'];n_absent=tiny[0]['no_adjacent_mismatch']['n_rows']
            finding=(f'독립 학습 모델 {len(tiny)}개의 괄호 정확도는 인접 불일치 단서가 있는 pair 집합에서 {100*min(present):.1f}–{100*max(present):.1f}% (n={n_present}), '
                     f'이 단서가 없는 집합에서 {100*min(absent):.1f}–{100*max(absent):.1f}% (n={n_absent})였다. '
                     '이는 남은 국소 단서와의 연관성을 점검해야 함을 보여 주지만, 사용한 학습 기제를 이 집계만으로 확정할 수 없다.')
        text += [f'## {split}: 저장된 baseline margin 재집계','',f"상태: `{result['status']}`. 모델 {len(models)}개. 미완료 모델: {', '.join(result['missing_models']) or '없음'}.",'',
          '### 괄호: 거짓 문항의 인접 종류 불일치 단서','',finding,'',
          '인접한 여는–닫는 기호가 `(]`, `(}`, `[)`, `[}`, `{)`, `{]` 중 하나면 단서 있음으로 분류했다. 올바른 짝 문항에는 이 단서가 없다. 단서가 없는 거짓 문항도 포함한 pair subset은 이 단순 국소 단서 없이 남는 사례를 보여 주지만, 재귀 parsing을 입증하지 않는다.','',
          _table(result,'syntax/local_cue',[('adjacent_mismatch_present','인접 불일치 있음'),('no_adjacent_mismatch','인접 불일치 없음')]),'',
          '### 괄호: 올바른 짝 문항의 최대 stack 깊이','']
        depths=sorted({int(key) for groups in models.values() for key in groups.get('syntax/max_depth',{})})
        text += [_table(result,'syntax/max_depth',[(str(d),f'깊이 {d}') for d in depths]),'',
          '깊이별 결과 역시 사후 기술 통계다. 깊이와 인접 단서 유무의 교차 집계 및 각 pair ID는 JSON에 함께 저장했다. 표본이 적거나 모델의 전체 과제 능력이 낮은 구간에서 강한 해석을 하지 않는다.','',
          '### 산술: 오답 거리와 일의 자리 carry','',
          _table(result,'arithmetic/false_offset',[('near_abs_offset_le_10','가까운 오답: 절대차≤10'),('far_abs_offset_gt_10','먼 오답: 절대차>10')]),'',
          _table(result,'arithmetic/carry',[('no_ones_carry','일의 자리 carry 없음'),('ones_carry','일의 자리 carry 있음')]),'',
          '모든 산술 pair에서 참·거짓 합계의 parity와 십진수 자릿수가 같다. 그렇더라도 숫자 빈도·피연산자 크기·특정 자릿수 패턴이 남을 수 있다. 오답 거리×carry 교차 집계는 JSON에 기록했고, 이 분석을 보고 새 cutoff를 선택하지 않는다.','',
          f"원본 데이터: `{result['data_source']['path']}` · SHA256 `{result['data_source']['split_file_sha256']}`",'',
          f"전체 수치와 모델별 NPZ/manifest 해시: `results/followup-v2/exploratory/stress_{split}.json`",'']
    text += ['## 남는 한계','',
      '24개의 wrapper는 같은 합성 의미 문법을 감싼 지시문이다. Boolean 과제의 제한된 연산 문법, 수 비교의 어휘·자리값 단서, 괄호의 다른 국소 구조 단서처럼 여기서 검정하지 않은 대체 설명이 남아 있다. 이러한 가능성을 나열하는 것은 추가 cutoff를 탐색하거나 유리한 결과를 고르기 위한 것이 아니다. 모델별 calibration에서 고정한 프롬프트 형식이 다를 수 있으므로 모델 간 차이를 shortcut 이용 차이로 단정할 수도 없다.','',
      'D4는 인과적 개입 자료에서 함께 저장한 **개입 전 baseline margin**에 대해 별도 명령으로만 집계한다. D3 실행은 D4 측정 파일을 읽지 않는다. D4에서도 동일한 이미 명시한 컷을 사용하되, 전체 분석의 사후·탐색적 지위를 유지한다.','']
    return '\n'.join(text)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,default=ROOT);parser.add_argument('--split',choices=['D3','D4'],default='D3');args=parser.parse_args()
    root=args.root.resolve();result=run_stress(root,args.split)
    if result['missing_models']:raise RuntimeError('Incomplete saved evidence; no stress artifact written. Missing: '+', '.join(result['missing_models']))
    out=root/'results/followup-v2/exploratory'/f'stress_{args.split}.json';out.parent.mkdir(parents=True,exist_ok=True)
    payload=json.dumps(result,sort_keys=True,indent=2,ensure_ascii=False,allow_nan=False)+'\n'
    if out.exists() and out.read_text()!=payload:raise ValueError('Refusing to replace divergent stress evidence; preserve it and version the analysis')
    if not out.exists():out.write_text(payload)
    reports=[result]
    if args.split=='D4':
        prior=out.with_name('stress_D3.json')
        if prior.is_file():reports.insert(0,json.loads(prior.read_text()))
    report=root/'reports/followup-v2/STRESS_ANALYSIS.md';report.parent.mkdir(parents=True,exist_ok=True);report.write_text(render_report(reports))
    print(json.dumps({'status':result['status'],'split':args.split,'models':len(result['models']),'missing':result['missing_models'],'json':str(out.relative_to(root))},ensure_ascii=False))


if __name__=='__main__':main()
