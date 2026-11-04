"""Bounded independent-initialization training; checkpoints never silently overwrite."""
from __future__ import annotations
import hashlib
import json
import time
from dataclasses import asdict
from pathlib import Path
import numpy as np
import torch
import torch.nn.functional as F
from .models import ByteTokenizer, ModelConfig, build_model


def parameter_hash(model):
    h = hashlib.sha256()
    for name, tensor in model.state_dict().items():
        h.update(name.encode())
        h.update(tensor.detach().cpu().contiguous().numpy().tobytes())
    return h.hexdigest()


def train_independent(config, train_records, output_dir, device="cuda"):
    """Train each seed from scratch on train only; no evaluation split is accepted.

    Config keys model (ModelConfig kwargs), seeds, steps, batch_size, lr,
    max_seconds_per_seed. Resume only an explicitly completed matching manifest.
    """
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    if any(r.get("split") != "train" for r in train_records):
        raise ValueError("Training must receive train records only")
    tok = ByteTokenizer()
    model_config = ModelConfig(**config.get("model", {}))
    examples = []
    for r in train_records:
        prompt = tok.encode(r["prompt"])
        ids = prompt + tok.encode(r["correct"]) + [tok.eos_token_id]
        if len(ids) > model_config.max_seq_len:
            raise ValueError("Training sequence exceeds model context; never truncate silently")
        examples.append((ids, len(prompt)))
    train_hash = hashlib.sha256(json.dumps(train_records, sort_keys=True).encode()).hexdigest()
    signature = hashlib.sha256(json.dumps({"config": config,"train_hash": train_hash},sort_keys=True).encode()).hexdigest()
    manifests = []
    for seed in config.get("seeds", [11, 29]):
        out = root / f"seed_{seed}"
        out.mkdir(exist_ok=True)
        manifest_path = out / "manifest.json"
        if manifest_path.exists():
            m = json.loads(manifest_path.read_text())
            if m.get("signature") != signature:
                raise ValueError("Refusing to reuse training with different config or data")
            if m.get("completed"):
                if not (out / "final.pt").exists():
                    raise ValueError("Archived manifest has no model weights. Use scripts/new_run.py for a fresh reproduction; do not overwrite archived evidence.")
                manifests.append(m)
                continue
        elif (out / "initial.pt").exists():
            raise ValueError("Incomplete run exists; choose a new output directory")
        torch.manual_seed(seed)
        rng = np.random.default_rng(seed)
        model = build_model(model_config, seed)
        initial_hash = parameter_hash(model)
        torch.save({"config":asdict(model_config),"state_dict":model.state_dict(),"seed":seed},out / "initial.pt")
        model.to(device)
        optimizer = torch.optim.AdamW(model.parameters(), lr=config.get("lr",3e-4),weight_decay=0.01)
        steps = config.get("steps", 1200)
        batch_size = config.get("batch_size",64)
        start = time.monotonic()
        losses = []
        model.train()
        for step in range(steps):
            chosen = [examples[i] for i in rng.integers(0,len(examples),batch_size)]
            length = max(len(x[0]) for x in chosen)
            ids = torch.zeros(batch_size,length,dtype=torch.long,device=device)
            valid = torch.zeros_like(ids,dtype=torch.bool)
            answer = torch.zeros_like(ids,dtype=torch.bool)
            for j,(seq,prompt_len) in enumerate(chosen):
                ids[j,:len(seq)] = torch.tensor(seq,device=device)
                valid[j,:len(seq)] = True
                answer[j,prompt_len:len(seq)] = True
            optimizer.zero_grad(set_to_none=True)
            with torch.autocast(device_type="cuda",dtype=torch.bfloat16,enabled=str(device).startswith("cuda")):
                logits = model(ids).logits[:,:-1]
                token_loss = F.cross_entropy(logits.float().reshape(-1,logits.shape[-1]),ids[:,1:].reshape(-1),reduction="none").view(batch_size,-1)
                lm = (token_loss*valid[:,1:]).sum()/valid[:,1:].sum()
                ans = (token_loss*answer[:,1:]).sum()/answer[:,1:].sum()
                loss = 0.25*lm+0.75*ans
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(),1.0)
            optimizer.step()
            if step % 25 == 0 or step+1 == steps:
                row={"seed":seed,"step":step+1,"loss":float(loss.detach()),"lm_loss":float(lm.detach()),"answer_loss":float(ans.detach()),"elapsed_seconds":time.monotonic()-start}
                losses.append(row)
                with (out / "training.jsonl").open("a") as f: f.write(json.dumps(row)+"\n")
                print(json.dumps(row),flush=True)
            if step+1 == steps//2:
                torch.save({"config":asdict(model_config),"state_dict":{k:v.cpu() for k,v in model.state_dict().items()},"seed":seed,"step":step+1},out/"middle.pt")
            if time.monotonic()-start > config.get("max_seconds_per_seed",1800):
                break
        model.cpu()
        final_path=out/"final.pt"
        torch.save({"config":asdict(model_config),"state_dict":model.state_dict(),"seed":seed,"step":step+1},final_path)
        manifest={"completed":True,"signature":signature,"seed":seed,"train_hash":train_hash,"model_config":asdict(model_config),"parameters":sum(p.numel() for p in model.parameters()),"initial_hash":initial_hash,"final_hash":parameter_hash(model),"steps":step+1,"planned_steps":steps,"stop_reason":"steps_finished" if step+1==steps else "per_seed_time_budget","elapsed_seconds":time.monotonic()-start,"checkpoint":str(final_path.resolve()),"initial_checkpoint":str((out/"initial.pt").resolve()),"losses":losses,"device":str(device)}
        manifest_path.write_text(json.dumps(manifest,indent=2))
        manifests.append(manifest)
        del model,optimizer
        if torch.cuda.is_available(): torch.cuda.empty_cache()
    if len(set(m["initial_hash"] for m in manifests)) != len(manifests):
        raise AssertionError("Independent initialization hashes must differ")
    return manifests


def load_trained(path, device="cpu"):
    checkpoint=torch.load(path,map_location="cpu",weights_only=True)
    model=build_model(ModelConfig(**checkpoint["config"]),checkpoint["seed"])
    model.load_state_dict(checkpoint["state_dict"])
    return model.to(device).eval(),ByteTokenizer()
