"""Read-only GGUF structural audit; no inference, corpus, or private data."""
from pathlib import Path
import json
import gguf
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=ROOT/'cache/gemma-v3/gemma-4-E2B-it-Q4_K_M.gguf'
 r=gguf.GGUFReader(p)
 widths=[]
 for t in r.tensors:
  if t.name.endswith('.ffn_down.weight'):
   widths.append({'layer':int(t.name.split('.')[1]),'native_neurons':int(t.shape[0]),'residual_width':int(t.shape[1]),'gguf_type':str(t.tensor_type)})
 widths.sort(key=lambda x:x['layer'])
 assert len(widths)==35
 assert sum(x['native_neurons'] for x in widths)==337920
 for row in widths:
  assert row['residual_width']==1536
  assert row['native_neurons']==(6144 if row['layer']<15 else 12288)
 metadata={k:r.fields[k].contents() for k in r.fields if k.startswith('gemma4.')}
 result={'status':'PASS','scope':'GGUF metadata and tensor shape audit; not forward correctness','tensor_count':len(r.tensors),'layers':35,'native_neurons':337920,'layer_widths':widths,'architecture_metadata':metadata,'source_sha256':'740185b21d22ceb83a11c3aa62ad5842ef32c70f6096d756bbee85a1e4ec34b8'}
 out=ROOT/'results/followup-v3-gemma-map/gguf_structure.json'
 if out.exists():raise RuntimeError('Preserve existing structural audit')
 out.write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({'status':'PASS','layers':35,'native_neurons':337920,'tensor_count':len(r.tensors)}))
if __name__=='__main__':main()
