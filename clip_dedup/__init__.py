import os

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import open_clip  # noqa: E402

from clip_dedup.cli import main  # noqa: E402

__version__ = "0.1.0"
