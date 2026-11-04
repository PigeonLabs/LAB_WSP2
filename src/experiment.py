"""Actual model measurement and held-out comparisons for the four pilots.

All selection uses D1. Mapping/thresholds use D2. D3/D4 are read only after
maps are frozen. Raw measurements, mapping indices, and row IDs are saved.
"""
from __future__ import annotations
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import time
import numpy as np
import torch
from .models import TinyDecoder, model_mlps, sample_layers
from .hooks import SwiGLUHook


def _json(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2, default=lambda x:x.item() if isinstance(x,np.generic) else str(x),allow_nan=False))


def _batches(rows, size):
    for i in range(0,len(rows),size): yield rows[i:i+size]


def _input(model, tokenizer, texts, device):
    seqs=[tokenizer.encode(t,add_special_tokens=False) if isinstance(t,str) else t for t in texts]
    if any(not x for x in seqs): raise ValueError("Empty prompt")
    ids=torch.full((len(seqs),max(map(len,seqs))), tokenizer.pad_token_id or 0,dtype=torch.long,device=device)
    mask=torch.zeros_like(ids)
    for i,seq in enumerate(seqs):
        ids[i,:len(seq)]=torch.tensor(seq,device=device)
        mask[i,:len(seq)]=1
    kwargs={"input_ids":ids}
    if not isinstance(model,TinyDecoder): kwargs.update(attention_mask=mask,use_cache=False)
    return kwargs,[len(x)-1 for x in seqs]


def _shared_answer_prefix(tokenizer,row):
    a=tokenizer.encode(row["correct"],add_special_tokens=False)
    b=tokenizer.encode(row["foil"],add_special_tokens=False)
    n=0
    while n<min(len(a),len(b)) and a[n]==b[n]: n+=1
    if n==min(len(a),len(b)): raise ValueError("Answer candidates must diverge before either ends")
    return a[:n]


def _autocast(device):
    return torch.autocast(device_type="cuda",dtype=torch.bfloat16,enabled=False)


@torch.inference_mode()
def capture(model,tokenizer,rows,selection=None,layers=None,batch_size=8,device="cuda"):
    """Capture answer-boundary native units; token IDs are never cross-matched."""
    model.eval()
    mlps=model_mlps(model)
    layers=sample_layers(model) if layers is None else list(layers)
    arrays={key:[] for key in ("product","gate","up","sign_regime","contribution_norm")}
    lengths=[]
    for batch in _batches(rows,batch_size):
        contexts=[tokenizer.encode(r["prompt"],add_special_tokens=False)+_shared_answer_prefix(tokenizer,r) for r in batch]
        kwargs,positions=_input(model,tokenizer,contexts,device)
        with ExitStack() as stack:
            hooks=[stack.enter_context(SwiGLUHook(mlps[l],neurons=None if selection is None else selection[l],positions=positions,capture_contribution=False)) for l in layers]
            with _autocast(device): model(**kwargs)
            for key in arrays:
                arrays[key].append(np.concatenate([h.records[key][:,0].numpy() for h in hooks],axis=1))
        lengths.extend(p+1 for p in positions)
    result={k:np.concatenate(v) for k,v in arrays.items()}
    result["token_lengths"]=np.asarray(lengths)
    result["layers"]=np.concatenate([np.full(mlps[l].down_proj.in_features if selection is None else len(selection[l]),l) for l in layers])
    result["neuron_ids"]=np.concatenate([np.arange(mlps[l].down_proj.in_features) if selection is None else np.asarray(selection[l]) for l in layers])
    return result


def select_candidates(discovery,rows,per_layer=16,seed=41):
    """Half concept-contrast candidates, half uniformly random remaining units."""
    if per_layer<2: raise ValueError("Need at least 2 candidates/layer: functional and random")
    a=discovery["product"].astype(np.float64)
    concepts=sorted(set(r["concept"] for r in rows))
    contrast=[]
    for c in concepts:
        pos=np.array([r["concept"]==c and r["label"]==1 for r in rows])
        neg=np.array([r["concept"]==c and r["label"]==0 for r in rows])
        contrast.append((a[pos].mean(0)-a[neg].mean(0))/(a.std(0)+1e-8))
    scores=np.max(np.abs(contrast),axis=0)
    rng=np.random.default_rng(seed)
    selection={}
    for layer in np.unique(discovery["layers"]):
        columns=np.where(discovery["layers"]==layer)[0]
        k=min(per_layer,len(columns)); functional=columns[np.argsort(scores[columns])[-(k//2):]]
        remaining=np.setdiff1d(columns,functional)
        random=rng.choice(remaining,k-len(functional),replace=False)
        chosen=np.r_[functional,random]
        selection[int(layer)]=discovery["neuron_ids"][chosen].tolist()
    return selection


@torch.inference_mode()
def sequence_margins(model,tokenizer,rows,device="cuda",batch_size=8,intervention=None):
    """Teacher-forced full continuation log likelihood, correct minus foil.

    Continuations are tokenized separately at the declared answer boundary.
    The intervention acts only on the last shared-context position before candidate divergence, identically for
    correct and foil; later continuation positions are left unchanged.
    """
    values=[]; token_counts=[]
    mlps=model_mlps(model)
    for start in range(0,len(rows),batch_size):
        batch=rows[start:start+batch_size]
        seqs=[]; spans=[]; boundary=[]
        for row in batch:
            p=tokenizer.encode(row["prompt"],add_special_tokens=False)
            for answer in (row["correct"],row["foil"]):
                y=tokenizer.encode(answer,add_special_tokens=False)
                if not p or not y: raise ValueError("Empty prompt or answer")
                seqs.append(p+y); spans.append((len(p),len(y))); boundary.append(len(p)+len(_shared_answer_prefix(tokenizer,row))-1)
        ids=torch.full((len(seqs),max(map(len,seqs))),tokenizer.pad_token_id or 0,dtype=torch.long,device=device)
        mask=torch.zeros_like(ids)
        for j,seq in enumerate(seqs): ids[j,:len(seq)]=torch.tensor(seq,device=device); mask[j,:len(seq)]=1
        kwargs={"input_ids":ids}
        if not isinstance(model,TinyDecoder): kwargs.update(attention_mask=mask,use_cache=False)
        with ExitStack() as stack:
            if intervention:
                replacement=intervention.get("replacement")
                if isinstance(replacement,np.ndarray):
                    replacement=np.repeat(replacement[start:start+len(batch)],2,axis=0).reshape(-1,1)
                stack.enter_context(SwiGLUHook(mlps[intervention["layer"]],neurons=[intervention["neuron"]],positions=boundary,mode=intervention["mode"],replacement=replacement,scale=intervention.get("scale",1.),capture_contribution=False))
            with _autocast(device): logits=model(**kwargs).logits
            # Only answer positions are normalized; avoid full [B,T,V] FP32 copies.
            scores=[]
            for j,(p,n) in enumerate(spans):
                logp=logits[j,p-1:p+n-1].float().log_softmax(-1)
                scores.append(logp.gather(-1,ids[j,p:p+n,None]).sum().item())
            values.extend(np.asarray(scores).reshape(-1,2)[:,0]-np.asarray(scores).reshape(-1,2)[:,1])
            token_counts.extend([(spans[2*j][1],spans[2*j+1][1]) for j in range(len(batch))])
    return np.asarray(values,dtype=np.float64),np.asarray(token_counts)


def competence(margins,rows):
    return {c:{"accuracy":float(np.mean(margins[[r["concept"]==c for r in rows]]>0)),"n":sum(r["concept"]==c for r in rows)} for c in sorted(set(r["concept"] for r in rows))}


def collect_model(model,tokenizer,dataset,output_dir,model_info,per_layer=16,batch_size=8,device="cuda"):
    """Collect D1/D2/D3 with candidate map fixed from D1 before D3 is touched."""
    out=Path(output_dir);out.mkdir(parents=True,exist_ok=True)
    signature=hashlib.sha256(json.dumps({"model_info":model_info,"dataset":dataset,"per_layer":per_layer,"boundary":"shared-answer-prefix-v2","precision":"float32"},sort_keys=True).encode()).hexdigest()
    if (out/"manifest.json").exists():
        m=json.loads((out/"manifest.json").read_text())
        if m.get("signature")!=signature: raise ValueError("Model, data, or selection changed in existing collection")
        return m
    started=time.monotonic()
    d1=capture(model,tokenizer,dataset["D1"],batch_size=batch_size,device=device)
    selection=select_candidates(d1,dataset["D1"],per_layer)
    # Freeze selection on disk before inspecting D2 or final evaluations.
    _json(out/"selection.json",{"selection":selection,"basis":"D1 only, half contrast / half random","per_layer":per_layer})
    columns=np.array([np.where((d1["layers"]==l)&(d1["neuron_ids"]==n))[0][0] for l,ids in selection.items() for n in ids])
    selected={k:(v[:,columns] if v.ndim==2 and v.shape[1]==len(d1["layers"]) else v[columns] if k in ("layers","neuron_ids") else v) for k,v in d1.items()}
    np.savez_compressed(out/"D1.npz",**selected)
    captures={"D1":selected}; evaluations={}
    for split in ("D1","D2","D3"):
        if split!="D1": captures[split]=capture(model,tokenizer,dataset[split],selection,batch_size=batch_size,device=device)
        margin,count=sequence_margins(model,tokenizer,dataset[split],device,batch_size)
        captures[split]["margins"]=margin; captures[split]["answer_token_counts"]=count
        captures[split]["row_ids"]=np.asarray([r["id"] for r in dataset[split]])
        np.savez_compressed(out/f"{split}.npz",**captures[split])
        evaluations[split]=competence(margin,dataset[split])
    profile=[]
    for j,(layer,neuron) in enumerate(zip(selected["layers"],selected["neuron_ids"])):
        vals=selected["product"][:,j]
        top=np.argsort(np.abs(vals))[-5:][::-1]
        profile.append({"layer":int(layer),"neuron":int(neuron),"mean":float(vals.mean()),"std":float(vals.std()),"q05":float(np.quantile(vals,.05)),"q50":float(np.quantile(vals,.5)),"q95":float(np.quantile(vals,.95)),"top_contexts":json.dumps([dataset["D1"][i]["prompt"] for i in top]),"sign_frequencies":json.dumps(np.bincount(selected["sign_regime"][:,j],minlength=5).tolist()),"primary_function":"UNKNOWN","explanation_confidence":"not estimated"})
    import pandas as pd
    pd.DataFrame(profile).to_parquet(out/"neuron_profiles.parquet",index=False)
    m={"signature":signature,"model_info":model_info,"selection":selection,"competence":evaluations,"elapsed_seconds":time.monotonic()-started,"num_candidates":len(columns),"splits":{s:len(dataset[s]) for s in captures},"position":"last shared-context token before correct/foil divergence; common answer prefix included; same text, model-specific tokenization","device":str(device)}
    _json(out/"manifest.json",m)
    return m


def causal_subset(rows,per_concept=128):
    """Outcome-blind complete pairs stratified round-robin across wrapper clusters."""
    result=[]
    if per_concept % 2: raise ValueError("Causal subset must contain complete pairs")
    for concept in sorted(set(r["concept"] for r in rows)):
        pairs={}
        for row in rows:
            if row["concept"]==concept: pairs.setdefault(row["pair_id"],[]).append(row)
        strata={}
        for pid,pair in sorted(pairs.items()):
            if len(pair)!=2: raise ValueError("Incomplete matched pair")
            strata.setdefault(pair[0]["group_id"],[]).append(pair)
        chosen=[]; cursor=0
        while len(chosen)<min(per_concept,2*len(pairs)):
            progressed=False
            for group,group_pairs in sorted(strata.items()):
                if cursor<len(group_pairs) and len(chosen)<per_concept:
                    chosen.extend(sorted(group_pairs[cursor],key=lambda r:r["label"]));progressed=True
            if not progressed:break
            cursor+=1
        result.extend(chosen)
    return result


def collect_causal(model,tokenizer,dataset,collection_dir,output_dir,per_layer=2,per_concept=128,batch_size=8,device="cuda"):
    """Measure zero, discovery-mean, and within-model opposite-pair patching."""
    out=Path(output_dir);out.mkdir(parents=True,exist_ok=True)
    signature=hashlib.sha256(json.dumps({"dataset":dataset,"source":str(Path(collection_dir).resolve()),"source_manifest_sha256":hashlib.sha256((Path(collection_dir)/"manifest.json").read_bytes()).hexdigest(),"per_layer":per_layer,"per_concept":per_concept,"boundary":"shared-answer-prefix-v2","precision":"float32"},sort_keys=True).encode()).hexdigest()
    if (out/"manifest.json").exists():
        previous=json.loads((out/"manifest.json").read_text())
        if previous.get("signature")!=signature:raise ValueError("Causal collection config changed")
        return previous
    source=Path(collection_dir)
    d1=np.load(source/"D1.npz")
    # One functional and one random candidate from each layer, not test-ranked.
    columns=[]
    for layer in np.unique(d1["layers"]):
        indices=np.where(d1["layers"]==layer)[0]
        n_functional=min(per_layer//2,len(indices)//2)
        n_random=min(per_layer-n_functional,len(indices)-len(indices)//2)
        columns.extend(indices[len(indices)//2-n_functional:len(indices)//2].tolist()+indices[-n_random:].tolist())
    columns=np.asarray(columns)
    sel={int(l):d1["neuron_ids"][columns][d1["layers"][columns]==l].tolist() for l in np.unique(d1["layers"])}
    _json(out/"selection.json",{"source_columns":columns.tolist(),"selection":sel,"basis":"D1 fixed; functional and random"})
    manifests={}
    for split in ("D2","D4"):
        rows=causal_subset(dataset[split],per_concept)
        act=capture(model,tokenizer,rows,sel,batch_size=batch_size,device=device)
        # Capture order is layer-group order, match original columns accordingly.
        selected_columns=[int(np.where((d1["layers"]==l)&(d1["neuron_ids"]==n))[0][0]) for l,n in zip(act["layers"],act["neuron_ids"])]
        means=d1["product"][:,selected_columns].mean(0)
        donors=[]
        for i,row in enumerate(rows):
            matches=[j for j,r in enumerate(rows) if r["pair_id"]==row["pair_id"] and r["label"]!=row["label"]]
            if len(matches)!=1: raise ValueError("Causal patching requires exactly one matched opposite-label donor")
            donors.append(matches[0])
        baseline,answer_counts=sequence_margins(model,tokenizer,rows,device,batch_size)
        effects=np.zeros((len(rows),len(means),3),dtype=np.float64)
        for j,(layer,neuron) in enumerate(zip(act["layers"],act["neuron_ids"])):
            for k,mode in enumerate(("zero","mean","patch")):
                replacement=float(means[j]) if mode=="mean" else act["product"][donors,j] if mode=="patch" else None
                after,_=sequence_margins(model,tokenizer,rows,device,batch_size,{"layer":int(layer),"neuron":int(neuron),"mode":mode,"replacement":replacement})
                effects[:,j,k]=baseline-after
            print(json.dumps({"causal_split":split,"neuron_completed":j+1,"total":len(means)}),flush=True)
        np.savez_compressed(out/f"{split}_causal.npz",effects=effects,margins=baseline,answer_token_counts=answer_counts,layers=act["layers"],neuron_ids=act["neuron_ids"],source_columns=np.asarray(selected_columns),row_ids=np.asarray([r["id"] for r in rows]),groups=np.asarray([r["group_id"] for r in rows]),concepts=np.asarray([r["concept"] for r in rows]),labels=np.asarray([r["label"] for r in rows]))
        manifests[split]={"n":len(rows),"competence":competence(baseline,rows)}
    import pandas as pd
    records=[]
    for split in ("D2","D4"):
        saved=np.load(out/f"{split}_causal.npz")
        for i,rid in enumerate(saved["row_ids"]):
            for j,(layer,neuron) in enumerate(zip(saved["layers"],saved["neuron_ids"])):
                for k,mode in enumerate(("zero","mean","patch")):records.append({"split":split,"row_id":rid,"layer":int(layer),"neuron":int(neuron),"intervention":mode,"effect":float(saved["effects"][i,j,k])})
    pd.DataFrame(records).to_parquet(out/"causal_effects.parquet",index=False)
    manifest={"signature":signature,"splits":manifests,"interventions":["zero","mean","patch"],"num_candidates":len(columns),"mean_reference":"D1","patch_reference":"matched opposite-label prompt, same model","effect":"original logP(correct)/P(foil) margin minus intervened margin"}
    _json(out/"manifest.json",manifest)
    return manifest


def _column_correlations(a,b):
    a=np.asarray(a,dtype=np.float64);b=np.asarray(b,dtype=np.float64)
    a=a-a.mean(0);b=b-b.mean(0)
    denom=np.sqrt((a*a).sum(0)*(b*b).sum(0))
    valid=denom>1e-14
    values=np.zeros(a.shape[1],dtype=np.float64)
    np.divide((a*b).sum(0),denom,out=values,where=valid)
    return np.clip(values,-1,1),valid


def _cluster_scores(a,b,groups,source,target):
    """Mean matched-neuron Pearson per wrapper; constant pairs get zero, flagged."""
    groups=np.asarray(groups);out=[];invalid=0
    for g in np.unique(groups):
        mask=groups==g
        left=a[mask][:,source];right=b[mask][:,target]
        if left.ndim==3: # examples x neurons x intervention -> observations x neurons
            left=left.transpose(0,2,1).reshape(-1,len(source));right=right.transpose(0,2,1).reshape(-1,len(target))
        corr,valid=_column_correlations(left,right)
        invalid+=int((~valid).sum())
        out.append(float(corr.mean()) if len(corr) else 0.)
    return np.asarray(out),invalid



def analysis_input_signature(paths,dataset,weight_similarity=None):
    """Content-addressed analysis inputs; independent of dictionary/set hash order."""
    signature={"version":"frozen-replay-inputs-v1", "dataset_sha256":hashlib.sha256(json.dumps(dataset,sort_keys=True).encode()).hexdigest(),
        "files":{str(i)+":"+Path(p).name:hashlib.sha256(Path(p).read_bytes()).hexdigest() for i,p in enumerate(paths)}}
    if weight_similarity is not None:
        weight=np.ascontiguousarray(weight_similarity,dtype=np.float64)
        signature["weight_similarity_sha256"]=hashlib.sha256(weight.tobytes()).hexdigest()
        signature["weight_similarity_shape"]=list(weight.shape)
    return signature


def _resume_analysis(out,signature):
    sidecar=out/"input_signature.json"
    if (out/"metrics.json").exists():
        if not sidecar.exists():
            raise ValueError("Historical analysis lacks verified input signature; run scripts/validate_results.py to replay frozen maps and backfill safely")
        saved=json.loads(sidecar.read_text())
        if saved.get("inputs")!=signature:raise ValueError("Analysis inputs changed; preserve existing results and use a new run directory")
        return json.loads((out/"metrics.json").read_text())
    return None


def analyze_pair(collection_a,collection_b,dataset,output_dir,pair_name="pair",weight_similarity=None):
    """Frozen D2 maps evaluated on D3; E1/E2/E3 share these measurements."""
    from .alignment import fit_alignment,calibration_threshold,match_neurons,semantic_fingerprint
    from .statistics import cluster_bootstrap,paired_randomization_test,fdr_bh
    import pandas as pd
    out=Path(output_dir);out.mkdir(parents=True,exist_ok=True)
    ca,cb=Path(collection_a),Path(collection_b)
    input_signature=analysis_input_signature([ca/"D2.npz",cb/"D2.npz",ca/"D3.npz",cb/"D3.npz"],dataset,weight_similarity)
    resumed=_resume_analysis(out,input_signature)
    if resumed is not None:return resumed
    a2,b2=np.load(ca/"D2.npz"),np.load(cb/"D2.npz")
    methods=["random","activation","rank","semantic","sign_semantic","label_shuffled"]
    maps={}
    for method in methods:
        maps[method]=fit_alignment(a2["product"],b2["product"],dataset["D2"],method=method,signs_a=a2["sign_regime"],signs_b=b2["sign_regime"],seed=1729)
    if weight_similarity is not None:
        maps["weight"]=match_neurons(weight_similarity)
    threshold=calibration_threshold(a2["product"],b2["product"],dataset["D2"],method="activation",permutations=100,seed=1729)
    maps["activation_partial"]=fit_alignment(a2["product"],b2["product"],dataset["D2"],method="activation",mode="partial",threshold=threshold)
    maps["activation_one_to_many"]=fit_alignment(a2["product"],b2["product"],dataset["D2"],method="activation",mode="one_to_many",threshold=threshold)
    # Complete map serialization is the artifact proving frozen mapping.
    serialized={name:{k:v.tolist() if isinstance(v,np.ndarray) else v for k,v in m.items()} for name,m in maps.items()}
    _json(out/"frozen_mappings.json",serialized)
    a3,b3=np.load(ca/"D3.npz"),np.load(cb/"D3.npz")
    expected=np.asarray([r["id"] for r in dataset["D3"]])
    if not (np.array_equal(a3["row_ids"],expected) and np.array_equal(b3["row_ids"],expected)):
        raise ValueError("Evaluation row alignment mismatch")
    groups=np.asarray([r["group_id"] for r in dataset["D3"]]);unique=np.unique(groups)
    results={};cluster={};match_rows=[]
    for name,mapping in maps.items():
        source,target=mapping["source"],mapping["target"]
        score,invalid=_cluster_scores(a3["product"],b3["product"],groups,source,target)
        cluster[name]=score
        summary=cluster_bootstrap(score,unique)
        results[name]={**summary,"coverage":float(mapping["coverage"]),"unmatched_source_fraction":float(mapping["unmatched_source_fraction"]),"invalid_constant_pair_clusters":invalid,"matched_pairs":len(source)}
        corr,valid=_column_correlations(a3["product"][:,source],b3["product"][:,target])
        for i,j,value,ok in zip(source,target,corr,valid):
            match_rows.append({"method":name,"source_index":int(i),"target_index":int(j),"source_layer":int(a3["layers"][i]),"target_layer":int(b3["layers"][j]),"source_neuron":int(a3["neuron_ids"][i]),"target_neuron":int(b3["neuron_ids"][j]),"heldout_pearson":float(value),"valid_variance":bool(ok)})
    comparisons={}
    for candidate,baseline in [("activation","random"),("rank","random"),("semantic","activation"),("sign_semantic","activation"),("semantic","label_shuffled")]:
        test=paired_randomization_test(cluster[candidate],cluster[baseline],unique)
        comparisons[f"{candidate}_minus_{baseline}"]={**test,"bootstrap":cluster_bootstrap(cluster[candidate]-cluster[baseline],unique)}
    pvals=[x["pvalue"] for x in comparisons.values()]
    for v,q in zip(comparisons.values(),fdr_bh(pvals)):v["qvalue"]=q
    # Primary semantic labels independently validated as signs on D3, not main metric.
    f2a=semantic_fingerprint(a2["product"],dataset["D2"]);f3a=semantic_fingerprint(a3["product"],dataset["D3"])
    f2b=semantic_fingerprint(b2["product"],dataset["D2"]);f3b=semantic_fingerprint(b3["product"],dataset["D3"])
    pd.DataFrame(match_rows).to_csv(out/"matches.csv",index=False)
    np.savez_compressed(out/"cluster_scores.npz",groups=unique,**cluster)
    metrics={"pair":pair_name,"metric":"mean within-wrapper held-out matched-neuron Pearson, equal wrapper weight","mapping_split":"D2","evaluation_split":"D3","partial_threshold":float(threshold),"results":results,"comparisons":comparisons,"semantic_profile_cross_split_sign_consistency":{"a":float(np.mean(np.sign(f2a)==np.sign(f3a))),"b":float(np.mean(np.sign(f2b)==np.sign(f3b)))},"limitations":["Six wrapper clusters: exploratory intervals and low-powered tests.","Activation response generalization is not a causal correspondence claim.","Synthetic truth contrasts have surface shortcuts.","Partial mapping is selected using shuffled D2 row-maximum null; zero coverage is allowed.","Constant response pairs contribute zero and are explicitly counted."]}
    _json(out/"metrics.json",metrics)
    _json(out/"input_signature.json",{"inputs":input_signature,"validation":"written at initial analysis completion"})
    return metrics


def analyze_causal_pair(causal_a,causal_b,collection_a,collection_b,dataset,output_dir,pair_name="pair"):
    """D2 wrapper-split tuning, freeze, then D4 causal generalization only."""
    from .alignment import cosine_similarity,match_neurons,fit_alignment,semantic_fingerprint
    from .statistics import cluster_bootstrap,paired_randomization_test,fdr_bh
    import pandas as pd
    from scipy.stats import rankdata
    out=Path(output_dir);out.mkdir(parents=True,exist_ok=True)
    input_signature=analysis_input_signature([Path(causal_a)/"D2_causal.npz",Path(causal_b)/"D2_causal.npz",Path(causal_a)/"D4_causal.npz",Path(causal_b)/"D4_causal.npz",Path(collection_a)/"D2.npz",Path(collection_b)/"D2.npz"],dataset)
    resumed=_resume_analysis(out,input_signature)
    if resumed is not None:return resumed
    a,b=np.load(Path(causal_a)/"D2_causal.npz"),np.load(Path(causal_b)/"D2_causal.npz")
    if not np.array_equal(a["row_ids"],b["row_ids"]):raise ValueError("Causal calibration row mismatch")
    # No D4 value contributes to matching, normalization, threshold, or weight.
    unique=np.unique(a["groups"]);fit=np.isin(a["groups"],unique[:len(unique)//2]);val=~fit
    if fit.sum()<2 or val.sum()<2:raise ValueError("Need independent D2 wrapper calibration folds")
    ae,be=a["effects"],b["effects"]
    scale_a=max(float(np.std(a["margins"][fit])),1e-8);scale_b=max(float(np.std(b["margins"][fit])),1e-8)
    an,bn=ae/scale_a,be/scale_b
    # Mean signed effects by concept/intervention preserve direction.
    concepts=sorted(set(a["concepts"].tolist()))
    def fingerprint(e,mask):
        return np.concatenate([e[mask&(a["concepts"]==c)].mean(0) for c in concepts],axis=1)
    causal_similarity=cosine_similarity(fingerprint(an,fit),fingerprint(bn,fit))
    # Semantic discovery/calibration views restricted to pre-selected causal neurons.
    ca,cb=np.load(Path(collection_a)/"D2.npz"),np.load(Path(collection_b)/"D2.npz")
    x=ca["product"][:,a["source_columns"]];y=cb["product"][:,b["source_columns"]]
    sx=ca["sign_regime"][:,a["source_columns"]];sy=cb["sign_regime"][:,b["source_columns"]]
    sem=cosine_similarity(semantic_fingerprint(x,dataset["D2"]),semantic_fingerprint(y,dataset["D2"]))
    maps={name:fit_alignment(x,y,dataset["D2"],method=name,signs_a=sx,signs_b=sy) for name in ("random","activation","semantic","sign_semantic")}
    maps["causal"]=match_neurons(causal_similarity)
    tuning=[]
    for weight in (0.,.25,.5,.75,1.):
        mapped=match_neurons((1-weight)*sem+weight*causal_similarity)
        score,_=_cluster_scores(an[val],bn[val],a["groups"][val],mapped["source"],mapped["target"])
        tuning.append((float(np.mean(score)),weight,mapped))
    _,best_weight,best=max(tuning,key=lambda item:(item[0],-item[1]))
    maps["semantic_causal"]=best
    _json(out/"frozen_mappings.json",{"mapping_fit":"D2 first three wrapper clusters; semantic D2","weight_validation":"D2 last three wrapper clusters","causal_weight":best_weight,"normalization":{"a":scale_a,"b":scale_b,"basis":"D2 fit margin std"},"candidates":[{"weight":w,"validation_score":s} for s,w,_ in tuning],"maps":{n:{k:v.tolist() if isinstance(v,np.ndarray) else v for k,v in m.items()} for n,m in maps.items()}})
    at,bt=np.load(Path(causal_a)/"D4_causal.npz"),np.load(Path(causal_b)/"D4_causal.npz")
    if not np.array_equal(at["row_ids"],bt["row_ids"]):raise ValueError("Causal evaluation row mismatch")
    results={};scores={};match_rows=[];groups=at["groups"];ug=np.unique(groups)
    for name,m in maps.items():
        ia,ib=m["source"],m["target"]
        score,invalid=_cluster_scores(at["effects"]/scale_a,bt["effects"]/scale_b,groups,ia,ib);scores[name]=score
        left=at["effects"][:,ia,:];right=bt["effects"][:,ib,:]
        lv=left.transpose(0,2,1).reshape(-1,len(ia));rv=right.transpose(0,2,1).reshape(-1,len(ib))
        pearson,valid=_column_correlations(lv,rv);spearman,_=_column_correlations(rankdata(lv,axis=0),rankdata(rv,axis=0))
        nonzero=(np.abs(left)>1e-7)&(np.abs(right)>1e-7)
        sign=float(np.mean(np.sign(left[nonzero])==np.sign(right[nonzero]))) if nonzero.any() else None
        results[name]={**cluster_bootstrap(score,ug),"pearson_pooled_mean":float(pearson.mean()),"spearman_pooled_mean":float(spearman.mean()),"causal_sign_agreement":sign,"nonzero_effect_fraction":float(nonzero.mean()),"invalid_constant_pair_clusters":invalid,"coverage":float(m["coverage"])}
        for i,j,p,s in zip(ia,ib,pearson,spearman):match_rows.append({"method":name,"source_index":int(i),"target_index":int(j),"source_layer":int(at["layers"][i]),"target_layer":int(bt["layers"][j]),"pearson":float(p),"spearman":float(s)})
    comparisons={}
    for method,baseline in [("causal","semantic"),("semantic_causal","semantic"),("semantic_causal","activation"),("semantic","random")]:
        comparisons[f"{method}_minus_{baseline}"]={**paired_randomization_test(scores[method],scores[baseline],ug),"bootstrap":cluster_bootstrap(scores[method]-scores[baseline],ug)}
    for value,q in zip(comparisons.values(),fdr_bh([v["pvalue"] for v in comparisons.values()])):value["qvalue"]=q
    # Different task matched control destroys correspondence without cross-model activation transplantation.
    shifted=np.roll(bt["effects"],len(bt["effects"])//len(concepts),axis=0)
    wrong,_=_cluster_scores(at["effects"],shifted,groups,best["source"],best["target"])
    pd.DataFrame(match_rows).to_csv(out/"alignment_results.csv",index=False)
    np.savez_compressed(out/"cluster_scores.npz",groups=ug,**scores)
    metrics={"pair":pair_name,"metric":"D4 within-wrapper Pearson of signed per-example effects across three interventions","causal_weight":best_weight,"results":results,"comparisons":comparisons,"mismatched_task_control":cluster_bootstrap(wrong,ug),"normalization":{"a":scale_a,"b":scale_b},"limitations":["Six held-out wrapper clusters; exploratory inference only.","Zero/mean/patch effects refer only to final prompt position.","Candidate semantic fingerprints are truth contrasts, not verified unique meanings.","Low-competence tasks are retained as controls and limit causal interpretation.","Selected causal neurons are small D1 functional/random subsets.","Cross-task generalization to entirely new task families was not tested."]}
    _json(out/"metrics.json",metrics)
    _json(out/"input_signature.json",{"inputs":input_signature,"validation":"written at initial analysis completion"})
    return metrics
