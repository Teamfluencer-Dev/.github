"""Tests for summarize.py. Run: python3 -m unittest discover -s actions/coverage-summary"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import summarize  # noqa: E402

LCOV = """TN:
SF:/work/repo/src/services/pay.ts
FNF:4
FNH:2
LF:40
LH:10
BRF:10
BRH:2
end_of_record
SF:/work/repo/src/utils/fmt.ts
FNF:2
FNH:2
LF:30
LH:30
BRF:0
BRH:0
end_of_record
SF:src/tiny/one.ts
LF:5
LH:0
end_of_record
"""


class SummarizeTest(unittest.TestCase):
    def test_totals_and_weakest_directories(self):
        files = [dict(f, path=summarize.relative(f["path"], "/work/repo")) for f in summarize.parse(LCOV)]
        self.assertEqual([f["path"] for f in files], ["src/services/pay.ts", "src/utils/fmt.ts", "src/tiny/one.ts"])
        out = summarize.render(files, "API")
        self.assertIn("| Satır | 40 | 75 | **53.3%** |", out)
        self.assertIn("| Dal (branch) | 2 | 10 | 20.0% |", out)
        self.assertIn("| Fonksiyon | 4 | 6 | 66.7% |", out)
        # weakest first; directories under MIN_DIR_LINES (src/tiny, 5 lines) are left out
        self.assertLess(out.index("`src/services`"), out.index("`src/utils`"))
        self.assertNotIn("src/tiny", out)

    def test_missing_or_empty_report_never_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = subprocess.run([sys.executable, str(HERE / "summarize.py"), f"{tmp}/none.info", "X"],
                                     capture_output=True, text=True)
            self.assertEqual(missing.returncode, 0)
            self.assertIn("bulunamadı", missing.stdout)
            empty = Path(tmp) / "lcov.info"
            empty.write_text("TN:\n")
            result = subprocess.run([sys.executable, str(HERE / "summarize.py"), str(empty), "X"],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0)
            self.assertIn("hiç dosya yok", result.stdout)

    def test_zero_found_shows_dash(self):
        self.assertEqual(summarize.pct(0, 0), "—")


if __name__ == "__main__":
    unittest.main()
