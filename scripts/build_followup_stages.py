"""Build followup-v2 stage snapshots from completed, saved evidence only.

Reporting is CPU-only. F1 opens calibration/training only; F2 opens the explicit
permutation control. Subsequent builders require completed analysis artifacts.
No D3/D4 activations or margins are opened by the F1/F2 builders.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
RUN=ROOT/'results/followup-v2'
SEEDS=(101,211,307,401,503)
MODELS=[f'seed{s}' for s in SEEDS]+['qwen','smol','olmo']

class NotReady(RuntimeError):pass

def read(path):
    path=Path(path)
    if not path.exists():raise NotReady(f'Missing required evidence: {path.relative_to(ROOT)}')
    return json.loads(path.read_text())

def rel(path):return Path(path).relative_to(ROOT).as_posix()

def metric(name,value,source,**kwargs):return dict(name=name,value=value,source=rel(source),**kwargs)

def comparison(name,result,source,scope):
    return {'name':name,'estimate':result.get('estimate',result.get('effect')),
            'ci':result.get('ci',(result.get('bootstrap') or {}).get('ci')),
            'pvalue':result.get('pvalue'),'qvalue':result.get('qvalue'),
            'correction_scope':scope,'source':rel(source)}

def base(stage,title,question):
    return {'id':stage,'title':title,'status':'MEASURED','question':question,
            'verdict':'INCONCLUSIVE','rationale':'','metrics':[], 'comparisons':[],
            'figures':[],'artifacts':[],'limitations':[]}

def f1():
    p=base('F1','5개 독립 초기화 학습과 calibration 전용 형식 선택',
           '독립 학습 모델을 확보하고 테스트셋을 보지 않고 평가 형식을 고정했는가?')
    train=[];lossrows=[];trainpaths=[];hashes=[]
    for seed in SEEDS:
        path=RUN/f'training/seed_{seed}/manifest.json';m=read(path)
        if not m.get('completed'):raise NotReady(f'Seed {seed} training incomplete')
        if m.get('seed')!=seed:raise ValueError('Training seed identity mismatch')
        train.append(m);trainpaths.append(rel(path));hashes.append(m['initial_hash'])
        p['metrics'] += [metric('Optimization steps',m['steps'],path,model=f'seed{seed}',unit='steps'),
                         metric('Training elapsed',m['elapsed_seconds'],path,model=f'seed{seed}',unit='seconds')]
        lossrows += [{'seed':f'seed{seed}','step':r['step'],'loss':r['loss'],'answer_loss':r['answer_loss']} for r in m['losses']]
        p['artifacts'].append({'label':f'Seed {seed} training provenance','path':rel(path)})
    if len(set(hashes))!=len(SEEDS):raise ValueError('F1 independent initial hashes must differ')
    selectedrows=[];variantrows=[];sources=[];chosen=[];eligible=0;total=0
    for name in MODELS:
        directory=RUN/'calibration'/name;spath=directory/'summary.json';lpath=directory/'lock.json'
        summary=read(spath);lock=read(lpath)
        if summary.get('status')!='CALIBRATED':raise NotReady(f'{name} calibration is not complete')
        if lock.get('source_split')!='calibration':raise ValueError('F1 only accepts calibration-derived locks')
        if lock['variant']!=summary['variant']:raise ValueError('Calibration lock and summary disagree')
        selected=lock['variant'];chosen.append(f'{name}: {selected}')
        variants=summary['calibration_metrics'];selected_metrics=variants[selected]
        for variant,values in variants.items():
            if values.get('split','calibration')!='calibration':raise ValueError('Held-out values cannot enter F1')
            variantrows.append({'model':name,'format':variant,'value':values['macro_accuracy']})
            p['metrics'].append(metric('Calibration macro accuracy',values['macro_accuracy'],spath,
                                      model=name,method=variant,split='calibration',unit='fraction',n=values['n']))
        for task,values in selected_metrics['per_task'].items():
            selectedrows.append({'model':f'{name} [{selected}]','task':task,'value':values['accuracy']})
            p['metrics'].append(metric('Selected-format calibration accuracy',values['accuracy'],spath,
                         model=name,method=selected,task=task,split='calibration',unit='fraction',
                         n=values['n'],ci=values['wilson95']))
            total+=1;eligible+=int(values['competent'])
        p['metrics'].append(metric('Calibration yes preference',selected_metrics['yes_rate'],spath,
                                  model=name,method=selected,unit='fraction',split='calibration',n=selected_metrics['n']))
        sources.extend([rel(spath),rel(lpath)])
        p['artifacts'] += [{'label':name+' calibration evidence','path':rel(spath)},
                           {'label':name+' frozen format','path':rel(lpath)}]
    p['rationale']=f'서로 다른 초기 파라미터 해시의 모델 {len(train)}개 학습과 {len(MODELS)}개 모델의 calibration 형식 고정을 완료했다. 선택한 형식의 calibration 과제 셀 {total}개 중 {eligible}개가 사전 능력 기준을 충족했다. 이는 형식 선택에 사용한 표본의 진단이며 독립 D3/D4 일반화 결과가 아니다.'
    p['competence_gate']={'rule':'task accuracy >=0.70 and Wilson95 lower >0.50; paired analysis requires both models',
                          'role':'Calibration diagnostic only; D3 and D4 competence assessed separately after mappings frozen',
                          'eligible_calibration_cells':eligible,'total_calibration_cells':total,'selected_formats':chosen}
    p['figures']=[{'id':'five_seed_training','kind':'line','title':'Five independent seeds: training objective',
                  'rows':lossrows,'x':'step','y':'loss','series':'seed','xlabel':'Optimization step',
                  'ylabel':'Weighted cross-entropy (nats)','yscale':'log','source':trainpaths,
                  'note':'Training loss is not held-out competence. No D3/D4 outcomes are used in this figure.'},
                 {'id':'selected_calibration_accuracy','kind':'heatmap','title':'Calibration accuracy under frozen selected formats',
                  'rows':selectedrows,'row':'model','column':'task','value':'value','vmin':0,'vmax':1,
                  'percent':True,'unit':'Accuracy; chance = 0.5','source':sources,
                  'note':'Selected on calibration itself; this is an in-sample readiness diagnostic, not final test accuracy.'},
                 {'id':'calibration_variant_comparison','kind':'heatmap','title':'Calibration format comparison',
                  'rows':variantrows,'row':'model','column':'format','value':'value','column_order':['default','explicit','fourshot'],
                  'vmin':0,'vmax':1,'percent':True,'unit':'Macro accuracy','source':sources,
                  'note':'Byte-tokenizer models use default only; unevaluated formats are N/A. One format is frozen per model.'}]
    p['limitations']=['Calibration format-selection scores are optimistic and are not final generalization estimates.',
                     'Wilson intervals are operational competence gates; they do not replace wrapper-cluster research intervals.',
                     'Five initialization seeds still represent one small architecture and one training distribution.',
                     'No D3 or D4 measurement is loaded by this stage builder.']
    p['next_action']='F2 constructed permutation control, then frozen D2 alignment before any F3 held-out evaluation.'
    return p


def f2():
    path=RUN/'positive_control/summary.json';m=read(path)
    required={'answer','span'}
    if set(m.get('alignment',{}))!=required or set(m.get('intervention_checks',{}))!=required:
        raise NotReady('Permutation positive-control output incomplete')
    if not isinstance(m.get('passed'),bool):raise ValueError('Positive control must record actual pass boolean')
    p=base('F2','정확한 뉴런 순열의 양성 대조군','의도적으로 만든 기능 보존 순열과 개입을 회복하는가?')
    p['verdict']='SUPPORTED' if m['passed'] else 'NOT SUPPORTED'
    p['rationale']='등록한 모델 내부 순열 대칭 대조군의 정렬·개입 검증을 '+('통과했다.' if m['passed'] else '통과하지 못했다.')+' 이는 측정 파이프라인의 해당 회복 성질을 검사하며, 독립적으로 학습된 모델의 의미 보존을 입증하지 않는다.'
    corr=[];recovery=[]
    for location,r in m['alignment'].items():
        for name,key in [('Permutation recovered fraction','recovered_fraction'),('Matched correlation','matched_correlation'),('Repeated random mean correlation','random_mean'),('Repeated random SD','random_sd'),('Maximum activation error','max_abs_product_difference')]:
            p['metrics'].append(metric(name,r[key],path,method=location,n=m['candidates'] if key=='recovered_fraction' else m['n'],unit='fraction of candidate neurons' if key=='recovered_fraction' else 'value'))
        corr += [{'label':f'{location}: recovered','value':r['matched_correlation']},
                 {'label':f'{location}: random mean','value':r['random_mean']}]
        recovery.append({'label':location,'value':r['recovered_fraction']})
        check=m['intervention_checks'][location]
        p['metrics'].append(metric('Baseline maximum logit discrepancy',check['baseline_max_abs_logit_difference'],path,method=location,unit='logit'))
        for mode,intervention in check['interventions'].items():
            p['metrics'].append(metric('Mapped intervention maximum effect discrepancy',intervention['effect_difference_max_abs'],path,method=location+'/'+mode,unit='logit'))
        if location in m.get('negative_checks',{}):
            negative=m['negative_checks'][location]
            p['metrics'].append(metric('Wrong identity mapping maximum logit discrepancy',negative['wrong_identity_mapping_max_abs_logit_difference'],path,method=location,unit='logit'))

    p['figures']=[{'id':'permutation_recovery','kind':'bar','title':'Known-permutation correspondence recovery',
                 'rows':recovery,'xlabel':'Recovered fraction','xlim':[0,1.1],'source':rel(path)},
                 {'id':'permutation_vs_random','kind':'interval','title':'Known-permutation correlation and repeated random mean',
                 'rows':corr,'xlabel':'Activation correlation','xlim':[-1.05,1.1],'source':rel(path),
                 'note':f"Random baseline has {m['random_replicates']} realizations; its SD is reported separately and is not labeled a confidence interval."}]
    p['artifacts']=[{'label':'Positive-control summary','path':rel(path)},
                    {'label':'Exact registered permutation','path':rel(path.parent/'mapping.json')}]
    p['limitations']=[m['scope'],f"Recovery fraction uses {m['candidates']} candidate neurons; correlations use {m['n']} input examples.",
                     'Logit equality uses the stored absolute plus relative tolerance, not absolute tolerance alone.',
                     'A constructed within-model permutation is not independent seed evidence.',
                     'Only the registered control and selected neuron/position coverage are tested.']
    return p


def f3():
    path=RUN/'alignment/summary.json';m=read(path)
    freeze_path=path.parent/'fit_manifest.json';frozen=read(freeze_path)
    if not m.get('full_protocol_complete') or m.get('n_final_evaluations')!=26 or m.get('n_trajectory_evaluations')!=40:
        raise NotReady('F3 requires all26 final and40 trajectory evaluations')
    if frozen.get('status')!='D2_MAPS_FROZEN' or not frozen.get('full_protocol_complete') or frozen.get('test_data_used'):
        raise ValueError('F3 requires complete D2-only map-freeze manifest')
    p=base('F3','독립 시드·이종 계열의 두 위치 정렬과 학습 궤적',
           '반복 무작위·학습 전 대조군을 통제한 독립 입력 대응이 존재하며 확장 의미 proxy가 개선하는가?')
    methods={'activation__flexible__hungarian':'Activation','rank__flexible__hungarian':'Rank',
             'semantic__flexible__hungarian':'Semantic','sign_semantic__flexible__hungarian':'Sign-semantic',
             'random__flexible':'Random (100)','label_shuffled__flexible__hungarian':'Shuffled labels'}
    heat={'answer':[],'span':[]};competence={};sources=[rel(path),rel(freeze_path)];eligible_cells=0
    mapping_rows=[]
    for item in m['evaluations']:
        ep=RUN/item['path'];e=read(ep)
        if hashlib.sha256(ep.read_bytes()).hexdigest()!=item['sha256']:raise ValueError('F3 evaluation source hash mismatch')
        pair='_'.join(item['pair']);position=item['position'];checkpoint=item['checkpoint']
        if e.get('evaluation_split')!='D3' or e.get('fit_split')!='D2':raise ValueError('F3 split mismatch')
        sources.append(rel(ep))
        for task,g in e['task_competence'].items():
            for which,name in zip(('model_a','model_b'),item['pair']):
                key=(name,checkpoint,task);value=g[which]['accuracy']
                if key in competence and competence[key]!=value:raise ValueError('Duplicated competence evidence disagrees')
                competence[key]=value
        if checkpoint=='final':
            fitpath=ep.parent/'fit.json';fit=read(fitpath)
            if hashlib.sha256(fitpath.read_bytes()).hexdigest()!=e['source']['fit_sha256']:
                raise ValueError('F3 frozen mapping hash mismatch')
            for method,values in e['descriptive'].items():
                mapping=fit['mappings'].get(method,{})
                mapping_rows.append({'pair':pair,'position':position,'method':method,
                    'mean':values['mean'],'valid_wrappers':values['n_valid_wrappers'],
                    'source_coverage':mapping.get('coverage'),'target_coverage':mapping.get('target_coverage'),
                    'source':rel(ep),'fit':rel(fitpath)})
            eligible_cells+=len(item['competent_tasks'])
            for key,label in methods.items():
                v=item['primary'][key]
                heat[position].append({'model_pair':pair,'method':label,'value':v['mean']})
                p['metrics'].append(metric('D3 response agreement',v['mean'],ep,model_pair=pair,
                      method=f'{position}/{label}',split='D3',unit='Pearson',n_clusters=v['n_valid_wrappers']))
    for name,test in m['confirmatory_tests'].items():
        p['comparisons'].append(comparison(name,test,path,'Predeclared F3 family member; global BH pending F6'))
    cohort_rows={name:[] for name in ('activation_minus_random','semantic_minus_activation')};trajectory=[]
    for cohort,stats in m['cohorts'].items():
        family,position,checkpoint=cohort.split('/')
        for contrast,test in stats['tests'].items():
            if test.get('effect') is None:continue
            row={'label':cohort,'value':test['effect'],'ci':(test.get('bootstrap') or {}).get('ci')}
            cohort_rows.setdefault(contrast,[]).append(row)
            p['metrics'].append(metric('Joint-wrapper '+contrast,test['effect'],path,
                     model_pair=family,method=position+'/'+checkpoint,unit='Pearson difference',
                     ci=row['ci'],n_clusters=test.get('n_clusters')))
            if family=='independent_seeds' and contrast=='activation_minus_random':
                trajectory.append({'checkpoint':{'initial':0,'middle':1,'final':2}[checkpoint],
                                   'position':position,'value':test['effect']})
    for position,rows in heat.items():
        p['figures'].append({'id':'final_'+position,'kind':'heatmap',
             'title':f'D3 final-model alignment: {position} position','rows':rows,
             'row':'model_pair','column':'method','value':'value','vmin':-1,'vmax':1,
             'unit':'Within-task wrapper-equal Pearson','source':sources,'figsize':[12,8.1],
             'note':'All task rows retained; competence-qualified strata are reported in the source. Random baseline averages100 frozen maps.'})
    for contrast,rows in cohort_rows.items():
        p['figures'].append({'id':contrast,'kind':'interval','title':'Joint-wrapper '+contrast,
             'rows':rows,'xlabel':'Pearson difference;95% shared-wrapper bootstrap CI','source':rel(path),
             'note':'All observed pairs remain together inside each resampled wrapper; these intervals are conditional on the fixed model collection, not unseen model seeds.'})
    p['figures'] += [{'id':'independent_seed_trajectory','kind':'line','title':'Independent-seed response correspondence across training',
            'rows':trajectory,'x':'checkpoint','y':'value','series':'position','xlabel':'Saved checkpoint',
            'ylabel':'Activation minus repeated-random Pearson','xticks':[0,1,2],
            'xticklabels':['Initial','Middle','Final'],'source':rel(path),
            'note':'The same final-D1 neurons and final-D2 maps are reused at all checkpoints. This is descriptive tracking, not checkpoint-specific feature discovery.'},
           {'id':'trajectory_competence','kind':'heatmap','title':'D3 task competence across models and checkpoints',
            'rows':[{'model':name+'/'+checkpoint,'task':task,'value':value} for (name,checkpoint,task),value in sorted(competence.items())],
            'row':'model','column':'task','value':'value','vmin':0,'vmax':1,'percent':True,'unit':'Accuracy;chance=50%',
            'source':sources,'note':'D3 was collected only after the registered D2 maps were frozen. Initial/middle/final are not independent model replications.'}]
    p['rationale']=f"등록한 최종 모델 비교26개와 초기·중간 체크포인트 비교40개를 완료했다. 두 위치의 최종 모델쌍×과제 셀 중 {eligible_cells}개에서 양쪽 모델의 능력 조건을 충족했다. 전체 과제 결과와 능력 조건을 구분하며, 학습 전 대응과 반복 무작위 매칭을 함께 공개한다. 확인 검정의 전역 BH는 F6에서 적용한다. 이종 계열은 calibration으로 고정한 서로 다른 프롬프트 접두 맥락을 사용하므로 동일 전체 입력의 비교가 아니며, 낮은 과제 능력에서 기능 보존의 부재를 결론내릴 수 없다."
    p['competence_gate']={'rule':'Both models accuracy>=0.70 and Wilson95 lower>0.50 per task',
                          'passed_final_pair_position_task_cells':eligible_cells,'total_final_pair_position_task_cells':104,
                          'role':'Reporting strata only; no refitting or model selection using D3'}
    supplementary=ROOT/'reports/followup-v2/F3_ALL_METHODS.md'
    lines=['# F3 — all frozen mapping variants', '',
           'Descriptive D3 measurements on the fixed final-model collection. These rows cover flexible/layer-restricted matching and Hungarian/partial/one-to-many variants, including label shuffling. Missing scores and undefined coverage remain N/A. Partial mapping can raise correlation by retaining fewer neurons; compare coverage alongside agreement. Random-map coverage is not recomputed here.', '',
           '| Pair | Position | Frozen method | D3 Pearson | Valid wrappers | Source coverage | Target coverage | Evidence |',
           '|---|---|---|---:|---:|---:|---:|---|']
    number=lambda value:'N/A' if value is None else f'{value:.4f}'
    for row in mapping_rows:
        lines.append(f"| {row['pair']} | {row['position']} | {row['method']} | {number(row['mean'])} | {row['valid_wrappers']} | {number(row['source_coverage'])} | {number(row['target_coverage'])} | [D3](../../{row['source']}) · [D2 map](../../{row['fit']}) |")
    supplementary.parent.mkdir(parents=True,exist_ok=True)
    supplementary.write_text('\n'.join(lines)+'\n')
    p['artifacts']=[{'label':'Complete alignment summary','path':rel(path)},
                    {'label':'D2 map-freeze manifest','path':rel(freeze_path)},
                    {'label':'All mapping variants and coverage','path':rel(supplementary)}]
    p['limitations']=['Five seeds produce ten dependent pairs, not ten independent replications.',
                     'Final-D1 candidate selection and final-D2 maps are reused across checkpoint trajectories.',
                     'Expanded semantic labels remain input-task/subtype truth-contrast proxies with UNKNOWN permitted.',
                     'One global confirmatory family is corrected in F6; interim p values are unadjusted.',
                     'A positive response correlation does not establish equal causal roles.',
                     'Cross-family prompts use calibration-selected formats: Qwen fourshot, Smol default, OLMo explicit. The target statement and row identity are shared, but prefix contexts differ; this is a calibrated-use comparison, not an identical-full-context test. Native character-span alignment does not remove the prefix confound.',
                     'All three pretrained families fall below the0.70 calibration competence threshold. D3 competence must be judged separately; low-competence failures cannot establish absence of functional conservation.']
    stress_path=RUN/'exploratory/stress_D3.json'
    if stress_path.exists():
        stress=read(stress_path)
        if stress.get('status')!='COMPLETE_DESCRIPTIVE' or stress.get('missing_models'):
            raise NotReady('F3 shortcut diagnostic is incomplete')
        if not stress.get('cuts_selected_after_D3_observed') or stress.get('primary_results_changed'):
            raise ValueError('Unexpected stress analysis scope')
        stress_rows=[];tiny={'adjacent_mismatch_present':[],'no_adjacent_mismatch':[]};counts={}
        for model,groups in stress['models'].items():
            for group,r in groups['syntax/local_cue'].items():
                label=('Local mismatch present' if group=='adjacent_mismatch_present' else 'No local mismatch')+f"\n(n={r['n_rows']} rows)"
                stress_rows.append({'model':model,'group':label,'value':r['accuracy_pair_balanced']})
                p['metrics'].append(metric('Posthoc syntax cue-stratum accuracy',r['accuracy_pair_balanced'],stress_path,
                    model=model,method=group,task='syntax',split='D3 exploratory',n=r['n_rows'],n_clusters=r['n_wrappers'],unit='fraction'))
                if model.startswith('seed'):tiny[group].append(r['accuracy_pair_balanced'])
                counts.setdefault(group,r['n_rows'])
                if counts[group]!=r['n_rows']:raise ValueError('Stress strata support differs across models')
        present=tiny['adjacent_mismatch_present'];absent=tiny['no_adjacent_mismatch']
        p['rationale']+=f" 사후 괄호 스트레스 분석에서 독립 학습 모델의 정확도는 인접 종류 불일치가 있는 pair 집합에서 {min(present):.1%}–{max(present):.1%}(n={counts['adjacent_mismatch_present']}), 없는 집합에서 {min(absent):.1%}–{max(absent):.1%}(n={counts['no_adjacent_mismatch']})였다. 작은 사후 부분집합과 내용 차이를 포함한 연관성이므로 인과적 shortcut 사용 증거는 아니지만, 전체 정확도 능력 gate만으로 재귀적·구조적 이해를 입증할 수 없음을 보여 준다. 수 비교·부정 과제의 측정과는 구분한다."
        p['figures'].append({'id':'posthoc_syntax_local_cue','kind':'heatmap',
            'title':'Posthoc D3 syntax accuracy by local-cue stratum','rows':stress_rows,
            'row':'model','column':'group','value':'value','vmin':0,'vmax':1,'percent':True,
            'unit':'Pair-balanced accuracy','source':rel(stress_path),'figsize':[10,6.5],
            'note':'Exploratory cuts chosen after D3; both true/false pair members retained. N counts rows. Unequal content and small n=26 stratum confound differences; no causal cue-use claim or confirmatory test.'})
        p['artifacts'] += [{'label':'Posthoc D3 shortcut stress measurements','path':rel(stress_path)},
                           {'label':'Stress analysis definitions and complete tables','path':'reports/followup-v2/STRESS_ANALYSIS.md'}]
        p['limitations'] += ['Overall syntax accuracy above the operational competence threshold does not prove recursive parsing or structural understanding. The posthoc no-adjacent-mismatch stratum is small and content-confounded; its gap is not a controlled causal effect.',
                             'Syntax shortcut findings do not substitute for separate construct validation of comparison, negation, or arithmetic. Frozen primary mappings, thresholds and tests are unchanged.']
    descriptive_path=path.parent/'competence_descriptive.json'
    if descriptive_path.exists():
        desc=read(descriptive_path)
        for r in desc['rows']:
            for key in ('activation','semantic','random','activation_minus_random','semantic_minus_activation'):
                p['metrics'].append(metric('Competence-qualified descriptive '+key,r[key],descriptive_path,
                  model_pair=r['cohort'],method=r['position'],task=r['task'],unit='Pearson or difference',n=r['eligible_pairs']))
        p['artifacts'].append({'label':'Competence-qualified descriptive task strata','path':rel(descriptive_path)})
    return p


def f5():
    path=RUN/'transfers/summary.json';m=read(path);config=read(ROOT/'configs/followup_v2.json')
    if m.get('status')!='COMPLETED':raise NotReady('Transfer experiment is incomplete')
    expected={f'seed{a}_to_seed{b}' for a,b in config['transplant']['directed_pairs']}
    if set(m['pairs'])!=expected:raise NotReady('Missing registered directed transfer pairs')
    p=base('F5','뉴런 이식과 선택적 보간 병합','D2에서 고정한 이식 정책이 D4 목표 과제와 부수 과제를 보존·개선하는가?')
    effect=m['aggregate_selected_minus_baseline']
    p['comparisons']=[comparison('D2-selected policy minus untouched target, aggregate target-task accuracy',effect,path,
                                 'One predeclared aggregate test; global BH pending F6; directed pairs not independent')]
    delta=[];accuracy=[];selected_count=0
    for pair,r in m['pairs'].items():
        policy_path=path.parent/pair/'policy.json';policy=read(policy_path)
        if not policy.get('frozen_before_D4_scoring'):raise ValueError('F5 policy must be persisted before D4 scoring')
        selected=r['policy']['selected'];selected_count+=int(selected is not None)
        baseline=r['d4_baseline_accuracy'];chosen=r['d4_conditions'][selected]['accuracy'] if selected else baseline
        stats=r['selected_minus_baseline'];delta.append({'label':pair,'value':stats['effect'],'ci':stats['bootstrap']['ci']})
        p['metrics'].append(metric('Selected policy target-task gain',stats['effect'],path,model_pair=pair,
                                  task=r['target_task'],unit='accuracy difference',ci=stats['bootstrap']['ci'],n_clusters=stats['n_clusters']))
        for condition,values in [('untouched',baseline),('D2-selected',chosen)]:
            for task,value in values.items():
                if isinstance(value,dict):value=value.get('accuracy')
                if value is None:continue
                accuracy.append({'model':pair+' / '+condition,'task':task,'value':value})
        p['artifacts'] += [{'label':pair+' frozen policy','path':rel(policy_path)},
                           {'label':pair+' summary','path':rel(policy_path.parent/'summary.json')}]
    p['rationale']=f"등록한 방향성 모델 쌍 {len(m['pairs'])}개의 D2 정책과 D4 평가를 완료했다. {selected_count}개 쌍에서 이식 정책을 선택했고 나머지는 미수정 모델을 유지했다. 주요 비교는 관측 모델들을 wrapper 안에서 함께 평균한 선택 정책 대 원래 모델의 차이이며, F6의 전역 다중검정 전에는 확증적 개선으로 판정하지 않는다."
    p['figures']=[{'id':'selected_policy_gain','kind':'interval','title':'D4 selected-policy gain by directed model pair',
                  'rows':delta,'xlabel':'Target-task accuracy difference','source':rel(path),
                  'note':'Pair intervals are descriptive; five pairs reuse models. The registered primary test averages pairs within wrappers.'},
                 {'id':'target_and_collateral_accuracy','kind':'heatmap','title':'D4 target and collateral-task accuracy',
                  'rows':accuracy,'row':'model','column':'task','value':'value','vmin':0,'vmax':1,'percent':True,
                  'source':rel(path),'unit':'Accuracy','note':'Only the D2-selected policy and untouched target are contrasted here; D4 does not choose a policy.'}]
    p['artifacts'].append({'label':'Aggregate transfer evidence','path':rel(path)})
    p['limitations']=['D2 jointly selects task, mapping, and interpolation weight; its gains are in-sample.',
                     'Random donors preserve target units/group size but not donor activation magnitude.',
                     'Native parameter interpolation does not establish circuit-preserving model merging.',
                     'Directed pairs reuse seeds; pair tests are descriptive and not five independent replications.']
    return p


def f4():
    path=RUN/'causal_alignment/summary.json';m=read(path)
    freeze_path=path.parent/'fit_manifest.json';frozen=read(freeze_path)
    if not m.get('full_protocol_complete') or m.get('n_evaluations')!=26:
        raise NotReady('F4 requires all26 pair/single-group evaluations')
    if frozen.get('status')!='D2_CAUSAL_MAPS_AND_WEIGHTS_FROZEN' or not frozen.get('full_protocol_complete') or frozen.get('test_data_used'):
        raise ValueError('F4 requires complete D2-only causal map and weight freeze')
    p=base('F4','단일·그룹 뉴런 인과 정렬과 dose-response',
           '독립 D4에서 의미·인과 결합 정렬이 의미 정렬보다 효과를 더 잘 예측하는가?')
    combined=[];semantic=[];weights=[];competence={};dose={};sources=[rel(path),rel(freeze_path)];eligible=0
    for item in m['evaluations']:
        ep=RUN/item['path'];e=read(ep)
        if hashlib.sha256(ep.read_bytes()).hexdigest()!=item['sha256']:raise ValueError('F4 evaluation source hash mismatch')
        if e.get('evaluation_split')!='D4' or e.get('fit_split')!='D2':raise ValueError('F4 split mismatch')
        sources.append(rel(ep));pair='_'.join(item['pair']);kind=item['unit_kind'];eligible+=len(item['competent_tasks'])
        for task,g in e['task_competence'].items():
            for which,name in zip(('model_a','model_b'),item['pair']):
                key=(name,task);value=g[which]['accuracy']
                if key in competence and competence[key]!=value:raise ValueError('Duplicated D4 competence evidence disagrees')
                competence[key]=value
        for location,methods in item['locations'].items():
            col=kind+'/'+location
            combined.append({'pair':pair,'condition':col,'value':methods['combined']['mean']})
            semantic.append({'pair':pair,'condition':col,'value':methods['semantic']['mean']})
            weights.append({'pair':pair,'condition':col,'value':item['selected_weights'][location]})
            for method,values in methods.items():
                p['metrics'].append(metric('D4 causal agreement',values['mean'],ep,model_pair=pair,
                        method=kind+'/'+location+'/'+method,split='D4',unit='Pearson',n_clusters=values['n_valid_wrappers']))
        for which,name in zip(('model_a','model_b'),item['pair']):
            observed=e['supplementary_dose_response'][which];key=(name,kind)
            if key in dose and dose[key]!=observed:raise ValueError('Repeated model dose diagnostic disagrees')
            dose[key]=observed
    for name,test in m['confirmatory_tests'].items():
        p['comparisons'].append(comparison(name,test,path,'Predeclared F4 family member; global BH pending F6'))
    contrasts=[]
    for cohort,stats in m['cohorts'].items():
        test=stats['tests']['combined_minus_semantic']
        if test.get('effect') is not None:
            contrasts.append({'label':cohort,'value':test['effect'],'ci':(test.get('bootstrap') or {}).get('ci')})
    p['figures']=[{'id':'combined_causal_agreement','kind':'heatmap','title':'D4 combined semantic-causal agreement',
                 'rows':combined,'row':'pair','column':'condition','value':'value','vmin':-1,'vmax':1,
                 'unit':'Within-task wrapper-equal Pearson','source':sources,'figsize':[11,8.1],
                 'note':'Primary evaluation uses zero/mean/patch only. Dose modes are supplementary; no trivial scale=1 identity enters matching.'},
                {'id':'semantic_causal_baseline','kind':'heatmap','title':'D4 semantic-only causal baseline',
                 'rows':semantic,'row':'pair','column':'condition','value':'value','vmin':-1,'vmax':1,
                 'unit':'Within-task wrapper-equal Pearson','source':sources,'figsize':[11,8.1],'show_in_readme':False},
                {'id':'combined_minus_semantic','kind':'interval','title':'D4 joint-wrapper combined minus semantic',
                 'rows':contrasts,'xlabel':'Causal Pearson difference;95% shared-wrapper CI','source':rel(path),
                 'note':'Observed pairs are retained jointly inside wrappers; global BH is deferred to F6.'},
                {'id':'d4_competence','kind':'heatmap','title':'D4 causal-evaluation task competence',
                 'rows':[{'model':name,'task':task,'value':value} for (name,task),value in sorted(competence.items())],
                 'row':'model','column':'task','value':'value','vmin':0,'vmax':1,'percent':True,
                 'unit':'Accuracy;chance=50%','source':sources,
                 'note':'D4 competence is measured separately from D3. Low competence is retained as a control, not interpreted as evidence against an unlearned function.'},
                {'id':'frozen_causal_weights','kind':'heatmap','title':'Causal weight selected on D2 validation wrappers',
                 'rows':weights,'row':'pair','column':'condition','value':'value','vmin':0,'vmax':1,
                 'unit':'Causal mixing weight','source':sources,'figsize':[11,8.1],'show_in_readme':False}]
    dose_rows={}
    for (name,kind),d in sorted(dose.items()):
        a=np.asarray(d['mean_absolute_effect'],float)
        if a.ndim!=3 or a.shape[1]!=2 or a.shape[2]!=len(d['mode_names']):raise ValueError('Unexpected dose diagnostic axes')
        averaged=a.mean(axis=0)
        for li,location in enumerate(('answer','span')):
            for mi,mode in enumerate(d['mode_names']):
                if mode.startswith('scale_'):
                    dose_rows.setdefault((kind,location),[]).append({'model':name,'scale':float(mode[6:]),'value':float(averaged[li,mi])})
        for label,key in [('Identity scale1 maximum effect','identity_scale_1_max_absolute_effect'),
                          ('Zero vs scale0 maximum discrepancy','zero_vs_scale_0_max_absolute_difference')]:
            p['metrics'].append(metric(label,d[key],path,model=name,method=kind,unit='log-likelihood margin'))
    for (kind,location),rows in dose_rows.items():
        p['figures'].append({'id':f'dose_{kind}_{location}','kind':'line',
             'title':f'D4 dose response: {kind} units at {location}', 'rows':rows,
             'x':'scale','y':'value','series':'model','xlabel':'Activation scale','ylabel':'Mean absolute margin effect',
             'source':sources,'show_in_readme':False,
             'note':'Descriptive mean over fixed units and examples; no uncertainty or model-population inference is attached. These dose modes never select the primary matching.'})
    p['rationale']=f"등록한 모델쌍·단위 종류26개에서 D4의 zero/mean/patch 인과 효과를 비교했다. 모델쌍×단위종류×과제 셀104개 중 {eligible}개가 양쪽 모델의 과제 능력 기준을 충족했다. 단일 뉴런과 그룹을 분리하며 dose-response는 주 정렬과 별도의 기술 진단으로 보존한다. 전역 다중검정과 전체 판정은 F6에서 완료한다. 이종 계열은 같은 목표 문장에도 서로 다른 calibration 선택 접두 맥락을 사용한다. 위치 정렬은 이 맥락 차이를 제거하지 않으며, 낮은 D4 능력에서는 기능 보존의 부재를 판정할 수 없다."
    p['competence_gate']={'rule':'Both models accuracy>=0.70 and Wilson95 lower>0.50 on D4',
                          'passed_pair_kind_task_cells':eligible,'total_pair_kind_task_cells':104,
                          'role':'Reporting strata only; never refit or select mappings using D4'}
    p['artifacts']=[{'label':'Causal analysis summary','path':rel(path)},
                    {'label':'D2 causal freeze manifest','path':rel(freeze_path)}]
    p['limitations']=['All model pairs sharing a seed are dependent; inference is conditional on the observed model collection.',
                     'Groups contain fixed D1 candidates; the results do not imply full circuit recovery.',
                     'Zero/mean/patch can alter activation distributions; dose response is supplementary.',
                     'Exact-zero or constant effects are not evidence of causal agreement.',
                     'No D4 outcome changes the frozen maps or D2-selected mixing weights.',
                     'Cross-family causal comparisons retain each calibration-selected prompt format: Qwen fourshot, Smol default, OLMo explicit. The same target statements have different prefix contexts. Character-span alignment cannot remove this context confound; conclusions concern calibrated-use conditions, not identical full inputs.',
                     'Pretrained calibration competence is below0.70. D4 competence is evaluated independently; low competence cannot falsify conservation of a function not established in the tested model.']
    return p


def prepared_stage(stage):
    """Accept a source-produced report payload only with explicit completion.

    Alignment/global runners may emit this small adapter artifact while their
    full numerical schemas remain available through its source references.
    """
    path=RUN/'report_inputs'/f'{stage}.json';payload=read(path)
    if payload.get('status') not in ('MEASURED','COMPLETE','PASS','NOT_APPLICABLE'):
        raise NotReady(f'{stage} report inputs are incomplete')
    if payload.get('id')!=stage:raise ValueError('Prepared report stage mismatch')
    payload.setdefault('artifacts',[]).append({'label':'Source report adapter','path':rel(path)})
    return payload

BUILDERS={'F1':f1,'F2':f2,'F3':f3,'F4':f4,
          'F5':f5,'F6':lambda:prepared_stage('F6')}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=list(BUILDERS));parser.add_argument('--render',action='store_true');args=parser.parse_args()
    try:payload=BUILDERS[args.stage]()
    except NotReady as error:
        print(json.dumps({'stage':args.stage,'status':'NOT_READY','reason':str(error)},ensure_ascii=False));return 2
    out=RUN/'stages'/f'{args.stage}.json';out.parent.mkdir(parents=True,exist_ok=True)
    text=json.dumps(payload,indent=2,ensure_ascii=False,allow_nan=False)+'\n'
    temporary=out.with_suffix('.json.tmp');temporary.write_text(text);temporary.replace(out)
    if args.render:
        from src.followup_reporting import render_followup_reports
        report=render_followup_reports(ROOT,args.stage)
    else:report=None
    print(json.dumps({'stage':args.stage,'status':payload['status'],'path':rel(out),'report':report},ensure_ascii=False))
    return 0

if __name__=='__main__':raise SystemExit(main())
