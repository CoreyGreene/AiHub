"""mlx_lm's model server with MLX's cache of freed memory capped.

Started by models.py as its own program (python -m server.model_server --model ... --port ...), so letting go of a
model is just stopping it, and all its memory comes back. The cap comes from the model tests (2026-11-21): without
it, one very long answer from the Qwen models crashed MLX ("Resource limit exceeded").
  CODEAI_CACHE_GB=4 (from settings.json's cache_gb)
"""

import os
import sys

import mlx.core as mx

mx.set_cache_limit(int(float(os.environ.get("CODEAI_CACHE_GB", "4")) * 2**30))

from mlx_lm.server import main  # noqa: E402

sys.argv[0] = "mlx_lm.server"
main()
