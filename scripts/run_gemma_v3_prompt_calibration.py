"""Pre-readiness common four-shot engineering diagnostic; no held-out data."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import json,argparse,time,hashlib
import torch
from scripts import run_gemma_v3_engineering as base
ROOT=Path(__file__).resolve().parents[1]
PREFIX={
'en':'''Judge each statement using only the supplied record. Follow that example's letter mapping. Give the letter and the same truth sentence as in these examples.

Record: The card is blue.
Statement: The card is blue.
Use A for a true statement and B for a false statement.
Answer: A. The statement is true.

Record: The card is green.
Statement: The card is red.
Use B for a true statement and A for a false statement.
Answer: A. The statement is false.

Record: The box is closed.
Statement: The box is closed.
Use B for a true statement and A for a false statement.
Answer: B. The statement is true.

Record: The door is open.
Statement: The door is closed.
Use A for a true statement and B for a false statement.
Answer: B. The statement is false.''',
'ko':'''제시된 기록만으로 각 진술을 판단하십시오. 문항마다 주어진 글자 대응을 따르십시오. 예시처럼 글자와 참·거짓 문장을 함께 답하십시오.

기록: 이 카드는 파란색이다.
진술: 이 카드는 파란색이다.
진술이 참이면 A, 거짓이면 B로 답하십시오.
답: A. 이 진술은 참이다.

기록: 이 카드는 초록색이다.
진술: 이 카드는 빨간색이다.
진술이 참이면 B, 거짓이면 A로 답하십시오.
답: A. 이 진술은 거짓이다.

기록: 이 상자는 닫혀 있다.
진술: 이 상자는 닫혀 있다.
진술이 참이면 B, 거짓이면 A로 답하십시오.
답: B. 이 진술은 참이다.

기록: 이 문은 열려 있다.
진술: 이 문은 닫혀 있다.
진술이 참이면 A, 거짓이면 B로 답하십시오.
답: B. 이 진술은 거짓이다.'''}
def main():
 p=argparse.ArgumentParser();p.add_argument('--model',choices=['gemma','qwen']);p.add_argument('--freeze-candidate',action='store_true');a=p.parse_args()
 candidate={'id':'common_fourshot_v1','prefix':PREFIX,'selection_rule':'Among raw and this shared four-shot candidate, maximize minimum of the two models engineering macro accuracy; ties choose raw. Freeze before any readiness inference.','scope':'E-only adaptive calibration, not held-out accuracy.'}
 path=ROOT/'configs/gemma_v3_prompt_candidates.json'
 if a.freeze_candidate:base.save(path,candidate);return
 assert json.loads(path.read_text())==candidate
 data=[dict(r,prompt=PREFIX[r['language']]+'\n\n'+r['prompt']) for r in base.rows()]
 started=time.monotonic();model,tok,prov=base.load(a.model);prov['prompt_variant']='common_fourshot_v1';prov['prompt_candidate_sha256']=base.sha(path)
 base.score(model,tok,prov,a.model+'_common_fourshot',8,source_rows=data)
 torch.cuda.synchronize();base.save(base.OUT/'runtime'/f'{a.model}_common_fourshot.json',{'elapsed_seconds':time.monotonic()-started,'peak_torch_allocated_bytes':torch.cuda.max_memory_allocated(),'stage':'engineering_prompt_calibration','script_sha256':base.sha(__file__)})
if __name__=='__main__':main()
