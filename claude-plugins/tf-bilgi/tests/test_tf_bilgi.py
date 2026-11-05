"""Tests for tf_bilgi.py — real git repos with local bare remotes, a fake gh, a stub kb.py.

Run: python3 -m unittest discover -s claude-plugins/tf-bilgi/tests -v

Nothing here touches the network: GitHub URLs are rewritten to local bare repos
(url.<path>.insteadOf) and git may only use the file protocol (GIT_ALLOW_PROTOCOL).
All people, logins and addresses below are fictional.
"""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SCRIPT = SCRIPTS / "tf_bilgi.py"
sys.path.insert(0, str(SCRIPTS))
import tf_bilgi  # noqa: E402

# Stub of the KB repo's araclar/kb.py: only the contract surface the plugin relies on.
STUB_KB = r'''#!/usr/bin/env python3
import json, os, subprocess, sys
from pathlib import Path
args = sys.argv[1:]
kok = os.environ.get("TF_BILGI_KOK", "")
komut = args[0] if args else ""
def git(*a):
    subprocess.run(["git", "-C", kok, *a], check=True, capture_output=True)
if komut == "kaydet":
    i = args.index("--mesaj")
    mesaj, yollar = args[i + 1], args[1:i] + args[i + 2:]
    git("add", "--", *yollar)
    git("commit", "-q", "-m", mesaj)
    if os.environ.get("STUB_KB_PUSH_YOK") != "1":
        git("pull", "--rebase", "-q", "origin", "main")
        git("push", "-q", "origin", "HEAD:main")
    print("kaydedildi: " + ", ".join(yollar))
    sys.exit(0)
if komut == "tara":
    hedef = args[1]
    metin = sys.stdin.read() if hedef == "-" else Path(hedef).read_text(encoding="utf-8")
    bulgu = "GIZLI-ANAHTAR" in metin
    if "--maskele" in args:
        sys.stdout.write(metin.replace("GIZLI-ANAHTAR-123", "[maskelendi]"))
    else:
        print(json.dumps({"bulgular": [{"tur": "sir", "satir": 1}] if bulgu else []}))
    sys.exit(3 if bulgu else 0)
print(json.dumps({"komut": args, "kok": kok, "cwd": os.getcwd()}))
sys.exit(int(os.environ.get("STUB_KB_CIKIS", "0")))
'''

# Fake GitHub CLI. `repo clone` clones the github.com URL, which the test git config
# rewrites to a local bare repo.
FAKE_GH = r'''#!{python}
import json, os, subprocess, sys
args = sys.argv[1:]
with open(os.environ["FAKE_GH_LOG"], "a") as log:
    log.write(json.dumps(args) + "\n")
if args[:2] == ["auth", "status"]:
    sys.exit(int(os.environ.get("FAKE_GH_AUTH", "0")))
if args[:2] == ["api", "user"]:
    login = os.environ.get("FAKE_GH_LOGIN", "")
    if not login:
        sys.exit(1)
    print(login)
    sys.exit(0)
if args[:2] == ["repo", "clone"]:
    slug, hedef = args[2], args[3]
    sys.exit(subprocess.run(["git", "clone", "-q", "https://github.com/%s.git" % slug, hedef]).returncode)
if args[:2] in (["pr", "view"], ["pr", "list"]):
    data = json.load(open(os.environ["FAKE_GH_PRS"]))
    repo = args[args.index("-R") + 1]
    if args[1] == "list":
        print(json.dumps(data["list"].get(repo, [])))
        sys.exit(0)
    anahtar = "%s#%s" % (repo, args[2])
    if anahtar not in data["view"]:
        print("no pull requests found", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(data["view"][anahtar]))
    sys.exit(0)
print("unexpected gh call: " + " ".join(args), file=sys.stderr)
sys.exit(99)
'''

KISILER = {"kisiler": {
    "ayse": {"ad": "Ayşe Örnek", "rol": "Dev", "birim": ["dev"], "kitle": ["dev"], "alanlar": ["ekip", "yonetim"],
             "github": "ayse-gh", "slack": None, "eposta": "ayse@ornek.test", "takip": []},
    "mert": {"ad": "Mert Örnek", "rol": "CS", "birim": ["cs"], "kitle": ["cs"], "alanlar": ["ekip"],
             "github": "mert-gh", "slack": None, "eposta": "mert@ornek.test", "takip": []},
}}
YAYIMLANMIS = "girdiler/2026/10/B-20261029-ayse-01.md"


def git(cwd, *args):
    out = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True)
    return out.stdout.strip()


def girdi_metni(girdi_id="B-20261105-ayse-01", baslik="Deneme girdisi"):
    return (f'---\nid: {girdi_id}\nbaslik: "{baslik}"\ntur: durum\nkonu: "ONERI: Deneme"\nalan: ekip\n'
            f'hedef_kitle: [dev]\ntldr: "Kısa özet."\ndurum: yayinda\nyazar: ayse\ntarih: 2026-11-05\n---\n'
            f'**Sonuç:** deneme\n')


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(os.path.realpath(tmp.name))
        self.gitconfig = self.tmp / "gitconfig"
        self.gitconfig.write_text("")
        bindir = self.tmp / "bin"
        bindir.mkdir()
        gh = bindir / "gh"
        gh.write_text(FAKE_GH.replace("{python}", sys.executable))
        gh.chmod(0o755)
        self.gh_log = self.tmp / "gh.log"
        self.gh_log.write_text("")
        self.cache = self.tmp / "cache"
        env = {
            "PATH": f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}",
            "GIT_CONFIG_GLOBAL": str(self.gitconfig), "GIT_CONFIG_NOSYSTEM": "1", "GIT_ALLOW_PROTOCOL": "file",
            "TF_BILGI_DIZIN": str(self.cache), "TF_BILGI_SURUM_KONTROLU": "0", "TF_BILGI_BUGUN": "2026-11-05",
            "FAKE_GH_LOG": str(self.gh_log), "FAKE_GH_LOGIN": "", "FAKE_GH_AUTH": "0",
        }
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        for name in ("TF_BILGI_KISI", "STUB_KB_CIKIS", "STUB_KB_PUSH_YOK", "GIT_DIR", "GIT_WORK_TREE"):
            os.environ.pop(name, None)
        for key, value in (("user.name", "Test"), ("user.email", "test@ornek.test"),
                           ("init.defaultBranch", "main"), ("commit.gpgsign", "false")):
            self.set_git_config(key, value)
        self.seed = {}
        self.bare = {}
        for alan in ("ekip", "yonetim"):
            self.seed[alan], self.bare[alan] = self.make_kb_repo(alan)
        os.environ["TF_BILGI_UZAK_EKIP"] = str(self.bare["ekip"])
        os.environ["TF_BILGI_UZAK_YONETIM"] = str(self.bare["yonetim"])

    # --- fixtures ---
    def set_git_config(self, key, value):
        subprocess.run(["git", "config", "--file", str(self.gitconfig), key, value], check=True)

    def make_kb_repo(self, alan):
        klasor = tf_bilgi.ALANLAR[alan]["klasor"]
        seed = self.tmp / "tohum" / klasor
        bare = self.tmp / "uzak" / f"{klasor}.git"
        bare.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True)
        subprocess.run(["git", "init", "-q", "-b", "main", str(seed)], check=True)
        onek = "B" if alan == "ekip" else "BY"
        files = {
            ".kb.json": json.dumps({"alan": alan, "girdi_onek": onek, "konu_onek": "K" if alan == "ekip" else "KY",
                                    "uzak": tf_bilgi.ALANLAR[alan]["uzak"]}),
            "kisiler.json": json.dumps(KISILER, ensure_ascii=False),
            "KONULAR.md": "# Konular\n",
            "araclar/kb.py": STUB_KB,
            "ham/DEFTER.tsv": "sha256\tyol\tgirdi\ttarih\n",
            YAYIMLANMIS.replace("B-", f"{onek}-"): girdi_metni(f"{onek}-20261029-ayse-01"),
        }
        for rel, text in files.items():
            path = seed / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        git(seed, "add", "--", *files)
        git(seed, "commit", "-q", "-m", "tohum")
        git(seed, "remote", "add", "origin", str(bare))
        git(seed, "push", "-q", "origin", "main")
        return seed, bare

    def seed_commit(self, alan, rel, text):
        path = self.seed[alan] / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        git(self.seed[alan], "add", "--", rel)
        git(self.seed[alan], "commit", "-q", "-m", f"ekle {rel}")
        git(self.seed[alan], "push", "-q", "origin", "main")

    def kok(self, alan="ekip"):
        return self.cache / tf_bilgi.ALANLAR[alan]["klasor"]

    # --- runners ---
    def run_main(self, *argv, stdin=""):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch.object(sys, "stdin", io.StringIO(stdin)):
            code = tf_bilgi.main(list(argv))
        return code, out.getvalue()

    def ok(self, *argv, stdin=""):
        code, out = self.run_main(*argv, stdin=stdin)
        self.assertEqual(code, 0, out)
        return json.loads(out)

    def stop(self, *argv, stdin=""):
        code, out = self.run_main(*argv, stdin=stdin)
        self.assertEqual(code, 2, out)
        return out

    def cli(self, *argv, stdin=""):
        proc = subprocess.run([sys.executable, str(SCRIPT), *argv], capture_output=True, text=True,
                              input=stdin, env=dict(os.environ))
        return proc.returncode, proc.stdout, proc.stderr

    def gh_calls(self):
        return [json.loads(line) for line in self.gh_log.read_text().splitlines() if line.strip()]


class HazirlaTest(Base):
    def test_clones_missing_cache_and_prints_contract_json(self):
        result = self.ok("hazirla")
        for key in ("kok", "alan", "kisi", "kb", "uzak"):
            self.assertIn(key, result)
        self.assertEqual(result["kok"], str(self.kok()))
        self.assertEqual(result["alan"], "ekip")
        self.assertEqual(result["kb"], str(self.kok() / "araclar" / "kb.py"))
        self.assertEqual(result["uzak"], "Teamfluencer-Dev/tf-bilgi")
        self.assertEqual(result["baglanti_koku"], "https://github.com/Teamfluencer-Dev/tf-bilgi/blob/main/")
        self.assertEqual(result["islem"], "klonlandi")
        self.assertTrue((self.kok() / ".kb.json").is_file())
        self.assertEqual((result["bugun"], result["bugun_gun"]), ("2026-11-05", "Perşembe"))
        self.assertEqual(result["takvim"][0], "2026-11-06 Cuma")
        self.assertEqual(len(result["takvim"]), 14)

    def test_second_run_pulls_new_commits(self):
        self.ok("hazirla")
        self.seed_commit("ekip", "girdiler/2026/11/B-20261104-mert-01.md", girdi_metni("B-20261104-mert-01"))
        result = self.ok("hazirla")
        self.assertEqual(result["islem"], "guncellendi")
        self.assertTrue((self.kok() / "girdiler/2026/11/B-20261104-mert-01.md").is_file())
        self.assertEqual(self.ok("hazirla")["islem"], "guncel")

    def test_dirty_tracked_file_refuses_and_does_not_pull(self):
        self.ok("hazirla")
        (self.kok() / "KONULAR.md").write_text("elle değişti\n")
        self.seed_commit("ekip", "yeni.md", "x\n")
        out = self.stop("hazirla")
        self.assertIn("KONULAR.md", out)
        self.assertIn("stash", out)
        self.assertFalse((self.kok() / "yeni.md").exists())

    def test_untracked_leftover_does_not_block_but_is_reported(self):
        self.ok("hazirla")
        leftover = self.kok() / "girdiler/2026/11/B-20261105-ayse-01.md"
        leftover.parent.mkdir(parents=True)
        leftover.write_text(girdi_metni())
        result = self.ok("hazirla")
        self.assertTrue(any("B-20261105-ayse-01" in n for n in result["notlar"]), result["notlar"])

    def test_yonetim_uses_its_own_clone(self):
        result = self.ok("hazirla", "--yonetim")
        self.assertEqual(result["kok"], str(self.kok("yonetim")))
        self.assertEqual(result["alan"], "yonetim")
        self.assertEqual(result["uzak"], "Teamfluencer-Dev/tf-bilgi-yonetim")
        self.assertFalse(self.kok("ekip").exists())

    def test_area_mismatch_stops(self):
        os.environ["TF_BILGI_UZAK_YONETIM"] = str(self.bare["ekip"])
        out = self.stop("hazirla", "--yonetim")
        self.assertIn("alanı 'ekip'", out)

    def test_cache_bound_to_another_remote_stops(self):
        self.ok("hazirla")
        other = self.tmp / "uzak" / "baska.git"
        subprocess.run(["git", "clone", "-q", "--bare", str(self.bare["ekip"]), str(other)], check=True)
        os.environ["TF_BILGI_UZAK_EKIP"] = str(other)
        self.assertIn("başka bir depoya bağlı", self.stop("hazirla"))

    def test_github_slug_is_cloned_with_gh_and_pulled(self):
        del os.environ["TF_BILGI_UZAK_EKIP"]  # default: Teamfluencer-Dev/tf-bilgi
        self.set_git_config(f"url.{self.bare['ekip']}.insteadOf", "https://github.com/Teamfluencer-Dev/tf-bilgi.git")
        result = self.ok("hazirla")
        self.assertEqual(result["islem"], "klonlandi")
        clone_calls = [c for c in self.gh_calls() if c[:2] == ["repo", "clone"]]
        self.assertEqual(clone_calls[0][2:4], ["Teamfluencer-Dev/tf-bilgi", str(self.kok())])
        helpers = git(self.kok(), "config", "--local", "--get-all", "credential.https://github.com.helper")
        self.assertIn("!gh auth git-credential", helpers)
        self.seed_commit("ekip", "yeni.md", "x\n")
        self.assertEqual(self.ok("hazirla")["islem"], "guncellendi")

    def test_missing_kb_py_stops(self):
        git(self.seed["ekip"], "rm", "-q", "araclar/kb.py")
        git(self.seed["ekip"], "commit", "-q", "-m", "kb yok")
        git(self.seed["ekip"], "push", "-q", "origin", "main")
        self.assertIn("araclar/kb.py yok", self.stop("hazirla"))

    def test_empty_remote_then_populated(self):
        empty = self.tmp / "uzak" / "bos.git"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(empty)], check=True)
        os.environ["TF_BILGI_UZAK_EKIP"] = str(empty)
        self.assertIn("henüz boş", self.stop("hazirla"))
        self.assertIn("henüz boş", self.stop("hazirla"))
        git(self.seed["ekip"], "push", "-q", str(empty), "main")
        result = self.ok("hazirla")
        self.assertEqual(result["islem"], "guncellendi")
        self.assertEqual(result["alan"], "ekip")

    def test_unpushed_commit_is_reported(self):
        self.ok("hazirla")
        (self.kok() / "not.md").write_text("x\n")
        git(self.kok(), "add", "not.md")
        git(self.kok(), "commit", "-q", "-m", "yerel")
        result = self.ok("hazirla")
        self.assertTrue(any("gönderilmemiş 1 commit" in n for n in result["notlar"]), result["notlar"])


class KisiTest(Base):
    def test_env_var_wins(self):
        os.environ["TF_BILGI_KISI"] = "mert"
        os.environ["FAKE_GH_LOGIN"] = "ayse-gh"
        result = self.ok("hazirla")
        self.assertEqual((result["kisi"], result["kisi_kaynagi"]), ("mert", "TF_BILGI_KISI"))
        self.assertNotIn("kisiler", result)

    def test_gh_login_second(self):
        os.environ["FAKE_GH_LOGIN"] = "Ayse-GH"
        self.set_git_config("user.email", "mert@ornek.test")
        result = self.ok("hazirla")
        self.assertEqual((result["kisi"], result["kisi_kaynagi"]), ("ayse", "github"))

    def test_git_email_third(self):
        os.environ["FAKE_GH_LOGIN"] = "bilinmeyen-gh"
        self.set_git_config("user.email", "MERT@ornek.test")
        result = self.ok("hazirla")
        self.assertEqual((result["kisi"], result["kisi_kaynagi"]), ("mert", "git-eposta"))

    def test_unresolved_is_null_with_candidates(self):
        result = self.ok("hazirla")
        self.assertIsNone(result["kisi"])
        self.assertEqual([k["anahtar"] for k in result["kisiler"]], ["ayse", "mert"])
        self.assertTrue(any("TF_BILGI_KISI" in n for n in result["notlar"]))

    def test_unknown_env_value_falls_through_with_note(self):
        os.environ["TF_BILGI_KISI"] = "yok"
        os.environ["FAKE_GH_LOGIN"] = "ayse-gh"
        result = self.ok("hazirla")
        self.assertEqual(result["kisi"], "ayse")
        self.assertTrue(any("'yok'" in n for n in result["notlar"]), result["notlar"])

    def test_person_outside_area_gets_note(self):
        os.environ["TF_BILGI_KISI"] = "mert"
        result = self.ok("hazirla", "--yonetim")
        self.assertEqual(result["kisi"], "mert")
        self.assertTrue(any("kayıtlı değil" in n for n in result["notlar"]), result["notlar"])


class OnKontrolTest(Base):
    def without(self, *missing):
        real = shutil.which
        patcher = mock.patch.object(tf_bilgi, "which", lambda name: None if name in missing else real(name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_missing_git(self):
        self.without("git")
        self.assertIn("git bulunamadı", self.stop("hazirla"))

    def test_github_remote_without_gh(self):
        del os.environ["TF_BILGI_UZAK_EKIP"]
        self.without("gh")
        out = self.stop("hazirla")
        self.assertIn("cli.github.com", out)
        self.assertIn("gh auth login", out)

    def test_github_remote_with_gh_logged_out(self):
        del os.environ["TF_BILGI_UZAK_EKIP"]
        os.environ["FAKE_GH_AUTH"] = "1"
        self.assertIn("gh auth login", self.stop("hazirla"))
        self.assertFalse(any(c[:2] == ["repo", "clone"] for c in self.gh_calls()))

    def test_local_remote_needs_no_gh(self):
        self.without("gh")
        self.assertEqual(self.ok("hazirla")["alan"], "ekip")

    def test_old_python(self):
        with mock.patch.object(tf_bilgi.sys, "version_info", (3, 8, 10)):
            self.assertIn("Python 3.9", self.stop("hazirla"))

    def test_clone_failure_explains_access(self):
        os.environ["TF_BILGI_UZAK_EKIP"] = str(self.tmp / "uzak" / "olmayan.git")
        self.assertIn("okuma-yazma yetkisi", self.stop("hazirla"))


class KbGecisTest(Base):
    def test_args_output_and_exit_code_pass_through(self):
        self.ok("hazirla")
        os.environ["STUB_KB_CIKIS"] = "3"
        code, out, _ = self.cli("kb", "son", "--gun", "3", "--json")
        self.assertEqual(code, 3)
        data = json.loads(out)
        self.assertEqual(data["komut"], ["son", "--gun", "3", "--json"])
        self.assertEqual(data["kok"], str(self.kok()))
        self.assertEqual(os.path.realpath(data["cwd"]), str(self.kok()))

    def test_yonetim_flag_selects_yonetim_clone(self):
        self.ok("hazirla", "--yonetim")
        code, out, _ = self.cli("kb", "--yonetim", "ara", "abonelik", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["kok"], str(self.kok("yonetim")))

    def test_stdin_passes_through(self):
        self.ok("hazirla")
        code, out, _ = self.cli("kb", "tara", "-", "--json", stdin="anahtar GIZLI-ANAHTAR-123")
        self.assertEqual(code, 3)
        self.assertEqual(json.loads(out)["bulgular"][0]["tur"], "sir")

    def test_librarian_and_raw_commit_commands_are_refused(self):
        self.ok("hazirla")
        for komut in ("kaydet", "yenile", "ozet"):
            self.assertIn("kb.py", self.stop("kb", komut))

    def test_needs_hazirla_first(self):
        self.assertIn("hazirla", self.stop("kb", "son"))


class YazTest(Base):
    def setUp(self):
        super().setUp()
        self.ok("hazirla")

    def test_writes_new_entry_to_dated_path(self):
        result = self.ok("yaz", stdin=girdi_metni())
        self.assertEqual(result["yol"], "girdiler/2026/11/B-20261105-ayse-01.md")
        self.assertEqual(result["url"], "https://github.com/Teamfluencer-Dev/tf-bilgi/blob/main/"
                                        "girdiler/2026/11/B-20261105-ayse-01.md")
        self.assertEqual((self.kok() / result["yol"]).read_text(), girdi_metni())

    def test_reads_from_file(self):
        draft = self.tmp / "taslak.md"
        draft.write_text(girdi_metni("B-20261105-ayse-02"))
        self.assertEqual(self.ok("yaz", "--dosya", str(draft))["id"], "B-20261105-ayse-02")

    def test_never_overwrites_published_entry(self):
        self.assertIn("yayımlanmış", self.stop("yaz", stdin=girdi_metni("B-20261029-ayse-01")))

    def test_existing_draft_needs_uzerine(self):
        self.ok("yaz", stdin=girdi_metni())
        self.assertIn("--uzerine", self.stop("yaz", stdin=girdi_metni(baslik="İkinci")))
        self.ok("yaz", "--uzerine", stdin=girdi_metni(baslik="İkinci"))
        self.assertIn("İkinci", (self.kok() / "girdiler/2026/11/B-20261105-ayse-01.md").read_text())

    def test_id_prefix_must_match_repo(self):
        self.assertIn("öneki 'B'", self.stop("yaz", stdin=girdi_metni("BY-20261105-ayse-01")))

    def test_rejects_missing_or_bad_frontmatter(self):
        self.assertIn("frontmatter", self.stop("yaz", stdin="id: B-20261105-ayse-01\n"))
        self.assertIn("kapanmamış", self.stop("yaz", stdin="---\nid: B-20261105-ayse-01\n"))
        self.assertIn("sözleşmeye uymuyor", self.stop("yaz", stdin="---\nid: K-0001\n---\n"))


class KaydetTest(Base):
    def setUp(self):
        super().setUp()
        self.ok("hazirla")

    def published(self, rel):
        return subprocess.run(["git", "-C", str(self.bare["ekip"]), "cat-file", "-e", f"main:{rel}"],
                              capture_output=True).returncode == 0

    def test_commits_and_pushes_new_entry_raw_file_and_ledger(self):
        entry = self.ok("yaz", stdin=girdi_metni())["yol"]
        ham = "ham/2026/11/3f9a2c1e-ornek.txt"
        (self.kok() / ham).parent.mkdir(parents=True)
        (self.kok() / ham).write_text("ham içerik\n")
        with open(self.kok() / tf_bilgi.DEFTER, "a") as defter:
            defter.write(f"abc\t{ham}\tB-20261105-ayse-01\t2026-11-05\n")
        result = self.ok("kaydet", "--mesaj", "B-20261105-ayse-01: Deneme", entry, ham, tf_bilgi.DEFTER)
        self.assertTrue(result["gonderildi"])
        self.assertEqual([b["yol"] for b in result["baglantilar"]], [entry, ham])
        self.assertTrue(result["baglantilar"][0]["url"].endswith(entry))
        for rel in (entry, ham):
            self.assertTrue(self.published(rel), rel)
        self.assertEqual(git(self.bare["ekip"], "log", "-1", "--format=%s", "main"), "B-20261105-ayse-01: Deneme")

    def test_accepts_absolute_paths_inside_cache(self):
        entry = self.ok("yaz", stdin=girdi_metni())["tam_yol"]
        self.assertTrue(self.ok("kaydet", "--mesaj", "m", entry)["gonderildi"])

    def test_refuses_librarian_files(self):
        (self.kok() / "KONULAR.md").write_text("elle\n")
        before = git(self.bare["ekip"], "rev-parse", "main")
        out = self.stop("kaydet", "--mesaj", "m", "KONULAR.md")
        self.assertIn("KONULAR.md: /paylas bu yola yazamaz", out)
        self.assertEqual(git(self.bare["ekip"], "rev-parse", "main"), before)

    def test_refuses_published_entry(self):
        (self.kok() / YAYIMLANMIS).write_text("değişti\n")
        self.assertIn("zaten yayımlanmış", self.stop("kaydet", "--mesaj", "m", YAYIMLANMIS))

    def test_ledger_is_append_only(self):
        (self.kok() / tf_bilgi.DEFTER).write_text("bozuk başlık\n")
        self.assertIn("yalnız satır eklenebilir", self.stop("kaydet", "--mesaj", "m", tf_bilgi.DEFTER))

    def test_refuses_when_other_files_are_staged(self):
        entry = self.ok("yaz", stdin=girdi_metni())["yol"]
        (self.kok() / "KONULAR.md").write_text("elle\n")
        git(self.kok(), "add", "KONULAR.md")
        self.assertIn("başka dosyalar commit için hazırlanmış", self.stop("kaydet", "--mesaj", "m", entry))

    def test_refuses_paths_outside_cache_and_missing_files(self):
        self.assertIn("dışında", self.stop("kaydet", "--mesaj", "m", "../disari.md"))
        self.assertIn("dosya yok", self.stop("kaydet", "--mesaj", "m", "girdiler/2026/11/B-20261105-ayse-09.md"))

    def test_accepts_new_onay_file(self):
        onay = "onaylar/B-20261029-ayse-01--mert.md"
        (self.kok() / onay).parent.mkdir(parents=True)
        (self.kok() / onay).write_text("---\ngirdi: B-20261029-ayse-01\nkisi: mert\ntarih: 2026-11-05\n---\n")
        result = self.ok("kaydet", "--mesaj", "alindi: B-20261029-ayse-01 (mert)", onay)
        self.assertTrue(self.published(onay))
        self.assertEqual(result["baglantilar"][0]["yol"], onay)

    def test_reports_unpushed_commit(self):
        os.environ["STUB_KB_PUSH_YOK"] = "1"
        entry = self.ok("yaz", stdin=girdi_metni())["yol"]
        result = self.ok("kaydet", "--mesaj", "m", entry)
        self.assertFalse(result["gonderildi"])
        self.assertTrue(result["notlar"])
        self.assertFalse(self.published(entry))

    def test_kb_failure_is_relayed(self):
        entry = self.ok("yaz", stdin=girdi_metni())["yol"]
        (self.kok() / "araclar" / "kb.py").write_text("import sys\nprint('itme reddedildi')\nsys.exit(1)\n")
        out = self.stop("kaydet", "--mesaj", "m", entry)
        self.assertIn("kb.py kaydet başarısız", out)
        self.assertIn("itme reddedildi", out)


class GeciciMaskeleTest(Base):
    def test_gecici_saves_stdin_under_cache(self):
        result = self.ok("gecici", "metin.txt", stdin="merhaba\nTA-2478\n")
        self.assertEqual(result["yol"], str(self.cache / "gecici" / "metin.txt"))
        self.assertEqual(Path(result["yol"]).read_text(), "merhaba\nTA-2478\n")

    def test_gecici_name_is_sanitised(self):
        result = self.ok("gecici", "../../x y.txt", stdin="a")
        self.assertEqual(result["yol"], str(self.cache / "gecici" / "x-y.txt"))

    def test_maskele_writes_masked_copy(self):
        self.ok("hazirla")
        src = self.tmp / "notlar.txt"
        src.write_text("token GIZLI-ANAHTAR-123 burada\n")
        result = self.ok("maskele", str(src))
        self.assertTrue(result["bulgu"])
        masked = Path(result["yol"]).read_text()
        self.assertNotIn("GIZLI-ANAHTAR-123", masked)
        self.assertIn("[maskelendi]", masked)
        self.assertEqual(Path(result["yol"]).parent, self.cache / "gecici")

    def test_maskele_refuses_binary(self):
        self.ok("hazirla")
        pdf = self.tmp / "rapor.pdf"
        pdf.write_bytes(b"%PDF-1.4\x00\x01")
        self.assertIn("ham: null", self.stop("maskele", str(pdf)))


class PrlerTest(Base):
    def setUp(self):
        super().setUp()
        api, web = "Teamfluencer-Dev/teamfluencerapi", "Teamfluencer-Dev/teamfluencer-web"

        def pr(number, head, base, rollup, merge="BLOCKED"):
            return {"number": number, "title": f"PR {number}", "headRefName": head, "baseRefName": base,
                    "url": f"https://github.com/x/pull/{number}", "state": "OPEN", "isDraft": False,
                    "mergeStateStatus": merge, "statusCheckRollup": rollup}

        ok = [{"__typename": "StatusContext", "context": "claude-review", "state": "SUCCESS"},
              {"__typename": "CheckRun", "name": "test", "status": "COMPLETED", "conclusion": "SUCCESS"}]
        pending = [{"__typename": "StatusContext", "context": "claude-review", "state": "PENDING"}]
        failed_run = [{"__typename": "CheckRun", "name": "claude-review", "status": "COMPLETED",
                       "conclusion": "FAILURE"}]
        data = {
            "view": {f"{api}#1976": pr(1976, "feature/TA-1-a", "master", ok, "CLEAN"),
                     f"{web}#689": pr(689, "feature/TF-2-b", "master", [])},
            "list": {api: [pr(1977, "feature/TA-1-c", "feature/TA-1-a", pending),
                           pr(1976, "feature/TA-1-a", "master", ok, "CLEAN")],
                     web: [pr(690, "feature/TF-3", "master", failed_run)]},
        }
        prs = self.tmp / "prs.json"
        prs.write_text(json.dumps(data))
        os.environ["FAKE_GH_PRS"] = str(prs)

    def test_short_refs_claude_review_and_merge_state(self):
        rows = self.ok("prler", "api#1976", "web#689")["satirlar"]
        self.assertEqual([r["pr"] for r in rows], ["api#1976", "web#689"])
        self.assertEqual(rows[0]["claude_review"], "basarili")
        self.assertEqual(rows[0]["merge_durumu_tr"], "merge'e hazır")
        self.assertEqual(rows[1]["claude_review"], "yok")
        self.assertEqual(rows[1]["repo"], "Teamfluencer-Dev/teamfluencer-web")

    def test_me_lists_own_prs_detects_stacking_and_dedupes(self):
        result = self.ok("prler", "api#1976", "@me", "--repo", "api", "--repo", "web")
        rows = {r["pr"]: r for r in result["satirlar"]}
        self.assertEqual(sorted(rows), ["api#1976", "api#1977", "web#690"])
        self.assertEqual(rows["api#1977"]["bagimli"], "api#1976")
        self.assertEqual(rows["api#1977"]["claude_review"], "bekliyor")
        self.assertIsNone(rows["api#1976"]["bagimli"])
        self.assertEqual(rows["web#690"]["claude_review"], "basarisiz")
        list_calls = [c for c in self.gh_calls() if c[:2] == ["pr", "list"]]
        self.assertTrue(all("@me" in c for c in list_calls))

    def test_url_ref_and_not_found(self):
        result = self.ok("prler", "https://github.com/Teamfluencer-Dev/teamfluencerapi/pull/1976", "api#9999")
        self.assertEqual([r["pr"] for r in result["satirlar"]], ["api#1976"])
        self.assertEqual(len(result["hatalar"]), 1)
        self.assertIn("api#9999", result["hatalar"][0])

    def test_bare_number_needs_single_repo(self):
        self.assertIn("--repo", self.stop("prler", "12"))
        self.assertEqual(self.ok("prler", "1976", "--repo", "teamfluencerapi")["satirlar"][0]["pr"], "api#1976")

    def test_only_read_only_gh_calls(self):
        self.ok("prler", "api#1976", "@me", "--repo", "api")
        for call in self.gh_calls():
            self.assertIn(call[:2], (["auth", "status"], ["pr", "view"], ["pr", "list"]), call)


class CliTest(Base):
    def test_hazirla_prints_json(self):
        code, out, _ = self.cli("hazirla")
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads(out)["alan"], "ekip")

    def test_stop_exits_2_with_turkish_message(self):
        code, out, _ = self.cli("kb", "son")
        self.assertEqual(code, 2)
        self.assertIn("önce", out)

    def test_usage(self):
        code, _, err = self.cli()
        self.assertEqual(code, 64)
        self.assertIn("kullanım", err)


if __name__ == "__main__":
    unittest.main()
