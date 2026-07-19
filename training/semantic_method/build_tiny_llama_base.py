from __future__ import annotations
import argparse, json, random
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from semantic_method_contract import ACTION_CODES, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True)
    ap.add_argument("--site", default="/mnt/data/m2323_site")
    ap.add_argument("--seed", type=int, default=2323)
    args = ap.parse_args()
    sys.path.insert(0, args.site)
    import torch
    from tokenizers import Tokenizer
    from tokenizers.models import WordLevel
    from tokenizers.pre_tokenizers import WhitespaceSplit
    from transformers import PreTrainedTokenizerFast, LlamaConfig, LlamaForCausalLM

    random.seed(args.seed); torch.manual_seed(args.seed)
    texts = []
    for r in rows(range(8)):
        texts.append("<|user|> SEMANTIC_METHOD " + r["prompt"] + " <|assistant|>")
    words = sorted({w for text in texts for w in text.split()} | set(ACTION_CODES.values()))
    specials = ["<pad>", "<unk>", "<bos>", "<eos>", "<|user|>", "<|assistant|>"]
    vocab_words = specials + [w for w in words if w not in specials]
    vocab = {w: i for i, w in enumerate(vocab_words)}
    tk = Tokenizer(WordLevel(vocab, unk_token="<unk>"))
    tk.pre_tokenizer = WhitespaceSplit()
    tok = PreTrainedTokenizerFast(
        tokenizer_object=tk,
        pad_token="<pad>", unk_token="<unk>", bos_token="<bos>", eos_token="<eos>",
        additional_special_tokens=["<|user|>", "<|assistant|>"],
    )
    cfg = LlamaConfig(
        vocab_size=len(tok), hidden_size=32, intermediate_size=64,
        num_hidden_layers=1, num_attention_heads=4, num_key_value_heads=4,
        max_position_embeddings=128, pad_token_id=tok.pad_token_id,
        bos_token_id=tok.bos_token_id, eos_token_id=tok.eos_token_id,
        tie_word_embeddings=False,
    )
    model = LlamaForCausalLM(cfg)
    out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(out); tok.save_pretrained(out)
    meta = {
        "schema": "tiny-local-llama-semantic-method-base-v1",
        "seed": args.seed,
        "parameters": sum(p.numel() for p in model.parameters()),
        "vocab_size": len(tok),
        "no_external_checkpoint": True,
    }
    (out / "BASE_MODEL_METADATA.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps(meta))

if __name__ == "__main__":
    main()
