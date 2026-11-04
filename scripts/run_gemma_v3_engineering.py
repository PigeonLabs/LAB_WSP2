"""Real engineering-only model/hook checks and full-continuation scores.

No readiness, discovery, fit or test data are opened by this runner.
"""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import argparse,json,time,hashlib
import numpy as np
import torch
from src.gemma_v3_engine import load_gemma_gguf,NativeGeluHook
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/followup-v3-gemma-map'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,x):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 if p.exists():raise RuntimeError('Refuse overwrite: '+str(p))
 p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def rows():
 r=[json.loads(s) for s in (ROOT/'data/followup-v3-gemma-map/engineering.jsonl').read_text().splitlines()]
 assert len(r)==512 and all(x['split']=='engineering' for x in r)
 return r
def fixtures():
 r=rows();out=[]
 for ci,concept in enumerate(sorted({x['concept'] for x in r})):
  for lang in ['en','ko']:
   x=next(x for x in r if x['concept']==concept and x['language']==lang and x['family_id'].endswith('-00') and x['semantic_state']==ci%2 and x['lexical']==0 and x['answer_code']==ci%2)
   out.append({'id':x['id'],'prompt':x['prompt']})
 return out

def load(which):
 torch.set_num_threads(2);torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
 if which=='gemma':return load_gemma_gguf(ROOT/'cache/gemma-v3/gemma-4-E2B-it-Q4_K_M.gguf',device='cuda',progress=lambda x:print(json.dumps(x),flush=True))
 from transformers import AutoModelForCausalLM,AutoTokenizer
 m=json.loads((ROOT/'configs/models.json').read_text())['models'];entry=next(x for x in m if x['model_id']=='Qwen/Qwen3-0.6B-Base')
 tokenizer=AutoTokenizer.from_pretrained(entry['local_path'],local_files_only=True,trust_remote_code=False);tokenizer.padding_side='right'
 model=AutoModelForCausalLM.from_pretrained(entry['local_path'],local_files_only=True,trust_remote_code=False,dtype=torch.float32,attn_implementation='eager').to('cuda').eval()
 return model,tokenizer,{'model_id':entry['model_id'],'revision':entry['revision'],'dtype':'float32','attention':'eager'}

@torch.inference_mode()
def validate(model,tok,prov):
 dest=OUT/'engineering_engine';dest.mkdir(parents=True,exist_ok=True)
 checks=[];outputs=[]
 for i,f in enumerate(fixtures()):
  ids=tok(f['prompt'],return_tensors='pt')['input_ids'].to('cuda')
  base=model(input_ids=ids,use_cache=False,logits_to_keep=1).logits[0,-1].float()
  if not torch.isfinite(base).all():raise RuntimeError('Nonfinite logits')
  arr=base.cpu().numpy();np.save(dest/f'fixture_{i}.npy',arr)
  outputs.append({'id':f['id'],'tokens':ids[0].tolist(),'top1_id':int(base.argmax()),'logits_file':f'fixture_{i}.npy'})
  if i in (0,1):
   for layer in [5,27]:
    state={}
    def capture(module,args):state['a']=args[0][0,-1].detach().clone()
    h=model.model.layers[layer].mlp.down_proj.register_forward_pre_hook(capture)
    cap=model(input_ids=ids,use_cache=False,logits_to_keep=1).logits[0,-1].float();h.remove()
    neuron=int(state['a'].abs().argmax());v=state['a'][neuron].item()
    for mode,kw in [(None,{}),('scale',{'scale':1}),('patch',{'replacement':v})]:
     with NativeGeluHook(model,layer,[neuron],positions=-1,mode=mode,**kw) as hook:
      tested=model(input_ids=ids,use_cache=False,logits_to_keep=1).logits[0,-1].float()
     error=float((tested-base).abs().max());checks.append({'fixture':i,'layer':layer,'neuron':neuron,'mode':str(mode),'max_logit_error':error,'passed':error<=1e-5})
    with NativeGeluHook(model,layer,[neuron],positions=-1,mode='zero'):
     changed=model(input_ids=ids,use_cache=False,logits_to_keep=1).logits[0,-1].float()
    delta=float((changed-base).abs().max());checks.append({'fixture':i,'layer':layer,'neuron':neuron,'mode':'zero','max_logit_change':delta,'passed':delta>1e-6})
  print(json.dumps({'validated_fixture':i,'tokens':ids.shape[1]}),flush=True)
 result={'status':'PASS_INTERNAL' if all(x['passed'] for x in checks) else 'FAIL_INTERNAL','scope':'Eight engineering prompts; exact logits are pending comparison with independent CPU reference. Not arbitrary-context equivalence.','provenance':prov,'rows':outputs,'checks':checks,'external_forward_parity':'PENDING'}
 save(dest/'validation.json',result)
 if result['status']!='PASS_INTERNAL':raise RuntimeError('Internal native hook validation failed')

@torch.inference_mode()
def score(model,tok,prov,which,batch,source_rows=None):
 source=rows() if source_rows is None else source_rows;items=[]
 if not all(r["split"]=="engineering" for r in source):raise RuntimeError("Engineering scorer refuses other splits")
 for r in source:
  prefix=tok(r['prompt'],add_special_tokens=True)['input_ids']
  for k,completion in enumerate(r['completions']):
   ids=tok(r['prompt']+completion,add_special_tokens=True)['input_ids']
   if ids[:len(prefix)]!=prefix:raise RuntimeError('Tokenizer crosses prompt-completion boundary: '+r['id'])
   items.append((r['id'],k,ids,len(prefix)))
 result={r['id']:[None,None] for r in source};start=time.monotonic()
 for offset in range(0,len(items),batch):
  group=items[offset:offset+batch];length=max(len(x[2]) for x in group);first=min(x[3] for x in group)-1
  ids=torch.full((len(group),length),tok.pad_token_id or 0,dtype=torch.long,device='cuda');mask=torch.zeros_like(ids)
  for j,(_,k,tokens,prefix) in enumerate(group):ids[j,:len(tokens)]=torch.tensor(tokens,device='cuda');mask[j,:len(tokens)]=1
  logits=model(input_ids=ids,attention_mask=mask,use_cache=False,logits_to_keep=length-first).logits.float()
  for j,(rid,k,tokens,prefix) in enumerate(group):
   pred=logits[j,prefix-1-first:len(tokens)-1-first]
   targets=ids[j,prefix:len(tokens)]
   val=-torch.nn.functional.cross_entropy(pred,targets,reduction='sum').item()
   if not np.isfinite(val):raise RuntimeError('Nonfinite score')
   result[rid][k]=val
  if offset%64==0:print(json.dumps({'model':which,'scored':min(offset+batch,len(items)),'total':len(items),'seconds':time.monotonic()-start}),flush=True)
 records=[]
 for r in source:
  scores=result[r['id']];pred=int(np.argmax(scores));records.append({k:r[k] for k in ['id','family_id','lineage_id','concept','language','semantic_state','answer_code','lexical','correct_index']}|{'scores':scores,'predicted_index':pred,'correct':pred==r['correct_index']})
 save(OUT/'engineering_scores'/f'{which}.json',{'status':'MEASURED_ENGINEERING_ONLY','model':which,'scope':'512 controlled engineering prompts /32 scenarios/4grammar lineages; not independent readiness or test','data_sha256':sha(ROOT/'data/followup-v3-gemma-map/engineering.jsonl'),'provenance':prov,'elapsed_seconds':time.monotonic()-start,'rows':records})

def main():
 p=argparse.ArgumentParser();p.add_argument('--phase',choices=['fixtures','validate','score'],required=True);p.add_argument('--model',choices=['gemma','qwen'],default='gemma');p.add_argument('--batch',type=int,default=4);a=p.parse_args()
 if a.phase=='fixtures':
  save(OUT/'engineering_engine/fixtures.json',fixtures());save(OUT/'engineering_engine/frozen_numeric_criteria.json',{'token_ids_exact':True,'fp32_reference_rmse_max':.001,'fp32_reference_max_abs_max':.01,'top1_exact':True,'scope':'eight preselected engineering fixtures; fixed before either forward output'});return
 start=time.monotonic();model,tok,prov=load(a.model)
 if a.phase=='validate':validate(model,tok,prov)
 else:score(model,tok,prov,a.model,a.batch)
 torch.cuda.synchronize();save(OUT/'runtime'/f'{a.model}_{a.phase}.json',{'elapsed_seconds':time.monotonic()-start,'peak_torch_allocated_bytes':torch.cuda.max_memory_allocated(),'stage':'engineering','script_sha256':sha(__file__)})
if __name__=='__main__':main()
