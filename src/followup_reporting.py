"""Source-backed followup-v2 stage reports; never edits pilot-v1 or root README.

The parent writes immutable measurement artifacts and stage JSON snapshots under
results/followup-v2/stages. This module renders those declared measurements;
it does not infer significance from chart overlap, tune, refit, or pool metrics.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
import os
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

STAGES = {
    'F0': 'Protocol, preservation and data audit',
    'F1': 'Calibration and five-seed learning',
    'F2': 'Exact permutation positive control',
    'F3': 'Independent and cross-family alignment',
    'F4': 'Single/group causal effects and dose response',
    'F5': 'Transplantation and selective merging',
    'F6': 'Global statistics, replay and preservation audit',
}
PALETTE=['#2869A6','#C27A2C','#A04F83','#788442','#65717B']
VALID_STATUSES={'PENDING','RUNNING','MEASURED','BLOCKED','FAILED','INCONCLUSIVE','NOT_APPLICABLE','COMPLETE','PASS','PARTIAL','PLANNED'}
VALID_VERDICTS={'SUPPORTED','NOT SUPPORTED','INCONCLUSIVE','NOT_APPLICABLE'}


def _json(path):
    return json.loads(path.read_text())


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _slug(value):
    return re.sub(r'[^a-zA-Z0-9_-]+','_',str(value)).strip('_').lower() or 'figure'


def _value(value,digits=4):
    if value is None:return '미측정'
    if isinstance(value,bool):return 'PASS' if value else 'FAIL'
    if isinstance(value,str):return value.replace('|','\\|').replace('\n',' ')
    value=float(value)
    if not math.isfinite(value):raise ValueError('Nonfinite report number')
    if value!=0 and abs(value)<10**(-digits):return f'{value:.2e}'
    return f'{value:.{digits}f}'.rstrip('0').rstrip('.')


def _interval(value):
    if value is None:return '미측정'
    if len(value)!=2 or not np.isfinite(value).all() or value[0]>value[1]:raise ValueError('Invalid interval')
    return f'[{_value(value[0])}, {_value(value[1])}]'


def _inside(root,path):
    result=(root/path).resolve()
    if not result.is_relative_to(root):raise ValueError('Report source must be inside workspace')
    return result


def _read_records(root,spec,stage_path):
    """Inline rows remain traceable to the actual saved stage JSON snapshot."""
    source=spec.get('source') or stage_path.relative_to(root).as_posix()
    sources=source if isinstance(source,list) else [source]
    for item in sources:
        if not _inside(root,item).exists():raise FileNotFoundError(f'Figure source missing: {item}')
    rows=spec.get('rows',spec.get('records'))
    if rows is None:
        path=_inside(root,sources[0])
        if path.suffix=='.csv':rows=list(csv.DictReader(path.open()))
        else:
            rows=_json(path)
            key=spec.get('records_key')
            if key:
                for part in key.split('.'):rows=rows[int(part)] if isinstance(rows,list) else rows[part]
            elif isinstance(rows,dict):rows=rows.get('rows',rows.get('records'))
    if not isinstance(rows,list):raise ValueError('Figure rows must be a list or provide records_key')
    if any(not isinstance(row,dict) for row in rows):raise ValueError('Figure rows must be objects')
    return rows,sources


def _setup(root):
    os.environ.setdefault('MPLCONFIGDIR',str(root/'cache/matplotlib'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10.5,'axes.titlesize':13,'axes.titleweight':'bold','axes.labelsize':10.5,'axes.spines.top':False,'axes.spines.right':False,'axes.edgecolor':'#65717B','text.color':'#26323D','axes.labelcolor':'#26323D','xtick.color':'#52616E','ytick.color':'#52616E','grid.color':'#E6E9EC','figure.facecolor':'white','axes.facecolor':'white','svg.fonttype':'none'})
    return plt


def _save(root,out,fig,name,rows,sources,spec):
    import matplotlib.pyplot as plt
    paths={suffix:out/f'{name}.{suffix}' for suffix in ('svg','png','json')}
    fig.savefig(paths['svg'],bbox_inches='tight',metadata={'Date':None})
    fig.savefig(paths['png'],dpi=160,bbox_inches='tight')
    receipt={'schema':'followup-figure-v1','title':spec.get('title',name),'encoding':{k:v for k,v in spec.items() if k not in ('rows','records')},'sources':[{'path':p,'sha256':_digest(_inside(root,p))} for p in sources],'rows':rows}
    paths['json'].write_text(json.dumps(receipt,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
    plt.close(fig)
    return {'id':name,'title':spec.get('title',name),'path':paths['svg'].relative_to(root).as_posix(),'png':paths['png'].relative_to(root).as_posix(),'receipt':paths['json'].relative_to(root).as_posix(),'note':spec.get('note',''),'show_in_readme':spec.get('show_in_readme',True)}


def _figure(root,out,plt,stage,spec,stage_path):
    rows,sources=_read_records(root,spec,stage_path)
    if not rows:return None
    kind=spec.get('kind','interval');name=f'{stage.lower()}_{_slug(spec.get("id",spec.get("title",kind)))}'
    title=spec.get('title',name)
    if kind=='heatmap':
        rowkey=spec.get('row','model');colkey=spec.get('column','task');valuekey=spec.get('value','value')
        rownames=spec.get('row_order') or list(dict.fromkeys(str(r[rowkey]) for r in rows));colnames=spec.get('column_order') or list(dict.fromkeys(str(r[colkey]) for r in rows))
        grid=np.full((len(rownames),len(colnames)),np.nan);seen=set()
        for r in rows:
            i,j=rownames.index(str(r[rowkey])),colnames.index(str(r[colkey]))
            if (i,j) in seen:raise ValueError(f'Duplicate heatmap cell in {name}: {i,j}')
            seen.add((i,j))
            if r.get(valuekey) is not None:grid[i,j]=float(r[valuekey])
        finite=grid[np.isfinite(grid)]
        if not len(finite):return None
        fig,ax=plt.subplots(figsize=tuple(spec.get('figsize',[max(7,.8*len(colnames)+3),max(3,.48*len(rownames)+1.8)])),layout='constrained')
        lo=spec.get('vmin',float(min(0,finite.min())));hi=spec.get('vmax',float(finite.max()))
        if hi==lo:hi=lo+1
        if lo < 0 < hi:
            from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
            cmap=LinearSegmentedColormap.from_list('signed_followup',['#B77328','#FAFAF9','#2869A6'])
            norm=TwoSlopeNorm(vmin=lo,vcenter=0,vmax=hi)
        else:
            cmap=plt.get_cmap('Blues').copy();norm=None
        cmap.set_bad('#ECEFF1')
        im=ax.imshow(grid,cmap=cmap,norm=norm,vmin=lo if norm is None else None,vmax=hi if norm is None else None,aspect='auto');ax.set_xticks(range(len(colnames)),colnames,rotation=spec.get('rotation',0));ax.set_yticks(range(len(rownames)),rownames)
        for i in range(len(rownames)):
            for j in range(len(colnames)):
                v=grid[i,j];text='N/A' if not np.isfinite(v) else f'{100*v:.1f}%' if spec.get('percent') else _value(v,3)
                ax.text(j,i,text,ha='center',va='center',color='white' if np.isfinite(v) and ((abs(float(norm(v))-.5)>.32) if norm is not None else (v-lo)/(hi-lo)>.65) else '#26323D',fontsize=10)
        ax.set_xlabel(spec.get('xlabel',''));ax.set_ylabel(spec.get('ylabel',''));fig.colorbar(im,ax=ax,label=spec.get('unit',''),shrink=.85)
    elif kind in ('line','scatter'):
        xkey=spec.get('x','step');ykey=spec.get('y','value');serieskey=spec.get('series')
        names=list(dict.fromkeys(str(r.get(serieskey,'')) for r in rows)) if serieskey else ['']
        fig,ax=plt.subplots(figsize=tuple(spec.get('figsize',[9,4.6])),layout='constrained')
        for i,series in enumerate(names):
            rr=[r for r in rows if not serieskey or str(r.get(serieskey,''))==series]
            rr=[r for r in rr if r.get(xkey) is not None and r.get(ykey) is not None]
            if not rr:continue
            rr=sorted(rr,key=lambda r:float(r[xkey]))
            x=np.array([float(r[xkey]) for r in rr]);y=np.array([float(r[ykey]) for r in rr])
            if not np.isfinite(x).all() or not np.isfinite(y).all():raise ValueError(f'Nonfinite values in {name}')
            color=PALETTE[i%len(PALETTE)]
            if kind=='line':ax.plot(x,y,label=series or None,color=color,lw=1.6,linestyle=['-','--',':','-.'][i%4],marker='o' if len(rr)<12 else None,markersize=4)
            else:ax.scatter(x,y,label=series or None,color=color,s=22,alpha=.65,marker=['o','s','^','D','x'][i%5])
        ax.set_xlabel(spec.get('xlabel',xkey));ax.set_ylabel(spec.get('ylabel',ykey));ax.grid(axis='y')
        if spec.get('yscale'):ax.set_yscale(spec['yscale'])
        if spec.get('xlim'):ax.set_xlim(spec['xlim'])
        if spec.get('xticks') is not None:ax.set_xticks(spec['xticks'],spec.get('xticklabels'))
        if spec.get('ylim'):ax.set_ylim(spec['ylim'])
        if 'reference' in spec:ax.axhline(spec['reference'],color='#65717B',linestyle=':',lw=1)
        if serieskey:ax.legend(frameon=False,ncol=min(3,len(names)),fontsize=9)
    elif kind in ('interval','bar'):
        labelkey=spec.get('label','label');valuekey=spec.get('value','value');cikey=spec.get('ci','ci')
        rr=[r for r in rows if r.get(valuekey) is not None]
        if not rr:return None
        fig,ax=plt.subplots(figsize=(9,max(3.4,.38*len(rr)+1.7)),layout='constrained')
        for i,r in enumerate(rr):
            val=float(r[valuekey]);ci=r.get(cikey)
            if not np.isfinite(val):raise ValueError(f'Nonfinite value in {name}')
            color=PALETTE[i%len(PALETTE)] if spec.get('categorical_colors') else PALETTE[0]
            if kind=='bar':ax.barh(i,val,color=color,height=.62)
            else:ax.plot(val,i,'o',color=color,markersize=6)
            if ci is not None:
                _interval(ci);ax.plot(ci,[i,i],lw=1.6,color=color)
            ax.annotate(_value(val,3),(val,i),xytext=(6,5),textcoords='offset points',fontsize=9,
                        color='white' if kind=='bar' and val<0 else '#26323D')
        ax.set_yticks(range(len(rr)),[str(r.get(labelkey,r.get('name',i))) for i,r in enumerate(rr)]);ax.set_ylim(len(rr)-.5,-.75);ax.set_xlabel(spec.get('xlabel',spec.get('unit','Value')));ax.axvline(0,lw=.8,color='#65717B');ax.grid(axis='x')
        if 'reference' in spec:ax.axvline(spec['reference'],lw=1,linestyle=':',color='#26323D')
        if spec.get('xlim'):ax.set_xlim(spec['xlim'])
    else:raise ValueError(f'Unsupported figure kind: {kind}')
    ax.set_title(title,pad=14)
    return _save(root,out,fig,name,rows,sources,spec)


def _metric_table(metrics):
    if not metrics:return '이 단계의 수치 측정은 아직 보고되지 않았습니다.'
    lines=['| 지표 | 조건·방법 | 측정값 | CI | 단위 | n / 군집 |','|---|---|---:|---|---|---|']
    for r in metrics:
        context=' / '.join(str(r[k]) for k in ('model_pair','model','method','task','split') if r.get(k) is not None)
        sample=' / '.join(str(r[k]) for k in ('n','n_clusters') if r.get(k) is not None)
        lines.append(f"| {r.get('name','')} | {context} | {_value(r.get('value'))} | {_interval(r.get('ci'))} | {r.get('unit','')} | {sample} |")
    return '\n'.join(lines)


def _comparison_table(comparisons):
    if not comparisons:return '대응 차이에 대한 확인 검정은 아직 보고되지 않았습니다.'
    lines=['| 비교 | Δ | CI | p | q | 보정 범위 |','|---|---:|---|---:|---:|---|']
    for r in comparisons:lines.append(f"| {r.get('name','')} | {_value(r.get('estimate',r.get('effect')))} | {_interval(r.get('ci'))} | {_value(r.get('pvalue'))} | {_value(r.get('qvalue'))} | {r.get('correction_scope','미지정')} |")
    return '\n'.join(lines)


def _review_text(review,prefix=''):
    parts=[]
    for answer in review['questions']:
        label=answer['verdict']+(f" ({answer['scope']})" if answer['verdict']=='SUPPORTED' else '')
        parts += [f"**{answer['id']} — {answer['question']} · {label}**", '',
                  answer['rationale'], '', '적용 범위: '+answer['scope'], '',
                  '근거: '+' · '.join(f'[{Path(path).name}]({prefix}{path})' for path in answer['evidence']), '']
    return '\n'.join(parts)


def _causal_competence_text(data,prefix=''):
    rows={}
    for row in data['rows']:
        key=(row['cohort'],row['unit_kind'],row['position'],row['concept'])
        rows.setdefault(key,{})[row['subset']]=row
    lines=[data['scope'], '',
           '| Cohort / unit / position | Task | All-pair combined r | Available/all pairs | Eligible combined r | Available/eligible pairs | Eligible wrapper coverage |',
           '|---|---|---:|---:|---:|---:|---:|']
    show=lambda value:'N/A' if value is None else _value(value)
    for key,subsets in rows.items():
        all_rows=subsets['all_pairs'];eligible=subsets['both_passed']
        a=all_rows['methods']['combined'];e=eligible['methods']['combined']
        lines.append(f"| {'/'.join(key[:3])} | {key[3]} | {show(a['mean'])} | {a['n_available_pairs']}/{all_rows['n_pairs_in_subset']} | {show(e['mean'])} | {e['n_available_pairs']}/{eligible['n_pairs_in_subset']} | {show(e['wrapper_coverage_fraction'])} |")
    lines += ['', 'No eligible pairs or unidentifiable cells remain N/A; zero is not substituted. The linked report contains every semantic/causal/combined/random mean, missing pair count and wrapper support.', '',
              f"[모든 방법과 누락 범위]({prefix}{data['report']}) · [수치 원본]({prefix}{data['source']})", '']
    return '\n'.join(lines)


def _causal_activation_text(data,prefix=''):
    methods=('semantic','combined','random','activation_raw','activation_task_centered')
    labels=('Semantic','Combined','Random','Raw activation','Task-centered activation')
    lines=[data['scope'],'','Cells: mean [available/total pairs; valid/possible wrapper cells].','',
           '| Cohort / unit / position | '+' | '.join(labels)+' |','|---|'+'---:|'*len(methods)]
    for row in data['rows']:
        cells=[]
        for method in methods:
            r=row['methods'][method];value='N/A' if r['mean'] is None else _value(r['mean'])
            cells.append(f"{value} [{r['n_available_pairs']}/{r['n_pairs_total']}; {r['n_valid_wrapper_cells']}/{r['n_possible_wrapper_cells']}]")
        lines.append('| '+row['cohort']+'/'+row['unit_kind']+'/'+row['position']+' | '+' | '.join(cells)+' |')
    lines+=['',f"[상세 범위와 모든 원본]({prefix}{data['report']}) · [측정 요약]({prefix}{data['source']})",'']
    return '\n'.join(lines)


def _causal_orientation_text(data,prefix=''):
    lines=[data['scope'],'','| Cohort / unit / position | Truth-oriented | Yes-oriented | Within-label |','|---|---:|---:|---:|']
    for row in data['rows']:
        values=[row['views'][view].get('mean') for view in ('truth_oriented','yes_oriented','within_label')]
        lines.append('| '+row['cohort']+' | '+' | '.join('N/A' if value is None else _value(value,5) for value in values)+' |')
    lines+=['',f"[모든 방법·유효 셀 범위·원본 경로]({prefix}{data['source']})",'']
    return '\n'.join(lines)


def _sources(root,stage_path,payload):
    candidates=[stage_path.relative_to(root).as_posix()]
    for row in payload.get('metrics',[])+payload.get('comparisons',[]):
        source=row.get('source')
        if source:candidates.extend(source if isinstance(source,list) else [source])
    for item in payload.get('artifacts',[]):
        if isinstance(item,str):candidates.append(item)
        elif item.get('path'):candidates.append(item['path'])
    output=[]
    for path in dict.fromkeys(candidates):
        absolute=_inside(root,path)
        if not absolute.exists():raise FileNotFoundError(f'Stage references missing artifact: {path}')
        output.append({'path':path,'sha256':_digest(absolute) if absolute.is_file() else None})
    return output


def _final_q_overlay(payload,sid,global_stats):
    """Update derived display only; frozen stage and measurement bytes stay intact."""
    if sid not in ('F3','F4','F5'):return payload
    if global_stats.get('family_size')!=110 or len(global_stats.get('tests',{}))!=110:
        raise ValueError('Final display requires the complete110-member global family')
    tests=global_stats['tests']
    for row in payload.get('comparisons',[]):
        key='F5/aggregate/selected_minus_baseline' if sid=='F5' else row['name']
        if key not in tests:raise ValueError('Comparison missing from final global family: '+key)
        test=tests[key]
        for shown,original in ((row.get('estimate',row.get('effect')),test.get('effect')),
                               (row.get('pvalue'),test.get('pvalue'))):
            if shown is None or original is None:
                if shown is not original:raise ValueError('Final comparison missing-value mismatch')
            elif not math.isclose(float(shown),float(original),rel_tol=1e-10,abs_tol=1e-12):
                raise ValueError('Final statistics disagree with frozen stage values: '+key)
        row['qvalue']=test.get('qvalue')
        row['correction_scope']='Final single110-member BH family; conditional dependent-pair estimates'
        row['global_test_id']=key
        original_source=row.get('source')
        row['source']=list(dict.fromkeys(([original_source] if isinstance(original_source,str) else original_source or [])+['results/followup-v2/statistics/global_tests.json']))
    replacements={
        '확인 검정의 전역 BH는 F6에서 적용한다.':'확인 검정의 q값은 F6의 단일110개 BH family에서 가져왔다.',
        '전역 다중검정과 전체 판정은 F6에서 완료한다.':'전역 다중검정은 F6의 단일110개 BH family로 완료했으며, 보정값과 해석 한계를 함께 보고한다.',
        'F6의 전역 다중검정 전에는 확증적 개선으로 판정하지 않는다.':'F6의 단일110개 BH family 보정값을 함께 보고하며, 효과와 과제 능력·설계 한계를 종합해 해석한다.',
        'One global confirmatory family is corrected in F6; interim p values are unadjusted.':'Final q values use the single110-member global BH family. Raw p values and original primary measurements are preserved.',
        'global BH is deferred to F6.':'q values are supplied by the final110-member global BH family.'}
    def refresh(text):
        for old,new in replacements.items():text=text.replace(old,new)
        return text
    payload['rationale']=refresh(payload.get('rationale',''))
    payload['limitations']=[refresh(x) for x in payload.get('limitations',[])]
    for spec in payload.get('figures',[]):
        if spec.get('note'):spec['note']=refresh(spec['note'])
    return payload


def _reviewed_stage_overlay(payload,sid,review):
    """Final scientific display is explicit about its difference from the interim record."""
    decision=review.get('stage_verdicts',{}).get(sid)
    if decision is None:return payload
    if review.get('status')!='REVIEWED' or decision.get('verdict') not in VALID_VERDICTS:
        raise ValueError('Final stage decision requires reviewed valid verdict')
    if not decision.get('scope') or not decision.get('rationale'):
        raise ValueError('Final stage decision requires explicit scope and rationale')
    payload['interim_snapshot_verdict']=payload.get('verdict','INCONCLUSIVE')
    payload['verdict']=decision['verdict']
    payload['final_verdict_scope']=decision['scope']
    payload['final_review_rationale']=decision['rationale']
    payload['rationale']+=' 최종 과학 검토: '+decision['rationale']+' 적용 범위: '+decision['scope']+'.'
    payload.setdefault('artifacts',[]).append({'label':'Final scoped scientific review; interim snapshot preserved',
                                             'path':'results/followup-v2/scientific_review.json'})
    return payload


def _hard_stress_supplement(root,reports,out,plt):
    """Render completed exploratory evidence without touching frozen stage snapshots."""
    run=root/'results/followup-v2';path=run/'hard_stress/summary.json'
    if not path.exists():return None
    summary=_json(path)
    if summary.get('status')!='COMPLETE_EXPLORATORY' or summary.get('n_evaluations')!=18 or len(summary.get('evaluations',{}))!=18:return None
    if not summary.get('no_primary_family_change'):raise ValueError('Hard-stress scope changed primary family')
    models=[f'seed{x}' for x in (101,211,307,401,503)]+['qwen','smol','olmo']
    expected={name+'/'+ck for name in models for ck in (('initial','middle','final') if name.startswith('seed') else ('final',))}
    if set(summary['evaluations'])!=expected:raise ValueError('Unexpected hard-stress model/checkpoint coverage')
    sources=[path.relative_to(root).as_posix()];final_rows=[];trajectory=[];table=[];limits=[]
    for model in models:
        for ck in ('initial','middle','final') if model.startswith('seed') else ('final',):
            item=summary['evaluations'][model+'/'+ck];sp=run/'hard_stress'/model/ck/'summary.json'
            if _json(sp)!=item or _digest(sp.parent/'measurements.npz')!=item['measurements_sha256']:
                raise ValueError('Hard-stress saved summary/measurement identity mismatch')
            sources.append(sp.relative_to(root).as_posix());m=item['metrics']
            if m['n']!=768 or m['n_wrappers']!=24:raise ValueError('Unexpected hard-stress denominator')
            limits.extend(item['limitations'])
            table.append({'model':model,'checkpoint':ck,**m,'source':sp.relative_to(root).as_posix()})
            if ck=='final':final_rows.append({'label':model,'value':m['accuracy'],'ci':m['accuracy_cluster_bootstrap95']['ci']})
            if model.startswith('seed'):trajectory.append({'model':model,'checkpoint':{'initial':0,'middle':1,'final':2}[ck],'value':m['accuracy']})
    specs=[{'id':'hard_final_accuracy','kind':'interval','title':'Final models on new hard syntax cases',
            'rows':final_rows,'xlabel':'Accuracy;95% wrapper-cluster bootstrap CI','xlim':[0,1],'reference':.5,'source':sources,
            'note':'768 balanced rows in24 wrappers; dotted line marks chance50%. These are posthoc-motivated new cases, frozen before inference, outside the110 primary tests.'},
           {'id':'hard_checkpoint_trajectory','kind':'line','title':'Hard syntax cases across five frozen training trajectories',
            'rows':trajectory,'x':'checkpoint','y':'value','series':'model','xticks':[0,1,2],
            'xticklabels':['Initial','Middle','Final'],'xlabel':'Saved checkpoint','ylabel':'Accuracy; chance =0.5',
            'ylim':[0,1],'reference':.5,'source':sources,
            'note':'Five separately initialized models; each line reuses one model across checkpoints. No retraining or checkpoint selection. This is not independent replication at each point.'}]
    figures=[_figure(root,out,plt,'supplement',spec,path) for spec in specs]
    alignment_path=run/'alignment/summary.json';alignment=_json(alignment_path);d3={};d3_sources={}
    for entry in alignment['evaluations']:
        if entry['checkpoint']!='final':continue
        ep=run/entry['path'];evaluation=_json(ep)
        if _digest(ep)!=entry['sha256']:raise ValueError('D3 competence source checksum mismatch')
        for side,model in zip(('model_a','model_b'),entry['pair']):
            value=evaluation['task_competence']['syntax'][side]['accuracy']
            if model in d3 and d3[model]!=value:raise ValueError('Repeated D3 syntax competence differs')
            d3[model]=value;d3_sources[model]=ep.relative_to(root).as_posix()
    final={r['model']:r for r in table if r['checkpoint']=='final'}
    trained=[final[name]['accuracy'] for name in models if name.startswith('seed')]
    original=[d3[name] for name in models if name.startswith('seed')]
    yes=[final[name]['yes_rate'] for name in models if name.startswith('seed')]
    narrative=(f"사후 D3 진단에서 동기를 얻어 새 hard syntax768문항(참·거짓 각384,24wrappers)을 구성·동결한 뒤18개 모델/체크포인트 측정을 완료했다. "
        f"학습 완료5개 모델의 정확도는 {min(trained):.2%}–{max(trained):.2%}였고, 원래 D3 괄호 정확도는 {min(original):.2%}–{max(original):.2%}였다. "
        f"새 문항에서 이 모델들의 yes 응답률은 {min(yes):.2%}–{max(yes):.2%}로, 균형 정확도와 함께 응답 편향을 확인해야 한다. "
        "두 집합은 내용·구조 분포가 달라 점수 차이가 shortcut 사용의 인과적 증거는 아니다. 이 결과는 전체 정확도 gate만으로 재귀 이해를 입증할 수 없음을 강조하며, 새로운 독립 확증 검정이나 원래 주 분석의 변경으로 취급하지 않는다.")
    limitations=list(dict.fromkeys(limits))+[
        'All18 confidence intervals are descriptive wrapper-cluster bootstrap intervals conditional on fixed models; no global claims are inferred from overlap or individual exploratory p-values.',
        'Balanced true/false pairs make chance accuracy50%; yes preference and true/false accuracy can still be highly asymmetric. Ties count as incorrect.',
        'Different calibration-selected prefix contexts remain for Qwen, Smol and OLMo; matched target content does not mean identical full prompts.',
        'Original D3 and the hard set differ in content and structural distribution. Their difference is not a controlled causal effect or proof of recursive parsing.']
    content='# 새 hard syntax 문항의 탐색적 검증\n\n**COMPLETE_EXPLORATORY · 주110개 검정에 포함하지 않음.**\n\n'+narrative+'\n\n'
    for f in figures:content+=f"![{f['title']}](../../{f['path']})\n\n{f['note']}\n\n[정확한 그림 값과 출처](../../{f['receipt']})\n\n"
    content+='## 모든18개 측정과 응답 편향\n\n| 모델 | 체크포인트 | n / wrappers | 정확도 |95% cluster CI | 참 정확도 | 거짓 정확도 | yes 비율 | tie 비율 |\n|---|---|---:|---:|---|---:|---:|---:|---:|\n'
    for r in table:
        content+=f"| [{r['model']}](../../{r['source']}) | {r['checkpoint']} | {r['n']} / {r['n_wrappers']} | {r['accuracy']:.2%} | {_interval(r['accuracy_cluster_bootstrap95']['ci'])} | {r['accuracy_true']:.2%} | {r['accuracy_false']:.2%} | {r['yes_rate']:.2%} | {r['tie_rate']:.2%} |\n"
    content+='\n## 원래 D3와 새 문항: 내용이 다른 기술 비교\n\n| 모델 | 원래 D3 syntax (n=192) | 새 hard syntax (n=768) |\n|---|---:|---:|\n'
    for name in models:content+=f"| {name} | [{d3[name]:.2%}](../../{d3_sources[name]}) | {final[name]['accuracy']:.2%} |\n"
    content+='\n## 한계\n\n'+'\n'.join('- '+s for s in limitations)+'\n\n## 원본\n\n'
    content+='\n'.join(f'- [{source}](../../{source})' for source in dict.fromkeys(sources+['data/followup-v2-hard-stress/manifest.json','src/followup_hard_stress.py']))+'\n'
    (reports/'HARD_STRESS_REPORT.md').write_text(content)
    block='### 보충 검증 — 새 hard syntax 문항\n\n'+narrative+'\n\n'
    for f in figures:block+=f"![{f['title']}]({f['path']})\n\n{f['note']}\n\n[그림 데이터]({f['receipt']})\n\n"
    block+='[18개 전체 측정·신뢰구간·응답 편향·출처](reports/followup-v2/HARD_STRESS_REPORT.md)\n\n'
    return {'section':block,'figures':figures,'limitations':limitations,'report':'reports/followup-v2/HARD_STRESS_REPORT.md'}


def render_followup_reports(root=None,max_stage=None):
    root=Path(root or Path(__file__).resolve().parents[1]).resolve()
    reports=root/'reports/followup-v2';reports.mkdir(parents=True,exist_ok=True)
    out=root/'artifacts/followup-v2/figures';out.mkdir(parents=True,exist_ok=True)
    plt=_setup(root);limit=int(max_stage[1:]) if max_stage else 6
    global_path=root/'results/followup-v2/statistics/global_tests.json'
    final_stage=root/'results/followup-v2/stages/F6.json'
    global_stats=_json(global_path) if limit==6 and global_path.exists() and final_stage.exists() else None
    final_review=_json(root/'results/followup-v2/scientific_review.json') if global_stats is not None else None
    date=datetime.now(ZoneInfo('Asia/Seoul')).strftime('%Y-%m-%d %H:%M KST')
    snapshots=[]
    for sid,title in STAGES.items():
        path=root/f'results/followup-v2/stages/{sid}.json'
        payload=_json(path) if path.exists() and int(sid[1:])<=limit else {'id':sid,'title':title,'status':'PENDING'}
        if global_stats is not None:
            payload=_final_q_overlay(payload,sid,global_stats)
            payload=_reviewed_stage_overlay(payload,sid,final_review)
        if payload.get('id',sid)!=sid:raise ValueError('Stage ID and filename disagree')
        status=payload.get('status','PENDING')
        if status not in VALID_STATUSES:raise ValueError(f'Unknown stage status: {status}')
        verdict=payload.get('verdict','INCONCLUSIVE')
        if verdict not in VALID_VERDICTS:raise ValueError(f'Invalid hypothesis verdict: {verdict}')
        if status in ('PENDING','RUNNING','BLOCKED','FAILED','PLANNED') and verdict=='SUPPORTED':raise ValueError('Unfinished stage cannot be SUPPORTED')
        figures=[]
        if path.exists() and int(sid[1:])<=limit:
            sources=_sources(root,path,payload)
            specs=list(payload.get('figures',[]))
            if not specs:
                groups={}
                for row in payload.get('metrics',[]):
                    if isinstance(row.get('value'),(int,float)) and not isinstance(row.get('value'),bool):groups.setdefault((row.get('name','Metric'),row.get('unit','')),[]).append(row)
                for (name,unit),records in groups.items():
                    if len(records)<2:continue
                    rr=[{'label':' / '.join(str(r[k]) for k in ('model_pair','model','method','task','split') if r.get(k) is not None) or str(i+1),'value':r['value'],'ci':r.get('ci')} for i,r in enumerate(records)]
                    specs.append({'id':name,'kind':'interval','title':name,'unit':unit,'rows':rr,'source':path.relative_to(root).as_posix(),'note':'Intervals are shown only when supplied by the saved result; no uncertainty is invented.'})
            for spec in specs:
                figure=_figure(root,out,plt,sid,spec,path)
                if figure:figures.append(figure)
        else:sources=[]
        verdict_label=verdict+(f" ({payload['final_verdict_scope']})" if payload.get('final_verdict_scope') else '')
        snapshot={'id':sid,'title':payload.get('title',title),'status':status,'verdict':verdict,'verdict_label':verdict_label,'payload':payload,'figures':figures,'sources':sources}
        snapshots.append(snapshot)
        content=f"# {sid} — {snapshot['title']}\n\n갱신: {date}. 실행 상태: **{status}**. 가설 판정: **{verdict_label}**.\n\n"
        if payload.get('interim_snapshot_verdict'):
            content+=f"원본 단계 스냅샷의 잠정 판정은 **{payload['interim_snapshot_verdict']}**로 보존되어 있습니다. 위 표시는 전역 보정 후의 [최종 과학 검토](../../results/followup-v2/scientific_review.json)가 정한 제한된 범위의 판정입니다. 원본 측정과 단계 JSON은 수정하지 않았습니다.\n\n"
        if payload.get('question'):content+='연구 질문: '+payload['question']+'\n\n'
        content+=payload.get('rationale','판정 근거가 아직 보고되지 않았습니다.')+'\n\n'
        if payload.get('scientific_review'):
            content+='## 네 연구 질문의 최종 검토\n\n'+_review_text(payload['scientific_review'],'../../')+'\n'
        if payload.get('competence_gate'):content+='## 과제 능력 조건\n\n'+json.dumps(payload['competence_gate'],ensure_ascii=False,indent=2)+'\n\n'
        content+='## 실제 측정\n\n'+_metric_table(payload.get('metrics',[]))+'\n\n## 비교와 불확실성\n\n'+_comparison_table(payload.get('comparisons',[]))+'\n\n'
        if payload.get('causal_competence'):
            content+='## 과제별 전체 쌍과 능력 조건을 충족한 쌍\n\n'+_causal_competence_text(payload['causal_competence'],'../../')+'\n'
        if payload.get('causal_activation_baselines'):
            content+='## 누락된 activation 기준선의 사후 보충 비교\n\n'+_causal_activation_text(payload['causal_activation_baselines'],'../../')+'\n'
        if payload.get('causal_answer_orientation'):
            content+='## 응답 방향에 따른 보조 인과 대응\n\n'+_causal_orientation_text(payload['causal_answer_orientation'],'../../')+'\n'
        if payload.get('dependence_sensitivity'):
            d=payload['dependence_sensitivity']
            content+='## 다중검정 의존성 민감도\n\n'+d['summary']+f" [SciPy 공식 문서]({d['reference']})\n\n[민감도 상세 보고서](../../{d['report']}) · [전체 BH/BY 수치](../../{d['source']})\n\n"
        if payload.get('resource_summary'):
            content+='## 실제 자원 기록과 측정 범위\n\n'+payload['resource_summary']+' [원본 기록](../../results/followup-v2/resource_accounting.json)\n\n'
        if payload.get('diagnostic_support'):
            content+='## 보조 인과 진단의 유효 셀 범위\n\n다른 view는 유효 셀 집합이 다를 수 있습니다. 값이 정의되지 않는 셀을 0 상관으로 바꾸지 않습니다.\n\n| Pair | 단위·위치 | View·방법 | 유효 셀 | 가능 셀 | 유효 비율 |\n|---|---|---|---:|---:|---:|\n'
            for r in payload['diagnostic_support']:
                content+=f"| {r['pair']} | {r['kind']}/{r['location']} | {r['view']}/{r['method']} | {r['finite_cells']} | {r['eligible_cells']} | {_value(r['finite_fraction'])} |\n"
            content+='\n'
        for f in figures:content+=f"![{f['title']}](../../{f['path']})\n\n{f['note']}\n\n[그림 수치와 출처](../../{f['receipt']})\n\n"
        if payload.get('limitations'):content+='## 해석 한계\n\n'+'\n'.join('- '+s for s in payload['limitations'])+'\n\n'
        if payload.get('next_action'):content+='## 다음 단계\n\n'+payload['next_action']+'\n\n'
        if sources:content+='## 원본과 재현\n\n'+'\n'.join(f"- [{s['path']}](../../{s['path']})" for s in sources)+'\n'
        (reports/f'{sid}_REPORT.md').write_text(content)
    table=['| 단계 | 실험 | 실행 상태 | 가설 판정 |','|---|---|---|---|']
    for s in snapshots:table.append(f"| {s['id']} | [{s['title']}](reports/followup-v2/{s['id']}_REPORT.md) | {s['status']} | {_value(s['verdict_label'])} |")
    common='실행 완료와 가설 지지는 별개입니다. 모델이 해당 과제를 학습했는지 먼저 확인하며, 낮은 능력의 대응 실패를 보존 가설의 반증으로 바꾸지 않습니다. 새 데이터·프로토콜·후보·검정 범위를 기록하고 기존 pilot-v1 결과를 보존합니다. 군집·모델 seed·매칭 seed·다중검정 범위가 다른 수치를 임의로 합치지 않습니다. 인과 효과 일치도 이식이나 병합의 유효성을 자동으로 보장하지 않습니다.'
    section=f"## 후속 연구 — followup-v2\n\n갱신: **{date}**. 이 절은 새 단계별 측정 파일에서 생성되었습니다.\n\n"+'\n'.join(table)+'\n\n'+common+'\n\n'
    if snapshots[-1]['payload'].get('executive_summary'):
        section=section.replace('이 절은 새 단계별 측정 파일에서 생성되었습니다.\n\n','이 절은 새 단계별 측정 파일에서 생성되었습니다.\n\n'+snapshots[-1]['payload']['executive_summary']+'\n\n',1)
    if snapshots[-1]['payload'].get('scientific_review'):
        section+='### 네 연구 질문의 최종 검토\n\n'+_review_text(snapshots[-1]['payload']['scientific_review'])+'\n'
    if final_review and final_review.get('stage_verdicts'):
        section+='F4/F5의 표시는 전역 보정 후 [최종 과학 검토](results/followup-v2/scientific_review.json)의 제한된 범위 판정입니다. 원본 단계 스냅샷의 잠정 판정은 그대로 보존했고, 아래 단계별 설명에서 이를 구분합니다.\n\n'
    for s in snapshots:
        p=s['payload']
        if s['status'] in ('PENDING','PLANNED'):continue
        section+=f"### {s['id']} — {s['title']}\n\n**{s['status']} · {s['verdict_label']}**. "+p.get('rationale','판정 근거 미보고.')+'\n\n'
        if p.get('interim_snapshot_verdict'):
            section+=f"원본 단계 스냅샷의 잠정 판정: **{p['interim_snapshot_verdict']}**. 현재 표시: **{s['verdict_label']}**. [최종 검토 근거](results/followup-v2/scientific_review.json).\n\n"
        if p.get('dependence_sensitivity'):
            d=p['dependence_sensitivity']
            section+=d['summary']+f" [SciPy 공식 문서]({d['reference']}) · [민감도 상세]({d['report']})\n\n"
        if p.get('resource_summary'):
            section+=p['resource_summary']+' [원본 기록](results/followup-v2/resource_accounting.json)\n\n'
        if p.get('causal_competence'):
            d=p['causal_competence']
            section+=f"[과제별 전체/능력충족 쌍의 인과 대응과 누락 범위]({d['report']}). 이 구분은 D4 결과를 조건으로 한 기술 통계이며, 추가 CI·p값·재학습을 포함하지 않습니다.\n\n"
        if p.get('causal_activation_baselines'):
            d=p['causal_activation_baselines']
            section+=f"[Raw/task-centered activation 인과 기준선의 사후 비교]({d['report']}). 두 대조군을 모두 공개하며 주110개 검정·p/q값은 바꾸지 않습니다.\n\n"
        for f in s['figures']:
            if f['show_in_readme']:section+=f"![{f['title']}]({f['path']})\n\n{f['note']}\n\n[그림 데이터]({f['receipt']})\n\n"
        section+=f"[{s['id']} 측정값·불확실성·원본](reports/followup-v2/{s['id']}_REPORT.md)\n\n"
    hard_supplement=_hard_stress_supplement(root,reports,out,plt) if limit>=3 else None
    if hard_supplement and snapshots[-1]['status']=='PENDING':section+=hard_supplement['section']
    critique=['# Followup-v2 research critique', '', '측정 완료 여부, 과제 능력, 대조군 회복, 가설 지지를 구분합니다. 아래 한계는 각 단계의 저장된 증거와 함께 읽어야 합니다.', '']
    for s in snapshots:
        if s['status'] in ('PENDING','PLANNED'):continue
        critique += [f"## {s['id']} — {s['title']}", '', f"상태: {s['status']}; 판정: {s['verdict_label']}.", '']
        if s['payload'].get('final_review_rationale'):
            critique += [s['payload']['final_review_rationale'], '',
                         '[최종 검토 원본](../../results/followup-v2/scientific_review.json)', '']
        critique += ['- '+item for item in s['payload'].get('limitations',[])]
        critique += ['', f"[측정과 원본]({s['id']}_REPORT.md)", '']
    if hard_supplement:
        critique+=['## 새 hard syntax 보충 검증', '']+['- '+item for item in hard_supplement['limitations']]+['','[전체 측정과 출처](HARD_STRESS_REPORT.md)','']
    (reports/'RESEARCH_CRITIQUE.md').write_text('\n'.join(critique)+'\n')
    section+='[연구 해석 한계와 비판](reports/followup-v2/RESEARCH_CRITIQUE.md)\n\n'
    (reports/'README_SECTION.md').write_text(section)
    full=section.replace('](reports/','](../../reports/').replace('](artifacts/','](../../artifacts/').replace('](results/','](../../results/').replace('](data/','](../../data/')
    (reports/'FINAL_FOLLOWUP_REPORT.md').write_text('# Followup-v2 research report\n\n'+full)
    receipt={'generated_kst':date,'stages':[{'id':s['id'],'status':s['status'],'verdict':s['verdict'],'verdict_scope':s['payload'].get('final_verdict_scope'),'interim_snapshot_verdict':s['payload'].get('interim_snapshot_verdict'),'sources':s['sources'],'figures':s['figures']} for s in snapshots],'supplements':[hard_supplement] if hard_supplement else [],'root_readme_edited':False,'pilot_v1_edited':False}
    (reports/'REPORT_GENERATION.json').write_text(json.dumps(receipt,indent=2,ensure_ascii=False)+'\n')
    return {'stage_status':{s['id']:s['status'] for s in snapshots},'figures':sum(len(s['figures']) for s in snapshots)+(len(hard_supplement['figures']) if hard_supplement else 0),'section':'reports/followup-v2/README_SECTION.md'}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--max-stage',choices=list(STAGES));args=parser.parse_args()
    print(json.dumps(render_followup_reports(max_stage=args.max_stage),indent=2,ensure_ascii=False))
