#!/usr/bin/env python3
from __future__ import annotations
import argparse,itertools,json,sys
from pathlib import Path
ACTIONS=['BIND_CONFIRMED','RESOLVE_SYSTEM','ASK_USER','BLOCK_CONTRADICTION','BLOCK_UNAVAILABLE']
CODE=dict(zip(ACTIONS,['RECTANGULAR_POCKET','RECTANGULAR_CONTOUR_INSIDE','RECTANGULAR_CONTOUR_OUTSIDE','true','abstain_when_unclear']))
def oracle(c,k,s,a):
 if k:return 'BLOCK_CONTRADICTION'
 if c:return 'BIND_CONFIRMED'
 if s and not a:return 'BLOCK_UNAVAILABLE'
 if s:return 'RESOLVE_SYSTEM'
 return 'ASK_USER'
def canonical(c,k,s,a,v):
 vals=['clarification_resolved' if c else 'pending_question','no_cross_layer_contradiction' if not k else 'coordinates_forbidden','machine_authority_false' if not s else 'provider_output_contains_no_rejected_fields','eligible_success' if a else 'abstain_when_unclear']
 if v==2:return '[ '+','.join(reversed(vals))+' ]'
 return '{ schema : v3 , input : [ '+','.join(vals)+' ] }'
def main():
 p=argparse.ArgumentParser();p.add_argument('--base-model',required=True);p.add_argument('--adapter',required=True);p.add_argument('--report',required=True);p.add_argument('--site',default='/mnt/data/unsloth_site');a=p.parse_args();sys.path.insert(0,a.site)
 import torch;torch.set_num_threads(1)
 from transformers import AutoModelForCausalLM,AutoTokenizer
 from peft import PeftModel
 tok=AutoTokenizer.from_pretrained(a.adapter);base=AutoModelForCausalLM.from_pretrained(a.base_model,dtype=torch.float32);m=PeftModel.from_pretrained(base,a.adapter);m.eval()
 ids=torch.tensor([tok.encode(x,add_special_tokens=False)[0] for x in CODE.values()]);inv={v:k for k,v in CODE.items()};codes=list(CODE.values());details=[]
 for bits in itertools.product([0,1],repeat=4):
  for v in (2,3):
   prompt='<|user|>METHOD_POLICY '+canonical(*bits,v)+'<|assistant|>';e=tok([prompt],return_tensors='pt');last=e['attention_mask'].sum(1)-1
   with torch.no_grad():sel=m(**e).logits[0,last.item(),ids];pred=inv[codes[int(sel.argmax())]]
   exp=oracle(*bits);details.append({'bits':bits,'variant':v,'expected':exp,'predicted':pred,'pass':pred==exp})
 critical=[x for x in details if not x['pass'] and x['expected'].startswith('BLOCK')];status='PASS' if all(x['pass'] for x in details) and not critical else 'FAIL';rep={'schema':'independent-unsloth-method-policy-reload-v1','status':status,'cases':len(details),'correct':sum(x['pass'] for x in details),'critical_errors':critical,'details':details};Path(a.report).write_text(json.dumps(rep,indent=2));print(json.dumps({k:rep[k] for k in ['status','cases','correct']}));raise SystemExit(0 if status=='PASS' else 2)
if __name__=='__main__':main()
