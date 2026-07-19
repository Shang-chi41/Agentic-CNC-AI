#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,random
from pathlib import Path
import torch
from torch import nn

FIELDS=["F1.role","F1.depth","F1.x_bounds","F1.y_bounds","tool.id","tool.diameter","stock.dimensions","stock.material","work_coordinate.origin","work_coordinate.z0","safe_z","feed","spindle","operating_range"]
ACTIONS=["BIND_CONFIRMED","RESOLVE_SYSTEM","ASK_USER","BLOCK_CONTRADICTION"]
SYSTEM={"tool.id","tool.diameter","safe_z","feed","spindle","operating_range"}

def label(field,confirmed,contradiction):
    if contradiction:return 3
    if confirmed:return 0
    if field in SYSTEM:return 1
    return 2

def vec(field,confirmed,contradiction):
    # Deliberately exclude field identity: the policy must learn authority, not memorize names.
    return [float(confirmed), float(contradiction), float(field in SYSTEM)]

def build(seed):
    rows=[]
    for f in FIELDS:
      for confirmed in (False,True):
       for contradiction in (False,True):
        if confirmed and contradiction: continue
        rows.append((vec(f,confirmed,contradiction),label(f,confirmed,contradiction),{"field":f,"confirmed":confirmed,"contradiction":contradiction}))
    random.Random(seed).shuffle(rows)
    return rows

class Net(nn.Module):
 def __init__(self):
  super().__init__(); self.net=nn.Sequential(nn.Linear(3,16),nn.ReLU(),nn.Linear(16,4))
 def forward(self,x): return self.net(x)

def main():
 p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--report',required=True);p.add_argument('--seed',type=int,default=3407);a=p.parse_args()
 torch.manual_seed(a.seed); rows=build(a.seed)
 # hidden combinations are fixed and include the user's exact failure pattern.
 hidden_keys={('F1.role',True,False),('tool.id',False,False),('tool.diameter',False,False),('F1.depth',False,False),('stock.dimensions',False,False),('work_coordinate.origin',False,False),('safe_z',False,False)}
 train=[r for r in rows if (r[2]['field'],r[2]['confirmed'],r[2]['contradiction']) not in hidden_keys]
 test=[r for r in rows if (r[2]['field'],r[2]['confirmed'],r[2]['contradiction']) in hidden_keys]
 X=torch.tensor([r[0] for r in train]); y=torch.tensor([r[1] for r in train])
 m=Net(); opt=torch.optim.AdamW(m.parameters(),lr=.03)
 torch.set_num_threads(1)
 for _ in range(120):
  opt.zero_grad(); loss=nn.functional.cross_entropy(m(X),y);loss.backward();opt.step()
 def eval_rows(rs):
  xx=torch.tensor([r[0] for r in rs]); pred=m(xx).argmax(1).tolist();
  details=[]
  for r,pred_i in zip(rs,pred): details.append({**r[2],"expected":ACTIONS[r[1]],"predicted":ACTIONS[pred_i],"pass":pred_i==r[1]})
  return sum(d['pass'] for d in details)/len(details),details
 train_acc,_=eval_rows(train); test_acc,details=eval_rows(test)
 out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True);torch.save({"state_dict":m.state_dict(),"fields":FIELDS,"actions":ACTIONS},out)
 report={"status":"PASS" if test_acc==1.0 else "FAIL","input_contract":"STRUCTURED_STATE_ONLY","free_language_used":False,"train_accuracy":train_acc,"hidden_accuracy":test_acc,"hidden_cases":details,"promotion_gate": test_acc==1.0}
 Path(a.report).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False))
 if test_acc!=1.0: raise SystemExit(2)
if __name__=='__main__':main()
