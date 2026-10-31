"""一键运行全部单元测试：``py tests/run_tests.py``。

- 自动把 ``src/`` 加入 import 路径
- 把 ``BLUEWHALE_DATA_DIR`` 指向临时目录，避免污染用户数据
- 全部通过 exit 0，失败 exit 1
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"


def main() -> int:
    # Windows GBK 控制台下避免个别字符导致 unittest 输出崩溃
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except Exception:  # noqa: BLE001
            pass
    sys.path.insert(0, str(SRC))
    temp_data = Path(tempfile.mkdtemp(prefix="bluewhale-tests-"))
    os.environ["BLUEWHALE_DATA_DIR"] = str(temp_data)
    try:
        loader = unittest.TestLoader()
        suite = loader.discover(str(ROOT / "tests"), pattern="test_*.py", top_level_dir=str(ROOT / "tests"))
        runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
        result = runner.run(suite)
    finally:
        shutil.rmtree(temp_data, ignore_errors=True)
    total = result.testsRun
    failures = len(result.failures) + len(result.errors)
    if result.wasSuccessful():
        print(f"\nALL TESTS PASSED ({total} tests)")
        return 0
    print(f"\nTESTS FAILED: {failures} / {total}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
