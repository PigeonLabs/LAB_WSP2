"""Replay fixed CPU/GPU forward parity on the eight R diagnostic fixtures."""
from pathlib import Path
import hashlib
import json
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'results/followup-v3-gemma-map'

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    folder = BASE / 'readiness_engine'
    reference = folder / 'llama_reference_fp32_gelu'
    gpu = json.loads((folder / 'gpu_logits.json').read_text())['rows']
    cpu = json.loads((reference / 'reference.json').read_text())['rows']
    criteria_path = BASE / 'engineering_engine/frozen_numeric_criteria.json'
    frozen = json.loads(criteria_path.read_text())
    criteria = frozen.get('criteria', frozen)
    rows = []
    assert len(gpu) == len(cpu) == 8
    for a, b in zip(gpu, cpu):
        assert a['id'] == b['id']
        gp = folder / a['logits_file']
        cp = reference / b['logits_file']
        x = np.load(gp).astype(np.float64)
        y = np.fromfile(cp, dtype='<f4').astype(np.float64)
        assert x.shape == y.shape == (262144,)
        assert np.isfinite(x).all() and np.isfinite(y).all()
        rmse = float(np.sqrt(np.mean((x-y)**2)))
        maximum = float(np.max(np.abs(x-y)))
        token_match = a['tokens'] == b['tokens']
        top_match = int(x.argmax()) == int(y.argmax()) == a['top1_id'] == b['top1_id']
        rows.append(dict(id=a['id'], token_ids_exact=token_match, top1_exact=top_match,
            rmse=rmse, max_abs=maximum, gpu_sha256=digest(gp), reference_sha256=digest(cp),
            passed=bool(token_match and top_match and rmse <= criteria['fp32_reference_rmse_max']
                        and maximum <= criteria['fp32_reference_max_abs_max'])))
    output = dict(status='PASS' if all(r['passed'] for r in rows) else 'FAIL',
        criteria=criteria, criteria_sha256=digest(criteria_path),
        scope='Eight fixed readiness inputs; patched official llama.cpp graph; shared GGUF dequantizer. No independent intervention or original-map reproduction claim.',
        reference_patch='results/followup-v3-gemma-map/reference_gelu_patch.json', rows=rows)
    (folder / 'forward_parity_fp32_gelu.json').write_text(json.dumps(output, indent=2)+'\n')
    print(json.dumps(dict(status=output['status'], fixtures=len(rows), max_abs=max(r['max_abs'] for r in rows))))
    if output['status'] != 'PASS':
        raise SystemExit(1)

if __name__ == '__main__':
    main()
