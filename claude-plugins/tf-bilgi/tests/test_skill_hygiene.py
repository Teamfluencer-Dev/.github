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

    def test_gizli_mode_never_touches_the_document(self):
        paylas = metin(PLUGIN / "skills" / "paylas" / "SKILL.md")
        bolum = paylas.split("## Gizli mode", 1)[1].split("\n## ", 1)[0]
        kurallar, adimlar = bolum.split("\nG1. ", 1)
        self.assertIn("Never read the document", kurallar)
        for komut in ("`TFB kb tara`", "`TFB maskele`", "`TFB kb ham-ekle`", "`TFB kb eslestir`"):
            self.assertIn(komut, kurallar, komut)  # yasak listesinde
        for parca in ("ham-ekle", "maskele", "eslestir", "metin.txt"):
            self.assertNotIn(parca, adimlar, parca)  # adımlarda belgeye dokunan komut yok
        okunanlar = re.findall(r"\bRead\b[^`]{0,40}?`([^`]+)`", adimlar)  # satır sonu da olabilir
        self.assertTrue(okunanlar)
        for yol in okunanlar:  # Read yalnız depo klonundaki dosyalara ya da çalıştırmanın klasörüne
            self.assertRegex(yol, r"^<(kok|D)>/", yol)
        self.assertEqual(adimlar.count("TFB kb tara"), 1)
        self.assertIn("TFB kb tara <D>/girdi.md", adimlar)  # yalnız kaydın kendisi taranır
        for secenek in ("--gizli-link-dosya <D>/link.txt", "TFB gizli-alicilar", "TFB temizle <D>", "taslak --help"):
            self.assertIn(secenek, adimlar, secenek)
        self.assertIn("gizli  : evet · içerik depoya girmez · link:", adimlar)

    def test_gizli_drive_steps_always_check_general_access(self):
        paylas = metin(PLUGIN / "skills" / "paylas" / "SKILL.md")
        g4 = paylas.split("\nG4. ", 1)[1].split("\nG5. ", 1)[0]
        self.assertNotIn("Unless the user already gave a Drive link", g4)  # verilen linkte de erişim denetlenir
        self.assertIn("also when the user already gave a Drive link", g4)
        self.assertIn("Paylaşımı kontrol et", g4)
        for yasak in ('"Teamfluencer" (kuruluş geneli', '"Bağlantıya sahip olan herkes"', "Ortak drive"):
            self.assertIn(yasak, g4, yasak)
        for baslik in ('header "Konum"', 'header "Kişiler"', 'header "Genel erişim"'):
            self.assertIn(baslik, g4, baslik)  # üç ayrı onay
        self.assertIn("none is inferred from another", g4)
        g8 = paylas.split("\nG8. ", 1)[1].split("\nG9. ", 1)[0]
        satir = [s for s in g8.splitlines() if s.strip().startswith("paylaşım:")]
        self.assertEqual(len(satir), 1)
        self.assertIn("genel erişim Kısıtlı — <kullanıcı onayladı | connector doğruladı>", satir[0])
        self.assertIn("states only what G4 confirmed", g8)

    def test_gizli_shared_drive_copy_link_is_required(self):
        paylas = metin(PLUGIN / "skills" / "paylas" / "SKILL.md")
        g4 = paylas.split("\nG4. ", 1)[1].split("\nG5. ", 1)[0]
        g5 = paylas.split("\nG5. ", 1)[1].split("\nG6. ", 1)[0]
        self.assertIn("Kopyasını oluştur", g4)
        self.assertIn("kopya oluşturmadıysan gerekmez; kopya oluşturduysan kopyanın bağlantısı şart", g4)
        self.assertIn("a copy was made in step 1", g4)  # üç soru kopyanın linki için yeniden
        self.assertIn("**and** no copy was made in G4 step 1", g5)
        self.assertIn("the copy's link is required", g5)
        self.assertIn("never record the original shared-drive link", g5)
        self.assertIn("ask the three G4 questions again for the copy", g5)
        self.assertNotIn("Unless the user already gave it, ask for the link", g5)
        self.assertIn("at most 40 characters", g5)

    def test_gizli_recovery_overwrites_same_id(self):
        paylas = metin(PLUGIN / "skills" / "paylas" / "SKILL.md")
        g9 = paylas.split("\nG9. ", 1)[1].split("\nSeveral gizli documents", 1)[0]
        for parca in ("TFB yaz --dosya <D>/girdi.md --uzerine", "at most 2 rounds", "never\n       write a second entry file",
                      "id already written", "`<D>` is kept"):
            self.assertIn(parca, g9, parca)

    def test_bulk_share_refuses_gizli(self):
        toplu = metin(PLUGIN / "skills" / "toplu-paylas" / "SKILL.md")
        adim0 = toplu.index("0. **Gizli?**")
        self.assertLess(adim0, toplu.index("TFB hazirla"))  # hazırlıktan önce durur
        self.assertIn("stop before staging anything", toplu[adim0:adim0 + 600])
        self.assertIn("Do not run `hazirla` or `toplu-hazirla`", toplu[adim0:adim0 + 600])

    def test_only_the_helper_runs_in_bash(self):
        for md in SKILLS:
            izinler = re.search(r"(?ms)^allowed-tools:\n(.*?)^---", metin(md)).group(1)
            bash = [s for s in izinler.splitlines() if "Bash(" in s]
            self.assertEqual(bash, ['  - Bash(python3 "${CLAUDE_PLUGIN_ROOT}/scripts/tf_bilgi.py" *)'], md)


if __name__ == "__main__":
    unittest.main()
