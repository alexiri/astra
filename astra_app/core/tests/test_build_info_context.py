from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch


@lru_cache(maxsize=1)
def _get_build_sha() -> object:
    project_dir = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(project_dir))
    from core.build_info import get_build_sha

    return get_build_sha


class BuildInfoTests(TestCase):
    def test_build_info_reads_env(self) -> None:
        with patch.dict(os.environ, {"ASTRA_BUILD_SHA": "abc1234"}):
            get_build_sha = _get_build_sha()
            self.assertEqual(get_build_sha(), "abc1234")

    def test_build_info_missing_env_returns_empty(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            get_build_sha = _get_build_sha()
            self.assertEqual(get_build_sha(), "")
