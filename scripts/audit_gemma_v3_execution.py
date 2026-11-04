#!/usr/bin/env python3
"""CPU preservation/archive/runtime audit; no model or statistical test execution.

The run index freezes completed execution evidence only. Mutable publications,
README, stage receipts, and this audit's own descendants are excluded to avoid
cycles. The original README is checked as an exact preserved suffix.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import hashlib
import io
import json
from pathlib import Path
import tarfile
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
PUBLICATION_CUTOFF='ad21a0a4b7db1a763d450d514627006eb04fae9e'


def read(path):return json.loads(Path(path).read_text())
def hash_bytes(raw):return hashlib.sha256(raw).hexdigest()
def save_once(path,value):
    raw=(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode();path=Path(path)
    if path.exists():
        if path.read_bytes()!=raw:raise FileExistsError('Refusing to replace frozen audit: '+str(path))
    else:path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)


def audit(root):
    root=Path(root).resolve();run=root/'results/followup-v3-gemma-map';cache={}
    def sha(path):
        path=Path(path)
        if path not in cache:
            h=hashlib.sha256()
            with path.open('rb') as stream:
                for block in iter(lambda:stream.read(4*1024*1024),b''):h.update(block)
            cache[path]=h.hexdigest()
        return cache[path]
    def relative(path):return str(Path(path).relative_to(root))
    def receipt(path):return dict(path=relative(path),sha256=sha(path),bytes=Path(path).stat().st_size)
    def safe_path(value):
        path=Path(value)
        if path.is_absolute() or '..' in path.parts:raise ValueError('Need safe repository-relative evidence path')
        return root/path
    snapshot_path=run/'preservation_before.json';snapshot=read(snapshot_path);entries=snapshot['files'];verified=[]
    if len(entries)!=3919 or len({e['path'] for e in entries})!=3919:raise ValueError('Preservation snapshot count or uniqueness changed')
    for entry in entries:
        if entry['path']=='README.md':continue
        path=safe_path(entry['path'])
        if not path.is_file() or path.stat().st_size!=entry['bytes'] or sha(path)!=entry['sha256']:raise ValueError('Historical evidence changed or missing: '+entry['path'])
        verified.append(entry['path'])
    original=next(e for e in entries if e['path']=='README.md');saved=root/'reports/followup-v3-gemma-map/README_before_execution.md'
    previous=saved.read_bytes();current=(root/'README.md').read_bytes()
    if hash_bytes(previous)!=original['sha256'] or len(previous)!=original['bytes'] or not current.endswith(previous):raise ValueError('Original README is not preserved exactly as current suffix')
    preservation=dict(status='PASS',snapshot=receipt(snapshot_path),snapshot_entries=len(entries),unchanged_non_readme_files=len(verified),
                      all_non_readme_sha256_verified=True,saved_readme=receipt(saved),current_readme_endswith_saved_exact_bytes=True,
                      current_readme_at_audit_sha256=hash_bytes(current),current_readme_hash_is_snapshot_only=True,
                      verified_paths=verified,scope='3918 historical files verified byte-for-byte; original root README verified via saved bytes and exact current suffix, not unchanged current README.')
    runtime_paths=sorted((run/'runtime').glob('*.json'))+[run/'engineering_extended_validation/summary.json'];timings=[]
    for path in runtime_paths:
        seconds=float(read(path)['elapsed_seconds'])
        if not np.isfinite(seconds) or seconds<0:raise ValueError('Invalid runtime receipt')
        timings.append(dict(receipt(path),elapsed_seconds=seconds))
    total=sum(x['elapsed_seconds'] for x in timings)
    runtime=dict(recorded_model_stage_wall_seconds=total,recorded_model_stage_wall_hours=total/3600,receipts=timings,
                 aggregation='Sum once per model-stage elapsed receipt, plus same-engine extended validation; nested scoring timers not added.',
                 gpu_active_time_measured=False,not_total_project_wall_time=True,
                 excluded_uninstrumented_costs=['CPU reference inference/build','model download/conversion','analysis/publication/wait time'],
                 incremental_model_stage_wall_cap_hours=5,recorded_model_stage_wall_below_cap=total<=5*3600)
    archive_manifest=run/'raw_archives/manifest.json';archives=[];all_members=set()
    for item in read(archive_manifest)['archives']:
        path=safe_path(item['path'])
        if sha(path)!=item['sha256'] or path.stat().st_size!=item['bytes']:raise ValueError('Archive bytes mismatch')
        expected={m['path']:m['sha256'] for m in item['members']}
        if len(expected)!=len(item['members']):raise ValueError('Duplicate archive manifest member')
        audited=[]
        with tarfile.open(path,'r:gz') as tar:
            members=tar.getmembers()
            if len(members)!=len(expected) or {m.name for m in members}!=set(expected):raise ValueError('Archive membership mismatch')
            for member in members:
                local=safe_path(member.name)
                if not member.isfile() or member.name in all_members:raise ValueError('Nonregular or duplicate cross-archive member')
                raw=tar.extractfile(member).read()
                if hash_bytes(raw)!=expected[member.name] or sha(local)!=expected[member.name]:raise ValueError('Archive member/local source checksum mismatch: '+member.name)
                record=dict(path=member.name,sha256=expected[member.name],bytes=len(raw))
                if member.name.endswith('.npy'):
                    array=np.load(io.BytesIO(raw),allow_pickle=False)
                    if not np.isfinite(array).all():raise ValueError('Nonfinite raw array')
                    record['finite_array_shape']=list(array.shape)
                elif member.name.endswith('.f32'):
                    if len(raw)%4:raise ValueError('Invalid raw float32 array length')
                    array=np.frombuffer(raw,dtype='<f4')
                    if not np.isfinite(array).all():raise ValueError('Nonfinite raw float32 array')
                    record['finite_array_shape']=list(array.shape)
                elif member.name.endswith('.json'):json.loads(raw)
                all_members.add(member.name);audited.append(record)
        archives.append(dict(receipt(path),member_count=len(audited),members=audited))
    data_dir=root/'data/followup-v3-gemma-map';observed=[]
    for path in sorted(data_dir.rglob('*.jsonl')):
        rows=[json.loads(line) for line in path.read_text().splitlines()]
        splits=sorted({r.get('split') for r in rows})
        if any(s not in ('engineering','readiness') for s in splits):raise ValueError('Closed split was materialized')
        observed.append(dict(receipt(path),rows=len(rows),splits=splits))
    forbidden={'discovery','fit','test','ood','D','F','T','O'}
    for directory in (data_dir,run):
        for path in directory.rglob('*'):
            if path.stem in forbidden or any(part in forbidden for part in path.relative_to(directory).parts):raise ValueError('Unexpected discovery/fit/test/OOD artifact: '+str(path))
    summary=read(run/'readiness_summary.json');replay=read(run/'readiness_replay_audit.json')
    if replay['status']!='PASS' or replay['summary_sha256']!=sha(run/'readiness_summary.json'):raise ValueError('Readiness replay source changed')
    if summary['test_opened'] or summary['ood_opened'] or summary['original_confirmatory_claims_evaluable']:raise ValueError('Closed-split/claim interpretation changed')
    lock_path=root/'configs/gemma_v3_prompt_lock.json';lock_sha=sha(lock_path);run_name='run_'+lock_sha[:12]
    index_path=run/run_name/'index.json'
    result=dict(status='PASS',audit_type='FINAL_CPU_EXECUTION_EVIDENCE_AUDIT',model_inference_executed=False,new_hypothesis_tests_executed=False,
                tests_rerun=False,preservation=preservation,runtime=runtime,
                raw_archives=dict(status='PASS',manifest=receipt(archive_manifest),archives=len(archives),members=len(all_members),archive_bytes=sum(a['bytes'] for a in archives),entries=archives,
                                  scope='Archive/member SHA256 matches local raw arrays and public source snapshots. Finite-array storage check, not new forward inference.'),
                closed_data_splits=dict(status='PASS',observed_jsonl=observed,discovery_materialized=False,fit_materialized=False,test_materialized=False,ood_materialized=False,
                                       scope='No matching data/result artifacts present; audited generator flags remain closed. Not a proof about unrecorded historical actions.'),
                readiness_replay=receipt(run/'readiness_replay_audit.json'),strict_template_generalization_gate=summary['strict_template_generalization_gate'],
                original_confirmatory_claims_evaluable=False,execution_index_path=relative(index_path),prompt_lock=receipt(lock_path),
                publication_cutoff=dict(last_verified_stage='G1',commit=PUBLICATION_CUTOFF,remote_verification='Performed by publisher; this CPU audit does not repeat network verification'),
                audit_script=receipt(Path(__file__).resolve()),limitations=['Operational evidence preservation and replay are distinct from scientific hypothesis support.',
                    'Runtime is instrumented model-stage wall time, not measured GPU-active hours or total project duration.',
                    'README/status/report artifacts may be updated after this audit; historical saved README remains required as exact suffix.'])
    audit_path=run/'execution_audit.json';save_once(audit_path,result)
    files=[]
    for path in sorted(run.rglob('*')):
        if not path.is_file() or '__pycache__' in path.parts:continue
        rel=path.relative_to(run)
        if any(part.startswith('run_') for part in rel.parts) or rel.parts[0] in ('stages','report_inputs') or path==audit_path:continue
        files.append(path)
    files.extend(sorted(data_dir.glob('*')))
    files.extend(p for p in (root/'configs').glob('*gemma*v3*.json') if p.is_file())
    files.extend(p for p in (root/'configs').glob('*followup_v3*.json') if p.is_file())
    files.extend(p for p in (root/'src').glob('gemma_v3*.py') if p.is_file())
    files.extend(p for p in (root/'scripts').glob('*gemma_v3*.py') if p.is_file() and p.name!='build_gemma_v3_report.py')
    files.extend(root/m for m in all_members if m.startswith('artifacts/'))
    files.append(root/'reports/v3/Rsourcecatalogv2.json')
    unique=sorted({p for p in files if p.is_file()})
    index=dict(schema_version=1,run_id=run_name,status='COMPLETED_E_AND_CONDITIONAL_R_EVIDENCE_INDEX',prompt_lock=receipt(lock_path),
               publication_cutoff_commit=PUBLICATION_CUTOFF,execution_audit=receipt(audit_path),files=[receipt(p) for p in unique],
               excludes=['Root README and report README fragments','Rendered reports/figures and G0-G6 stage/report-input receipts','This run index and future execution-audit descendants'],
               circular_hash_policy='Audit omits index hash; index hashes audit; draft G6 receipt hashes both and is not indexed.',
               source_scope='Completed engineering/readiness execution, source bank, fixed data/config/code, archive and runtime evidence; no D/F/T/O runs.')
    save_once(index_path,index)
    draft=dict(schema_version=1,stage='G6',status='MEASURED',draft_for_parent_review=True,title='Execution preservation and portable evidence audit',
               summary=f'CPU audit verified3918 unchanged historical files plus exact preserved README suffix; {len(archives)} raw archives/{len(all_members)} members match their local sources. D/F/T/O remain absent.',
               scope='Operational audit only; no new model inference, hypothesis tests, or evidence of native-function conservation.',
               verdict='EXECUTION_AUDIT_PASS; SCIENTIFIC_GATES_REMAIN_UNMET',rationale='Readiness has no jointly capable model/task-language cells; strict renderer-generalization gate remains failed.',
               sources=[relative(audit_path),relative(index_path),'results/followup-v3-gemma-map/readiness_replay_audit.json'],
               source_sha256={relative(audit_path):sha(audit_path),relative(index_path):sha(index_path)},
               metrics=[dict(name='Historical non-README files preserved',value=len(verified),unit='files',source=relative(audit_path)),
                        dict(name='Archive members replayed',value=len(all_members),unit='members',source=relative(audit_path)),
                        dict(name='Recorded model-stage wall time',value=total/3600,unit='hours; not GPU-active time',source=relative(audit_path))],
               figures=[],limitations=result['limitations'],artifacts=[relative(audit_path),relative(index_path)])
    save_once(run/'report_inputs/G6.json',draft)
    return dict(status=result['status'],preserved_non_readme=len(verified),readme_exact_suffix=True,archives=len(archives),archive_members=len(all_members),
                recorded_model_stage_wall_seconds=total,recorded_model_stage_wall_hours=total/3600,indexed_files=len(unique),index=relative(index_path),audit_sha256=sha(audit_path),index_sha256=sha(index_path))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,default=ROOT);args=parser.parse_args();print(json.dumps(audit(args.root),ensure_ascii=False))


if __name__=='__main__':main()
