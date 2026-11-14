import hashlib
import logging
from typing import Any, Dict, List, Optional
import numpy as np

logger = logging.getLogger("inclusive_ats.ml.embeddings")


class EmbeddingEncoder:
    def __init__(
        self,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        device: str = "cpu",
        chunk_tokens: int = 240,
        batch_size: int = 16
    ):
        self.model_name = model_name
        self.device = device
        self.chunk_tokens = chunk_tokens
        self.batch_size = batch_size
        self._cache: Dict[str, np.ndarray] = {}
        
        import torch
        from sentence_transformers import SentenceTransformer

        self._torch = torch
        logger.info(f"Loading SentenceTransformer encoder '{model_name}' on {device}...")
        self.encoder = SentenceTransformer(model_name, device=device)
        self.encoder.eval()
        self.tokenizer = self.encoder.tokenizer
        
        # Fallback special token IDs
        self.cls_token_id = getattr(self.tokenizer, "cls_token_id", 101) or 101
        self.sep_token_id = getattr(self.tokenizer, "sep_token_id", 102) or 102
        logger.info("SentenceTransformer encoder initialized successfully.")

    def _get_cache_key(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def encode(self, texts: List[str]) -> np.ndarray:
        """
        Encodes a list of texts into 384-dimensional normalized embeddings
        using token-weighted normalized chunk pooling matching training.
        """
        unique_texts = list(dict.fromkeys(texts))
        vectors: Dict[str, np.ndarray] = {}
        pending_texts: List[str] = []

        # Check cache
        for text in unique_texts:
            key = self._get_cache_key(text)
            if key in self._cache:
                vectors[text] = self._cache[key]
            else:
                pending_texts.append(text)

        if pending_texts:
            sums = np.zeros((len(pending_texts), 384), dtype=np.float64)
            weights = np.zeros(len(pending_texts), dtype=np.float64)
            batch: List[Dict[str, Any]] = []
            owners: List[int] = []
            sizes: List[int] = []

            def flush():
                tokens = self.tokenizer.pad(batch, padding=True, return_tensors="pt")
                tokens = {k: v.to(self.encoder.device) for k, v in tokens.items()}
                with self._torch.inference_mode():
                    output = self.encoder(tokens)["sentence_embedding"]
                    output = self._torch.nn.functional.normalize(output, p=2, dim=1).cpu().numpy()
                for vec, owner, size in zip(output, owners, sizes):
                    sums[owner] += vec * size
                    weights[owner] += size
                batch.clear()
                owners.clear()
                sizes.clear()

            for owner, text in enumerate(pending_texts):
                ids = self.tokenizer.encode(text, add_special_tokens=False, truncation=False)
                for start in range(0, max(1, len(ids)), self.chunk_tokens):
                    chunk = ids[start:start + self.chunk_tokens]
                    seq = [self.cls_token_id] + chunk + [self.sep_token_id]
                    encoded = {
                        "input_ids": seq,
                        "token_type_ids": [0] * len(seq),
                        "attention_mask": [1] * len(seq)
                    }
                    batch.append(encoded)
                    owners.append(owner)
                    sizes.append(max(1, len(chunk)))
                    if len(batch) >= self.batch_size:
                        flush()

            if batch:
                flush()

            for owner, text in enumerate(pending_texts):
                denom = max(weights[owner], 1.0)
                vec = sums[owner] / denom
                norm = max(float(np.linalg.norm(vec)), 1e-12)
                norm_vec = (vec / norm).astype(np.float32)
                vectors[text] = norm_vec
                
                # Cache vector in memory (limit cache to 5000 items)
                if len(self._cache) < 5000:
                    self._cache[self._get_cache_key(text)] = norm_vec

        return np.stack([vectors[t] for t in texts])
