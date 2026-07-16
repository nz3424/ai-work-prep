import argparse

from src.tokenizer import BPETokenizer
from src.transformer import ModelConfig, TinyTransformer
import torch

def load_checkpoint(checkpoint_path: str, tokenizer_path: str) -> tuple[TinyTransformer, BPETokenizer]:
    checkpoint = torch.load(checkpoint_path, map_location="cpu")
    model_config = ModelConfig(**checkpoint["model_config"])
    model = TinyTransformer(model_config)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()
    tokenizer = BPETokenizer.load(tokenizer_path)
    return model, tokenizer

def generate(model: TinyTransformer, tokenizer: BPETokenizer, prompt: str,
             max_new_tokens: int, temperature: float = 1.0, top_k: int | None = None, seed: int | None = None) -> str:
    
    

    if seed is not None:
            torch.manual_seed(seed)

    encoded_prompt = torch.tensor(tokenizer.encode(prompt), dtype=torch.long).unsqueeze(0) 
    for _ in range(max_new_tokens):
        with torch.no_grad():
            logits = model(encoded_prompt[:, -model.config.context_length:])
            # (1, seq_len, vocab_size) -> (1, vocab_size)
            logits = logits[:, -1, :] / temperature 
            if top_k is not None:
                assert top_k <= tokenizer.vocab_size, f"top_k {top_k} exceeds vocab_size {tokenizer.vocab_size}"
                top_k_values, top_k_indices = torch.topk(logits, top_k)
                logits[logits < top_k_values[:, [-1]]] = float('-inf')
            probs = torch.softmax(logits, dim=-1)  
            next_token = torch.multinomial(probs, num_samples=1)  
            encoded_prompt = torch.cat([encoded_prompt, next_token], dim=1) 
    generated_ids = encoded_prompt.squeeze(0).tolist()
    return tokenizer.decode(generated_ids)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sample text from a trained checkpoint.")
    parser.add_argument("--checkpoint-path", default="checkpoints/model.pt")
    parser.add_argument("--tokenizer-path", default="checkpoints/tokenizer.json")
    parser.add_argument("--prompt", default="\n")
    parser.add_argument("--max-new-tokens", type=int, default=200)
    parser.add_argument("--temperature", type=float, default=1.0)
    parser.add_argument("--top-k", type=int, default=None)
    parser.add_argument("--seed", type=int, default=None)
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    model, tokenizer = load_checkpoint(args.checkpoint_path, args.tokenizer_path)
    print(generate(
        model, tokenizer, args.prompt, args.max_new_tokens,
        temperature=args.temperature, top_k=args.top_k, seed=args.seed,
    ))