"""Generate GitHub Markdown and static figures exclusively from saved measurements.

Safe to invoke after every stage: unmeasured stages remain pending. Published
numbers are machine-read; derived chart rows are saved beside the figures.
"""
from __future__ import annotations
import csv
import json
import os
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np

STAGES = {
    'E1': ('Independent Seed Neuron Conservation', '독립 초기화 모델의 기능 대응', 'activation', 'random'),
    'E2': ('Cross-Family Neuron Conservation', '이종 Base 모델의 기능 대응', 'activation', 'random'),
    'E3': ('Main-Function Semantic Alignment', '의미 정렬의 독립 입력 일반화', 'semantic', 'activation'),
    'E4': ('Causal-Role Alignment', '독립 인과 효과 일치', 'semantic_causal', 'semantic'),
}
METHODS = {'random':'Random','activation':'Activation','rank':'Rank','semantic':'Semantic','sign_semantic':'Sign-aware semantic','label_shuffled':'Label-shuffled','weight':'Weight (local)','causal':'Causal only','causal_only':'Causal only','semantic_causal':'Semantic + causal','combined':'Semantic + causal','activation_partial':'Activation (partial)','activation_one_to_many':'Activation (one-to-many)'}
COLORS = {'random':'#7B858E','activation':'#2869A6','rank':'#8A9DAF','semantic':'#C27A2C','sign_semantic':'#A04F83','label_shuffled':'#B1B7BD','weight':'#788442','causal':'#2869A6','causal_only':'#2869A6','semantic_causal':'#C27A2C','combined':'#C27A2C'}


def _read(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def _num(value, digits=3):
    return '미측정' if value is None or not np.isfinite(float(value)) else f'{float(value):.{digits}f}'


def _ci(value):
    return '미측정' if value is None else f'[{_num(value[0])}, {_num(value[1])}]'


def _path(root, path):
    return Path(path).relative_to(root).as_posix()


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip()+'\n')


def _setup(root):
    os.environ.setdefault('MPLCONFIGDIR', str(root/'cache/matplotlib'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'axes.titlesize':14,'axes.titleweight':'bold','axes.labelsize':11,'axes.spines.top':False,'axes.spines.right':False,'axes.edgecolor':'#65717B','text.color':'#26323D','axes.labelcolor':'#26323D','xtick.color':'#52616E','ytick.color':'#52616E','grid.color':'#E6E9EC','figure.facecolor':'white','axes.facecolor':'white','svg.fonttype':'none'})
    return plt


def _save(fig, out, name, rows, sources):
    fig.savefig(out/f'{name}.svg', bbox_inches='tight', metadata={'Date':None})
    fig.savefig(out/f'{name}.png', dpi=160, bbox_inches='tight')
    (out/f'{name}.json').write_text(json.dumps({'sources':sources,'rows':rows},indent=2,ensure_ascii=False))
    import matplotlib.pyplot as plt
    plt.close(fig)
    return name


def _training(root, out, plt):
    paths=sorted((root/'results/pilot-v1/training').glob('seed_*/manifest.json'))
    manifests=[_read(p) for p in paths]
    if not manifests:return [],[]
    fig,axes=plt.subplots(1,2,figsize=(11,3.8),layout='constrained')
    rows=[]
    for i,m in enumerate(manifests):
        rr=m.get('losses',[])
        if not rr:continue
        color=['#2869A6','#C27A2C'][i%2]
        style=['-','--'][i%2]
        for ax,key,label in zip(axes,['loss','answer_loss'],['Training objective','Answer-token loss']):
            ax.plot([r['step'] for r in rr],[r[key] for r in rr],label=f"Seed {m['seed']}",color=color,linestyle=style,lw=1.7)
            ax.set_xlabel('Optimization step');ax.set_ylabel('Cross-entropy (nats)');ax.set_title(label);ax.set_yscale('log');ax.grid(axis='y');ax.legend(frameon=False)
        rows.extend(rr)
    fig.suptitle('E1: independently initialized 20.7M-parameter models',fontsize=15,fontweight='bold')
    _save(fig,out,'e1_training',rows,[_path(root,p) for p in paths])
    return manifests,['e1_training']


def _collections(root):
    collections=[]
    for path in sorted((root/'results/pilot-v1').rglob('manifest.json')):
        m=_read(path)
        if isinstance(m,dict) and 'competence' in m and (path.parent/'D3.npz').exists():
            info=m.get('model_info',{})
            name=info.get('name') or info.get('model_id') or info.get('id') or path.parent.name
            collections.append((str(name),path.parent,m))
    return collections


def _competence(root,out,plt,collections):
    if not collections:return []
    concepts=['arithmetic','comparison','negation','syntax']
    data=np.array([[m['competence'].get('D3',{}).get(c,{}).get('accuracy',np.nan) for c in concepts] for _,_,m in collections])
    fig,ax=plt.subplots(figsize=(9,max(3.2,.55*len(collections)+1.8)),layout='constrained')
    im=ax.imshow(data,vmin=0,vmax=1,cmap='Blues',aspect='auto')
    ax.set_xticks(range(4),concepts);ax.set_yticks(range(len(collections)),[n.replace('HuggingFaceTB/','').replace('Qwen/','').replace('allenai/','') for n,_,_ in collections]);ax.set_title('D3 held-out task competence')
    for i in range(len(collections)):
        for j in range(4):
            if np.isfinite(data[i,j]):ax.text(j,i,f'{data[i,j]*100:.1f}%',ha='center',va='center',color='white' if data[i,j]>.65 else '#26323D')
    fig.colorbar(im,ax=ax,label='Correct vs foil accuracy; chance = 50%',shrink=.8)
    rows=[{'model':n,'concept':c,'accuracy':float(data[i,j]),'n':m['competence']['D3'].get(c,{}).get('n')} for i,(n,_,m) in enumerate(collections) for j,c in enumerate(concepts) if np.isfinite(data[i,j])]
    _save(fig,out,'competence',rows,[_path(root,p/'manifest.json') for _,p,_ in collections]);return ['competence']


def _find_metrics(root,stage):
    base=root/'results/pilot-v1'
    nested=sorted((base/stage).glob('*/metrics.json'))
    if nested:
        pairs=[]
        for p in nested:
            item=_read(p);item['_source']=_path(root,p)
            pairs.append(item)
        return base/stage,{'pairs':pairs,'source_paths':[_path(root,p) for p in nested]}
    candidates=[base/stage/f'{stage}_metrics.json',base/stage/'metrics.json',base/stage.lower()/f'{stage}_metrics.json',base/stage.lower()/'metrics.json',base/f'{stage}_metrics.json']
    candidates+=list(base.rglob(f'{stage}_metrics.json'))
    for p in candidates:
        if p.exists():return p,_read(p)
    return None,None


def _method_rows(metrics):
    """Normalize the engine's pair/method metrics without changing estimands."""
    if not metrics:return []
    result=[]
    pairs=metrics.get('pairs',[])
    if isinstance(pairs,dict):pairs=[dict(v,pair=k) for k,v in pairs.items()]
    if not pairs and ('methods' in metrics or 'results' in metrics):pairs=[metrics]
    for pair in pairs:
        pname=pair.get('pair',pair.get('name','model pair'))
        if isinstance(pname,list):pname=' ↔ '.join(map(str,pname))
        methods=pair.get('methods',pair.get('results',{}))
        if isinstance(methods,list):methods={m['method']:m for m in methods}
        for name,m in methods.items():
            summary=m.get('summary',m.get('score',m.get('heldout',m.get('statistics',m))))
            if not isinstance(summary,dict):summary={'mean':summary}
            mean=summary.get('mean',m.get('mean'))
            ci=summary.get('ci',m.get('ci'))
            if mean is not None:result.append({'pair':str(pname),'method':name,'mean':float(mean),'ci':ci,'raw':m,'pair_raw':pair})
    return result


def _method_chart(root,out,plt,stage,rows,source):
    if not rows:return []
    names=list(dict.fromkeys(r['pair'] for r in rows)); n=len(names)
    fig,axes=plt.subplots(n,1,figsize=(10,max(3.3*n,4)),squeeze=False,layout='constrained')
    export=[]
    for ax,pair in zip(axes[:,0],names):
        rr=[r for r in rows if r['pair']==pair]
        for i,r in enumerate(rr):
            c=COLORS.get(r['method'],'#2869A6')
            ax.plot(r['mean'],i,'o',color=c,markersize=7)
            if r['ci'] is not None:ax.plot(r['ci'],[i,i],color=c,lw=1.8)
            ax.annotate(_num(r['mean']),(r['mean'],i),xytext=(7,5),textcoords='offset points',fontsize=9)
            export.append({k:v for k,v in r.items() if k not in ('raw','pair_raw')})
        ax.set_yticks(range(len(rr)),[METHODS.get(r['method'],r['method']) for r in rr]);ax.invert_yaxis();ax.axvline(0,color='#56616A',lw=.8);ax.grid(axis='x');ax.set_title(pair);ax.set_xlabel('Held-out causal agreement' if stage=='E4' else 'Held-out response agreement');ax.set_xlim(-1.05,1.05)
    fig.suptitle(f'{stage}: method comparison · 95% wrapper-cluster intervals',fontsize=14,fontweight='bold')
    sources=list(dict.fromkeys(r['pair_raw'].get('_source',_path(root,source)) for r in rows))
    name=f'{stage.lower()}_methods';_save(fig,out,name,export,sources);return [name]


def _markdown_table(rows):
    if not rows:return '정렬 평가가 아직 완료되지 않아 측정값을 제시하지 않습니다.'
    lines=['| 모델 쌍 | 방법 | 독립 평가 평균 | 95% CI | 후보 coverage |','|---|---|---:|---|---:|']
    for r in rows:lines.append(f"| {r['pair']} | {METHODS.get(r['method'],r['method'])} | {_num(r['mean'])} | {_ci(r['ci'])} | {_num(r['raw'].get('coverage'))} |")
    return '\n'.join(lines)


def _comparison_table(metrics):
    lines=['| 모델 쌍 | 방법 차이 | Δ | Δ 95% CI | p | BH q |','|---|---|---:|---|---:|---:|']
    for pair in (metrics or {}).get('pairs',[]):
        for name,r in pair.get('comparisons',{}).items():
            lines.append(f"| {pair['pair']} | {name} | {_num(r.get('effect'))} | {_ci(r.get('bootstrap',{}).get('ci'))} | {_num(r.get('pvalue'),4)} | {_num(r.get('qvalue'),4)} |")
    return '\n'.join(lines) if len(lines)>2 else '대응 차이 검정은 아직 미측정입니다.'


def _structure_figures(root,out,plt,stages):
    made=[]
    e1=stages['E1']['metrics']
    if e1:
        pairs=e1.get('pairs',[]);methods=['random','activation','rank','semantic','sign_semantic','label_shuffled','weight']
        arr=np.array([[p['results'].get(m,{}).get('mean',np.nan) for m in methods] for p in pairs])
        fig,ax=plt.subplots(figsize=(10,3.5),layout='constrained')
        im=ax.imshow(arr,cmap='RdBu_r',vmin=-1,vmax=1,aspect='auto')
        labels=[METHODS[m].replace(' ','\n').replace('Label-shuffled','Label-\nshuffled') for m in methods]
        ax.set_xticks(range(len(methods)),labels);ax.set_yticks(range(len(pairs)),[p['pair'] for p in pairs]);ax.set_title('E1: trained and untrained control correspondence')
        for i in range(len(pairs)):
            for j in range(len(methods)):
                if np.isfinite(arr[i,j]):ax.text(j,i,f'{arr[i,j]:.3f}',ha='center',va='center',color='white' if abs(arr[i,j])>.65 else '#26323D')
                else:ax.text(j,i,'N/A',ha='center',va='center',color='#7B858E')
        fig.colorbar(im,ax=ax,label='D3 within-wrapper Pearson',shrink=.8)
        rows=[{'pair':p['pair'],'method':m,'mean':float(arr[i,j])} for i,p in enumerate(pairs) for j,m in enumerate(methods) if np.isfinite(arr[i,j])]
        made.append(_save(fig,out,'e1_seed_heatmap',rows,e1['source_paths']));stages['E1']['figures'].append('e1_seed_heatmap')
    pairs=(stages['E2']['metrics'] or {}).get('pairs',[])
    if pairs:
        fig,axes=plt.subplots(1,len(pairs),figsize=(4.2*len(pairs),4),squeeze=False,layout='constrained');export=[];sources=[]
        for ax,p in zip(axes[0],pairs):
            path=root/p['_source'];csvpath=path.parent/'matches.csv'
            rr=list(csv.DictReader(csvpath.open()));rr=[r for r in rr if r['method']=='activation'];xs=sorted(set(int(r['source_layer']) for r in rr));ys=sorted(set(int(r['target_layer']) for r in rr));counts=np.zeros((len(xs),len(ys)),int)
            for r in rr:counts[xs.index(int(r['source_layer'])),ys.index(int(r['target_layer']))]+=1
            im=ax.imshow(counts,cmap='Blues',vmin=0,vmax=16,aspect='equal');ax.set_xticks(range(len(ys)),ys);ax.set_yticks(range(len(xs)),xs);ax.set_xlabel('Target layer (zero-based)');ax.set_ylabel('Source layer (zero-based)');ax.set_title(p['pair'])
            for i,x in enumerate(xs):
                for j,y in enumerate(ys):
                    ax.text(j,i,str(counts[i,j]),ha='center',va='center',color='white' if counts[i,j]>9 else '#26323D');export.append({'pair':p['pair'],'source_layer':x,'target_layer':y,'matched_neurons':int(counts[i,j])})
            sources.append(_path(root,csvpath))
        fig.suptitle('E2: flexible layer mapping · D2 activation assignment',fontsize=14,fontweight='bold')
        fig.colorbar(im,ax=axes[0].tolist(),label='Matched candidate neurons',shrink=.8)
        made.append(_save(fig,out,'e2_layers',export,sources));stages['E2']['figures'].append('e2_layers')
    pairs=(stages['E4']['metrics'] or {}).get('pairs',[])
    if pairs:
        panels=[];export=[];sources=[]
        for p in pairs:
            name=p['pair'];left_name,right_name=name.split('_',1)
            pa=root/'results/pilot-v1/causal'/left_name/'D4_causal.npz';pb=root/'results/pilot-v1/causal'/right_name/'D4_causal.npz'
            mapping_path=(root/p['_source']).parent/'frozen_mappings.json'
            if not pa.exists() or not pb.exists() or not mapping_path.exists():continue
            a,b=np.load(pa),np.load(pb);mapping=_read(mapping_path)['maps']['semantic_causal'];norm=p['normalization'];ia,ib=mapping['source'],mapping['target']
            points=[]
            for concept in sorted(set(a['concepts'].tolist())):
                mask=a['concepts']==concept
                for index,(i,j) in enumerate(zip(ia,ib)):
                    for k,mode in enumerate(['zero','mean','patch']):
                        row={'pair':name,'concept':concept,'matched_pair':index,'intervention':mode,'a_effect':float(a['effects'][mask,i,k].mean()/norm['a']),'b_effect':float(b['effects'][mask,j,k].mean()/norm['b'])};points.append(row);export.append(row)
            panels.append((name,left_name,right_name,points));sources.extend([_path(root,pa),_path(root,pb),_path(root,mapping_path)])
        if panels:
            fig,axes=plt.subplots(1,len(panels),figsize=(4.3*len(panels),4.3),squeeze=False,layout='constrained')
            for ax,(name,left,right,points) in zip(axes[0],panels):
                for k,mode in enumerate(['zero','mean','patch']):
                    pp=[r for r in points if r['intervention']==mode];ax.scatter([r['a_effect'] for r in pp],[r['b_effect'] for r in pp],s=24,alpha=.65,color=['#2869A6','#C27A2C','#A04F83'][k],marker=['o','s','^'][k],label=mode)
                ax.axhline(0,color='#7B858E',lw=.7);ax.axvline(0,color='#7B858E',lw=.7);ax.set_title(name);ax.set_xlabel(f'{left}: normalized effect');ax.set_ylabel(f'{right}: normalized effect');ax.ticklabel_format(style='sci',axis='both',scilimits=(-2,2));ax.legend(frameon=False,fontsize=9)
            fig.suptitle('E4: D4 mean effect by matched neuron, task and intervention',fontsize=14,fontweight='bold')
            made.append(_save(fig,out,'e4_causal_scatter',export,sources));stages['E4']['figures'].append('e4_causal_scatter')
    return made


def _verdict(metrics):
    if not metrics:return 'INCONCLUSIVE'
    v=metrics.get('verdict',metrics.get('hypothesis_verdict','INCONCLUSIVE'))
    return v if v in ('SUPPORTED','NOT SUPPORTED','INCONCLUSIVE') else 'INCONCLUSIVE'


def _interpretation(stage, metrics):
    if not metrics:return '이 단계의 최종 정렬 평가가 아직 완료되지 않았습니다.'
    lines=[]
    key={'E1':'activation_minus_random','E2':'activation_minus_random','E3':'semantic_minus_activation','E4':'semantic_causal_minus_semantic'}[stage]
    for pair in metrics.get('pairs',[]):
        c=pair.get('comparisons',{}).get(key,{})
        if not c:continue
        q=c.get('qvalue');delta=c.get('effect')
        finding='양의 차이가 관찰됨' if delta is not None and delta>0 else '제안 방법의 양의 개선이 관찰되지 않음'
        significance='BH 보정 후 유의 기준 q<0.05 충족' if q is not None and q<.05 else 'BH 보정 후 유의 기준 q<0.05 미충족'
        lines.append(f"- **{pair['pair']}**: {key} Δ={_num(delta)}, Δ 95% CI {_ci(c.get('bootstrap',{}).get('ci'))}, q={_num(q,4)}. {finding}; {significance}.")
    if stage=='E1':lines.append('학습 전 대조군에서도 대응이 나타나면 공유된 아키텍처·표면 패턴만으로 상관이 생길 수 있습니다. 학습 모델의 산술·부정 과제 능력이 약한 조건도 있으므로 H1의 일반적 기능 보존 주장은 판단을 보류합니다.')
    elif stage=='E2':lines.append('모델 쌍별 능력 차이와 같은 yes/no 답변 공간의 영향을 분리해야 합니다. 반응 상관만으로 이종 모델의 동일 의미 기능을 확정하지 않습니다.')
    elif stage=='E3':lines.append('주기능이라고 부르는 값은 네 합성 과제의 참·거짓 선택성 proxy입니다. 독립 반응 지표의 개선과 보편적 의미 해석의 개선은 별개입니다.')
    else:lines.append('각 모델 내부 개입의 D4 효과를 비교했습니다. 일부 모델 쌍의 개선만으로 모든 모델 계열에 일반화하지 않으며, 낮은 과제 능력과 적은 wrapper 수가 해석을 제한합니다.')
    return '\n'.join(lines)


def render_reports(root=None,max_stage=None):
    root=Path(root or Path(__file__).resolve().parents[1]).resolve()
    reports=root/'reports';reports.mkdir(exist_ok=True)
    out=root/'artifacts/figures';out.mkdir(parents=True,exist_ok=True)
    plt=_setup(root)
    manifests,figures=_training(root,out,plt)
    if max_stage is not None and max_stage not in STAGES:raise ValueError('max_stage must be E1, E2, E3 or E4')
    stage_limit=int(max_stage[1]) if max_stage else 4
    collections=_collections(root)
    if stage_limit==1:collections=[row for row in collections if row[0].startswith(('seed','untrained'))]
    figures+=_competence(root,out,plt,collections)
    stages={}
    for stage in STAGES:
        p,m=_find_metrics(root,stage) if int(stage[1])<=stage_limit else (None,None);rows=_method_rows(m)
        fs=_method_chart(root,out,plt,stage,rows,p) if p else []
        stages[stage]={'path':p,'metrics':m,'rows':rows,'figures':fs,'verdict':_verdict(m)};figures+=fs
    figures+=_structure_figures(root,out,plt,stages)
    date=datetime.now(ZoneInfo('Asia/Seoul')).strftime('%Y-%m-%d %H:%M KST')
    summary=['| Experiment | Hypothesis | Main Metric | Baseline | Proposed | Improvement | CI | Verdict |','|---|---|---|---:|---:|---:|---|---|']
    for stage,(title,hyp,proposed,baseline) in STAGES.items():
        s=stages[stage];rr=s['rows'];primary=[r for r in rr if stage!='E1' or 'untrained' not in r['pair']];pa=[r for r in primary if r['method']==proposed];ba=[r for r in primary if r['method']==baseline]
        # Do not average pair intervals or pool unlike pair estimands.
        if len(pa)==len(ba)==1 and pa[0]['pair']==ba[0]['pair']:
            p,b=pa[0],ba[0];delta=p['mean']-b['mean'];comparison=p['pair_raw'].get('comparisons',{}).get(f'{proposed}_minus_{baseline}',{});val=[_num(b['mean']),_num(p['mean']),_num(delta),_ci(comparison.get('bootstrap',{}).get('ci'))]
        elif rr:val=['모델 쌍별','모델 쌍별','모델 쌍별','상세 표 참조']
        else:val=['미측정']*4
        metric='D4 causal effect agreement' if stage=='E4' else 'D3 response agreement'
        summary.append(f"| {stage} | {hyp} | {metric} | {' | '.join(val)} | {s['verdict']} |")
    summary='\n'.join(summary)
    limitations='''이 연구는 제한된 합성 참·거짓 과제의 파일럿입니다. 학습·탐색·정렬·독립 반응 평가·독립 인과 평가를 분리했지만 의미 문법은 공유합니다. 여섯 wrapper 군집의 부트스트랩 신뢰구간과 무작위화 검정은 탐색적입니다. 뉴런 개수를 독립 표본 수로 사용하지 않습니다. BH q는 모델 쌍별 비교군 안에서 보정한 값이며 연구 전체의 다중검정 보정이 아닙니다. Random 기준선은 쌍당 한 번 고정한 매칭으로, 그 무작위 매칭 자체의 변동은 CI에 포함되지 않습니다. 모델의 과제 능력이 낮으면 대응 실패를 기능 보존의 기각으로 해석하지 않습니다. 활성값 유사성·의미 설명·인과 효과 일치를 구분하며, 긍정적 결과도 뉴런 복사나 모델 병합의 안전성을 보장하지 않습니다.'''
    methodology='''- **E1:** 서로 다른 초기 가중치로 학습한 소형 RMSNorm·RoPE·SwiGLU decoder 두 개. 초기/중간/최종 체크포인트와 학습 로그를 보존합니다.
- **E2:** 공개 Base 모델의 같은 원문에 대한 모델별 토큰화를 사용합니다. 약 20/40/60/80% 깊이에서 gate, up, SwiGLU product, 부호 구간과 down 기여를 관찰합니다.
- **E3:** random, activation, rank, semantic, sign-aware semantic, label-shuffled 기준선을 비교합니다. D1에서 후보 선택, D2에서 정렬을 고정하고 D3에서 독립 반응을 평가합니다.
- **E4:** 동일 모델 내부 zero/mean/matched-patch 개입의 정답–대비 답변 sequence log-likelihood margin 변화를 측정합니다. D2로 정렬·결합을 결정하고 D4에서 평가합니다. 인과 효과와 통계는 FP32 이상으로 처리합니다.
- **통계:** 동일 wrapper의 모든 개념을 함께 재표집합니다. 개별 뉴런의 수를 연구 반복 수로 해석하지 않습니다. 보고서의 수치는 저장된 JSON/NPZ/Parquet에서 자동 생성됩니다.'''
    training='\n'.join(f"- Seed {m['seed']}: {m['parameters']:,} parameters, {m['steps']:,} steps, {m['elapsed_seconds']:.1f} s; 초기 SHA256 `{m['initial_hash']}`." for m in manifests) or '학습 측정값 없음.'
    for stage,(title,hyp,_,_) in STAGES.items():
        s=stages[stage];status='실제 결과 파일 확보' if s['metrics'] else '정렬·최종 평가 대기'
        source=f"[측정 원본](../{_path(root,s['path'])})" if s['path'] else '최종 정렬 지표 파일이 아직 없습니다.'
        imgs='\n\n'.join(f'![{stage} method comparison](../artifacts/figures/{n}.svg)' for n in s['figures'])
        text=f'# {stage}: {title}\n\n갱신: {date}. 상태: **{status}**. 가설 판단: **{s["verdict"]}**.\n\n연구 질문: {hyp}.\n\n{source}\n\n{_interpretation(stage,s["metrics"])}\n\n{_markdown_table(s["rows"])}\n\n## 대응 차이 검정\n\n{_comparison_table(s["metrics"])}\n\n{imgs}\n\n## 방법과 해석\n\n{methodology}\n\n{limitations}\n\n## 검증·다음 단계\n\n[데이터 설계와 shortcut 한계](DATA_DESIGN_LIMITATIONS.md), [선행연구](../literature_review.md), [재현 소스](../src/experiment.py)를 함께 확인해야 합니다. 낮은 능력, 부호별 차이, 미매칭 및 부정적 결과를 포함해 다음 단계의 독립 평가 가능성을 판단합니다.'
        if stage=='E1':text+='\n\n## 실제 학습 기록\n\n'+training+'\n\n![E1 training](../artifacts/figures/e1_training.svg)' if manifests else ''
        _write(reports/f'{stage}_report.md',text)
    _write(reports/'EXECUTIVE_SUMMARY.md',f'# Executive Summary\n\n갱신: {date}. 실행 완료와 가설 지지는 다른 판단입니다.\n\n{summary}\n\n{limitations}\n\n'+ '\n'.join(f'- [{e} 상세 보고서]({e}_report.md)' for e in STAGES))
    critique='''# Research Critique

## 타당성과 대체 설명

1. 산술 오답이 정답의 ±1인 구성은 parity shortcut을 허용하고, 괄호 오류는 개수 단서로 검출할 수 있습니다. 부정 과제에는 속성 이름의 동일성·숫자 접미사 단서가 있습니다. 이 과제의 성공을 일반 산술·구문·논리 능력의 획득으로 해석할 수 없습니다.
2. 같은 여섯 wrapper를 여러 개념에 적용했습니다. 개념×wrapper를 24개 독립 군집으로 세지 않고 wrapper 여섯 개로 처리합니다. 작은 군집 수, 단일 데이터 생성 시드 및 선택한 모델 쌍은 일반화 범위를 제한합니다.
3. E1은 짧은 합성 과제 학습이며 자연어 사전학습 LLM의 보편적 성질을 검증하지 않습니다. 두 초기화만으로 시드 분산을 정밀하게 추정할 수 없습니다.
4. 의미 fingerprint는 사전 정의한 네 가지 과제의 참·거짓 대비입니다. 뉴런의 완전한 의미 설명이나 독립적으로 검증된 단일 주기능이라고 부를 수 없습니다. UNKNOWN을 숨기거나 설명 모델의 판단을 증거로 대체하지 않습니다.
5. 후보 탐색에는 선택 편향이 있습니다. 기능 후보와 무작위 후보를 모두 포함해도 전체 뉴런 모집단의 보존율을 추정하는 표본은 아닙니다.
6. 상대 깊이 정렬은 구조적 동등성을 보장하지 않습니다. 같은 원문과 답변을 사용해도 토크나이저별 경계·길이·확률 척도 차이가 남습니다.
7. 단일 뉴런 zero/mean/patch는 세 개입의 정합성을 검사할 수 있으나 완전한 회로를 복원하지 않습니다. 주변 회로·보상 경로·분포 외 개입의 영향을 받습니다.
8. 높은 held-out 상관만으로 기능적 동등성, 인과 추상화, transplant 성공을 주장할 수 없습니다. 동형 모델도 무작위 초기화에서 구조적 상관을 보일 수 있어 untrained control이 필요합니다.
9. Random 기준선은 모델 쌍당 하나의 고정 매칭입니다. 군집 CI는 무작위 매칭 seed의 변동을 포함하지 않습니다. BH 보정은 모델 쌍 안의 비교군 범위이며 연구 전체 보정으로 제시하면 안 됩니다.
10. 부분 정렬 임계값은 D2 shuffled row-maximum 분포의 탐색적 기준입니다. 개별 뉴런의 유의성이나 전체 뉴런 모집단의 보존율로 해석할 수 없습니다. 학습 중 기능 변화, 완전히 새로운 과제군의 일반화, dose-response와 회로 보존은 현재 결과 범위를 넘어섭니다.

## 선행연구와 기준선

뉴런 정렬·모델 병합·선택적 이식은 이미 연구되었습니다. [문헌 검토](../literature_review.md)를 근거로 독립 초기화와 이종 계열의 held-out 인과 효과 비교에 질문을 한정합니다. 단일 레이어 가중치 cosine은 완전한 Git Re-Basin이 아닙니다. SAE, optimal transport 및 회로 단위 정렬을 직접 실행하지 않았다면 그 방법들보다 우월하다고 주장할 수 없습니다.

## 후속 검증 조건

새 데이터 버전에서 shortcut을 차단하고, 더 많은 wrapper·독립 초기화·모델 쌍·학습 seed를 사전 고정해야 합니다. D3/D4를 본 뒤 동일 버전의 후보나 임계값을 바꿔 얻은 결과는 본 확인 분석으로 재사용하지 않습니다. 실패한 실행과 수정 이유는 삭제하지 않고 별도 로그로 보존합니다.
'''
    if (reports/'ENGINE_AUDIT.md').exists():critique+='\n\n[실행 코드·실제 E1 결과 감사](ENGINE_AUDIT.md)는 데이터 행 정렬, 저장된 매칭의 재계산, 초기화 독립성, 부정적 대조군과 재시작 한계를 구체적으로 기록합니다.\n'
    _write(reports/'RESEARCH_CRITIQUE.md',critique)
    nxt='''# Next Experiments

| 우선순위 | 실험 | 예상 기여 | 난이도·자원 | 주요 실패 요인 |
|---|---|---|---|---|
| 1 | Shortcut을 차단한 신규 benchmark와 5개 이상 독립 초기화 | 파일럿의 대체 설명과 시드 변동 검증 | 중간; 소형 모델 여러 회 재학습·GPU 수 시간 이상 | 일반화 실패, 합성 분포 의존 |
| 2 | 동일 모델의 여러 체크포인트에서 기능 형성 추적 | 주기능·부차 반응의 학습 궤적 구분 | 중간; 체크포인트별 수집·저장 | 반응 확장을 recursive generalization으로 과해석 |
| 3 | One-to-many / neuron-group causal alignment | 분산된 기능과 단일 뉴런 대응의 한계 검증 | 높음; 조합 탐색·개입 수 급증 | 정렬기의 과적합, 불안정한 그룹 선택 |
| 4 | Cross-model neuron transplantation | 인과 일치가 실제 이식을 예측하는지 검증 | 높음; 표현 공간 보정·안전한 평가 | 다운스트림 회로 비호환, 부작용 |
| 5 | Circuit-preserving selective model merging | 선택적 지식 이전과 일반 능력 보존 평가 | 매우 높음; 회로 추정·다수 benchmark | 표현 차원·tokenizer·학습 이력의 차이 |

현재 결과의 미측정 부분을 먼저 완료하고 가설별 독립 평가 결과를 확인해야 합니다. 숫자 예산은 실제 모델·후보 수의 단위 실행 시간을 다시 측정해 정합니다. 위 자원 표현은 측정된 완료 시간이 아닌 후속 연구 계획입니다.
'''
    _write(reports/'NEXT_EXPERIMENTS.md',nxt)
    completed=[e for e,s in stages.items() if s['metrics']]
    report=f'# Final Research Report — Native Neuron Conservation\n\n갱신: {date}. 결과 파일이 확인된 단계: **{", ".join(completed) or "없음"}**. 미완료 단계의 가설 판단은 `INCONCLUSIVE`이며 구현 완료를 실제 실행 완료로 해석하지 않습니다.\n\n## 연구 배경\n\nGoodfire의 [Neural Networks Are Already Clean](https://already-clean.goodfire.com/)을 검증 대상 작업 가설로 삼습니다. 원본 SwiGLU 뉴런의 활성·주기능 proxy·독립 인과 효과가 모델 간에 어떻게 대응하는지를 별개로 평가합니다. [선행연구 검토](../literature_review.md)는 ARM·LED-Merging·HeteroFusion·Git Re-Basin·Rosetta·SAE와의 차이를 기록합니다.\n\n## 가설별 결과\n\n{summary}\n\n## 모델·데이터·방법\n\n{methodology}\n\n{training}\n\n실제 모델 revision·라이선스는 [모델 manifest](../configs/models.json), 데이터 생성 규칙은 [데이터 protocol](../configs/data_protocol.json), 사전 설정은 [pilot config](../configs/pilot.json)에 기록합니다.\n\n## 결과와 시각자료\n\n'+ '\n\n'.join(f'### {e}\n\n[{e} 보고서]({e}_report.md)\n\n{_markdown_table(s["rows"])}'+''.join(f'\n\n![{e}](../artifacts/figures/{n}.svg)' for n in s['figures']) for e,s in stages.items())+f'\n\n## 해석과 한계\n\n{limitations}\n\n[상세 비판](RESEARCH_CRITIQUE.md)과 [후속 실험 우선순위](NEXT_EXPERIMENTS.md)를 참조합니다.'
    report+='\n\n## 대응 비교의 통계와 판단 근거\n\n'+'\n\n'.join(f'### {e}\n\n{_interpretation(e,s["metrics"])}\n\n{_comparison_table(s["metrics"])}' for e,s in stages.items())
    env=_read(root/'results/pilot-v1/environment.json',{})
    if env:
        environment=f"GPU: **{env.get('gpu_name','미측정')}**. Python {env.get('python','미측정')}, PyTorch {env.get('packages',{}).get('torch','미측정')}, CUDA runtime {env.get('cuda','미측정')}. [실제 환경 원본](../results/pilot-v1/environment.json)에 패키지 버전·디스크·초기 Git commit을 기록했습니다."
        report+='\n\n## 실행 환경과 재현성\n\n'+environment
    if 'competence' in figures:report+='\n\n## 모델별 과제 능력\n\n![D3 competence](../artifacts/figures/competence.svg)\n\n정답과 대비 답변 중 더 높은 전체 continuation likelihood를 가지는 후보를 선택했습니다. 우연 수준은 50%이며 낮은 능력의 과제도 대조군으로 보존합니다.'
    _write(reports/'FINAL_RESEARCH_REPORT.md',report)
    readme=f'# Native Neuron Conservation Pilot\n\n독립적으로 학습된 모델에서 원본 뉴런의 **활성 반응·의미 proxy·인과 역할**이 보존되는지를 검증합니다. [MASTER.md](MASTER.md)에 따른 연구이며, 결과는 각 단계의 실제 측정 파일에서 자동 생성됩니다.\n\n갱신: **{date}**. 정렬 평가 결과가 있는 단계: **{", ".join(completed) or "아직 없음"}**.\n\n## 실험 결과\n\n{summary}\n\n{limitations}\n\n'
    if 'competence' in figures:readme+='![Held-out competence](artifacts/figures/competence.svg)\n\n정답과 대비 답변의 전체 continuation likelihood를 비교한 D3 정확도입니다. 우연 수준은 50%입니다.\n\n'
    for e,s in stages.items():
        if s['figures']:readme+=f'### {e} — {STAGES[e][0]}\n\n'+_interpretation(e,s['metrics'])+'\n\n'+ '\n\n'.join(f'![{e} method comparison](artifacts/figures/{n}.svg)' for n in s['figures'])+f'\n\n[{e} 방법·원본 데이터·통계](reports/{e}_report.md)\n\n'
    if manifests:readme+='## 독립 초기화 모델 학습\n\n![E1 training](artifacts/figures/e1_training.svg)\n\n'+training+'\n\n학습 손실 감소는 과제 일반화나 뉴런 보존의 증거를 대신하지 않습니다.\n\n'
    readme+='''## 재현과 자료

```bash
make smoke
make e1
make e2
make e3
make e4
make pilot
make report
```

- [최종 연구 보고서](reports/FINAL_RESEARCH_REPORT.md)
- [Executive summary](reports/EXECUTIVE_SUMMARY.md)
- [비판적 검토](reports/RESEARCH_CRITIQUE.md)
- [다음 실험](reports/NEXT_EXPERIMENTS.md)
- [문헌 검토](literature_review.md)
- [데이터 설계 한계](reports/DATA_DESIGN_LIMITATIONS.md)
- [실험 코드](src/experiment.py) · [보고서 생성 코드](src/reporting.py)

각 그림 옆 JSON은 실제 그림 값과 원본 파일 경로를 보존합니다. 모델 가중치와 캐시는 저장소에 업로드하지 않고, 정확한 revision과 데이터·체크포인트 해시로 추적합니다. 유료 외부 API는 사용하지 않습니다.
'''
    _write(root/'README.md',readme)
    return {'completed_stages':completed,'figures':figures,'reports':[str(p.relative_to(root)) for p in reports.glob('*.md')]}


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--max-stage',choices=list(STAGES));args=parser.parse_args()
    print(json.dumps(render_reports(max_stage=args.max_stage),indent=2,ensure_ascii=False))
