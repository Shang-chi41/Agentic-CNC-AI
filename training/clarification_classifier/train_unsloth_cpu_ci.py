#!/usr/bin/env python3
"""Actual Unsloth LoRA training proof on project trajectories in CPU-CI mode.

This is deliberately transparent:
- Unsloth 2026.7.3 is imported and FastLanguageModel.get_peft_model creates LoRA.
- GPU-only trainer/fused-loss patches are bypassed because this proof environment has
  CPU-only PyTorch. The adapter itself is produced by Unsloth's public API.
- Training uses a plain PyTorch optimizer and explicit cross entropy over the closed
  enum target token, so no CUDA-only fused loss is invoked.
- This proves real weight updates and baseline-vs-candidate evaluation, not production
  GPU throughput or an official CPU support claim.
"""
from __future__ import annotations
import argparse, hashlib, json, os, random, sys, time
from collections import defaultdict
from pathlib import Path
from typing import Any


def parse_args():
    p=argparse.ArgumentParser()
    p.add_argument('--trajectories', required=True)
    p.add_argument('--base-model', required=True)
    p.add_argument('--output-dir', required=True)
    p.add_argument('--report', required=True)
    p.add_argument('--unsloth-site', default='/mnt/data/unsloth_site')
    p.add_argument('--epochs', type=int, default=240)
    p.add_argument('--lr', type=float, default=0.03)
    p.add_argument('--seed', type=int, default=3407)
    return p.parse_args()


def load_role_records(path: Path) -> list[dict[str, Any]]:
    records=[]
    for line in path.read_text(encoding='utf-8').splitlines():
        if not line.strip(): continue
        t=json.loads(line)
        c=t.get('classification') or {}
        accepted=c.get('accepted') or {}
        if set(accepted) != {'F1.role'}: continue
        value=accepted['F1.role']
        allowed=(c.get('allowed_values') or {}).get('F1.role') or []
        oracle=t.get('success_oracle') or {}
        if not oracle.get('eligible_classifier_training'): continue
        if value not in allowed: continue
        records.append({
            'sha': t['trajectory_sha256'],
            'question': t.get('pending_question',''),
            'message': t.get('user_message',''),
            'value': value,
            'allowed_values': allowed,
        })
    if not records: raise RuntimeError('No oracle-approved F1.role trajectories')
    return records


def stratified_split(records: list[dict[str,Any]], seed:int):
    groups=defaultdict(list)
    for r in records: groups[r['value']].append(r)
    train=[]; test=[]
    rng=random.Random(seed)
    for value, rows in sorted(groups.items()):
        rng.shuffle(rows)
        n_test=max(1, round(len(rows)*0.25))
        n_test=min(n_test, max(1,len(rows)-1)) if len(rows)>1 else 1
        test.extend(rows[:n_test]); train.extend(rows[n_test:])
    rng.shuffle(train); rng.shuffle(test)
    return train,test


def balance_rows(rows, labels, seed):
    groups={v:[r for r in rows if r['value']==v] for v in labels}
    target=max(len(x) for x in groups.values())
    rng=random.Random(seed+99)
    balanced=[]
    for v in labels:
        source=groups[v]
        if not source: raise RuntimeError(f'Missing train class {v}')
        shuffled=list(source); rng.shuffle(shuffled)
        balanced.extend(shuffled[i % len(shuffled)] for i in range(target))
    rng.shuffle(balanced)
    return balanced


def main():
    a=parse_args()
    os.environ.setdefault('UNSLOTH_ALLOW_CPU','1')
    os.environ.setdefault('UNSLOTH_DISABLE_AUTO_UPDATES','1')
    os.environ.setdefault('UNSLOTH_COMPILE_DISABLE','1')
    os.environ.setdefault('UNSLOTH_USE_NEW_MODEL','0')
    sys.path.insert(0,a.unsloth_site)
    import torch
    torch.set_num_threads(1)
    random.seed(a.seed); torch.manual_seed(a.seed)
    class Props:
        name='CPU-CI compatibility shim'; total_memory=4*1024**3; major=8; minor=0; multi_processor_count=1
    # Import-time hardware introspection only. Runtime remains CPU and is recorded below.
    torch.cuda.get_device_capability=lambda *x,**k:(8,0)
    torch.cuda.get_device_properties=lambda *x,**k:Props()
    torch.cuda.device_count=lambda:0
    torch.cuda.is_available=lambda:False

    # Load standard HF base before Unsloth patches to avoid GPU-only rotary cache creation.
    from transformers import AutoModelForCausalLM, AutoTokenizer
    tokenizer=AutoTokenizer.from_pretrained(a.base_model)
    base=AutoModelForCausalLM.from_pretrained(a.base_model, dtype=torch.float32)
    base.max_seq_length=128
    base._saved_temp_tokenizer=tokenizer
    device=torch.device('cpu'); base.to(device)

    records=load_role_records(Path(a.trajectories))
    train_rows,test_rows=stratified_split(records,a.seed)
    labels=sorted({r['value'] for r in records})
    target_ids={v: tokenizer.convert_tokens_to_ids(v) for v in labels}
    if any(i in {None,tokenizer.unk_token_id} for i in target_ids.values()):
        raise RuntimeError(f'Target enum missing from tokenizer: {target_ids}')

    def prompt(r):
        # The exact user message is retained; allowed values make runtime/training contract parity explicit.
        allowed=' '.join(r['allowed_values'])
        return f"<|user|> {r['question']} allowed_values {allowed} user_message {r['message']} <|assistant|>"

    def encode_batch(rows):
        enc=tokenizer([prompt(r) for r in rows], padding=True, truncation=True, max_length=96, return_tensors='pt')
        # Last non-padding position predicts the enum token.
        last=enc['attention_mask'].sum(dim=1)-1
        y=torch.tensor([target_ids[r['value']] for r in rows],dtype=torch.long)
        return {k:v.to(device) for k,v in enc.items()}, last.to(device), y.to(device)

    @torch.no_grad()
    def evaluate(model, rows):
        model.eval(); enc,last,y=encode_batch(rows)
        logits=model(**enc).logits
        selected=logits[torch.arange(len(rows)),last]
        candidate=torch.tensor([target_ids[v] for v in labels],dtype=torch.long)
        pred_idx=selected[:,candidate].argmax(dim=1)
        preds=[labels[i] for i in pred_idx.tolist()]
        correct=sum(p==r['value'] for p,r in zip(preds,rows))
        per=[]
        for r,p in zip(rows,preds): per.append({'sha':r['sha'],'expected':r['value'],'predicted':p,'correct':p==r['value']})
        return {'accuracy':correct/len(rows),'correct':correct,'total':len(rows),'predictions':per}

    baseline=evaluate(base,test_rows)
    balanced_train=balance_rows(train_rows,labels,a.seed)

    import unsloth
    from unsloth import FastLanguageModel
    from unsloth.models.llama import FastLlamaModel
    import unsloth.models.llama as unsloth_llama
    unsloth_llama.DEVICE_TYPE_TORCH='cpu'
    unsloth_version=getattr(unsloth,'__version__','unknown')
    # CPU-CI compatibility: disable only the GPU-oriented trainer patch. LoRA creation
    # still runs through FastLanguageModel.get_peft_model.
    FastLlamaModel.patch_peft_model=staticmethod(lambda model,use_gradient_checkpointing=True:model)
    model=FastLanguageModel.get_peft_model(
        base,r=4,target_modules=['q_proj','k_proj','v_proj','o_proj'],
        lora_alpha=8,lora_dropout=0.0,bias='none',use_gradient_checkpointing=False,
        random_state=a.seed,modules_to_save=['lm_head'],
    )
    trainable=sum(p.numel() for p in model.parameters() if p.requires_grad)
    total=sum(p.numel() for p in model.parameters())
    if trainable<=0: raise RuntimeError('No trainable LoRA parameters')
    before={n:p.detach().clone() for n,p in model.named_parameters() if p.requires_grad}
    opt=torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],lr=a.lr,weight_decay=0.0)
    enc,last,y_token=encode_batch(balanced_train)
    label_to_index={v:i for i,v in enumerate(labels)}
    y=torch.tensor([label_to_index[r['value']] for r in balanced_train],dtype=torch.long,device=device)
    candidate_ids=torch.tensor([target_ids[v] for v in labels],dtype=torch.long,device=device)
    loss_history=[]; start=time.time()
    model.train()
    for epoch in range(a.epochs):
        opt.zero_grad(set_to_none=True)
        logits=model(**enc).logits
        selected=logits[torch.arange(len(balanced_train)),last][:,candidate_ids]
        loss=torch.nn.functional.cross_entropy(selected,y)
        loss.backward(); opt.step()
        if epoch in {0,1,2,4,9,19,39,79,119,159,199,a.epochs-1}:
            loss_history.append({'epoch':epoch+1,'loss':float(loss.detach())})
    elapsed=time.time()-start
    changed={n:float((p.detach()-before[n]).abs().max()) for n,p in model.named_parameters() if p.requires_grad}
    max_delta=max(changed.values())
    candidate=evaluate(model,test_rows)

    out=Path(a.output_dir); out.mkdir(parents=True,exist_ok=True)
    model.save_pretrained(out)
    tokenizer.save_pretrained(out)
    adapter_files=sorted(p.name for p in out.iterdir() if p.is_file())
    file_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file()}
    report={
      'schema':'unsloth-cpu-ci-empirical-proof-v1',
      'status':'PASS' if candidate['accuracy']>baseline['accuracy'] and max_delta>0 else 'FAIL',
      'scope':'actual Unsloth LoRA creation and weight training on CPU-CI; not production GPU throughput proof',
      'unsloth_version':unsloth_version,
      'torch_version':torch.__version__,
      'device':'cpu','cuda_available':False,
      'base_model':str(Path(a.base_model).resolve()),
      'dataset':{'source':str(Path(a.trajectories).resolve()),'records':len(records),'train':len(train_rows),'balanced_train':len(balanced_train),'test':len(test_rows),'class_counts':{v:sum(r['value']==v for r in records) for v in labels}},
      'training':{'epochs':a.epochs,'lr':a.lr,'trainable_parameters':trainable,'total_parameters':total,'elapsed_seconds':elapsed,'loss_history':loss_history,'max_trainable_weight_delta':max_delta},
      'baseline':baseline,'candidate':candidate,
      'improvement':candidate['accuracy']-baseline['accuracy'],
      'adapter':{'directory':str(out.resolve()),'files':adapter_files,'sha256':file_hashes},
      'compatibility_notes':['FastLanguageModel.get_peft_model used directly','GPU-only FastLlamaModel.patch_peft_model bypassed in CPU-CI','loss computed with torch cross_entropy to avoid CUDA-only fused loss'],
    }
    Path(a.report).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('status','unsloth_version','device','improvement')},ensure_ascii=False))
    print('baseline',baseline['accuracy'],'candidate',candidate['accuracy'],'delta',max_delta,'loss',loss_history[0],loss_history[-1])
    if report['status']!='PASS': raise SystemExit(2)

if __name__=='__main__': main()
