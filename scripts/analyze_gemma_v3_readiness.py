#!/usr/bin/env python3
"""CPU-only fixed-renderer readiness summary and independent raw-score replay.

No model imports, no fitting, no new data, no confirmatory p-values. Every
bootstrap resamples whole provenance clusters and keeps all within-family
variants, languages and models paired. Shared-reference clusters use a ratio
estimator retaining the original family-weighted point estimand.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.gemma_v3_readiness import (audit_source_catalog,validate_readiness,sha_file,read_json)
from src.gemma_v3_data import CONCEPTS,LANGUAGES
MODELS=('gemma','qwen')
N_BOOT=10000
BASE_SEED=20261104
META_KEYS=('id','family_id','lineage_id','concept','language','semantic_state','answer_code','lexical','correct_index','source_cluster_id','source_reference_cluster_id')


def seed_for(concept,axis):
    return int.from_bytes(hashlib.sha256(f'{BASE_SEED}/{concept}/{axis}'.encode()).digest()[:8],'little')


def threshold(accuracy,lower):return bool(accuracy>=.75 and lower>.50)


def load_evidence(root):
    root=Path(root).resolve();run=root/'results/followup-v3-gemma-map'
    paths={'data':'data/followup-v3-gemma-map/readiness.jsonl','manifest':'data/followup-v3-gemma-map/readiness_manifest.json',
           'source_catalog':'reports/v3/Rsourcecatalogv2.json','prompt_lock':'configs/gemma_v3_prompt_lock.json',
           'amendment':'results/followup-v3-gemma-map/readiness_conditional_amendment.json'}
    paths.update({name:f'results/followup-v3-gemma-map/readiness_scores/{name}.json' for name in MODELS})
    for path in paths.values():
        if not (root/path).is_file():raise RuntimeError('Complete paired readiness evidence required: '+path)
    hashes={key:sha_file(root/rel) for key,rel in paths.items()}
    manifest=read_json(root/paths['manifest']);lock=read_json(root/paths['prompt_lock']);amend=read_json(root/paths['amendment'])
    for name,key in [('data','data_sha256'),('source_catalog','source_catalog_sha256'),('prompt_lock','prompt_lock_sha256'),('amendment','amendment_sha256')]:
        if hashes[name]!=manifest[key]:raise ValueError('Frozen readiness checksum mismatch: '+name)
    if sha_file(root/'src/gemma_v3_readiness.py')!=manifest['source_code_sha256']:raise ValueError('Readiness generator changed after freeze')
    if lock['status']!='FROZEN_BEFORE_READINESS' or amend['conditional_capability_only'] is not True or amend['strict_template_generalization_passed'] is not False or amend['test_opened'] is not False:raise ValueError('Conditional amendment or prompt lock mismatch')
    if amend['thresholds_unchanged']!={'accuracy':.75,'descriptive_source_cluster_CI_lower':.5}:raise ValueError('Original capability thresholds changed')
    records=[json.loads(line) for line in (root/paths['data']).read_text().splitlines()]
    source_audit=audit_source_catalog(read_json(root/paths['source_catalog']),root)
    if source_audit!=manifest['source_audit']:raise ValueError('Source lineage audit changed')
    if validate_readiness(records,source_audit,lock['prefix'])!=manifest['validation']:raise ValueError('Readiness validation manifest changed')
    expected={r['id']:r for r in records};raw={};predictions={};ties={}
    for name in MODELS:
        payload=read_json(root/paths[name]);raw[name]=payload
        if payload['model']!=name or payload['status']!='MEASURED_CONDITIONAL_DIAGNOSTIC':raise ValueError('Model/status mismatch')
        if payload['data_sha256']!=hashes['data'] or payload['amendment_sha256']!=hashes['amendment'] or payload['provenance']['prompt_lock_sha256']!=hashes['prompt_lock']:raise ValueError('Scoring source mismatch')
        measured=payload['rows']
        if len(measured)!=len(records) or len({r['id'] for r in measured})!=len(records) or {r['id'] for r in measured}!=set(expected):raise ValueError('Missing, duplicated or unexpected score rows')
        table={r['id']:r for r in measured};ordered=[table[r['id']] for r in records]
        scores=np.array([r['scores'] for r in ordered],float)
        if scores.shape!=(len(records),2) or not np.isfinite(scores).all() or np.any(scores>1e-7):raise ValueError('Invalid full-continuation logP scores')
        predicted=scores.argmax(axis=1);correct=predicted==[r['correct_index'] for r in records]
        for row,pred,ok in zip(ordered,predicted,correct):
            if any(row[k]!=expected[row['id']][k] for k in META_KEYS):raise ValueError('Measured metadata differs from frozen record')
            if row['predicted_index']!=int(pred) or row['correct'] is not bool(ok):raise ValueError('Saved prediction/accuracy does not replay')
        checks=payload['batch_checks']
        if len(checks)!=8 or any(not c['passed'] or not np.isfinite(c['absolute_score_error']) or not 0<=c['absolute_score_error']<=.001 for c in checks):raise ValueError('Batch/single numeric checks failed')
        predictions[name]=correct.astype(float)
        ties[name]=dict(exact_ties=int(np.sum(scores[:,0]==scores[:,1])),absolute_margin_below_0_002=int(np.sum(np.abs(scores[:,0]-scores[:,1])<.002)),
                        note='Margin diagnostic only; no rows dropped or labels changed. Eight batch checks do not establish a universal error bound.')
    return records,raw,predictions,manifest,paths,hashes,ties


def family_panel(records,predictions):
    families=sorted({r['family_id'] for r in records});meta=[];panel=[]
    for family in families:
        indices=[i for i,r in enumerate(records) if r['family_id']==family];items=[records[i] for i in indices]
        if len(indices)!=16 or len({(r['concept'],r['source_cluster_id'],r['source_reference_cluster_id']) for r in items})!=1:raise ValueError('Invalid family/cluster partition')
        values=np.empty((len(MODELS),len(LANGUAGES)))
        for li,lang in enumerate(LANGUAGES):
            selected=[i for i in indices if records[i]['language']==lang]
            if len(selected)!=8:raise ValueError('Eight variants per family/language required')
            for mi,name in enumerate(MODELS):values[mi,li]=predictions[name][selected].mean()
        panel.append(values);meta.append({k:items[0][k] for k in ('family_id','concept','source_cluster_id','source_reference_cluster_id')})
    return np.asarray(panel),meta


def cluster_draws(panel,meta,concept,axis,n_boot=N_BOOT):
    indices=[i for i,r in enumerate(meta) if r['concept']==concept]
    keys=sorted({meta[i][axis] for i in indices})
    if any(len({r['concept'] for r in meta if r[axis]==key})!=1 for key in keys):raise ValueError('Cross-concept cluster requires a different prespecified joint design')
    sums=[];sizes=[]
    for key in keys:
        take=[i for i in indices if meta[i][axis]==key]
        sums.append(panel[take].sum(axis=0));sizes.append(len(take))
    sums=np.asarray(sums);sizes=np.asarray(sizes)
    draws=np.random.default_rng(seed_for(concept,axis)).integers(0,len(keys),size=(n_boot,len(keys)))
    values=sums[draws].sum(axis=1)/sizes[draws].sum(axis=1)[:,None,None]
    return values,keys,sizes.tolist()


def summarize(records,predictions,manifest,paths,hashes,ties,n_boot=N_BOOT):
    panel,meta=family_panel(records,predictions);rows=[];models={};draws_by_axis={}
    for axis in ('source_cluster_id','source_reference_cluster_id'):
        draws_by_axis[axis]={c:cluster_draws(panel,meta,c,axis,n_boot) for c in CONCEPTS}
    for mi,model in enumerate(MODELS):
        model_rows=[]
        for concept in CONCEPTS:
            for li,language in enumerate(LANGUAGES):
                selected=[i for i,r in enumerate(records) if r['concept']==concept and r['language']==language]
                correct=int(predictions[model][selected].sum());accuracy=correct/len(selected)
                primary,keys,sizes=draws_by_axis['source_cluster_id'][concept]
                secondary,refs,ref_sizes=draws_by_axis['source_reference_cluster_id'][concept]
                ci=np.quantile(primary[:,mi,li],[.025,.975]).tolist();ci_ref=np.quantile(secondary[:,mi,li],[.025,.975]).tolist()
                row=dict(model=model,concept=concept,language=language,accuracy=accuracy,correct=correct,n_rows=len(selected),
                         n_families=len({records[i]['family_id'] for i in selected}),
                         source_cluster_bootstrap=dict(ci95=ci,n_clusters=len(keys),families_per_cluster=sizes),
                         shared_reference_cluster_sensitivity=dict(ci95=ci_ref,n_clusters=len(refs),families_per_cluster=ref_sizes,
                                                                   caution='Very few clusters; interval is descriptive and potentially unstable' if len(refs)<10 else 'Conditional descriptive sensitivity'),
                         conditional_threshold_met=threshold(accuracy,ci[0]),shared_reference_threshold_met=threshold(accuracy,ci_ref[0]),
                         original_confirmatory_scientific_eligibility=False)
                rows.append(row);model_rows.append(row)
        main=np.mean([draws_by_axis['source_cluster_id'][c][0][:,mi].mean(axis=1) for c in CONCEPTS],axis=0)
        refs=np.mean([draws_by_axis['source_reference_cluster_id'][c][0][:,mi].mean(axis=1) for c in CONCEPTS],axis=0)
        models[model]=dict(accuracy=float(predictions[model].mean()),correct=int(predictions[model].sum()),n_rows=len(records),
                           source_ci95=np.quantile(main,[.025,.975]).tolist(),shared_reference_ci95=np.quantile(refs,[.025,.975]).tolist(),
                           conditional_cells_meeting_threshold=sum(r['conditional_threshold_met'] for r in model_rows),n_cells=len(model_rows),score_margin_diagnostic=ties[model])
    paired=[]
    for concept in CONCEPTS:
        for language in LANGUAGES:
            cells=[r for r in rows if r['concept']==concept and r['language']==language]
            paired.append(dict(concept=concept,language=language,both_models_conditional_threshold_met=all(r['conditional_threshold_met'] for r in cells),
                               both_models_shared_reference_threshold_met=all(r['shared_reference_threshold_met'] for r in cells),original_confirmatory_scientific_eligibility=False))
    return dict(status='MEASURED_CONDITIONAL_READINESS_SUMMARY',models=models,rows=rows,paired_cells=paired,
                paired_cells_meeting_conditional_threshold=sum(r['both_models_conditional_threshold_met'] for r in paired),
                bootstrap=dict(replicates=n_boot,base_seed=BASE_SEED,seed_derivation='SHA256(base_seed/concept/axis), first8bytes little-endian',
                               primary_axis='source_cluster_id',secondary_axis='source_reference_cluster_id',
                               scheme='Stratify by concept; resample whole clusters with replacement, retaining all families/variants/languages/models jointly.',
                               point_estimand='Equal family mean inside concept/language; overall equal concept/language mean.',
                               unequal_cluster_rule='Sum resampled cluster family totals / sum resampled family counts, not unweighted cluster means.',
                               interval='Descriptive percentile95%; conditional fixed renderer/source frame/model collection; not a simultaneous CI.'),
                thresholds=dict(accuracy_min=.75,ci_lower_strictly_greater_than=.5),source_paths=paths,source_sha256=hashes,
                analysis_script_sha256=sha_file(__file__),strict_template_generalization_gate='FAIL_SHARED_RENDERERS',
                original_confirmatory_claims_evaluable=False,test_opened=False,ood_opened=False,
                actual_source_clusters=manifest['source_audit']['source_components'],actual_shared_reference_clusters=manifest['source_audit']['shared_reference_sensitivity_components'],
                actual_renderer_lineages=4,limitations=['No new hypothesis tests or changes to the four-claim family.',
                    'Conditional capability flags do not pass the original template/generalization/power gate.',
                    'Convenience source records and shared institutions may remain dependent beyond recorded graph edges.',
                    'Sixteen variants are repeated measurements, not sixteen independent sources.',
                    'A passing controlled-record task does not establish broad semantic or natural-language competence.'])



def response_diagnostics(records,raw):
    """Deterministic code/truth diagnostics; no fitting, exclusions or p-values."""
    result={}
    for model in MODELS:
        lookup={r['id']:r for r in raw[model]['rows']};values=[]
        for r in records:
            predicted=0 if lookup[r['id']]['scores'][0]>=lookup[r['id']]['scores'][1] else 1
            letter=r['completions'][predicted].split('.',1)[0].strip()
            if letter not in ('A','B'):raise ValueError('Unexpected canonical answer code')
            values.append(dict(r,predicted=predicted,predicted_letter=letter,is_correct=predicted==r['correct_index']))
        def tabulate(items):
            letters=Counter(x['predicted_letter'] for x in items)
            return dict(n=len(items),accuracy=sum(x['is_correct'] for x in items)/len(items),
                        predicted_answer_code_counts={k:letters[k] for k in ('A','B')},
                        predicted_answer_code_frequencies={k:letters[k]/len(items) for k in ('A','B')},
                        predicted_proposition_counts={name:sum(x['predicted']==k for x in items) for k,name in enumerate(('statement_true','statement_false'))})
        pooled=[];by_concept=[]
        for state,code,language in __import__('itertools').product((0,1),(0,1),LANGUAGES):
            selected=[v for v in values if (v['semantic_state'],v['answer_code'],v['language'])==(state,code,language)]
            metadata=dict(semantic_state=state,answer_code=code,language=language)
            pooled.append(dict(metadata,**tabulate(selected)))
            for concept in CONCEPTS:
                by_concept.append(dict(metadata,concept=concept,**tabulate([v for v in selected if v['concept']==concept])))
        table={(v['family_id'],v['semantic_state'],v['lexical'],v['answer_code'],v['language']):v for v in values}
        code_pairs=[];truth_pairs=[];lex_pairs=[]
        for v in values:
            f,t,l,c,lang=v['family_id'],v['semantic_state'],v['lexical'],v['answer_code'],v['language']
            if c==0:code_pairs.append((v,table[f,t,l,1,lang]))
            if t==0:truth_pairs.append((v,table[f,1,l,c,lang]))
            if l==0:lex_pairs.append((v,table[f,t,1,c,lang]))
        result[model]=dict(overall=tabulate(values),truth_code_language_cells=pooled,concept_truth_code_language_cells=by_concept,
                           answer_code_reversal=dict(n_pairs=len(code_pairs),semantic_prediction_consistency_rate=float(np.mean([a['predicted']==b['predicted'] for a,b in code_pairs])),
                                                     same_output_letter_rate=float(np.mean([a['predicted_letter']==b['predicted_letter'] for a,b in code_pairs])),
                                                     both_correct_rate=float(np.mean([a['is_correct'] and b['is_correct'] for a,b in code_pairs]))),
                           semantic_counterfactual=dict(n_pairs=len(truth_pairs),prediction_flip_rate=float(np.mean([a['predicted']!=b['predicted'] for a,b in truth_pairs])),
                                                        both_correct_rate=float(np.mean([a['is_correct'] and b['is_correct'] for a,b in truth_pairs]))),
                           lexical_rephrasing=dict(n_pairs=len(lex_pairs),semantic_prediction_consistency_rate=float(np.mean([a['predicted']==b['predicted'] for a,b in lex_pairs]))),
                           interpretation='Observed response-pattern diagnostics only; no causal mechanism attribution, general reasoning-inability claim, new tuning or hypothesis test.')
    return result


def replay_independently(root,summary):
    """Separate scalar/raw path: no stored correct flags or summary bootstrap helper."""
    root=Path(root);checks=0
    if summary['analysis_script_sha256']!=sha_file(__file__) or summary['bootstrap']['replicates']!=N_BOOT or summary['thresholds']!={'accuracy_min':.75,'ci_lower_strictly_greater_than':.5}:raise ValueError('Analysis settings or source changed')
    for key,path in summary['source_paths'].items():
        if sha_file(root/path)!=summary['source_sha256'][key]:raise ValueError('Replay source hash mismatch')
        checks+=1
    canonical=[json.loads(line) for line in (root/summary['source_paths']['data']).read_text().splitlines()]
    family_records={}
    for row in canonical:family_records.setdefault(row['family_id'],[]).append(row)
    fractions={};raw_tables={}
    for model in MODELS:
        measured=read_json(root/summary['source_paths'][model])['rows'];lookup={r['id']:r for r in measured};raw_tables[model]=lookup
        for family,items in family_records.items():
            for lang in LANGUAGES:
                values=[]
                for r in items:
                    if r['language']!=lang:continue
                    scores=lookup[r['id']]['scores']
                    predicted=0 if scores[0]>=scores[1] else 1
                    ok=int(predicted==r['correct_index'])
                    if lookup[r['id']]['predicted_index']!=predicted or bool(lookup[r['id']]['correct'])!=bool(ok):raise ValueError('Raw scalar argmax replay mismatch')
                    values.append(ok);checks+=1
                fractions[model,family,lang]=sum(values)/len(values)
    distributions={}
    for axis in ('source_cluster_id','source_reference_cluster_id'):
        for concept in CONCEPTS:
            families=sorted(f for f,items in family_records.items() if items[0]['concept']==concept)
            keys=sorted({family_records[f][0][axis] for f in families})
            members=[[f for f in families if family_records[f][0][axis]==key] for key in keys]
            choices=np.random.default_rng(seed_for(concept,axis)).integers(0,len(keys),size=(summary['bootstrap']['replicates'],len(keys)))
            # Independent count-matrix weighting instead of indexed cluster sums.
            multiplicities=np.array([np.bincount(choice,minlength=len(keys)) for choice in choices],float)
            denominator=multiplicities@np.array([len(group) for group in members],float)
            for model in MODELS:
                for lang in LANGUAGES:
                    totals=np.array([sum(fractions[model,f,lang] for f in group) for group in members])
                    distributions[axis,concept,model,lang]=(multiplicities@totals)/denominator
    for row in summary['rows']:
        model,concept,lang=row['model'],row['concept'],row['language']
        families=[f for f,items in family_records.items() if items[0]['concept']==concept]
        point=sum(fractions[model,f,lang] for f in families)/len(families)
        if not np.isclose(point,row['accuracy'],rtol=0,atol=1e-15) or row['correct']!=round(point*row['n_rows']):raise ValueError('Independent accuracy replay mismatch')
        for axis,field,flag in [('source_cluster_id','source_cluster_bootstrap','conditional_threshold_met'),('source_reference_cluster_id','shared_reference_cluster_sensitivity','shared_reference_threshold_met')]:
            ci=np.quantile(distributions[axis,concept,model,lang],[.025,.975])
            if not np.allclose(ci,row[field]['ci95'],rtol=0,atol=1e-12) or bool(point>=.75 and ci[0]>.5)!=row[flag]:raise ValueError('Independent bootstrap/threshold replay mismatch')
            checks+=1
    for model in MODELS:
        point=sum(v for (m,_,_),v in fractions.items() if m==model)/(len(family_records)*len(LANGUAGES))
        if not np.isclose(point,summary['models'][model]['accuracy'],atol=1e-15):raise ValueError('Overall accuracy replay mismatch')
        for axis,field in [('source_cluster_id','source_ci95'),('source_reference_cluster_id','shared_reference_ci95')]:
            overall=np.mean([distributions[axis,c,model,l] for c in CONCEPTS for l in LANGUAGES],axis=0)
            if not np.allclose(np.quantile(overall,[.025,.975]),summary['models'][model][field],atol=1e-12,rtol=0):raise ValueError('Overall bootstrap replay mismatch')
            checks+=1
    for model,diagnostics in summary['response_diagnostics'].items():
        for cell in diagnostics['truth_code_language_cells']+diagnostics['concept_truth_code_language_cells']:
            take=[r for r in canonical if all(r[k]==cell[k] for k in ('semantic_state','answer_code','language')) and ('concept' not in cell or r['concept']==cell['concept'])]
            codes={'A':0,'B':0};success=0;prop=[0,0]
            for r in take:
                scores=raw_tables[model][r['id']]['scores'];pred=0 if scores[0]>=scores[1] else 1
                codes[r['completions'][pred].split('.',1)[0].strip()]+=1;success+=int(pred==r['correct_index']);prop[pred]+=1
            if codes!=cell['predicted_answer_code_counts'] or len(take)!=cell['n'] or success/len(take)!=cell['accuracy'] or prop!=list(cell['predicted_proposition_counts'].values()):raise ValueError('Independent code/truth contingency replay mismatch')
            checks+=1
    for model,diagnostics in summary['response_diagnostics'].items():
        table={}
        for r in canonical:
            scores=raw_tables[model][r['id']]['scores'];pred=0 if scores[0]>=scores[1] else 1
            table[(r['family_id'],r['semantic_state'],r['lexical'],r['answer_code'],r['language'])]=(pred,r['completions'][pred].split('.',1)[0].strip(),pred==r['correct_index'])
        for axis,field in [(3,'answer_code_reversal'),(1,'semantic_counterfactual'),(2,'lexical_rephrasing')]:
            pairs=[]
            for key,a in table.items():
                if key[axis]!=0:continue
                other=list(key);other[axis]=1;pairs.append((a,table[tuple(other)]))
            expected={'n_pairs':len(pairs)}
            if axis in (2,3):expected['semantic_prediction_consistency_rate']=sum(a[0]==b[0] for a,b in pairs)/len(pairs)
            if axis==3:expected['same_output_letter_rate']=sum(a[1]==b[1] for a,b in pairs)/len(pairs)
            if axis==1:expected['prediction_flip_rate']=sum(a[0]!=b[0] for a,b in pairs)/len(pairs)
            if axis in (1,3):expected['both_correct_rate']=sum(a[2] and b[2] for a,b in pairs)/len(pairs)
            if expected!=diagnostics[field]:raise ValueError('Independent paired diagnostic replay mismatch')
            checks+=1
    for cell in summary['paired_cells']:
        subset=[r for r in summary['rows'] if r['concept']==cell['concept'] and r['language']==cell['language']]
        if cell['both_models_conditional_threshold_met']!=all(r['conditional_threshold_met'] for r in subset) or cell['both_models_shared_reference_threshold_met']!=all(r['shared_reference_threshold_met'] for r in subset):raise ValueError('Paired conditional flags mismatch')
    if summary['paired_cells_meeting_conditional_threshold']!=sum(r['both_models_conditional_threshold_met'] for r in summary['paired_cells']):raise ValueError('Paired cell count mismatch')
    if summary['strict_template_generalization_gate']!='FAIL_SHARED_RENDERERS' or summary['original_confirmatory_claims_evaluable'] is not False or summary['test_opened'] or summary['ood_opened']:raise ValueError('Readiness interpretation changed')
    return dict(status='PASS',model_weights_loaded=False,raw_prediction_rows_replayed=len(canonical)*len(MODELS),
                full_continuation_scores_replayed=len(canonical)*len(MODELS)*2,cell_intervals_replayed=len(summary['rows'])*2,
                bootstrap_replicates=summary['bootstrap']['replicates'],checks_passed=checks,source_sha256=summary['source_sha256'],
                analysis_script_sha256=sha_file(__file__),
                independent_replay_method='Scalar argmax from saved logP and frozen answer index; separate family grouping and count-matrix cluster bootstrap.',
                scope='Weights-free numerical replay of stored measurements; no claim of rerunning model inference or historical execution chronology.')


def save_once(path,value):
    path=Path(path);payload=json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n'
    if path.exists() and path.read_text()!=payload:raise FileExistsError('Refusing to replace readiness analysis evidence: '+str(path))
    path.parent.mkdir(parents=True,exist_ok=True)
    if not path.exists():path.write_text(payload)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,default=ROOT);parser.add_argument('--replay-only',action='store_true');args=parser.parse_args()
    run=args.root/'results/followup-v3-gemma-map';summary_path=run/'readiness_summary.json'
    records,raw,predictions,manifest,paths,hashes,ties=load_evidence(args.root)
    if args.replay_only:summary=read_json(summary_path)
    else:
        summary=summarize(records,predictions,manifest,paths,hashes,ties)
        summary['response_diagnostics']=response_diagnostics(records,raw)
    audit=replay_independently(args.root,summary)
    if not args.replay_only:save_once(summary_path,summary)
    audit['summary_sha256']=sha_file(summary_path);save_once(run/'readiness_replay_audit.json',audit)
    print(json.dumps({'status':summary['status'],'models':summary['models'],'paired_cells_meeting_threshold':summary['paired_cells_meeting_conditional_threshold'],'audit':audit['status']},ensure_ascii=False))


if __name__=='__main__':main()
