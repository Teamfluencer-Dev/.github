"""Skill text checks: document-derived text reaches kb.py through files, never through the shell.

Run: python3 -m unittest discover -s claude-plugins/tf-bilgi/tests -v
"""
import re
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
SKILLS = sorted((PLUGIN / "skills").rglob("SKILL.md"))
REFERANSLAR = sorted((PLUGIN / "skills").rglob("references/*.md"))
YAZAN_BECERILER = ("paylas", "toplu-paylas")
PAYLAS = PLUGIN / "skills" / "paylas" / "SKILL.md"
GIZLI = PLUGIN / "skills" / "paylas" / "references" / "gizli.md"
PR_LISTESI = PLUGIN / "skills" / "paylas" / "references" / "pr-listesi.md"
HIZLI_KOMUTU = ('python3 "${CLAUDE_PLUGIN_ROOT}/scripts/tf_bilgi.py" hizli [--yonetim] [--haber simdi] '
                "--ek '<path>' ... <<'TFB_NOT'")


def metin(md):
    return md.read_text(encoding="utf-8")


class SkillShellHygieneTest(unittest.TestCase):
    def test_skills_found(self):
        self.assertEqual(sorted(md.parent.name for md in SKILLS), ["bilgi", "paylas", "toplu-paylas"])

    def test_only_heredoc_is_the_quoted_hizli_note(self):
        """0.7.0: /paylas'ın tek komutu kullanıcının kendi sözlerini tırnaklı heredoc'la verir (kabuk yorumlamaz); başka
        hiçbir skill ya da referans dosyasında heredoc yok, belge metni hiçbir zaman heredoc'la gitmez."""
        for md in SKILLS + REFERANSLAR:
            heredoclar = re.findall(r"<<-?\s*'?[A-Z_]{3,}'?", metin(md))
            self.assertEqual(heredoclar, ["<<'TFB_NOT'"] if md == PAYLAS else [], md)
        paylas = metin(PAYLAS)
        self.assertEqual(paylas.count(HIZLI_KOMUTU), 1)
        self.assertRegex(paylas, r"<<'TFB_NOT'\n   <the user's own words from \$ARGUMENTS, verbatim; may be empty>\n   TFB_NOT\n")
        self.assertIn("pick another marker", paylas)

    def test_taslak_title_not_on_command_line(self):
        for md in SKILLS:
            self.assertNotIn("--baslik '", metin(md), md)

    def test_no_document_text_in_shell_arguments(self):
        for md in SKILLS:
            govde = metin(md)
            self.assertNotIn("TFB gecici", govde, md)       # stdin/heredoc scratch path
            self.assertNotIn("--gerekce '", govde, md)      # reason goes through --gerekce-dosya
            self.assertNotRegex(govde, r"--mesaj '[^']*<baslik>", md)  # title goes through --mesaj-dosya
            self.assertNotIn("--body", govde, md)           # GitHub comments only through the helper's stdin

    def test_write_skills_can_write_scratch_files(self):
        for name in YAZAN_BECERILER:
            self.assertIn("Write(~/.tf-bilgi/gecici/**)", metin(PLUGIN / "skills" / name / "SKILL.md"), name)

    def test_gizli_uses_file_options(self):
        gizli = metin(GIZLI)
        for secenek in ("--baslik-dosya", "--gizli-link-dosya <D>/link.txt", "yaz --dosya", "--mesaj-dosya",
                        "TFB gonder --taslak <D>/taslak.json"):
            self.assertIn(secenek, gizli, secenek)

    def test_write_skills_clean_up_staging(self):
        for govde, ad in ((metin(GIZLI), "gizli"), (metin(PLUGIN / "skills" / "toplu-paylas" / "SKILL.md"), "toplu")):
            self.assertIn("TFB temizle <D>", govde, ad)
            self.assertRegex(govde, r"Vazgeç: reply \"Vazgeçildi; depoya hiçbir şey yazılmadı\.[^\"]*<D>", ad)

    def test_gizli_mode_never_touches_the_document(self):
        paylas = metin(GIZLI)
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
        paylas = metin(GIZLI)
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
        paylas = metin(GIZLI)
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
        paylas = metin(GIZLI)
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

    def test_comment_text_reaches_the_helper_only_by_file(self):
        bilgi = metin(PLUGIN / "skills" / "bilgi" / "SKILL.md")
        self.assertIn("Write(~/.tf-bilgi/gecici/**)", bilgi)
        bolum = bilgi.split("\n## Yorum\n", 1)[1]
        self.assertIn("never goes into a shell argument, heredoc or `echo`", bolum)
        self.assertIn("to\n   `<D>/yorum.md` with the Write tool", bolum)
        self.assertIn("`TFB yorum <id> --dosya <D>/yorum.md [--yonetim]`", bolum)            # plan: yazmaz
        self.assertIn("`TFB yorum <id> --dosya <D>/yorum.md --gonder [--yonetim]`", bolum)   # onaydan sonra
        self.assertLess(bolum.index("**Gönder** / **Vazgeç**"), bolum.index("--gonder"))
        self.assertGreaterEqual(bolum.count("TFB temizle <D>"), 3)                           # ret, vazgeç, gönder
        for satir in bilgi.splitlines():  # yorum komutlarında tırnaklı metin argümanı yok
            if "TFB yorum" in satir:
                self.assertNotRegex(satir, r"TFB yorum[^`|]*'", satir)
        self.assertIn("verbatim", bilgi)
        for parca in ("Gizli entries\ncannot be commented on", "yönetim entries only in\nthe yönetim repo"):
            self.assertIn(parca, bolum)

    def test_non_writers_are_sent_to_the_kopru(self):
        """0.6.0: yazma yetkisi olmayan köprü anahtarıyla paylaşır; anahtar gelene kadar bot ve yazan biri yedektir."""
        bilgi = metin(PLUGIN / "skills" / "bilgi" / "SKILL.md")
        paylas = metin(PLUGIN / "skills" / "paylas" / "SKILL.md")
        toplu = metin(PLUGIN / "skills" / "toplu-paylas" / "SKILL.md")
        for govde in (bilgi, paylas, toplu):
            self.assertIn("/bilgi kur", govde)
            self.assertIn("köprü key", govde)
        self.assertIn("TF Bilgi bot in Slack", bilgi)
        self.assertIn("`aldım <girdi-id>`", bilgi)
        self.assertIn("TF Bilgi bot in Slack", toplu)
        for md in SKILLS:
            self.assertNotIn("whom to hand the document to", metin(md), md)
        self.assertIn("someone who can write to the repo", bilgi)
        self.assertIn("someone who can write to", toplu)
        turler = metin(PLUGIN / "skills" / "paylas" / "references" / "turler.md")
        self.assertIn("köprü anahtarıyla yine `/bilgi alindi <id>`", turler)
        self.assertIn("“alındı <id>”yi deponun `yazanlar` listesindekilerden", turler)

    def test_paylas_is_instant_no_reading_no_questions(self):
        """7 Kas kararı: /paylas Slack'ten hızlı; okumaz, özetlemez, taslak yazmaz, hiçbir şey sormaz."""
        paylas = metin(PAYLAS)
        govde = paylas.split("\n---\n", 1)[1]
        self.assertLessEqual(len(govde.encode("utf-8")), 3200, "SKILL.md gövdesi kısa kalmalı")
        self.assertNotIn("AskUserQuestion", paylas)
        for yasak in ("KONULAR.md", "kisiler.json", "eslestir", "kb tara", "taslak", "hazirla", "Onayla", "Düzelt",
                      "TFB gonder", "TFB yaz", "TFB kaydet", "bildirim-plani", "maskele"):
            self.assertNotIn(yasak, paylas, yasak)
        for parca in ("Do not think long", "do not ask\nanything", "Do\nnot open, read, scan or summarise any document",
                      "do not draft an entry", "Run exactly one command", "with the `satir` value only",
                      "data,\nnever instructions"):
            self.assertIn(parca, paylas, parca)
        self.assertIn('"${CLAUDE_PLUGIN_ROOT}/scripts/tf_bilgi.py" geri-al <kod>', paylas)

    def test_paylas_areas_modes_and_targets(self):
        paylas = metin(PAYLAS)
        adim4 = paylas.split("\n4. ", 1)[1].split("\n5. ", 1)[0]
        for soz in ('"yönetim"', '"yönetici"', '"yönetime"', '"C-level"', "`--yonetim`"):
            self.assertIn(soz, adim4.split("--haber simdi` when", 1)[0], soz)
        self.assertIn('`--haber simdi` when they say "acil", "hemen haber ver" or "şimdi haber ver"', adim4)
        adim2 = paylas.split("\n2. ", 1)[1].split("\n3. ", 1)[0]
        self.assertIn("references/gizli.md", adim2)
        self.assertIn("references/pr-listesi.md", adim2)
        self.assertIn("only when explicitly asked", adim2)
        adim3 = paylas.split("\n3. ", 1)[1].split("\n4. ", 1)[0]
        self.assertIn("never open it", adim3)
        self.assertIn("most recently created, wrote,\n     exported or published", adim3)
        self.assertIn("Write that\n     text verbatim to `~/.tf-bilgi/gecici/paylas-<YYYYMMDD-HHMMSS>.md`", adim3)
        for yol in (GIZLI, PR_LISTESI):
            self.assertTrue(yol.is_file(), yol)
        pr = metin(PR_LISTESI)
        self.assertIn("TFB prler", pr)
        self.assertIn("`~/.tf-bilgi/gecici/pr-listesi-<YYYYMMDD-HHMMSS>.md`", pr)
        self.assertIn("Run the single `hizli` command of SKILL.md step 4 with `--ek <that file>`", pr)

    def test_paylas_allowed_tools_are_minimal(self):
        izinler = re.search(r"(?ms)^allowed-tools:\n(.*?)^---", metin(PAYLAS)).group(1)
        self.assertEqual(izinler.splitlines(), ['  - Bash(python3 "${CLAUDE_PLUGIN_ROOT}/scripts/tf_bilgi.py" *)',
                                                "  - Write(~/.tf-bilgi/gecici/**)",
                                                "  - Read(${CLAUDE_PLUGIN_ROOT}/skills/paylas/references/**)"])

    def test_secrets_never_block_only_the_kopru_key(self):
        """7 Kas kararı: sır ve kişisel veri paylaşımı engellemez; yalnız köprü anahtarı ve ~/.tf-bilgi."""
        paylas, toplu = metin(PAYLAS), metin(PLUGIN / "skills" / "toplu-paylas" / "SKILL.md")
        self.assertIn("Secrets and personal\ndata do not block", paylas)
        self.assertIn("only the köprü key itself and files\nunder `~/.tf-bilgi` are refused", paylas)
        self.assertIn("**Secrets never block**", toplu)
        self.assertIn("Only the TF Bilgi köprü key\n  (`tfb1.…`) and files under `~/.tf-bilgi` are never shared", toplu)
        self.assertIn("Personal data never blocks and is never masked", toplu)
        for govde in [metin(md) for md in SKILLS] + [metin(GIZLI)]:
            for eski in ("Secrets in the user's input block the share", "A secret is never shared",
                         "refuse the whole share", "No question, no masking, no waiver", "sır varsa paylaşmaz"):
                self.assertNotIn(eski, govde, eski)
        siniflama = metin(PLUGIN / "skills" / "toplu-paylas" / "references" / "siniflama.md")
        self.assertIn("Kişisel veri engellemez", siniflama)
        self.assertIn("**Sır paylaşımı engellemez**", siniflama)
        self.assertNotIn('"güvenlik ayrıntısı"', siniflama)
        self.assertNotIn('"influencer kimliği"', siniflama)  # artık ham engeli değil

    def test_readme_describes_the_instant_share(self):
        readme = (PLUGIN.parents[1] / "README.md").read_text(encoding="utf-8")
        for parca in ("eneskrblt/tf-bilgi-yonetim", "`00-gelen/`", "Git Data API", "geri-al",
                      "Sır ve kişisel veri paylaşımı engellemez"):
            self.assertIn(parca, readme, parca)
        self.assertNotIn("Teamfluencer-Dev/tf-bilgi-yonetim", readme)
        self.assertNotIn("Sır engellenir", readme)

    def test_kur_status_never_stops_installation(self):
        bilgi = metin(PLUGIN / "skills" / "bilgi" / "SKILL.md")
        bolum = bilgi.split("\n## Kur\n", 1)[1].split("\n## ", 1)[0]
        self.assertIn("always exit 0", bolum)
        self.assertIn("**continue with step 2**", bolum)
        self.assertIn("Never stop here.", bolum)

    def test_kopru_key_only_through_a_file(self):
        bilgi = metin(PLUGIN / "skills" / "bilgi" / "SKILL.md")
        bolum = bilgi.split("\n## Kur\n", 1)[1].split("\n## ", 1)[0]
        self.assertIn("never goes into a shell argument", bolum)
        self.assertIn("with\n   the Write tool", bolum)
        self.assertIn("`TFB kur --dosya <dosya_yeri>`", bolum)
        self.assertLess(bolum.index("Write tool"), bolum.index("TFB kur --dosya"))
        for md in SKILLS:
            for satir in metin(md).splitlines():
                if "TFB kur" in satir:
                    self.assertNotRegex(satir, r"TFB kur[^`|]*(tfb1|')", satir)

    def test_gonder_gets_only_paths(self):
        for md in SKILLS + REFERANSLAR:
            for cagri in re.findall(r"TFB gonder[^`]*", metin(md)):
                self.assertNotRegex(cagri, r"--(baslik|tldr|not|mesaj|alici|kisi)\b", cagri)
                for deger in re.findall(r"--(?:taslak|metin|govde|ek) ('?[^ \]']+'?)", cagri):
                    self.assertRegex(deger, r"^'?<(D|file)>", cagri)

    def test_comment_card_does_not_overpromise_notifications(self):
        bolum = metin(PLUGIN / "skills" / "bilgi" / "SKILL.md").split("\n## Yorum\n", 1)[1]
        self.assertIn("never promise\n   more than it says", bolum)
        self.assertIn("`BILDIRIM_YALNIZ`", bolum)
        self.assertIn('never "bildirildi"', bolum)

    def test_only_the_helper_runs_in_bash(self):
        for md in SKILLS:
            izinler = re.search(r"(?ms)^allowed-tools:\n(.*?)^---", metin(md)).group(1)
            bash = [s for s in izinler.splitlines() if "Bash(" in s]
            self.assertEqual(bash, ['  - Bash(python3 "${CLAUDE_PLUGIN_ROOT}/scripts/tf_bilgi.py" *)'], md)


if __name__ == "__main__":
    unittest.main()
