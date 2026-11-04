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
    return {'id':name,'title':spec.get('title',name),'path':paths['svg'].relative_to(root).as_posix(),'png':paths['png'].relative_to(root).as_posix(),'receipt':paths['json'].relative_to(root).as_posix(),'note':spec.get('note','')}


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
        fig,ax=plt.subplots(figsize=(max(7,.8*len(colnames)+3),max(3,.48*len(rownames)+1.8)),layout='constrained')
        lo=spec.get('vmin',float(min(0,finite.min())));hi=spec.get('vmax',float(finite.max()))
        if hi==lo:hi=lo+1
        cmap=plt.get_cmap('Blues').copy();cmap.set_bad('#ECEFF1')
        im=ax.imshow(grid,cmap=cmap,vmin=lo,vmax=hi,aspect='auto');ax.set_xticks(range(len(colnames)),colnames,rotation=spec.get('rotation',0));ax.set_yticks(range(len(rownames)),rownames)
        for i in range(len(rownames)):
            for j in range(len(colnames)):
                v=grid[i,j];text='N/A' if not np.isfinite(v) else f'{100*v:.1f}%' if spec.get('percent') else _value(v,3)
                ax.text(j,i,text,ha='center',va='center',color='white' if np.isfinite(v) and (v-lo)/(hi-lo)>.65 else '#26323D',fontsize=10)
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
            ax.annotate(_value(val,3),(val,i),xytext=(6,5),textcoords='offset points',fontsize=9)
        ax.set_yticks(range(len(rr)),[str(r.get(labelkey,r.get('name',i))) for i,r in enumerate(rr)]);ax.set_ylim(len(rr)-.5,-.75);ax.set_xlabel(spec.get('xlabel',spec.get('unit','Value')));ax.axvline(0,lw=.8,color='#65717B');ax.grid(axis='x')
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


def render_followup_reports(root=None,max_stage=None):
    root=Path(root or Path(__file__).resolve().parents[1]).resolve()
    reports=root/'reports/followup-v2';reports.mkdir(parents=True,exist_ok=True)
    out=root/'artifacts/followup-v2/figures';out.mkdir(parents=True,exist_ok=True)
    plt=_setup(root);limit=int(max_stage[1:]) if max_stage else 6
    date=datetime.now(ZoneInfo('Asia/Seoul')).strftime('%Y-%m-%d %H:%M KST')
    snapshots=[]
    for sid,title in STAGES.items():
        path=root/f'results/followup-v2/stages/{sid}.json'
        payload=_json(path) if path.exists() and int(sid[1:])<=limit else {'id':sid,'title':title,'status':'PENDING'}
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
        snapshot={'id':sid,'title':payload.get('title',title),'status':status,'verdict':verdict,'payload':payload,'figures':figures,'sources':sources}
        snapshots.append(snapshot)
        content=f"# {sid} — {snapshot['title']}\n\n갱신: {date}. 실행 상태: **{status}**. 가설 판정: **{verdict}**.\n\n"
        if payload.get('question'):content+='연구 질문: '+payload['question']+'\n\n'
        content+=payload.get('rationale','판정 근거가 아직 보고되지 않았습니다.')+'\n\n'
        if payload.get('competence_gate'):content+='## 과제 능력 조건\n\n'+json.dumps(payload['competence_gate'],ensure_ascii=False,indent=2)+'\n\n'
        content+='## 실제 측정\n\n'+_metric_table(payload.get('metrics',[]))+'\n\n## 비교와 불확실성\n\n'+_comparison_table(payload.get('comparisons',[]))+'\n\n'
        for f in figures:content+=f"![{f['title']}](../../{f['path']})\n\n{f['note']}\n\n[그림 수치와 출처](../../{f['receipt']})\n\n"
        if payload.get('limitations'):content+='## 해석 한계\n\n'+'\n'.join('- '+s for s in payload['limitations'])+'\n\n'
        if payload.get('next_action'):content+='## 다음 단계\n\n'+payload['next_action']+'\n\n'
        if sources:content+='## 원본과 재현\n\n'+'\n'.join(f"- [{s['path']}](../../{s['path']})" for s in sources)+'\n'
        (reports/f'{sid}_REPORT.md').write_text(content)
    table=['| 단계 | 실험 | 실행 상태 | 가설 판정 |','|---|---|---|---|']
    for s in snapshots:table.append(f"| {s['id']} | [{s['title']}](reports/followup-v2/{s['id']}_REPORT.md) | {s['status']} | {s['verdict']} |")
    common='실행 완료와 가설 지지는 별개입니다. 모델이 해당 과제를 학습했는지 먼저 확인하며, 낮은 능력의 대응 실패를 보존 가설의 반증으로 바꾸지 않습니다. 새 데이터·프로토콜·후보·검정 범위를 기록하고 기존 pilot-v1 결과를 보존합니다. 군집·모델 seed·매칭 seed·다중검정 범위가 다른 수치를 임의로 합치지 않습니다. 인과 효과 일치도 이식이나 병합의 유효성을 자동으로 보장하지 않습니다.'
    section=f"## 후속 연구 — followup-v2\n\n갱신: **{date}**. 이 절은 새 단계별 측정 파일에서 생성되었습니다.\n\n"+'\n'.join(table)+'\n\n'+common+'\n\n'
    for s in snapshots:
        p=s['payload']
        if s['status'] in ('PENDING','PLANNED'):continue
        section+=f"### {s['id']} — {s['title']}\n\n**{s['status']} · {s['verdict']}**. "+p.get('rationale','판정 근거 미보고.')+'\n\n'
        for f in s['figures']:section+=f"![{f['title']}]({f['path']})\n\n{f['note']}\n\n[그림 데이터]({f['receipt']})\n\n"
        section+=f"[{s['id']} 측정값·불확실성·원본](reports/followup-v2/{s['id']}_REPORT.md)\n\n"
    (reports/'README_SECTION.md').write_text(section)
    full=section.replace('](reports/','](../../reports/').replace('](artifacts/','](../../artifacts/')
    (reports/'FINAL_FOLLOWUP_REPORT.md').write_text('# Followup-v2 research report\n\n'+full)
    receipt={'generated_kst':date,'stages':[{'id':s['id'],'status':s['status'],'verdict':s['verdict'],'sources':s['sources'],'figures':s['figures']} for s in snapshots],'root_readme_edited':False,'pilot_v1_edited':False}
    (reports/'REPORT_GENERATION.json').write_text(json.dumps(receipt,indent=2,ensure_ascii=False)+'\n')
    return {'stage_status':{s['id']:s['status'] for s in snapshots},'figures':sum(len(s['figures']) for s in snapshots),'section':'reports/followup-v2/README_SECTION.md'}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--max-stage',choices=list(STAGES));args=parser.parse_args()
    print(json.dumps(render_followup_reports(max_stage=args.max_stage),indent=2,ensure_ascii=False))
