#!/usr/bin/env python3
"""Read-only descriptive F4 stratification, after all26 D4 evaluations complete.

No model calls, fitting, primary hypothesis tests, CIs, p-values, or FDR changes.
The both-passed subset conditions on D4 outcomes and is descriptive only.
"""
from __future__ import annotations
import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path
import statistics

ROOT=Path(__file__).resolve().parents[1]
CONCEPTS=('arithmetic','comparison','negation','syntax')
METHODS=('semantic','causal','combined','random')
POSITIONS=('answer','span')
KINDS=('single','group')


def sha_file(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):return json.loads(Path(path).read_text())


def validate_gate(gate):
    """Check consistency of the existing accuracy/Wilson gate; do not change it."""
    passed=[]
    for side in ('model_a','model_b'):
        item=gate[side];n=item['n'];correct=item['correct']
        if not isinstance(n,int) or not isinstance(correct,int) or n<=0 or not 0<=correct<=n:raise ValueError('Invalid competence gate counts')
        p=correct/n;z=1.959963984540054;denom=1+z*z/n
        center=(p+z*z/(2*n))/denom;half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/denom
        if not math.isclose(item['accuracy'],p,abs_tol=1e-12):raise ValueError('Competence accuracy/count mismatch')
        if any(not math.isclose(a,b,abs_tol=1e-12) for a,b in zip(item['wilson95'],[center-half,center+half])):raise ValueError('Competence Wilson interval mismatch')
        decision=p>=.70 and center-half>.5
        if item['passed'] is not decision:raise ValueError('Existing competence decision inconsistent with frozen rule')
        passed.append(decision)
    if gate['both_passed'] is not all(passed):raise ValueError('Both-passed flag inconsistent')
    return all(passed)


def load_complete_evidence(root):
    root=Path(root).resolve();run=root/'results/followup-v2';summary_path=run/'causal_alignment/summary.json'
    if not summary_path.is_file():raise RuntimeError('F4 summary is absent; do not inspect partial D4 outcomes')
    summary=read_json(summary_path)
    if (summary.get('full_protocol_complete') is not True or summary.get('n_evaluations')!=26 or
        summary.get('expected_evaluations')!=26 or len(summary.get('evaluations',[]))!=26):
        raise RuntimeError('F4 requires all26 completed evaluations before descriptive stratification')
    config=read_json(root/'configs/followup_v2.json');seeds=[f'seed{s}' for s in config['training']['seeds']]
    if len(seeds)!=5 or len(set(seeds))!=5:raise ValueError('Expected five independently trained model identities')
    cohorts={'independent_seeds':list(itertools.combinations(seeds,2)),
             'cross_family':list(itertools.combinations(('qwen','smol','olmo'),2))}
    expected={(tuple(pair),kind):cohort for cohort,pairs in cohorts.items() for pair in pairs for kind in KINDS}
    found={};sources=[]
    for entry in summary['evaluations']:
        pair=tuple(entry['pair']);kind=entry['unit_kind'];identity=(pair,kind)
        if identity not in expected or identity in found:raise ValueError('Unexpected or duplicate F4 pair/kind identity')
        relative=Path('causal_alignment')/'_'.join(pair)/kind/'eval.json'
        if Path(entry['path'])!=relative:raise ValueError('Unexpected F4 evaluation path')
        path=(run/relative).resolve()
        if not path.is_relative_to(run):raise ValueError('F4 evaluation path escapes run directory')
        digest=sha_file(path)
        if digest!=entry['sha256']:raise ValueError(f'F4 evaluation hash mismatch: {relative}')
        evidence=read_json(path)
        if tuple(evidence['pair'])!=pair or evidence['unit_kind']!=kind or evidence['cohort']!=expected[identity]:raise ValueError('F4 evaluation metadata mismatch')
        if evidence.get('evaluation_split')!='D4' or evidence.get('fit_split')!='D2':raise ValueError('Need frozen D2 maps evaluated on D4')
        if set(evidence['by_task'])!=set(CONCEPTS) or set(evidence['task_competence'])!=set(CONCEPTS):raise ValueError('Missing task-level F4 evidence')
        for concept in CONCEPTS:
            validate_gate(evidence['task_competence'][concept])
            locations=evidence['by_task'][concept]['locations']
            if set(locations)!=set(POSITIONS):raise ValueError('Missing answer/span task evidence')
            for location in POSITIONS:
                descriptors=locations[location]['descriptive']
                for method in METHODS:
                    value=descriptors[method];mean=value['mean'];valid=value['n_valid_wrappers'];total=value['n_wrappers']
                    if total!=24 or not isinstance(valid,int) or not 0<=valid<=total:raise ValueError('Invalid wrapper support counts')
                    if (mean is None)!=(valid==0):raise ValueError('Missing mean inconsistent with wrapper coverage')
                    if mean is not None and (not math.isfinite(mean) or abs(mean)>1+1e-9):raise ValueError('Nonfinite or out-of-range causal correlation')
        actual_eligible=[c for c in sorted(CONCEPTS) if evidence['task_competence'][c]['both_passed']]
        if sorted(evidence['competent_tasks'])!=actual_eligible:raise ValueError('Competent-task list disagrees with D4 gate')
        found[identity]=evidence;sources.append({'path':str(path.relative_to(root)),'sha256':digest,'pair':list(pair),'unit_kind':kind})
    if set(found)!=set(expected):raise ValueError('Incomplete F4 pair/kind coverage')
    return found,{'path':str(summary_path.relative_to(root)),'sha256':sha_file(summary_path)},sources


def aggregate(evidence,summary_source,sources):
    rows=[]
    for cohort in ('independent_seeds','cross_family'):
        for kind in KINDS:
            candidates=[item for item in evidence.values() if item['cohort']==cohort and item['unit_kind']==kind]
            candidates.sort(key=lambda item:tuple(item['pair']))
            expected=10 if cohort=='independent_seeds' else 3
            if len(candidates)!=expected:raise ValueError('Cohort pair count mismatch')
            for position in POSITIONS:
                for concept in CONCEPTS:
                    eligible=[item for item in candidates if item['task_competence'][concept]['both_passed']]
                    for subset,selected in (('all_pairs',candidates),('both_passed',eligible)):
                        methods={}
                        for method in METHODS:
                            values=[]
                            for item in selected:
                                cell=item['by_task'][concept]['locations'][position]['descriptive'][method]
                                values.append({'pair':'_'.join(item['pair']),**cell})
                            finite=[x['mean'] for x in values if x['mean'] is not None]
                            valid_wrappers=sum(x['n_valid_wrappers'] for x in values);possible_wrappers=sum(x['n_wrappers'] for x in values)
                            methods[method]={'mean':statistics.fmean(finite) if finite else None,
                                'n_available_pairs':len(finite),'n_missing_pairs':len(values)-len(finite),
                                'n_complete_wrapper_pairs':sum(x['n_valid_wrappers']==x['n_wrappers'] for x in values),
                                'n_valid_wrapper_cells':valid_wrappers,'n_possible_wrapper_cells':possible_wrappers,
                                'wrapper_coverage_fraction':valid_wrappers/possible_wrappers if possible_wrappers else None,
                                'pair_values':values}
                        rows.append({'cohort':cohort,'unit_kind':kind,'position':position,'concept':concept,'subset':subset,
                            'n_pairs_total':len(candidates),'n_pairs_in_subset':len(selected),
                            'n_pairs_gate_eligible':len(eligible),'n_pairs_gate_ineligible':len(candidates)-len(eligible),
                            'pair_ids':['_'.join(item['pair']) for item in selected],
                            'excluded_pair_ids':['_'.join(item['pair']) for item in candidates if item not in selected],
                            'methods':methods})
    return {'version':'followup-v2-causal-competence-descriptive-v1','status':'COMPLETE_DESCRIPTIVE',
        'source_summary':summary_source,'source_summary_sha256':summary_source['sha256'],'sources':sources,
        'n_source_evaluations':len(evidence),'n_strata':len(rows),'rows':rows,
        'metric':'Mean across observed pair-level within-task, wrapper-and-intervention-equal causal Pearson correlations',
        'aggregation':'Each finite pair mean receives equal weight; undefined pair means stay missing. Pair and wrapper coverage are reported per method.',
        'both_passed_definition':'Existing D4 gate for BOTH models: accuracy>=0.70 and Wilson95 lower bound>0.50. No thresholds are refit.',
        'subset_interpretation':'Selection uses D4 outcomes; both-passed tables are descriptive conditional summaries, not independent confirmatory inference.',
        'primary_evaluations_modified':False,'primary_family_modified':False,'new_tests_or_intervals':False,
        'limitations':['Shared models make seed pairs dependent; observed-pair means are not independent model replications.',
            'A method can have fewer valid wrapper cells or pair means; compare its displayed support before comparing means.',
            'No eligible pairs means N/A, never zero agreement or a negative hypothesis result.',
            'Passing the original syntax competence gate does not establish hierarchical syntax: the fresh hard-stress probe removed an adjacent mismatch cue and must be considered separately.',
            'Hard-stress and these competence-conditioned tables remain outside the primary110-test family.',
            'No new CIs, p-values, hypotheses, fitting, or model selection are performed.']}


def _cell(value):
    mean='N/A' if value['mean'] is None else f"{value['mean']:.4f}"
    return f"{mean} [{value['n_available_pairs']}; {value['n_valid_wrapper_cells']}/{value['n_possible_wrapper_cells']}]"


def render_report(result):
    text=['# F4 과제 능력별 인과 정렬 기술 통계','',
      '**기존 D4 평가26개를 모두 완료한 뒤, 저장된 과제별 정렬 점수만 재집계했다.** 정렬을 다시 학습하거나 주 검정군110개를 변경하지 않았다. 이 문서는 새 가설 검정·p값·신뢰구간을 제공하지 않는다.','',
      '`all_pairs`는 관측 모델 쌍 전체, `both_passed`는 해당 D4 과제에서 두 모델 모두 기존 능력 기준(정확도≥0.70, Wilson95 하한>0.50)을 통과한 쌍이다. **D4 결과에 조건을 건 부분집합이므로 독립적인 확인적 추론으로 해석할 수 없다.** 공통 모델을 사용하는 쌍들도 독립 반복이 아니다.','',
      '표의 각 값은 해당 과제·위치·개입 단위에서 관측한 모델 쌍의 평균 상관계수다. 각 쌍의 점수는 기존 평가에서 wrapper와 개입 유형에 동일 가중을 준 값이며, 여기서는 유한한 쌍 평균들을 동일 가중으로 평균한다. 미정의 값은0으로 채우지 않는다.','',
      '셀 형식: **평균 [유효 쌍 수; 유효 wrapper 셀/가능 wrapper 셀]**. `Pairs`는 해당 부분집합의 쌍 수/전체 관측 쌍 수다. 방법별 누락 쌍 수와 완전한 wrapper 지원을 가진 쌍 수, 개별 쌍 점수는 [JSON](../../results/followup-v2/causal_alignment/competence_descriptive.json)에 기록했다.','']
    for cohort in ('independent_seeds','cross_family'):
        title='독립 초기화 모델' if cohort=='independent_seeds' else '서로 다른 모델 계열'
        text += [f'## {title}','']
        for kind in KINDS:
            for position in POSITIONS:
                text += [f'### {kind} · {position}','',
                         '| Task | Subset | Pairs | Semantic | Causal | Combined | Random |',
                         '|---|---|---:|---:|---:|---:|---:|']
                for row in result['rows']:
                    if (row['cohort'],row['unit_kind'],row['position'])!=(cohort,kind,position):continue
                    text.append('| '+ ' | '.join([row['concept'],row['subset'],f"{row['n_pairs_in_subset']}/{row['n_pairs_total']}"]+[_cell(row['methods'][method]) for method in METHODS])+' |')
                text.append('')
    text += ['## 해석 제한과 syntax 구성 타당성','',
      '기존 syntax 과제에서 능력 기준을 통과했더라도 계층적 괄호 구조를 학습했다는 뜻은 아니다. [새 hard-stress 평가](HARD_STRESS_REPORT.md)는 인접 괄호 종류 불일치 단서를 제거한 별도 동결 문항을 사용했다. [데이터 설계](../../data/followup-v2-hard-stress/README.md)와 [기존 문항의 사후 단서 분석](STRESS_ANALYSIS.md)을 함께 읽어야 한다. 높은 인과 정렬 상관은 공통 답변 편향이나 제한된 단서 처리로도 설명될 수 있다.','',
      '능력 통과 쌍이0개이면 결과는 N/A다. 이를 인과적 기능이 없다는 증거로 해석하지 않는다. 방법별 지원 셀이 다르면 평균 차이에 누락 패턴의 영향이 포함될 수 있다. 이 표를 보고 새로운 정렬 가중치·임계값·주 평가 과제를 선택하지 않는다.','',
      '## 출처와 무결성','',
      f"전체 평가 요약: [summary.json](../../{result['source_summary']['path']}) · SHA256 `{result['source_summary_sha256']}`",'',
      '| Evaluation | SHA256 |','|---|---|']
    for source in result['sources']:
        label='_'.join(source['pair'])+'/'+source['unit_kind']
        text.append(f"| [{label}](../../{source['path']}) | `{source['sha256']}` |")
    text.append('');return '\n'.join(text)


def write_once(path,text):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        if path.read_text()!=text:raise ValueError(f'Refusing to overwrite changed descriptive evidence: {path}')
    else:path.write_text(text)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,default=ROOT);args=parser.parse_args()
    root=args.root.resolve();evidence,summary,sources=load_complete_evidence(root);result=aggregate(evidence,summary,sources)
    out=root/'results/followup-v2/causal_alignment/competence_descriptive.json';report=root/'reports/followup-v2/CAUSAL_COMPETENCE.md'
    payload=json.dumps(result,sort_keys=True,indent=2,ensure_ascii=False,allow_nan=False)+'\n';markdown=render_report(result)
    # Preflight both destinations before writing either; primary files are never opened for writing.
    for path,text in ((out,payload),(report,markdown)):
        if path.exists() and path.read_text()!=text:raise ValueError(f'Existing artifact differs: {path}')
    write_once(out,payload);write_once(report,markdown)
    print(json.dumps({'status':result['status'],'source_evaluations':len(evidence),'strata':len(result['rows']),'output':str(out.relative_to(root))}))


if __name__=='__main__':main()
