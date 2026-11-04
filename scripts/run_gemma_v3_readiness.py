"""Fixed-prompt conditional readiness diagnostic; never opens T/O or selects maps."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import argparse,json,time,hashlib
import numpy as np
import torch
from scripts.run_gemma_v3_engineering import load,save,sha
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/followup-v3-gemma-map'
@torch.inference_mode()
def main():
 p=argparse.ArgumentParser();p.add_argument('--model',choices=['gemma','qwen'],required=True);p.add_argument('--data',required=True);a=p.parse_args()
 source=Path(a.data);records=[json.loads(s) for s in source.read_text().splitlines()]
 assert len(records)==1024 and len({r['family_id'] for r in records})==64
 assert all(r['split'] in ('readiness','readiness_conditional') for r in records)
 lock=ROOT/'configs/gemma_v3_prompt_lock.json';amend=OUT/'readiness_conditional_amendment.json'
 assert json.loads(amend.read_text())['prompt_lock_sha256']==sha(lock)
 assert json.loads(lock.read_text())['status']=='FROZEN_BEFORE_READINESS'
 start=time.monotonic();model,tok,prov=load(a.model);prov['prompt_lock_sha256']=sha(lock);items=[]
 for r in records:
  prefix=tok(r['prompt'],add_special_tokens=True)['input_ids']
  for k,c in enumerate(r['completions']):
   ids=tok(r['prompt']+c,add_special_tokens=True)['input_ids']
   if ids[:len(prefix)]!=prefix:raise RuntimeError('Completion boundary mismatch: '+r['id'])
   items.append((r['id'],k,ids,len(prefix)))
 result={r['id']:[None,None] for r in records};batch_checks=[];score_start=time.monotonic()
 for offset in range(0,len(items),8):
  group=items[offset:offset+8];length=max(len(x[2]) for x in group);first=min(x[3] for x in group)-1
  ids=torch.full((len(group),length),tok.pad_token_id or 0,dtype=torch.long,device='cuda');mask=torch.zeros_like(ids)
  for j,(_,_,tokens,_) in enumerate(group):ids[j,:len(tokens)]=torch.tensor(tokens,device='cuda');mask[j,:len(tokens)]=1
  logits=model(input_ids=ids,attention_mask=mask,use_cache=False,logits_to_keep=length-first).logits.float()
  for j,(rid,k,tokens,prefix) in enumerate(group):
   value=-torch.nn.functional.cross_entropy(logits[j,prefix-1-first:len(tokens)-1-first],ids[j,prefix:len(tokens)],reduction='sum').item()
   if not np.isfinite(value):raise RuntimeError('Nonfinite continuation score')
   result[rid][k]=value
   if offset==0:
    one_ids=torch.tensor([tokens],device='cuda');one=model(input_ids=one_ids,use_cache=False,logits_to_keep=len(tokens)-prefix+1).logits[0].float()
    single=-torch.nn.functional.cross_entropy(one[:-1],one_ids[0,prefix:],reduction='sum').item();err=abs(single-value)
    batch_checks.append({'id':rid,'alternative':k,'absolute_score_error':err,'passed':err<=.001})
  if offset%128==0:print(json.dumps({'model':a.model,'scored':min(offset+8,len(items)),'total':len(items),'seconds':time.monotonic()-score_start}),flush=True)
 if not all(r['passed'] for r in batch_checks):raise RuntimeError('Batch/single score discrepancy')
 # Fixed first scenario per concept/language, used only for numeric cross-engine parity.
 fixtures=[];fixture_receipts=[]
 for concept in sorted({r['concept'] for r in records}):
  for language in ['en','ko']:
   row=next(r for r in records if r['concept']==concept and r['language']==language)
   fixtures.append({'id':row['id'],'prompt':row['prompt']})
   if a.model=='gemma':
    token_ids=tok(row['prompt'],return_tensors='pt')['input_ids'].to('cuda');v=model(input_ids=token_ids,use_cache=False,logits_to_keep=1).logits[0,-1].float().cpu().numpy()
    folder=OUT/'readiness_engine';folder.mkdir(parents=True,exist_ok=True);name=f'fixture_{len(fixtures)-1}.npy';np.save(folder/name,v)
    fixture_receipts.append({'id':row['id'],'tokens':token_ids[0].tolist(),'top1_id':int(v.argmax()),'logits_file':name})
 if a.model=='gemma':save(OUT/'readiness_engine/fixtures.json',fixtures);save(OUT/'readiness_engine/gpu_logits.json',{'rows':fixture_receipts,'criteria':'results/followup-v3-gemma-map/engineering_engine/frozen_numeric_criteria.json'})
 rows=[]
 for r in records:
  values=result[r['id']];pred=int(np.argmax(values));rows.append({k:r[k] for k in ['id','family_id','lineage_id','concept','language','semantic_state','answer_code','lexical','correct_index'] if k in r}|{'source_cluster_id':r.get('source_cluster_id',r['family_id']),'source_reference_cluster_id':r.get('source_reference_cluster_id',r.get('source_cluster_id',r['family_id'])),'scores':values,'predicted_index':pred,'correct':pred==r['correct_index']})
 save(OUT/'readiness_scores'/f'{a.model}.json',{'status':'MEASURED_CONDITIONAL_DIAGNOSTIC','model':a.model,'scope':'64 source records/4 shared renderer lineages; convenience sample; no independent-template generalization or confirmatory gate pass','data_sha256':sha(source),'amendment_sha256':sha(amend),'provenance':prov,'batch_checks':batch_checks,'rows':rows,'scoring_seconds':time.monotonic()-score_start})
 torch.cuda.synchronize();save(OUT/'runtime'/f'{a.model}_readiness_conditional.json',{'elapsed_seconds':time.monotonic()-start,'peak_torch_allocated_bytes':torch.cuda.max_memory_allocated(),'script_sha256':sha(__file__)})
if __name__=='__main__':main()
