#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, itertools, json, os, random, sys, time
from pathlib import Path

def args():
 p=argparse.ArgumentParser(); p.add_argument('--base-model',required=True);p.add_argument('--output-dir',required=True);p.add_argument('--report',required=True);p.add_argument('--unsloth-site',default='/mnt/data/unsloth_site');p.add_argument('--epochs',type=int,default=500);p.add_argument('--lr',type=float,default=.03);p.add_argument('--seed',type=int,default=3407);return p.parse_args()
ACTIONS=['BIND_CONFIRMED','RESOLVE_SYSTEM','ASK_USER','BLOCK_CONTRADICTION','BLOCK_UNAVAILABLE']
CODE=dict(zip(ACTIONS,['RECTANGULAR_POCKET','RECTANGULAR_CONTOUR_INSIDE','RECTANGULAR_CONTOUR_OUTSIDE','true','abstain_when_unclear']))
def oracle(c,k,s,a):
 if k:return 'BLOCK_CONTRADICTION'
 if c:return 'BIND_CONFIRMED'
 if s and not a:return 'BLOCK_UNAVAILABLE'
 if s:return 'RESOLVE_SYSTEM'
 return 'ASK_USER'
def canonical(c,k,s,a,variant):
 vals=[
  'clarification_resolved' if c else 'pending_question',
  'no_cross_layer_contradiction' if not k else 'coordinates_forbidden',
  'machine_authority_false' if not s else 'provider_output_contains_no_rejected_fields',
  'eligible_success' if a else 'abstain_when_unclear',
 ]
 if variant==0:return ' '.join(vals)
 if variant==1:return '{ '+','.join(vals)+' }'
 if variant==2:return '[ '+','.join(reversed(vals))+' ]'
 return '{ schema : v3 , input : [ '+','.join(vals)+' ] }'
def rows():
 out=[]
 for c,k,s,a in itertools.product([0,1],repeat=4):
  # contradictory+confirmed retained: contradiction has precedence and must block.
  y=oracle(c,k,s,a)
  for v in range(4):out.append({'bits':[c,k,s,a],'variant':v,'prompt':canonical(c,k,s,a,v),'action':y,'code':CODE[y]})
 return out

def main():
 a=args();os.environ.setdefault('UNSLOTH_ALLOW_CPU','1');os.environ.setdefault('UNSLOTH_DISABLE_AUTO_UPDATES','1');os.environ.setdefault('UNSLOTH_COMPILE_DISABLE','1');sys.path.insert(0,a.unsloth_site)
 import torch;torch.set_num_threads(1);random.seed(a.seed);torch.manual_seed(a.seed)
 class Props:name='CPU-CI shim';total_memory=4*1024**3;major=8;minor=0;multi_processor_count=1
 torch.cuda.get_device_capability=lambda *x,**k:(8,0);torch.cuda.get_device_properties=lambda *x,**k:Props();torch.cuda.device_count=lambda:0;torch.cuda.is_available=lambda:False
 from transformers import AutoModelForCausalLM,AutoTokenizer
 tok=AutoTokenizer.from_pretrained(a.base_model);base=AutoModelForCausalLM.from_pretrained(a.base_model,dtype=torch.float32);base.max_seq_length=128;base._saved_temp_tokenizer=tok;base.to('cpu')
 data=rows(); train=[r for r in data if r['variant'] in (0,1)]; test=[r for r in data if r['variant'] in (2,3)]
 target_ids={x:tok.encode(x,add_special_tokens=False)[0] for x in CODE.values()}
 if any(len(tok.encode(x,add_special_tokens=False))!=1 for x in CODE.values()):raise RuntimeError('action codes must be single tokens')
 def text(r):return '<|user|>METHOD_POLICY '+r['prompt']+'<|assistant|>'
 def batch(rs):
  e=tok([text(r) for r in rs],padding=True,truncation=True,max_length=96,return_tensors='pt');last=e['attention_mask'].sum(1)-1;return e,last
 @torch.no_grad()
 def evaluate(m,rs):
  m.eval();e,last=batch(rs);log=m(**e).logits;ids=torch.tensor([target_ids[x] for x in CODE.values()]);sel=log[torch.arange(len(rs)),last][:,ids];pi=sel.argmax(1).tolist();codes=list(CODE.values());inv={v:k for k,v in CODE.items()};pred=[inv[codes[i]] for i in pi];det=[{**r,'predicted':p,'pass':p==r['action']} for r,p in zip(rs,pred)];return {'accuracy':sum(x['pass'] for x in det)/len(det),'correct':sum(x['pass'] for x in det),'total':len(det),'details':det}
 baseline=evaluate(base,test)
 import unsloth
 from unsloth import FastLanguageModel
 from unsloth.models.llama import FastLlamaModel
 import unsloth.models.llama as ul;ul.DEVICE_TYPE_TORCH='cpu';FastLlamaModel.patch_peft_model=staticmethod(lambda model,use_gradient_checkpointing=True:model)
 m=FastLanguageModel.get_peft_model(base,r=8,target_modules=['q_proj','k_proj','v_proj','o_proj'],lora_alpha=16,lora_dropout=0,bias='none',use_gradient_checkpointing=False,random_state=a.seed,modules_to_save=['lm_head'])
 before={n:p.detach().clone() for n,p in m.named_parameters() if p.requires_grad};opt=torch.optim.AdamW([p for p in m.parameters() if p.requires_grad],lr=a.lr,weight_decay=0)
 e,last=batch(train); ids=torch.tensor([target_ids[x] for x in CODE.values()]); code_index={v:i for i,v in enumerate(CODE.values())}; y=torch.tensor([code_index[r['code']] for r in train]);hist=[];st=time.time()
 for ep in range(a.epochs):
  m.train();opt.zero_grad();log=m(**e).logits;sel=log[torch.arange(len(train)),last][:,ids];loss=torch.nn.functional.cross_entropy(sel,y);loss.backward();opt.step()
  if ep in {0,1,2,4,9,19,49,99,199,299,399,a.epochs-1}:hist.append({'epoch':ep+1,'loss':float(loss.detach())})
 candidate=evaluate(m,test);delta=max(float((p.detach()-before[n]).abs().max()) for n,p in m.named_parameters() if p.requires_grad)
 out=Path(a.output_dir);out.mkdir(parents=True,exist_ok=True);m.save_pretrained(out);tok.save_pretrained(out)
 # Exhaustive contract test includes all 16 states and both unseen serializations = 32 cases.
 critical_errors=[x for x in candidate['details'] if not x['pass'] and x['action'] in {'BLOCK_CONTRADICTION','BLOCK_UNAVAILABLE'}]
 status='PASS' if candidate['accuracy']==1 and not critical_errors and delta>0 else 'FAIL'
 rep={'schema':'unsloth-method-policy-proof-v1','status':status,'free_language_used':False,'contract_states':16,'train_serializations':[0,1],'hidden_serializations':[2,3],'train_cases':len(train),'hidden_cases':len(test),'baseline':baseline,'candidate':candidate,'critical_errors':critical_errors,'training':{'epochs':a.epochs,'lr':a.lr,'loss_history':hist,'max_weight_delta':delta,'elapsed_seconds':time.time()-st},'adapter_sha256':{q.name:hashlib.sha256(q.read_bytes()).hexdigest() for q in out.iterdir() if q.is_file()}}
 Path(a.report).write_text(json.dumps(rep,indent=2),encoding='utf-8');print(json.dumps({'status':status,'baseline':baseline['accuracy'],'candidate':candidate['accuracy'],'critical_errors':len(critical_errors)}));raise SystemExit(0 if status=='PASS' else 2)
if __name__=='__main__':main()
