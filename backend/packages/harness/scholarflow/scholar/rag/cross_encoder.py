"""Cross-Encoder backends for ScholarFlow stage-2 rerank.

Real neural CE uses a local ONNX MiniLM (opt-in path / download).
``stub-cross-encoder`` is deterministic for unit tests only — never label stub
outputs as real Cross-Encoder quality results.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from abc import ABC, abstractmethod
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger("scholarflow.scholar.rag.cross_encoder")

DEFAULT_CE_REPO = "Xenova/ms-marco-MiniLM-L-6-v2"
DEFAULT_CE_ONNX = "onnx/model_quantized.onnx"
STUB_NAMES = {"stub-cross-encoder", "stub-ce"}
HYBRID_NAMES = {"hybrid-score", "lexical-overlap", "none", ""}


class CrossEncoderUnavailable(RuntimeError):
    """Raised when a real Cross-Encoder was requested but cannot be loaded."""


class CrossEncoderBackend(ABC):
    name: str
    is_stub: bool = False

    @abstractmethod
    def score_pairs(self, query: str, passages: list[str]) -> list[float]:
        raise NotImplementedError


class StubCrossEncoder(CrossEncoderBackend):
    """Deterministic lexical+hash scorer for offline unit tests only."""

    name = "stub-cross-encoder"
    is_stub = True

    def score_pairs(self, query: str, passages: list[str]) -> list[float]:
        q = set(re.findall(r"[a-z0-9]+", (query or "").lower()))
        out: list[float] = []
        for p in passages:
            toks = set(re.findall(r"[a-z0-9]+", (p or "").lower()))
            overlap = len(q & toks) / max(len(q), 1)
            h = int(hashlib.md5(f"{query}::{p[:200]}".encode()).hexdigest()[:8], 16)
            noise = (h % 1000) / 10000.0
            out.append(float(overlap + noise))
        return out


class OnnxMiniLMCrossEncoder(CrossEncoderBackend):
    """ONNX Cross-Encoder (ms-marco MiniLM) via onnxruntime — 8GB-friendly."""

    is_stub = False

    def __init__(self, model_dir: Path, *, max_length: int = 256) -> None:
        import onnxruntime as ort
        from tokenizers import Tokenizer

        self.model_dir = Path(model_dir)
        self.max_length = max_length
        tok_path = self.model_dir / "tokenizer.json"
        onnx_path = self.model_dir / "onnx" / "model_quantized.onnx"
        if not onnx_path.is_file():
            # accept flat layout
            alt = self.model_dir / DEFAULT_CE_ONNX.replace("/", os.sep)
            onnx_path = alt if alt.is_file() else onnx_path
        if not tok_path.is_file() or not onnx_path.is_file():
            raise CrossEncoderUnavailable(
                f"ONNX Cross-Encoder files missing under {self.model_dir} "
                f"(need tokenizer.json and {DEFAULT_CE_ONNX})"
            )
        self.tokenizer = Tokenizer.from_file(str(tok_path))
        self.tokenizer.enable_truncation(max_length=max_length)
        self.tokenizer.enable_padding(length=max_length)
        self.session = ort.InferenceSession(
            str(onnx_path),
            providers=["CPUExecutionProvider"],
        )
        self.name = f"onnx:{DEFAULT_CE_REPO}"
        self._input_names = {i.name for i in self.session.get_inputs()}

    def score_pairs(self, query: str, passages: list[str]) -> list[float]:
        if not passages:
            return []
        scores: list[float] = []
        # Batch in small chunks to keep peak RAM low on 8GB hosts
        batch_size = 8
        for start in range(0, len(passages), batch_size):
            batch = passages[start : start + batch_size]
            encs = [self.tokenizer.encode(query, p or "") for p in batch]
            ids = np.array([e.ids for e in encs], dtype=np.int64)
            mask = np.array([e.attention_mask for e in encs], dtype=np.int64)
            type_ids = np.array(
                [getattr(e, "type_ids", [0] * len(e.ids)) for e in encs],
                dtype=np.int64,
            )
            feeds: dict[str, Any] = {}
            if "input_ids" in self._input_names:
                feeds["input_ids"] = ids
            if "attention_mask" in self._input_names:
                feeds["attention_mask"] = mask
            if "token_type_ids" in self._input_names:
                feeds["token_type_ids"] = type_ids
            logits = self.session.run(None, feeds)[0]
            scores.extend(float(x) for x in np.asarray(logits).reshape(-1))
        return scores


def _default_model_dir() -> Path:
    env = os.getenv("SCHOLAR_RAG_CE_MODEL_DIR")
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "evaluation" / "models" / "ce-minilm"
        if candidate.is_dir():
            return candidate
        if (parent / "evaluation").is_dir() and (parent / "docs" / "scholar-flow").is_dir():
            return parent / "evaluation" / "models" / "ce-minilm"
    return Path.cwd() / "evaluation" / "models" / "ce-minilm"


def download_onnx_cross_encoder(model_dir: Path | None = None) -> Path:
    """Explicit download — never called unless SCHOLAR_RAG_ALLOW_MODEL_DOWNLOAD=1."""
    from huggingface_hub import hf_hub_download

    root = Path(model_dir) if model_dir else _default_model_dir()
    root.mkdir(parents=True, exist_ok=True)
    for filename in ("tokenizer.json", "config.json", DEFAULT_CE_ONNX):
        hf_hub_download(repo_id=DEFAULT_CE_REPO, filename=filename, local_dir=str(root))
    return root


def _allow_download() -> bool:
    return (os.getenv("SCHOLAR_RAG_ALLOW_MODEL_DOWNLOAD") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


@lru_cache(maxsize=4)
def _cached_backend(key: str) -> CrossEncoderBackend:
    if key in STUB_NAMES:
        return StubCrossEncoder()
    model_dir = _default_model_dir()
    onnx_path = model_dir / "onnx" / "model_quantized.onnx"
    if not onnx_path.is_file():
        if _allow_download():
            logger.info("Downloading ONNX Cross-Encoder to %s", model_dir)
            download_onnx_cross_encoder(model_dir)
        else:
            raise CrossEncoderUnavailable(
                "Real Cross-Encoder requested but model not found. "
                f"Place files under {model_dir} or set SCHOLAR_RAG_ALLOW_MODEL_DOWNLOAD=1 "
                "and SCHOLAR_RAG_RERANK_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2. "
                "Do not treat stub-cross-encoder as a real CE result."
            )
    return OnnxMiniLMCrossEncoder(model_dir)


def resolve_rerank_mode(rerank_model: str) -> str:
    name = (rerank_model or "hybrid-score").strip()
    if name in HYBRID_NAMES:
        return "hybrid-score" if name != "none" else "none"
    if name in STUB_NAMES:
        return "stub-cross-encoder"
    if name.startswith("cross-encoder/") or name.startswith("ce:") or "MiniLM" in name:
        return "cross-encoder"
    if name == "cross-encoder":
        return "cross-encoder"
    return name


def get_cross_encoder(rerank_model: str) -> CrossEncoderBackend | None:
    """Return a CE backend, or None when hybrid-score/none is selected."""
    mode = resolve_rerank_mode(rerank_model)
    if mode in {"hybrid-score", "none", "lexical-overlap"}:
        return None
    if mode == "stub-cross-encoder":
        return _cached_backend("stub-cross-encoder")
    if mode == "cross-encoder":
        return _cached_backend("cross-encoder")
    # Unknown name: try as CE path
    return _cached_backend("cross-encoder")


def clear_cross_encoder_cache() -> None:
    _cached_backend.cache_clear()
