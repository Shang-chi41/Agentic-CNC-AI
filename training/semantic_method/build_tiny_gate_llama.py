from __future__ import annotations
import argparse,json,random,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
from semantic_gate_contract import ACTION_CODES,rows

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--site',default='/mnt/data/m2323_site');p.add_argument('--seed',type=int,default=2330);a=p.parse_args();sys.path.insert(0,a.site)
 import torch
 from tokenizers import Tokenizer
 from tokenizers.models import WordLevel
 from tokenizers.pre_tokenizers import WhitespaceSplit
 from transformers import PreTrainedTokenizerFast,LlamaConfig,LlamaForCausalLM
 random.seed(a.seed);torch.manual_seed(a.seed)
 texts=["<|user|> SEMANTIC_GATE "+r['prompt']+" <|assistant|>" for r in rows(range(8))]
 words=sorted({w for x in texts for w in x.split()}|set(ACTION_CODES.values()))
 sp=['<pad>','<unk>','<bos>','<eos>','<|user|>','<|assistant|>'];vv=sp+[w for w in words if w not in sp];v={w:i for i,w in enumerate(vv)}
 t=Tokenizer(WordLevel(v,unk_token='<unk>'));t.pre_tokenizer=WhitespaceSplit();tok=PreTrainedTokenizerFast(tokenizer_object=t,pad_token='<pad>',unk_token='<unk>',bos_token='<bos>',eos_token='<eos>',additional_special_tokens=['<|user|>','<|assistant|>'])
 cfg=LlamaConfig(vocab_size=len(tok),hidden_size=32,intermediate_size=64,num_hidden_layers=1,num_attention_heads=4,num_key_value_heads=4,max_position_embeddings=64,pad_token_id=tok.pad_token_id,bos_token_id=tok.bos_token_id,eos_token_id=tok.eos_token_id,tie_word_embeddings=False)
 m=LlamaForCausalLM(cfg);o=Path(a.output);o.mkdir(parents=True,exist_ok=True);m.save_pretrained(o);tok.save_pretrained(o);meta={'schema':'tiny-gate-llama-v1','seed':a.seed,'parameters':sum(q.numel() for q in m.parameters()),'vocab_size':len(tok),'no_external_checkpoint':True};(o/'BASE_MODEL_METADATA.json').write_text(json.dumps(meta,indent=2));print(json.dumps(meta))
if __name__=='__main__':main()
