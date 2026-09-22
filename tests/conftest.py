"""Loads .env before test collection, so real credentials (GROQ_API_KEY,
WANDB_API_KEY, etc.) configured in it are visible to skipif conditions and
test bodies alike — without this, a skipif checking os.environ directly
would incorrectly skip live-credential tests just because nothing had
triggered shared/env.py's import-time side effect yet."""

import shared.env  # noqa: F401
