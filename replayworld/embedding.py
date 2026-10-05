from __future__ import annotations

import numpy as np

from .config import EmbeddingConfig


class Embedder:
    def __init__(self, config: EmbeddingConfig):
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(config.model, device=config.device)
        self.batch_size = config.batch_size

    def encode(self, texts: list[str]) -> np.ndarray:
        vectors = self.model.encode(
            texts,
            batch_size=self.batch_size,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return vectors.astype(np.float32)
