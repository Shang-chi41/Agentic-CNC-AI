#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,random,sys,hashlib
from collections import defaultdict
from pathlib import Path

def args():
 p=argparse.ArgumentParser(); p.add_argument('--trajectories',required=True); p.add_argument('--base-model',required=True); p.add_argument('--adapter',required=True); p.add_argument('--report',required=True); p.add_argument('--unsloth-site',default='/mnt/data/unsloth_site'); p.add_argument('--seed',type=int,default=3407); return p.parse_args()

def load(p):
 out=[]
 for line in Path(p).read_text(encoding='utf8').splitlines():
  if not line.strip():continue
  t=json.loads(line); c=t.get('classification') or {}; a=c.get('accepted') or {}
  if set(a)!={'F1.role'}:continue
  v=a['F1.role']; allowed=(c.get('allowed_values') or {}).get('F1.role') or []
  if not (t.get('success_oracle') or {}).get('eligible_classifier_training') or v not in allowed:continue
  out.append({'sha':t['trajectory_sha256'],'question':t.get('pending_question',''),'message':t.get('user_message',''),'value':v,'allowed_values':allowed})
 return out

def split(rows,seed):
 g=defaultdict(list)
 for r in rows:g[r['value']].append(r)
 rng=random.Random(seed); tr=[];te=[]
 for _,x in sorted(g.items()):
  rng.shuffle(x); n=max(1,round(len(x)*.25)); n=min(n,max(1,len(x)-1)) if len(x)>1 else 1;te+=x[:n];tr+=x[n:]
 rng.shuffle(tr);rng.shuffle(te);return tr,te

def main():
 a=args();sys.path.insert(0,a.unsloth_site)
 import torch;torch.set_num_threads(1)
 from transformers import AutoModelForCausalLM,AutoTokenizer
 from peft import PeftModel
 tok=AutoTokenizer.from_pretrained(a.adapter)
 base=AutoModelForCausalLM.from_pretrained(a.base_model,dtype=torch.float32)
 model=PeftModel.from_pretrained(base,a.adapter,is_trainable=False)
 rows=load(a.trajectories);_,test=split(rows,a.seed); labels=sorted({r['value'] for r in rows}); ids=torch.tensor([tok.convert_tokens_to_ids(v) for v in labels])
 def prompt(r):return f"<|user|> {r['question']} allowed_values {' '.join(r['allowed_values'])} user_message {r['message']} <|assistant|>"
 enc=tok([prompt(r) for r in test],padding=True,truncation=True,max_length=96,return_tensors='pt');last=enc['attention_mask'].sum(1)-1
 with torch.no_grad():logits=model(**enc).logits;sel=logits[torch.arange(len(test)),last][:,ids];pi=sel.argmax(1).tolist()
 pred=[labels[i] for i in pi]; per=[{'sha':r['sha'],'expected':r['value'],'predicted':p,'correct':p==r['value']} for r,p in zip(test,pred)]
 acc=sum(x['correct'] for x in per)/len(per)
 adapter=Path(a.adapter);hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in adapter.iterdir() if p.is_file()}
 rep={'schema':'unsloth-adapter-independent-reload-v1','status':'PASS' if acc>=.75 else 'FAIL','accuracy':acc,'correct':sum(x['correct'] for x in per),'total':len(per),'predictions':per,'adapter_sha256':hashes,'loader':'transformers.AutoModelForCausalLM + peft.PeftModel; no training-process state reused'}
 Path(a.report).write_text(json.dumps(rep,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps({'status':rep['status'],'accuracy':acc,'total':len(per)}))
 if rep['status']!='PASS':raise SystemExit(2)
if __name__=='__main__':main()
