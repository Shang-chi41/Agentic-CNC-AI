#!/usr/bin/env python3
from __future__ import annotations
import argparse,itertools,json,random
from pathlib import Path
import numpy as np, torch
torch.set_num_threads(1)
from torch import nn
import torchcde
from sklearn.metrics import roc_auc_score,average_precision_score
ACTIONS=['BIND_CONFIRMED','RESOLVE_SYSTEM','ASK_USER','BLOCK_CONTRADICTION','BLOCK_UNAVAILABLE']
STAGES=['OBSERVE','CHECK_CONTRADICTION','CHECK_CONFIRMED','CHECK_OWNERSHIP','CHECK_RESOLVER','EMIT_ACTION']
def oracle(c,k,s,a):
 if k:return 3
 if c:return 0
 if s and not a:return 4
 if s:return 1
 return 2
def trajectory(bits,action=None,jitter=0.,seed=0):
 c,k,s,a=bits; action=oracle(c,k,s,a) if action is None else action;rng=np.random.default_rng(seed);rows=[]
 for i in range(6):
  x=np.array([c,k,s,a]+[int(j==i) for j in range(6)]+[int(i==5 and j==action) for j in range(5)],dtype=np.float32)
  if jitter:x+=rng.normal(0,jitter,len(x)).astype(np.float32)
  rows.append(x)
 return np.stack(rows)
class Func(nn.Module):
 def __init__(self,h,c):super().__init__();self.h=h;self.c=c;self.n=nn.Sequential(nn.Linear(h,48),nn.Tanh(),nn.Linear(48,h*c))
 def forward(self,z):return self.n(z).view(-1,self.h,self.c)
class CDE(nn.Module):
 def __init__(self,c,h=20):super().__init__();self.i=nn.Linear(c,h);self.f=Func(h,c);self.g=nn.Sequential(nn.Linear(c,32),nn.Tanh(),nn.Linear(32,c));self.o=nn.Linear(h,c)
 def forward(self,x0,dx):
  z=self.i(x0)
  for j in range(dx.shape[1]):
   d=torch.sigmoid(self.g(dx[:,j]))*dx[:,j];z=z+torch.bmm(self.f(z),d.unsqueeze(-1)).squeeze(-1)
  return self.o(z)
def controls(arr):
 # Genuine continuous control: natural cubic spline over prefix, derivatives at interval midpoints.
 x=torch.tensor(arr[:,:5]);t=torch.arange(5,dtype=x.dtype);coef=torchcde.natural_cubic_coeffs(x,t=t);sp=torchcde.CubicSpline(coef,t=t);x0=sp.evaluate(t[0]);dx=torch.stack([sp.derivative((t[j]+t[j+1])/2) for j in range(4)],1);target=torch.tensor(arr[:,5]);return x0,dx,target
def main():
 p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--report',required=True);p.add_argument('--epochs',type=int,default=350);p.add_argument('--seeds',default='11,23,47');a=p.parse_args();states=list(itertools.product([0,1],repeat=4));runs=[];best=None
 for seed in map(int,a.seeds.split(',')):
  random.seed(seed);np.random.seed(seed);torch.manual_seed(seed)
  train=np.stack([trajectory(b,jitter=.001,seed=seed*1000+i*20+j) for i,b in enumerate(states) for j in range(6)])
  cal=np.stack([trajectory(b) for b in states]+[trajectory(b,jitter=.001,seed=seed*2000+i) for i,b in enumerate(states)])
  x0,dx,y=controls(train);m=CDE(train.shape[-1]);opt=torch.optim.AdamW(m.parameters(),lr=.008,weight_decay=1e-6);hist=[]
  for ep in range(a.epochs):
   pred=m(x0,dx);loss=((pred-y)**2).mean();opt.zero_grad();loss.backward();torch.nn.utils.clip_grad_norm_(m.parameters(),5);opt.step()
   if ep in {0,1,2,4,9,19,49,99,199,a.epochs-1}:hist.append({'epoch':ep+1,'loss':float(loss.detach())})
  def err(arr):
   a0,ad,ay=controls(arr);m.eval()
   with torch.no_grad():return ((m(a0,ad)-ay)**2).mean(1).numpy()
  ce=err(cal);threshold=float(np.max(ce)*1.05+1e-9)
  succ=np.stack([trajectory(b) for b in states]);se=err(succ)
  fails=np.stack([trajectory(b,w) for b in states for w in range(5) if w!=oracle(*b)]);fe=err(fails)
  ylab=np.r_[np.zeros(len(se)),np.ones(len(fe))];score=np.r_[se,fe];pred=score>threshold;tp=int(((pred==1)&(ylab==1)).sum());fp=int(((pred==1)&(ylab==0)).sum());fn=int(((pred==0)&(ylab==1)).sum());tn=int(((pred==0)&(ylab==0)).sum());prec=tp/(tp+fp) if tp+fp else 0;rec=tp/(tp+fn) if tp+fn else 0;f1=2*prec*rec/(prec+rec) if prec+rec else 0
  r={'seed':seed,'train_success_only':True,'success_train':len(train),'heldout_success':len(se),'failure_cases':len(fe),'threshold':threshold,'tp':tp,'fp':fp,'fn':fn,'tn':tn,'precision':prec,'recall':rec,'f1':f1,'success_false_positive_rate':fp/len(se),'failure_detection_rate':tp/len(fe),'auroc':float(roc_auc_score(ylab,score)),'auprc':float(average_precision_score(ylab,score)),'history':hist};runs.append(r)
  if best is None or f1>best[0]:best=(f1,m.state_dict(),seed)
 status='PASS' if all(r['fp']==0 and r['fn']==0 for r in runs) else 'FAIL';rep={'schema':'method-policy-oat-neural-cde-v2','status':status,'scope':'finite structured Method Policy contract; no free language','seeds':runs,'gates':{'all_seed_false_positive_zero':all(r['fp']==0 for r in runs),'all_seed_false_negative_zero':all(r['fn']==0 for r in runs),'train_success_only':all(r['train_success_only'] for r in runs)}};Path(a.report).write_text(json.dumps(rep,indent=2));Path(a.out).parent.mkdir(parents=True,exist_ok=True);torch.save({'state_dict':best[1],'seed':best[2],'actions':ACTIONS},a.out);print(json.dumps({'status':status,'runs':[{k:r[k] for k in ['seed','fp','fn','f1','auroc']} for r in runs]}));raise SystemExit(0 if status=='PASS' else 2)
if __name__=='__main__':main()
