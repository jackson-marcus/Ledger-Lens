"""Root conftest: stub fastembed/onnxruntime with a hash-based embedder.

On Windows dev/CI environments where onnxruntime_pybind11_state DLL is
unavailable, we replace fastembed.TextEmbedding with a deterministic
bag-of-words hash projection so embedding-based tests run offline.
"""

import hashlib
import re
import sys
import types

import numpy as np


class _StubEmbedding:
    """Deterministic lexical hash embedder standing in for fastembed."""

    def __init__(self, *args, **kwargs) -> None:
        pass

    def embed(self, texts):
        for text in texts:
            vec = np.zeros(96, dtype=np.float32)
            for tok in re.findall(r"[a-z0-9]+", str(text).lower()):
                vec[int(hashlib.md5(tok.encode()).hexdigest(), 16) % 96] += 1.0
            yield vec


def _stub_onnx_and_fastembed() -> None:
    try:
        import fastembed  # noqa: F401

        # Real fastembed imported fine, nothing to do
        return
    except (ImportError, OSError):
        pass

    # Stub fastembed
    if "fastembed" not in sys.modules:
        fe = types.ModuleType("fastembed")
        fe.TextEmbedding = _StubEmbedding
        sys.modules["fastembed"] = fe
    else:
        sys.modules["fastembed"].TextEmbedding = _StubEmbedding

    # Stub onnxruntime family
    for name in [
        "onnxruntime",
        "onnxruntime.capi",
        "onnxruntime.capi._pybind_state",
        "onnxruntime.capi.onnxruntime_pybind11_state",
    ]:
        if name not in sys.modules:
            sys.modules[name] = types.ModuleType(name)


_stub_onnx_and_fastembed()
