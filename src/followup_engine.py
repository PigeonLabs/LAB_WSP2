"""Version-two measurement engine; original pilot artifacts and methods are untouched.

All model scoring is FP32. Neurons are selected on D1 only. Supplied records must
already use the model's calibration-locked prompt variant and valid character
spans. Interventions are same-model, at the shared-answer boundary or statement.
"""
from __future__ import annotations
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import time
import numpy as np
import torch
from .experiment import capture,select_candidates,sequence_margins,_shared_answer_prefix
from .hooks import SwiGLUHook
from .models import TinyDecoder,model_mlps,token_span_indices

VERSION='followup-measurement-v2'


def _digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def _write(path,value):
    Path(path).write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n')


def _save(path,**arrays):
    path=Path(path);temp=path.with_suffix(path.suffix+'.tmp')
    with temp.open('wb') as f:np.savez_compressed(f,**arrays)
    temp.replace(path)


def _selection(selection):
    return {int(k):[int(n) for n in values] for k,values in sorted(selection.items(),key=lambda x:int(x[0]))}


def _records(records,allowed=None):
    if not records or len({r['id'] for r in records})!=len(records):raise ValueError('Nonempty unique row IDs required')
    splits={r['split'] for r in records}
    if len(splits)!=1 or allowed is not None and not splits<=set(allowed):raise ValueError('Unexpected or mixed record splits')
    for r in records:
        a,b=r['span']
        if not 0<=a<b<=len(r['prompt']):raise ValueError('Invalid statement character span')
    return next(iter(splits))


def _prompt(tokenizer,row):
    encoded=tokenizer(row['prompt'],add_special_tokens=False,return_offsets_mapping=True)
    ids=list(encoded['input_ids']);offsets=[tuple(map(int,x)) for x in encoded['offset_mapping']]
    if ids!=tokenizer.encode(row['prompt'],add_special_tokens=False):raise ValueError('Offset tokenizer and scorer disagree')
    indices=token_span_indices(offsets,*row['span'])
    if not indices:raise ValueError('Statement span contains no tokens')
    common=_shared_answer_prefix(tokenizer,row)
    return ids,indices,common


def _pack(model,tokenizer,sequences,device):
    ids=torch.full((len(sequences),max(map(len,sequences))),tokenizer.pad_token_id or 0,dtype=torch.long,device=device)
    mask=torch.zeros_like(ids)
    for i,seq in enumerate(sequences):
        ids[i,:len(seq)]=torch.as_tensor(seq,device=device);mask[i,:len(seq)]=1
    kwargs={'input_ids':ids}
    if not isinstance(model,TinyDecoder):kwargs.update(attention_mask=mask,use_cache=False)
    return kwargs,ids


def _require_fp32(model):
    if next(model.parameters()).dtype!=torch.float32:raise ValueError('Follow-up measurements require FP32 model weights')


@torch.inference_mode()
def capture_views(model,tokenizer,records,selection,device='cuda',batch_size=16):
    """Observe identical units at an answer boundary and over their statement span.

    Span means retain sign-route frequency and per-route product sums divided by
    span token count. These are not the sign of an averaged gate or up value.
    """
    _records(records);_require_fp32(model);model.eval();selection=_selection(selection);mlps=model_mlps(model)
    result={key:[] for key in ['answer_product','answer_gate','answer_up','answer_sign_regime','answer_contribution_norm','span_product','span_gate','span_up','span_contribution_norm','span_sign_frequencies','span_product_by_sign']}
    prompt_lengths=[];span_lengths=[];answer_positions=[]
    for start in range(0,len(records),batch_size):
        rows=records[start:start+batch_size];encoded=[_prompt(tokenizer,r) for r in rows]
        seqs=[ids+common for ids,span,common in encoded];kwargs,_=_pack(model,tokenizer,seqs,device)
        with ExitStack() as stack:
            hooks=[stack.enter_context(SwiGLUHook(mlps[layer],neurons=neurons,positions=None,capture_contribution=False)) for layer,neurons in selection.items()]
            model(**kwargs)
            arrays={k:np.concatenate([h.records[k].numpy() for h in hooks],axis=-1) for k in ['product','gate','up','sign_regime','contribution_norm']}
            for i,(ids,span,common) in enumerate(encoded):
                position=len(ids)+len(common)-1;prompt_lengths.append(len(ids));span_lengths.append(len(span));answer_positions.append(position)
                for key in ['product','gate','up','contribution_norm']:
                    result['answer_'+key].append(arrays[key][i,position])
                    result['span_'+key].append(arrays[key][i,span].mean(0,dtype=np.float64))
                result['answer_sign_regime'].append(arrays['sign_regime'][i,position])
                signs=arrays['sign_regime'][i,span];products=arrays['product'][i,span]
                result['span_sign_frequencies'].append(np.stack([(signs==k).mean(0) for k in range(5)],axis=-1))
                result['span_product_by_sign'].append(np.stack([(products*(signs==k)).mean(0,dtype=np.float64) for k in range(5)],axis=-1))
    arrays={k:np.asarray(v) for k,v in result.items()}
    arrays.update(layers=np.asarray([l for l,ids in selection.items() for _ in ids]),neuron_ids=np.asarray([n for ids in selection.values() for n in ids]),prompt_token_lengths=np.asarray(prompt_lengths),span_token_lengths=np.asarray(span_lengths),answer_positions=np.asarray(answer_positions),row_ids=np.asarray([r['id'] for r in records]),groups=np.asarray([r['group_id'] for r in records]),concepts=np.asarray([r['concept'] for r in records]),labels=np.asarray([r['label'] for r in records]))
    # Explicit aliases make old analysis helpers usable without concealing location.
    arrays['product']=arrays['answer_product'];arrays['sign_regime']=arrays['answer_sign_regime']
    for name,value in arrays.items():
        if np.issubdtype(value.dtype,np.number) and not np.isfinite(value).all():raise ValueError(f'Nonfinite measurement: {name}')
    return arrays


def collect(model,tokenizer,records,output_dir,model_info,selection=None,per_layer=8,device='cuda',batch_size=16):
    """Collect one split; omitted selection is allowed only for D1 discovery.

    Returns a manifest; arrays are saved as measurements.npz. A completed artifact
    is reused only when model, full records, selection, and options match exactly.
    """
    split=_records(records);out=Path(output_dir);out.mkdir(parents=True,exist_ok=True)
    supplied=None if selection is None else _selection(selection)
    plan={'version':VERSION,'model_info':model_info,'records_sha256':_digest(records),'selection':supplied,'per_layer':per_layer,'split':split,'precision':'float32','boundary':'before answer divergence after common answer prefix','span':'mean over character-overlapping statement tokens'}
    signature=_digest(plan)
    if (out/'manifest.json').exists():
        old=json.loads((out/'manifest.json').read_text())
        if old['signature']!=signature:raise ValueError('Collection inputs changed; use a new output directory')
        return old
    if (out/'measurements.npz').exists():raise ValueError('Partial collection exists; preserve it and use a new directory')
    if selection is None and split!='D1':raise ValueError('Candidate selection is restricted to D1')
    start=time.monotonic();_require_fp32(model)
    if selection is None:
        discovery=capture(model,tokenizer,records,batch_size=batch_size,device=device)
        selection=select_candidates(discovery,records,per_layer=per_layer,seed=1729)
    selection=_selection(selection)
    _write(out/'selection.json',{'selection':selection,'basis':'D1 half contrast/half random' if supplied is None else 'frozen supplied selection'})
    arrays=capture_views(model,tokenizer,records,selection,device,batch_size)
    arrays['margins'],arrays['answer_token_counts']=sequence_margins(model,tokenizer,records,device,batch_size)
    _save(out/'measurements.npz',**arrays)
    competence={c:{'n':int(np.sum(arrays['concepts']==c)),'accuracy':float(np.mean(arrays['margins'][arrays['concepts']==c]>0))} for c in sorted(set(arrays['concepts']))}
    manifest={'signature':signature,'plan':plan,'selection':selection,'n':len(records),'neurons':len(arrays['neuron_ids']),'competence':competence,'elapsed_seconds':time.monotonic()-start,'device':str(device),'measurements_sha256':hashlib.sha256((out/'measurements.npz').read_bytes()).hexdigest()}
    _write(out/'manifest.json',manifest)
    return manifest


def intervention_units(selection,group_per_layer=4,singles_per_layer=2):
    """Fixed D1-candidate groups: functional/random mixture, no outcome ranking."""
    selection=_selection(selection);units=[]
    for layer,neurons in selection.items():
        half=len(neurons)//2
        if group_per_layer<2 or group_per_layer>len(neurons) or singles_per_layer!=2:raise ValueError('Need valid mixed group size and exactly two singles/layer')
        nf=group_per_layer//2;nr=group_per_layer-nf
        if nf>half or nr>len(neurons)-half:raise ValueError('Group exceeds functional/random candidate strata')
        mixed=neurons[half-nf:half]+neurons[-nr:]
        for tag,neuron in [('functional',neurons[half-1]),('random',neurons[-1])]:
            units.append({'id':f'L{layer}_N{neuron}_{tag}','kind':'single','units_by_layer':{layer:[neuron]}})
        units.append({'id':f'L{layer}_group{group_per_layer}','kind':'group','units_by_layer':{layer:mixed}})
    return units


def stratified_pairs(records,pairs_per_task_wrapper=None):
    """Outcome-blind complete-pair selection across every represented wrapper."""
    _records(records)
    groups={}
    for row in records:groups.setdefault((row['concept'],row['group_id']),{}).setdefault(row['pair_id'],[]).append(row)
    chosen=[]
    for _,pairs in sorted(groups.items()):
        ids=sorted(pairs)
        if pairs_per_task_wrapper is not None:
            if pairs_per_task_wrapper<1:raise ValueError('Need at least one pair per task/wrapper')
            ids=ids[:pairs_per_task_wrapper]
        for pid in ids:
            pair=pairs[pid]
            if len(pair)!=2 or {r['label'] for r in pair}!={0,1}:raise ValueError('Every patch donor pair must contain opposite labels')
            chosen.extend(sorted(pair,key=lambda r:r['label']))
    return chosen


@torch.inference_mode()
def intervention_margins(model,tokenizer,records,units_by_layer,location,mode,replacements=None,scale=1.,device='cuda',batch_size=16):
    """Full continuation margin under a group intervention on explicit positions.

    replacements: dict layer->[K] discovery means or [N,K] per-example donor
    values. Span patching broadcasts the donor's span mean over recipient tokens.
    """
    from .followup_interventions import group_hooks
    if location not in ('answer','span'):raise ValueError('Unknown intervention location')
    _require_fp32(model);model.eval();units_by_layer=_selection(units_by_layer);values=[]
    for start in range(0,len(records),batch_size):
        rows=records[start:start+batch_size];encoded=[_prompt(tokenizer,r) for r in rows]
        seqs=[];answer_spans=[];positions=[]
        for row,(ids,span,common) in zip(rows,encoded):
            for answer in (row['correct'],row['foil']):
                tail=tokenizer.encode(answer,add_special_tokens=False)
                seqs.append(ids+tail);answer_spans.append((len(ids),len(tail)))
                positions.append([len(ids)+len(common)-1] if location=='answer' else span)
        kwargs,ids=_pack(model,tokenizer,seqs,device)
        mask=torch.zeros_like(ids,dtype=torch.bool)
        for j,pos in enumerate(positions):mask[j,pos]=True
        reference={}
        for layer,value in (replacements or {}).items():
            value=np.asarray(value)
            reference[int(layer)]=np.repeat(value[start:start+len(rows)],2,axis=0) if value.ndim==2 else value
        with group_hooks(model,units_by_layer,positions=mask,mode=mode,replacement_by_layer=reference or None,scale=scale):
            logits=model(**kwargs).logits
            scores=[]
            for j,(p,n) in enumerate(answer_spans):
                logp=logits[j,p-1:p+n-1].float().log_softmax(-1)
                scores.append(float(logp.gather(-1,ids[j,p:p+n,None]).sum()))
        scores=np.asarray(scores).reshape(-1,2);values.extend(scores[:,0]-scores[:,1])
    result=np.asarray(values,np.float64)
    if not np.isfinite(result).all():raise ValueError('Nonfinite intervention margin')
    return result


def collect_causal(model,tokenizer,records,d1_dir,output_dir,model_info,units=None,locations=('answer','span'),modes=('zero','mean','patch','scale_0','scale_0.5','scale_1','scale_1.5','scale_2'),pairs_per_task_wrapper=4,device='cuda',batch_size=16,max_seconds=None):
    """Checkpoint each frozen intervention/location/mode for safe partial resume.

    Candidate units come from the supplied D1 collection; callers may supply
    groups frozen from D2. D3 is never accepted for causal fitting/evaluation.
    """
    split=_records(records,{'D2','D4'});out=Path(output_dir);out.mkdir(parents=True,exist_ok=True)
    d1_dir=Path(d1_dir);d1_manifest=json.loads((d1_dir/'manifest.json').read_text())
    if d1_manifest['plan']['split']!='D1':raise ValueError('Mean references must come from D1')
    if d1_manifest['plan']['model_info']!=model_info:raise ValueError('Causal model differs from discovery model')
    selection=_selection(d1_manifest['selection']);units=intervention_units(selection) if units is None else units
    if len({u['id'] for u in units})!=len(units):raise ValueError('Intervention IDs must be unique')
    for unit in units:
        for layer,neurons in _selection(unit['units_by_layer']).items():
            if not set(neurons)<=set(selection.get(layer,[])):raise ValueError('Intervention contains a neuron outside frozen D1 candidates')
    rows=stratified_pairs(records,pairs_per_task_wrapper)
    plan={'version':VERSION,'model_info':model_info,'records_sha256':_digest(rows),'d1_signature':d1_manifest['signature'],'d1_measurements_sha256':hashlib.sha256((d1_dir/'measurements.npz').read_bytes()).hexdigest(),'units':units,'locations':list(locations),'modes':list(modes),'split':split,'patch_policy':'same-model opposite-label donor; donor span mean broadcast over recipient statement span','precision':'float32','pairs_per_task_wrapper':pairs_per_task_wrapper}
    signature=_digest(plan)
    if (out/'plan.json').exists():
        old=json.loads((out/'plan.json').read_text())
        if old['signature']!=signature:raise ValueError('Causal inputs changed; choose a new output directory')
    else:_write(out/'plan.json',{'signature':signature,'plan':plan})
    if (out/'manifest.json').exists():return json.loads((out/'manifest.json').read_text())
    start=time.monotonic();d1=np.load(d1_dir/'measurements.npz');references=out/'references'
    collect(model,tokenizer,rows,references,model_info,selection=selection,device=device,batch_size=batch_size)
    measured=np.load(references/'measurements.npz');baseline=measured['margins'];donors=[]
    for row in rows:
        matches=[i for i,r in enumerate(rows) if r['pair_id']==row['pair_id'] and r['label']!=row['label']]
        if len(matches)!=1:raise ValueError('Missing paired patch donor')
        donors.append(matches[0])
    effects=np.zeros((len(rows),len(units),len(locations),len(modes)),np.float64)
    checkpoint=out/'chunks';checkpoint.mkdir(exist_ok=True);runtimes=[]
    for ui,unit in enumerate(units):
        selected=_selection(unit['units_by_layer'])
        columns={layer:[int(np.flatnonzero((d1['layers']==layer)&(d1['neuron_ids']==n))[0]) for n in ns] for layer,ns in selected.items()}
        for li,location in enumerate(locations):
            key=location+'_product'
            for mi,mode_name in enumerate(modes):
                chunk=checkpoint/f'unit{ui:03d}_location{li}_mode{mi}.npz'
                if chunk.exists():
                    saved=np.load(chunk)
                    if str(saved['signature'])!=signature:raise ValueError('Causal checkpoint signature mismatch')
                    after=saved['margin_intervened'];seconds=float(saved['seconds'])
                else:
                    then=time.monotonic();mode=mode_name;scale=1.;replacement=None
                    if mode_name.startswith('scale_'):mode='scale';scale=float(mode_name[6:])
                    if mode=='mean':replacement={l:d1[key][:,cols].mean(0) for l,cols in columns.items()}
                    elif mode=='patch':replacement={l:measured[key][donors][:,cols] for l,cols in columns.items()}
                    after=intervention_margins(model,tokenizer,rows,selected,location,mode,replacement,scale,device,batch_size)
                    seconds=time.monotonic()-then
                    _save(chunk,signature=np.asarray(signature),margin_intervened=after,seconds=np.asarray(seconds))
                if after.shape!=baseline.shape or not np.isfinite(after).all():raise ValueError('Malformed causal checkpoint')
                effects[:,ui,li,mi]=baseline-after;runtimes.append(seconds)
                print(json.dumps({'split':split,'unit':unit['id'],'location':location,'mode':mode_name,'seconds':seconds}),flush=True)
                if max_seconds is not None and time.monotonic()-start>max_seconds:raise TimeoutError('Causal time budget reached; checkpointed chunks can resume')
    _save(out/'effects.npz',effects=effects,margins=baseline,row_ids=measured['row_ids'],groups=measured['groups'],concepts=measured['concepts'],labels=measured['labels'],unit_ids=np.asarray([u['id'] for u in units]),unit_kinds=np.asarray([u['kind'] for u in units]),locations=np.asarray(locations),modes=np.asarray(modes),answer_token_counts=measured['answer_token_counts'])
    manifest={'signature':signature,'plan':plan,'n':len(rows),'num_units':len(units),'elapsed_seconds_this_call':time.monotonic()-start,'intervention_seconds_total':sum(runtimes),'effects_sha256':hashlib.sha256((out/'effects.npz').read_bytes()).hexdigest(),'device':str(device)}
    _write(out/'manifest.json',manifest);return manifest


def load_collection(directory):
    """Return validated manifest plus in-memory arrays, without loading a model."""
    directory=Path(directory);manifest=json.loads((directory/'manifest.json').read_text())
    raw=directory/'measurements.npz'
    if hashlib.sha256(raw.read_bytes()).hexdigest()!=manifest['measurements_sha256']:raise ValueError('Collection array checksum mismatch')
    with np.load(raw,allow_pickle=False) as saved:arrays={k:saved[k] for k in saved.files}
    return manifest,arrays


# Public name for F5 evaluation callers; this never transplants activations.
group_sequence_margins=intervention_margins
