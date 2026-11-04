"""CPU-only final report adapter from complete, audited followup-v2 evidence.

This never runs models, modifies primary measurements, or invents absent results.
Run with --render to refresh F6 and the derived reports after all evidence exists.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.build_followup_stages import RUN, MODELS, NotReady, read, rel, base, metric, comparison, add_causal_competence, add_causal_activation_baselines


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise NotReady(message)


def source_entry(path, label):
    return {'label': label, 'path': rel(path)}


def runtime_accounting(hard, transfers):
    entries = []
    def add(path, category, key='elapsed_seconds', data=None):
        data = read(path) if data is None else data
        value = data.get(key)
        if not isinstance(value, (float, int)) or value < 0:
            raise ValueError(f'Invalid saved elapsed time: {path}')
        entries.append({'category': category, 'seconds': value, 'source': rel(path)})
    add(RUN/'training/runtime.json', 'Training', 'seconds')
    for model in MODELS:
        add(RUN/'calibration'/model/'summary.json', 'Calibration')
    runtime_paths = sorted((RUN/'runtime').glob('*.json'))
    require(bool(runtime_paths), 'No stage runtime receipts')
    for path in runtime_paths:
        category = path.stem.split('_')[0]
        add(path, category, 'seconds')
    add(RUN/'positive_control/summary.json', 'Permutation control')
    for pair, values in transfers['pairs'].items():
        add(RUN/'transfers'/pair/'summary.json', 'Transfer', data=values)
    for name, values in hard['evaluations'].items():
        add(RUN/'hard_stress'/name/'summary.json', 'Hard stress', data=values)
    totals = {}
    for entry in entries:
        totals[entry['category']] = totals.get(entry['category'], 0.) + entry['seconds']
    return {'entries': entries, 'category_seconds': totals, 'total_seconds': sum(totals.values()),
            'scope': 'Sum of saved serial model-stage wall intervals, including CPU/IO/transfer overhead. An upper wall-duration accounting for recorded GPU-bearing stages, not GPU utilization, active kernel time, or complete project elapsed time. CPU statistical analysis and reporting are excluded. Training is counted once via aggregate runtime; its per-seed manifests are not added again.'}


def build():
    global_path = RUN/'statistics/global_tests.json'
    audit_path = RUN/'final_audit.json'
    hard_path = RUN/'hard_stress/summary.json'
    diagnostics_path = RUN/'exploratory_causal_diagnostics/summary.json'
    transfer_path = RUN/'transfers/summary.json'
    proxy_path = RUN/'exploratory_proxy_ablation/summary.json'
    dependence_path = RUN/'statistics/dependence_sensitivity.json'
    review_path = RUN/'scientific_review.json'
    global_stats, audit, hard, diagnostics, transfers, proxy, dependence = [read(p) for p in
        (global_path, audit_path, hard_path, diagnostics_path, transfer_path, proxy_path, dependence_path)]
    require(global_stats.get('family_size') == 110 and len(global_stats.get('tests', {})) == 110,
            'Final reporting requires the complete110-member global family')
    require(dependence.get('family_size') == 110 and len(dependence.get('tests', {})) == 110
            and dependence.get('source_sha256') == digest(global_path)
            and dependence.get('independent_bh_verification', {}).get('passed')
            and dependence.get('primary_results_changed') is False
            and dependence.get('additional_hypotheses') == 0,
            'Complete, unchanged-family dependence sensitivity is required')
    require((ROOT/'reports/followup-v2/DEPENDENCE_SENSITIVITY.md').is_file(),
            'Dependence sensitivity source report missing')
    review = read(review_path)
    allowed_verdicts = {'SUPPORTED', 'NOT SUPPORTED', 'INCONCLUSIVE', 'NOT_APPLICABLE'}
    require(review.get('status') == 'REVIEWED' and len(review.get('questions', [])) == 4
            and review.get('overall_verdict') in allowed_verdicts,
            'Four completed scientific-review answers and overall verdict are required')
    for answer in review['questions']:
        if not all(answer.get(key) for key in ('id', 'question', 'rationale', 'scope', 'evidence')):
            raise ValueError('Scientific review answer needs question, rationale, scope and evidence')
        if answer.get('verdict') not in allowed_verdicts:
            raise ValueError('Scientific review contains invalid verdict')
        for source in answer['evidence']:
            if not isinstance(source, str) or not (ROOT/source).is_file():
                raise ValueError('Scientific review references absent evidence: '+str(source))
    require(audit.get('status') == 'PASS_COMPLETE', 'Final audit is not PASS_COMPLETE')
    replay = audit.get('replay', {})
    require(replay.get('status') in ('COMPLETE', 'PASS_COMPLETE') and replay.get('complete', True)
            and not replay.get('errors') and replay.get('exit_code', 0) == 0,
            'Primary replay has not passed completely')
    tests = audit.get('tests', {})
    require(isinstance(tests.get('passed'), int) and tests['passed'] > 0 and not tests.get('failed', 0) and not tests.get('errors', 0),
            'Full pytest result count absent or failing')
    for stage in range(6):
        snap = read(RUN/'stages'/f'F{stage}.json')
        require(snap.get('status') in ('MEASURED', 'COMPLETE', 'PASS'), f'F{stage} not measured')
    require(hard.get('status') == 'COMPLETE_EXPLORATORY' and hard.get('n_evaluations') == 18
            and len(hard.get('evaluations', {})) == 18, 'Hard-stress sweep incomplete')
    require(diagnostics.get('full_protocol_complete') and diagnostics.get('n_evaluations') == 26,
            'Causal answer-bias diagnostics incomplete')
    require(diagnostics.get('excluded_from_confirmatory_family') and not diagnostics.get('maps_refitted'),
            'Causal diagnostics scope disagrees with frozen primary design')
    require(transfers.get('status') == 'COMPLETED' and len(transfers.get('pairs', {})) == 5,
            'Transfer evaluations incomplete')
    require(proxy.get('full_protocol_complete') and proxy.get('n_comparisons') == 26
            and proxy.get('excluded_from_confirmatory_family'), 'Matched proxy ablation incomplete')
    p = base('F6', '전역 보정·재현 검증과 최종 연구 판정',
             '원래 결과를 보존한 후속 측정에서 어떤 대응과 한계를 확인했는가?')
    p['verdict'] = review['overall_verdict']
    p['scientific_review'] = review
    p['artifacts'] = [source_entry(path, label) for path, label in (
        (global_path, 'One global110-test BH family'), (audit_path, 'Final test and replay audit'),
        (hard_path, 'Independent frozen hard-case exploratory evaluation'),
        (diagnostics_path, 'Frozen-map causal answer-orientation diagnostics'),
        (transfer_path, 'Completed transfer experiments'), (proxy_path, 'Matched four-dimensional versus expanded proxy ablation'),
        (dependence_path, 'Posthoc BH/BY dependence sensitivity'),
        (review_path, 'Reviewed answers to the four scientific questions'))]
    for answer in review['questions']:
        p['artifacts'] += [{'label': answer['id']+' reviewed evidence', 'path': source}
                           for source in answer['evidence']]
    p['artifacts'].append({'label': 'Dependence sensitivity methods, identities and limitations',
                           'path': 'reports/followup-v2/DEPENDENCE_SENSITIVITY.md'})
    rejected = dependence['rejections']
    p['dependence_sensitivity'] = {
        'summary': f"같은110개 원래 p값의 사후 민감도 분석에서 q<0.05 기각 수는 주 분석 BH {rejected['bh']['count']}개, BY {rejected['by']['count']}개였다. BH 원래 값은 SciPy 독립 재계산과 일치했다. BY는 유효한 p값 사이의 임의 의존성에 대한 더 보수적인 보정이며, 기존 BH 결과·가설 수·p값을 바꾸지 않았다. 기각 수는 기능 보존 가설의 지지 수가 아니다. BY도 잘못된 p값, wrapper sign-flip의 교환가능성·대칭성 위반, 낮은 과제 능력 또는 construct confound를 고치지 않는다.",
        'reference': dependence['reference'], 'report': 'reports/followup-v2/DEPENDENCE_SENSITIVITY.md',
        'source': rel(dependence_path)}
    for method in ('bh', 'by', 'bh_only'):
        p['metrics'].append(metric('Posthoc dependence sensitivity rejection count', rejected[method]['count'],
                                  dependence_path, method=method, unit='hypotheses at q<0.05'))
    for name, test in global_stats['tests'].items():
        p['comparisons'].append(comparison(name, test, global_path,
            'Single predeclared110-member BH family; pair estimates are conditional and dependent'))
    p['metrics'] += [metric('Global BH family size', 110, global_path, unit='tests'),
                     metric('Full pytest passed', tests['passed'], audit_path, unit='tests'),
                     metric('Replay checks passed', replay.get('checks_passed'), audit_path, unit='checks')]
    # Explicit preservation scope: local coverage is not automatically archive coverage.
    preservation = replay.get('preservation_coverage')
    require(isinstance(preservation, dict) and preservation.get('verified_count') is not None,
            'Explicit preservation coverage missing from final replay')
    p['metrics'] += [metric('Preserved pilot artifacts verified locally', preservation['verified_count'], audit_path, unit='files'),
                     metric('Locally omitted pilot artifacts', preservation.get('optional_omitted_count', 0), audit_path, unit='files')]
    archive = audit.get('archive_replay', audit.get('portable_replay'))
    archive_scope = '배포 아카이브의 별도 replay 범위는 이 로컬 검증에서 자동으로 보장하지 않는다.'
    if isinstance(archive, dict):
        coverage = archive.get('preservation_coverage', {})
        archive_scope = f"배포 아카이브 replay 상태는 {archive.get('status', 'UNREPORTED')}이며, 검증 파일 {coverage.get('verified_count', '미보고')}개·생략 파일 {coverage.get('optional_omitted_count', '미보고')}개의 범위를 따로 기록했다."
    p['preservation_scope'] = {'local': preservation, 'archive': archive,
                              'saved_readme': 'reports/pilot-v1-README.md', 'claim': archive_scope}
    p['artifacts'] += [source_entry(RUN/'preservation_before.json', 'Pre-followup preservation hashes'),
                       {'label': 'Original pilot README saved verbatim', 'path': 'reports/pilot-v1-README.md'}]
    # Hard cases: all18 evaluations, explicit different-content comparison with D3.
    hard_rows, hard_final, d3_comparison, hard_sources = [], [], [], [rel(hard_path)]
    alignment = read(RUN/'alignment/summary.json')
    d3_syntax = {}
    for item in alignment['evaluations']:
        if item['checkpoint'] != 'final':
            continue
        evaluation = read(RUN/item['path'])
        hard_sources.append(rel(RUN/item['path']))
        for which, model in zip(('model_a', 'model_b'), item['pair']):
            value = evaluation['task_competence']['syntax'][which]['accuracy']
            if model in d3_syntax and d3_syntax[model] != value:
                raise ValueError('D3 syntax competence evidence disagrees')
            d3_syntax[model] = value
    hard_sources.append(rel(RUN/'alignment/summary.json'))
    for name, evaluation in hard['evaluations'].items():
        sp = RUN/'hard_stress'/name/'summary.json'
        saved = read(sp)
        if saved != evaluation:
            raise ValueError('Hard-stress aggregate differs from individual summary')
        raw = sp.parent/'measurements.npz'
        if digest(raw) != saved['measurements_sha256']:
            raise ValueError('Hard-stress measurement hash mismatch')
        metrics = saved['metrics']; model, checkpoint = name.split('/')
        hard_rows.append({'model': model, 'checkpoint': checkpoint, 'value': metrics['accuracy']})
        p['metrics'].append(metric('New hard syntax accuracy', metrics['accuracy'], sp, model=model,
            method=checkpoint, n=metrics['n'], n_clusters=metrics['n_wrappers'], unit='fraction',
            ci=metrics['accuracy_cluster_bootstrap95']['ci']))
        hard_sources.append(rel(sp))
        if checkpoint == 'final':
            hard_final.append({'label': model, 'value': metrics['accuracy'], 'ci': metrics['accuracy_cluster_bootstrap95']['ci']})
            d3_comparison += [{'model': model, 'dataset': 'Original D3 syntax\n(n=192)', 'value': d3_syntax[model]},
                              {'model': model, 'dataset': f"New hard cases\n(n={metrics['n']})", 'value': metrics['accuracy']}]
    p['figures'] += [
        {'id': 'hard_stress_checkpoints', 'kind': 'heatmap', 'title': 'Exploratory hard syntax cases across frozen checkpoints',
         'rows': hard_rows, 'row': 'model', 'column': 'checkpoint', 'column_order': ['initial', 'middle', 'final'],
         'vmin': 0, 'vmax': 1, 'percent': True, 'unit': 'Accuracy; chance =0.5', 'source': hard_sources,
         'note': 'New768-row dataset was frozen before its inference, after D3 motivated the question. No retraining/refitting; this remains posthoc exploratory evidence, outside the110 primary tests. Pretrained initial/middle checkpoints are N/A.'},
        {'id': 'hard_stress_final_intervals', 'kind': 'interval', 'title': 'Final models on new hard syntax cases',
         'rows': hard_final, 'xlabel': 'Accuracy;95% wrapper-cluster bootstrap CI', 'xlim': [0, 1], 'reference': .5,
         'source': hard_sources, 'note': 'Chance=.5 reference; uncertainty is conditional on these frozen models and this generated dataset.'},
        {'id': 'syntax_original_vs_hard', 'kind': 'heatmap', 'title': 'Original syntax and new hard cases: different content',
         'rows': d3_comparison, 'row': 'model', 'column': 'dataset', 'vmin': 0, 'vmax': 1, 'percent': True,
         'unit': 'Accuracy', 'source': hard_sources, 'figsize': [10, 6.5],
         'note': 'The datasets differ in content and construction. Their accuracy difference is not a randomized causal estimate of shortcut use and does not prove or disprove recursive parsing.'}]
    # Matched proxy ablation: samev2 candidates/metric; no confirmatory tests.
    proxy_rows = []
    for cohort, result in proxy['cohorts'].items():
        contrast=result['expanded_minus_old']
        estimate = contrast['mean']
        ci = contrast['ci']
        proxy_rows.append({'label': cohort, 'value': estimate, 'ci': ci})
        p['metrics'].append(metric('Exploratory expanded minus four-dimensional proxy', estimate, proxy_path,
                                  model_pair=cohort, unit='Pearson difference', ci=ci))
    for item in proxy['comparisons']:
        source = RUN/item['path']
        if digest(source) != item['sha256']:
            raise ValueError('Proxy ablation comparison hash mismatch')
        for method, value in item['descriptive'].items():
            p['metrics'].append(metric('Matched exploratory proxy ablation', value, source,
                model_pair='_'.join(item['pair']), method=item['position']+'/'+method, unit='Pearson or difference'))
    p['figures'].append({'id': 'proxy_ablation', 'kind': 'interval', 'title': 'Posthoc matched proxy ablation on followup-v2',
         'rows': proxy_rows, 'xlabel': 'Expanded minus original4D proxy;95% shared-wrapper CI', 'source': rel(proxy_path),
         'note': 'Requested after D3 observation. Samev2 data, frozen candidates and evaluation metric; not independent confirmation or attribution of the full pilot-v1 to followup-v2 change.'})
    # Answer orientation: preserve undefined scores and record identifiable support.
    bias_rows, support_rows, bias_sources = [], [], [rel(diagnostics_path)]
    for cohort, views in diagnostics['cohorts'].items():
        for view, methods in views.items():
            for method, result in methods.items():
                value = result.get('mean')
                p['metrics'].append(metric('Exploratory causal orientation agreement', value, diagnostics_path,
                    model_pair=cohort, method=view+'/'+method, unit='Pearson', ci=result.get('ci'), n=result.get('n_pairs')))
                if method == 'combined':
                    bias_rows.append({'cohort': cohort, 'view': view.replace('_', '\n'), 'value': value})
    for item in diagnostics['evaluations']:
        ep = RUN/item['path']
        if digest(ep) != item['sha256']:
            raise ValueError('Causal bias diagnostic source hash mismatch')
        evaluation = read(ep); bias_sources.append(rel(ep))
        for location, views in evaluation['locations'].items():
            for view, values in views.items():
                for method, wrappers in values['support'].items():
                    finite = sum(x['finite_neuron_task_mode_cells'] for x in wrappers.values())
                    eligible = sum(x['eligible_neuron_task_mode_cells'] for x in wrappers.values())
                    support_rows.append({'pair': '_'.join(item['pair']), 'kind': item['unit_kind'],
                        'location': location, 'view': view, 'method': method, 'finite_cells': finite,
                        'eligible_cells': eligible, 'finite_fraction': finite/eligible if eligible else None,
                        'source': rel(ep)})
    p['figures'].append({'id': 'causal_answer_orientation', 'kind': 'heatmap',
        'title': 'Supplementary combined-map causal agreement by orientation', 'rows': bias_rows,
        'row': 'cohort', 'column': 'view', 'value': 'value', 'vmin': -1, 'vmax': 1,
        'unit': 'Pearson; undefined support = N/A', 'source': bias_sources, 'figsize': [12, 6.8],
        'note': 'Same frozen maps and primary zero/mean/patch interventions. Views may have different identifiable cell support; constant/insufficient scores remain N/A. Within-label attenuation is consistent with answer-orientation confounding, not proof of its exclusive cause.'})
    p['diagnostic_support'] = support_rows
    runtime = runtime_accounting(hard, transfers)
    p['runtime_accounting'] = runtime
    resource_path=RUN/'resource_accounting.json';resources=read(resource_path)
    if abs(resources['total_seconds']-runtime['total_seconds'])>1e-8 or resources['category_seconds']!=runtime['category_seconds']:
        raise ValueError('Resource accounting disagrees with deduplicated runtime receipts')
    peak_source=ROOT/resources['peak_source'];peak=read(peak_source)
    if peak.get('peak_allocated_bytes')!=resources['peak_recorded_torch_allocated_bytes']:
        raise ValueError('Recorded peak Torch allocation source disagrees')
    disk=sum(resources['measured_followup_directory_bytes'].values())
    p['resource_summary']=(f"기록된 모델 단계 경과시간 합계는 {runtime['total_seconds']/3600:.6f}시간이다. "
        f"최대 기록 Torch allocated memory는 {resources['peak_recorded_torch_allocated_bytes']/2**30:.5f}GiB이며, "
        f"resource-accounting 스냅샷 당시 명시한 후속 디렉터리 합계는 {disk/2**30:.6f}GiB였다. "
        "경과시간에는 CPU·I/O·전송 overhead가 포함되며 GPU 활성시간·이용률·프로젝트 전체 경과시간이 아니다. "
        "Torch allocated는 전체 물리 VRAM 사용량과 다르다. 디스크 합계에는 로컬 체크포인트와 재시작 chunk가 포함되지만 기존 base-model cache와 무관한 workspace 파일은 제외한다.")
    p['metrics'] += [metric('Peak recorded Torch allocated memory',resources['peak_recorded_torch_allocated_bytes']/2**30,resource_path,unit='GiB'),
                     metric('Named followup directory snapshot total',disk/2**30,resource_path,unit='GiB')]
    for directory,size in resources['measured_followup_directory_bytes'].items():
        p['metrics'].append(metric('Named directory snapshot storage',size/2**30,resource_path,method=directory,unit='GiB'))
    p['artifacts'] += [source_entry(resource_path,'Resource accounting snapshot and exact scope'),
                       source_entry(peak_source,'Peak Torch allocated-memory receipt')]
    p['metrics'].append({'name': 'Recorded GPU-bearing stage wall sum', 'value': runtime['total_seconds'],
                         'source': [e['source'] for e in runtime['entries']], 'unit': 'seconds'})
    for category, seconds in runtime['category_seconds'].items():
        for entry in runtime['entries']:
            if entry['category'] == category:
                p['artifacts'].append({'label': 'Runtime receipt: '+category, 'path': entry['source']})
        p['metrics'].append({'name': 'Recorded stage wall subtotal', 'value': seconds, 'method': category,
                             'unit': 'seconds', 'source': [e['source'] for e in runtime['entries'] if e['category'] == category]})
    p['figures'].append({'id': 'recorded_wall_intervals', 'kind': 'bar', 'title': 'Recorded model-stage wall intervals',
        'rows': [{'label': k, 'value': v/60} for k, v in runtime['category_seconds'].items()],
        'xlabel': 'Minutes; stage wall intervals, not GPU active time', 'source': [e['source'] for e in runtime['entries']],
        'note': runtime['scope']})
    # Human-readable primary findings, without deriving support from threshold counts.
    f3 = read(RUN/'alignment/summary.json'); f4 = read(RUN/'causal_alignment/summary.json')
    p['primary_findings'] = {'F3_cohorts': f3['cohorts'], 'F4_cohorts': f4['cohorts'],
                             'F5_aggregate': transfers['aggregate_selected_minus_baseline']}
    final_tiny = [e['metrics']['accuracy'] for name, e in hard['evaluations'].items()
                  if name.startswith('seed') and name.endswith('/final')]
    f3a = f3['cohorts']['independent_seeds/answer/final']['tests']
    f3s = f3['cohorts']['independent_seeds/span/final']['tests']
    f5 = transfers['aggregate_selected_minus_baseline']
    for stage, summary, source in (('F3', f3, RUN/'alignment/summary.json'),
                                    ('F4', f4, RUN/'causal_alignment/summary.json')):
        for cohort, values in summary['cohorts'].items():
            if stage == 'F3' and not cohort.endswith('/final'):
                continue
            for contrast, result in values['tests'].items():
                p['metrics'].append(metric(stage+' descriptive joint-wrapper '+contrast,
                    result.get('effect'), source, model_pair=cohort, unit='Pearson difference',
                    ci=(result.get('bootstrap') or {}).get('ci'), n_clusters=result.get('n_clusters')))
    causal_effects=[]
    for cohort, values in f4['cohorts'].items():
        if cohort.startswith('independent_seeds/'):
            value=values['tests']['combined_minus_semantic'].get('effect')
            causal_effects.append(cohort.split('/',1)[1]+' '+('미정의' if value is None else f'{value:+.4f}'))
    p['rationale'] = (f"원래 pilot 결과와 원래 README 사본을 보존하고 검증했다(로컬 검증{preservation['verified_count']}개). "
        f"독립 학습 모델의 activation−random 평균 대응 차이는 answer {f3a['activation_minus_random']['effect']:.4f}, span {f3s['activation_minus_random']['effect']:.4f}였고, "
        f"semantic−activation 차이는 각각 {f3a['semantic_minus_activation']['effect']:.4f}, {f3s['semantic_minus_activation']['effect']:.4f}였다. "
        '독립 시드의 인과 결합−의미 단독 차이는 '+', '.join(causal_effects)+'였다. '
        f"D2 선택 이식 정책의 D4 목표 과제 평균 변화는 {100*f5['effect']:+.4f} percentage points였다. "
        f"새768개 hard syntax 문항에서 학습 완료5개 모델의 정확도 범위는 {min(final_tiny):.1%}–{max(final_tiny):.1%}였다. "
        f"전체110개 주 검정을 하나의 BH family로 보정하고{tests['passed']}개 테스트 및 저장 수치 replay를 통과했다. "
        "확증적 q와 기술적 cohort CI를 구분하며, 높은 합성 과제 정확도·개입 상관만으로 보편적 의미 기능 보존이나 재귀 이해를 입증하지 않는다. 네 연구 질문의 최종 판정은 별도 과학 검토의 근거와 적용 범위를 따른다. "+archive_scope)
    p['executive_summary'] = p['rationale']
    p['limitations'] = [
        'Five trained seeds share one architecture/training distribution; overlapping pairs are dependent. Wrapper uncertainty is conditional on observed models, not unseen-seed population uncertainty.',
        'All110 predeclared tests share one BH family. Conditional pair effects and cohort confidence intervals are not independent replications; exploratory proxy, stress, and orientation diagnostics are outside that family.',
        'Posthoc BY sensitivity reuses the same110 original p-values; it does not replace primary BH, create new hypotheses, or repair invalid individual p-values, wrapper sign-flip assumptions, low competence or construct confounds.',
        'Qwen fourshot, Smol default and OLMo explicit retain different prompt-prefix contexts. Shared target statements and native span alignment do not create identical full-context comparisons.',
        'An operational accuracy/Wilson gate does not validate the intended construct. Syntax results can reflect remaining local cues; the posthoc small D3 stratum and new hard set have different content.',
        'New hard cases were frozen before their inference but designed after D3 observation; they remain exploratory, not a new confirmatory test or evidence of recursive parsing.',
        'Truth-oriented, yes-oriented and within-label causal views can differ in identifiable support. Attenuation is not proof that answer bias exclusively caused the original association.',
        'The four-dimensional versus expanded proxy comparison uses the samefollowup-v2 evidence and was requested after D3; it cannot explain every historical pilot-v1 to followup-v2 change.',
        'Native neuron transplantation and parameter interpolation do not establish whole-circuit-preserving model merging.',
        runtime['scope'], resources['disk_scope']+' This is the saved accounting snapshot, not a promise that later report generation consumes zero additional bytes.',
        'Peak Torch allocated memory measures the framework allocator, not total physical device usage or GPU utilization.',
        preservation.get('claim', ''), archive_scope,
        'Saved-artifact replay does not establish historical execution chronology or independently regenerate excluded model weights.'
    ] + audit.get('limitations', [])
    add_causal_competence(p)
    add_causal_activation_baselines(p)
    p['executive_summary']=p['rationale']
    return p


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--render', action='store_true')
    args = parser.parse_args()
    try:
        payload = build()
    except NotReady as error:
        print(json.dumps({'stage': 'F6', 'status': 'NOT_READY', 'reason': str(error)}, ensure_ascii=False))
        return 2
    path = RUN/'report_inputs/F6.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    temporary.replace(path)
    if args.render:
        from scripts.build_followup_stages import prepared_stage
        from src.followup_reporting import render_followup_reports
        stage = RUN/'stages/F6.json'
        stage.write_text(json.dumps(prepared_stage('F6'), ensure_ascii=False, indent=2, allow_nan=False)+'\n')
        print(json.dumps(render_followup_reports(ROOT, 'F6'), ensure_ascii=False))
    else:
        print(json.dumps({'stage': 'F6', 'status': 'MEASURED', 'adapter': rel(path)}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
