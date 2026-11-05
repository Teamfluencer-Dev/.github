"""Skill text checks: document-derived text reaches kb.py through files, never through the shell.

Run: python3 -m unittest discover -s claude-plugins/tf-bilgi/tests -v
"""
import re
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
SKILLS = sorted((PLUGIN / "skills").rglob("SKILL.md"))
YAZAN_BECERILER = ("paylas", "toplu-paylas")


def metin(md):
    return md.read_text(encoding="utf-8")


class SkillShellHygieneTest(unittest.TestCase):
    def test_skills_found(self):
        self.assertEqual(sorted(md.parent.name for md in SKILLS), ["bilgi", "paylas", "toplu-paylas"])

    def test_no_heredoc_in_any_skill(self):
        for md in SKILLS:
            self.assertNotRegex(metin(md), r"<<-?\s*'?[A-Z_]{3,}'?", md)

    def test_taslak_title_not_on_command_line(self):
        for md in SKILLS:
            self.assertNotIn("--baslik '", metin(md), md)

    def test_no_document_text_in_shell_arguments(self):
        for md in SKILLS:
            govde = metin(md)
            self.assertNotIn("TFB gecici", govde, md)       # stdin/heredoc scratch path
            self.assertNotIn("--gerekce '", govde, md)      # reason goes through --gerekce-dosya
            self.assertNotRegex(govde, r"--mesaj '[^']*<baslik>", md)  # title goes through --mesaj-dosya

    def test_write_skills_can_write_scratch_files(self):
        for name in YAZAN_BECERILER:
            self.assertIn("Write(~/.tf-bilgi/gecici/**)", metin(PLUGIN / "skills" / name / "SKILL.md"), name)

    def test_write_skills_use_file_options(self):
        paylas = metin(PLUGIN / "skills" / "paylas" / "SKILL.md")
        for secenek in ("--baslik-dosya", "eslestir --dosya", "yaz --dosya", "--mesaj-dosya", "--gerekce-dosya"):
            self.assertIn(secenek, paylas, secenek)

    def test_write_skills_clean_up_staging(self):
        for name in YAZAN_BECERILER:
            govde = metin(PLUGIN / "skills" / name / "SKILL.md")
            self.assertIn("TFB temizle <D>", govde, name)
            self.assertRegex(govde, r"Vazgeç: reply \"Vazgeçildi; depoya hiçbir şey yazılmadı\.[^\"]*<D>", name)

    def test_only_the_helper_runs_in_bash(self):
        for md in SKILLS:
            izinler = re.search(r"(?ms)^allowed-tools:\n(.*?)^---", metin(md)).group(1)
            bash = [s for s in izinler.splitlines() if "Bash(" in s]
            self.assertEqual(bash, ['  - Bash(python3 "${CLAUDE_PLUGIN_ROOT}/scripts/tf_bilgi.py" *)'], md)


if __name__ == "__main__":
    unittest.main()
