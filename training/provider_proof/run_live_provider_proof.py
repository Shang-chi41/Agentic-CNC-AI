#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,os,socket,sys,time
from pathlib import Path

def main():
 p=argparse.ArgumentParser();p.add_argument('--report',required=True);a=p.parse_args()
 root=Path(__file__).resolve().parents[2];sys.path.insert(0,str(root))
 from edge_backend.ai.closed_enum_classifier import validate_classification_result
 req={
  'schema':'closed-enum-clarification-request-v1','request_id':'live-provider-proof',
  'pending_question':'Bạn muốn giữ hay khoét phần chữ nhật?',
  'allowed_fields':['F1.role'],
  'allowed_values':{'F1.role':['RECTANGULAR_POCKET','RECTANGULAR_CONTOUR_INSIDE','RECTANGULAR_CONTOUR_OUTSIDE']},
  'user_message':'Giữ nguyên phần giữa và cho dao chạy vòng ngoài',
  'rules':{'abstain_when_unclear':True,'numbers_forbidden':True,'coordinates_forbidden':True,'tool_ids_forbidden':True,'machine_authority_forbidden':True},
 }
 report={'schema':'live-provider-empirical-proof-v1','time_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'request':req,'providers':{}}
 # OpenRouter: cannot be called without an externally issued credential.
 if not os.getenv('OPENROUTER_API_KEY'):
  report['providers']['openrouter']={'status':'BLOCKED_MISSING_CREDENTIAL','credential_env':'OPENROUTER_API_KEY','live_call_performed':False}
 else:
  try:
   from edge_backend.ai.providers.openrouter_provider import OpenRouterProvider
   provider=OpenRouterProvider();t=time.monotonic();raw=provider.classify_closed_enum(req);elapsed=time.monotonic()-t
   accepted,trace=validate_classification_result(raw,req)
   report['providers']['openrouter']={'status':'PASS' if accepted.get('F1.role')=='RECTANGULAR_CONTOUR_OUTSIDE' else 'FAIL','live_call_performed':True,'model':provider.model,'elapsed_seconds':elapsed,'raw':raw,'validation':trace,'error':provider.last_classification_error}
  except Exception as e:
   report['providers']['openrouter']={'status':'FAIL','live_call_performed':True,'error':f'{type(e).__name__}: {e}'}
 # Ollama: first prove an actual server and model are available, then classify.
 try:
  import requests
  from edge_backend.ai.providers.ollama_provider import OllamaProvider
  provider=OllamaProvider();tags_url=provider.base_url.rstrip('/')+'/tags';t=time.monotonic();resp=requests.get(tags_url,timeout=3);health_elapsed=time.monotonic()-t
  if resp.status_code!=200: raise RuntimeError(f'Ollama tags HTTP {resp.status_code}')
  models=[m.get('name') or m.get('model') for m in (resp.json().get('models') or [])]
  if provider.model not in models and not any(str(m).split(':')[0]==provider.model.split(':')[0] for m in models):
   report['providers']['ollama']={'status':'BLOCKED_MODEL_NOT_AVAILABLE','live_server':True,'live_call_performed':False,'base_url':provider.base_url,'configured_model':provider.model,'available_models':models,'health_seconds':health_elapsed}
  else:
   t=time.monotonic();raw=provider.classify_closed_enum(req);elapsed=time.monotonic()-t;accepted,trace=validate_classification_result(raw,req)
   report['providers']['ollama']={'status':'PASS' if accepted.get('F1.role')=='RECTANGULAR_CONTOUR_OUTSIDE' else 'FAIL','live_server':True,'live_call_performed':True,'base_url':provider.base_url,'model':provider.model,'elapsed_seconds':elapsed,'raw':raw,'validation':trace,'error':provider.last_classification_error}
 except Exception as e:
  report['providers']['ollama']={'status':'BLOCKED_ENDPOINT_UNAVAILABLE','live_server':False,'live_call_performed':False,'base_url':os.getenv('OLLAMA_BASE_URL','http://localhost:11434/api'),'error':f'{type(e).__name__}: {e}'}
 statuses=[v['status'] for v in report['providers'].values()]
 report['overall']='PASS' if statuses==['PASS','PASS'] else 'BLOCKED' if any(x.startswith('BLOCKED') for x in statuses) else 'FAIL'
 Path(a.report).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
 print(json.dumps({'overall':report['overall'],'statuses':statuses},ensure_ascii=False))
 raise SystemExit(0 if report['overall']=='PASS' else 3 if report['overall']=='BLOCKED' else 2)
if __name__=='__main__':main()
