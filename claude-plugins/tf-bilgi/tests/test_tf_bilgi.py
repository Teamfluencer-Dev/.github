"""Tests for tf_bilgi.py — real git repos with local bare remotes, a fake gh, a stub kb.py.

Run: python3 -m unittest discover -s claude-plugins/tf-bilgi/tests -v

Nothing here touches the network: GitHub URLs are rewritten to local bare repos
(url.<path>.insteadOf) and git may only use the file protocol (GIT_ALLOW_PROTOCOL).
All people, logins and addresses below are fictional.
"""
import contextlib
import hashlib
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

GERCEK_KB_SHA256 = tf_bilgi.KB_SHA256  # the shipped pin (tests patch it to the stub's hash)

# Stub of the KB repo's araclar/kb.py: only the contract surface the plugin relies on.
STUB_KB = r'''#!/usr/bin/env python3
import json, os, subprocess, sys
from pathlib import Path
args = sys.argv[1:]
kok = os.environ.get("TF_BILGI_KOK", "")
komut = args[0] if args else ""
def git(*a):
    subprocess.run(["git", "-C", kok, *a], check=True, capture_output=True)
def deger(ad):
    for i, t in enumerate(args):
        if t == ad:
            return args[i + 1]
        if t.startswith(ad + "="):
            return t.split("=", 1)[1]
    return None
if komut == "alindi":
    kisi, kaydeden = deger("--kisi"), deger("--kaydeden")
    rel = "onaylar/%s--%s.md" % (args[1], kisi)
    satirlar = ["---", "girdi: " + args[1], "kisi: " + kisi]
    satirlar += ["kaydeden: " + kaydeden] if kaydeden and kaydeden != kisi else []
    (Path(kok) / "onaylar").mkdir(exist_ok=True)
    (Path(kok) / rel).write_text("\n".join(satirlar + ["tarih: 2026-11-05", "---", ""]), encoding="utf-8")
    print(json.dumps({"komut": args, "durum": "yeni", "yol": rel}))
    sys.exit(0)
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
STUB_SHA256 = hashlib.sha256(STUB_KB.encode("utf-8")).hexdigest()

# Runs tf_bilgi.main in a fresh interpreter with KB_SHA256 set to the given hashes (the stub's), so CLI tests go
# through the real pin check without an environment override existing in production.
CLI_SARMAL = ("import sys; sys.path.insert(0, sys.argv[1]); import tf_bilgi; "
              "tf_bilgi.KB_SHA256 = tuple(sys.argv[2].split(',')); sys.exit(tf_bilgi.main(sys.argv[3:]))")

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
if args[:1] == ["api"] and len(args) > 1 and args[1].startswith("repos/"):  # push yetkisi
    if os.environ.get("FAKE_GH_REPO_CIKIS"):
        sys.exit(int(os.environ["FAKE_GH_REPO_CIKIS"]))
    print(os.environ.get("FAKE_GH_PUSH", "true"))
    sys.exit(0)
if args[:2] == ["api", "--paginate"] and "/issues/" in args[2]:  # tercih yorumları, --jq .[]
    if os.environ.get("FAKE_GH_YORUM_CIKIS"):
        sys.exit(int(os.environ["FAKE_GH_YORUM_CIKIS"]))
    for yorum in json.load(open(os.environ["FAKE_GH_YORUMLAR"])):
        print(json.dumps(yorum))
    sys.exit(0)
if args[:2] == ["issue", "comment"]:
    print("https://github.com/%s/issues/%s#issuecomment-99" % (args[args.index("-R") + 1], args[2]))
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
        pin = mock.patch.object(tf_bilgi, "KB_SHA256", (STUB_SHA256,))
        pin.start()
        self.addCleanup(pin.stop)
        self.yorumlar = self.tmp / "yorumlar.json"
        self.yorumlar.write_text("[]")
        os.environ["FAKE_GH_YORUMLAR"] = str(self.yorumlar)
        for name in ("TF_BILGI_KISI", "STUB_KB_CIKIS", "STUB_KB_PUSH_YOK", "GIT_DIR", "GIT_WORK_TREE", "FAKE_GH_PUSH",
                     "FAKE_GH_REPO_CIKIS", "FAKE_GH_YORUM_CIKIS", "TF_BILGI_SIMDI"):
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
                                    "uzak": tf_bilgi.ALANLAR[alan]["uzak"], "yazanlar": ["ayse"],
                                    "tercih_issue": 7, "tercih_yoneticileri": ["ayse"]}),
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
        proc = subprocess.run([sys.executable, "-c", CLI_SARMAL, str(SCRIPTS), ",".join(tf_bilgi.KB_SHA256), *argv],
                              capture_output=True, text=True, input=stdin, env=dict(os.environ))
        return proc.returncode, proc.stdout, proc.stderr

    def cli_betik(self, *argv):
        """The real script entry point (no pin override)."""
        proc = subprocess.run([sys.executable, str(SCRIPT), *argv], capture_output=True, text=True,
                              env=dict(os.environ))
        return proc.returncode, proc.stdout, proc.stderr

    def gh_calls(self):
        return [json.loads(line) for line in self.gh_log.read_text().splitlines() if line.strip()]

    def github_uzak(self):
        """Varsayılan GitHub slug'ı (gh ile klon, yetki denetimi); URL yerel bare depoya yönlenir."""
        del os.environ["TF_BILGI_UZAK_EKIP"]
        self.set_git_config(f"url.{self.bare['ekip']}.insteadOf", "https://github.com/Teamfluencer-Dev/tf-bilgi.git")

    def yorum(self, *yorumlar):
        self.yorumlar.write_text(json.dumps(list(yorumlar)))


def yorum(login, govde, no=1, zaman="2026-11-05T09:00:00Z", duzenlendi=None):
    return {"id": no, "user": {"login": login}, "body": govde, "created_at": zaman, "updated_at": duzenlendi or zaman}


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


class KbSurumTest(Base):
    """kb.py eklentiye sabitli: yalnız KB_SHA256'daki sürüm, yalıtılmış kipte (python3 -I) çalışır."""

    def test_eslesen_surum_calisir(self):
        self.assertEqual(self.ok("hazirla")["kb"], str(self.kok() / "araclar" / "kb.py"))
        code, out, _ = self.cli("kb", "son", "--json")
        self.assertEqual(code, 0, out)

    def test_farkli_surum_hicbir_komutu_calistirmaz(self):
        self.ok("hazirla")
        self.seed_commit("ekip", "araclar/kb.py", STUB_KB.replace("import json,", "print('DEGISTIRILMIS-KB')\nimport json,"))
        out = self.stop("hazirla")
        self.assertIn("eklentinin onayladığı sürüm değil", out)
        self.assertIn("claude plugin marketplace update teamfluencer && claude plugin update tf-bilgi@teamfluencer", out)
        code, out, err = self.cli("kb", "son", "--json")
        self.assertEqual(code, 2)
        self.assertNotIn("DEGISTIRILMIS-KB", out + err)
        for argv in (("maskele", str(self.kok() / "KONULAR.md")), ("kaydet", "--mesaj", "m", "KONULAR.md")):
            self.assertIn("onayladığı sürüm değil", self.stop(*argv), argv)

    def test_dosya_yoksa_durur(self):
        git(self.seed["ekip"], "rm", "-q", "araclar/kb.py")
        git(self.seed["ekip"], "commit", "-q", "-m", "kb yok")
        git(self.seed["ekip"], "push", "-q", "origin", "main")
        self.assertIn("araclar/kb.py yok", self.stop("hazirla"))

    def test_yanina_konan_modul_kb_py_yi_degistiremez(self):
        self.seed_commit("ekip", "araclar/json.py", "raise SystemExit('araclar/json.py yüklendi')\n")
        self.ok("hazirla")
        code, out, err = self.cli("kb", "son", "--json")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(json.loads(out)["komut"], ["son", "--json"])
        self.assertFalse(list(self.kok().rglob("__pycache__")))

    def test_sabit_bicimi(self):
        self.assertTrue(GERCEK_KB_SHA256)
        for ozet in GERCEK_KB_SHA256:
            self.assertRegex(ozet, r"^[0-9a-f]{64}$")
        self.assertEqual(len(set(GERCEK_KB_SHA256)), len(GERCEK_KB_SHA256))

    def test_gecis_iki_surumu_de_kabul_eder(self):
        """0.4.0 geçişi: KB depolarındaki eski kb.py ile gizli paylaşımlı yeni kb.py birlikte sabitli (KB §12)."""
        self.assertIn("76677edd9f348d1dea7827f3449cf8fb6b8767705b896264129260329a27da23", GERCEK_KB_SHA256)
        self.assertEqual(len(GERCEK_KB_SHA256), 2)
        eski_stub = STUB_KB + "# eski\n"
        self.seed_commit("ekip", "araclar/kb.py", eski_stub)
        iki = (hashlib.sha256(eski_stub.encode()).hexdigest(), STUB_SHA256)
        with mock.patch.object(tf_bilgi, "KB_SHA256", iki):
            self.assertEqual(self.ok("hazirla")["alan"], "ekip")  # eski hash geçer
            self.seed_commit("ekip", "araclar/kb.py", STUB_KB)
            self.assertEqual(self.ok("hazirla")["alan"], "ekip")  # yeni hash geçer
            self.seed_commit("ekip", "araclar/kb.py", STUB_KB + "# başka\n")
            self.assertIn("eklentinin onayladığı sürüm değil", self.stop("hazirla"))


class KisiTest(Base):
    def test_env_var_conflicting_with_gh_login_stops(self):
        os.environ["TF_BILGI_KISI"] = "mert"
        os.environ["FAKE_GH_LOGIN"] = "ayse-gh"
        out = self.stop("hazirla")
        self.assertIn("Başkası adına paylaşılmaz", out)

    def test_env_var_used_when_gh_login_unmapped_or_same(self):
        os.environ["TF_BILGI_KISI"] = "mert"
        for login in ("bilinmeyen-gh", "mert-gh", ""):
            os.environ["FAKE_GH_LOGIN"] = login
            result = self.ok("hazirla")
            self.assertEqual((result["kisi"], result["kisi_kaynagi"]), ("mert", "TF_BILGI_KISI"), login)
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

    def test_guard_finds_subcommand_like_argparse(self):
        self.ok("hazirla")
        for argv in (("--json", "kaydet", "--mesaj", "x", "CLAUDE.md"), ("--bugun", "2026-11-05", "yenile"),
                     ("--bu", "2026-11-05", "ozet", "gunluk"), ("--", "kaydet", "--mesaj", "x", "KONULAR.md"),
                     ("--json", "fsck"), ("taslakx",)):
            out = self.stop("kb", *argv)
            self.assertTrue("kb.py" in out or "izinli değil" in out, (argv, out))
        for argv in (("--kok", "/tmp", "son"), ("son", "--kok", "/tmp"), ("son", "--ko=/tmp"), ("--k", "/tmp", "son")):
            self.assertIn("--kok verilemez", self.stop("kb", *argv), argv)
        code, out, _ = self.cli("kb", "--json", "son", "--gun", "3")
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads(out)["komut"], ["--json", "son", "--gun", "3"])

    def test_repeated_options_are_refused(self):
        self.ok("hazirla")
        os.environ["TF_BILGI_KISI"] = "ayse"
        for argv in (("alindi", "B-20261029-ayse-01", "--kisi", "ayse", "--kisi", "mert"),
                     ("alindi", "B-20261029-ayse-01", "--kisi", "ayse", "--ki=mert"),
                     ("son", "--gun", "3", "--gun", "9")):
            self.assertIn("iki kez", self.stop("kb", *argv), argv)

    def test_izin_ekle_only_for_resolved_person(self):
        self.ok("hazirla")
        os.environ["TF_BILGI_KISI"] = "ayse"
        self.assertIn("kendi adınıza", self.stop("kb", "izin-ekle", "x.pdf", "--kategori", "telefon", "--kisi", "mert",
                                                 "--gerekce", "kurum santrali"))
        code, out, _ = self.cli("kb", "izin-ekle", "x.pdf", "--kategori", "telefon", "--kisi", "ayse", "--gerekce", "santral")
        self.assertEqual(code, 0, out)

    def test_alindi_only_for_resolved_person(self):
        self.ok("hazirla")
        self.assertIn("Kim olduğunuz bulunamadı", self.stop("kb", "alindi", "B-20261029-ayse-01", "--kisi", "mert"))
        os.environ["TF_BILGI_KISI"] = "mert"  # yazanlar'da değil
        for argv in (("--kisi", "ayse"), ("--ki=ayse",)):
            out = self.stop("kb", "alindi", "B-20261029-ayse-01", *argv)
            self.assertIn("yalnız kendi adınıza", out)
            self.assertIn("`yazanlar` listesindekiler kaydeder", out)
        self.assertIn("yalnız kendiniz kaydedersiniz",
                      self.stop("kb", "alindi", "B-20261029-ayse-01", "--kisi", "mert", "--kaydeden", "ayse"))
        self.assertIn("--kisi gerekli", self.stop("kb", "alindi", "B-20261029-ayse-01"))
        self.assertFalse((self.kok() / "onaylar").exists())
        code, out, _ = self.cli("kb", "alindi", "B-20261029-ayse-01", "--kisi", "mert", "--json")
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads(out)["komut"], ["alindi", "B-20261029-ayse-01", "--kisi", "mert", "--json"])

    def test_yazan_baskasi_adina_alindi_kaydeder(self):
        """.kb.json yazanlar'daki biri (ayse) yazma yetkisi olmayanın (mert) alındısını kaydeder: kaydeden = ayse."""
        self.ok("hazirla")
        os.environ["TF_BILGI_KISI"] = "ayse"
        code, out, _ = self.cli("kb", "alindi", "B-20261029-ayse-01", "--kisi", "mert", "--json")
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads(out)["komut"],
                         ["alindi", "B-20261029-ayse-01", "--kisi", "mert", "--json", "--kaydeden", "ayse"])
        self.assertIn("kaydeden: ayse", (self.kok() / "onaylar/B-20261029-ayse-01--mert.md").read_text())
        code, out, _ = self.cli("kb", "--json", "alindi", "B-20261029-ayse-01", "--kisi", "mert")
        self.assertEqual(json.loads(out)["komut"],
                         ["--json", "alindi", "B-20261029-ayse-01", "--kisi", "mert", "--kaydeden", "ayse"])
        code, out, _ = self.cli("kb", "alindi", "B-20261029-ayse-01", "--kisi", "mert", "--ka=ayse")
        self.assertEqual(json.loads(out)["komut"], ["alindi", "B-20261029-ayse-01", "--kisi", "mert", "--ka=ayse"])
        self.assertIn("yalnız kendiniz kaydedersiniz",
                      self.stop("kb", "alindi", "B-20261029-ayse-01", "--kisi", "mert", "--kaydeden", "mert"))
        self.assertIn("iki kez", self.stop("kb", "alindi", "B-20261029-ayse-01", "--kisi", "mert", "--kaydeden", "ayse",
                                           "--ka", "ayse"))
        self.assertIn("`--` kullanılmaz", self.stop("kb", "alindi", "--", "B-20261029-ayse-01", "--kisi", "mert"))
        self.assertIn("kendi adınıza", self.stop("kb", "izin-ekle", "x.pdf", "--kategori", "telefon", "--kisi", "mert",
                                                 "--gerekce", "santral"))  # izin-ekle'de başkası adına yok

    def test_needs_hazirla_first(self):
        self.assertIn("hazirla", self.stop("kb", "son"))


class TopluHazirlaTest(Base):
    """/toplu-paylas: kb.py toplu-hazirla yalnız gecici/ altına hazırlık klasörü kurabilir."""

    def setUp(self):
        super().setUp()
        self.ok("hazirla")
        self.gecici = self.cache / "gecici"
        self.gecici.mkdir(parents=True, exist_ok=True)
        self.kaynak = self.tmp / "artifaktlar"
        self.kaynak.mkdir()

    def test_whitelisted_and_cikti_under_gecici_passes_through(self):
        hedef = self.gecici / "toplu-20261105-120000"
        code, out, _ = self.cli("kb", "toplu-hazirla", str(self.kaynak), "--cikti", str(hedef))
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads(out)["komut"], ["toplu-hazirla", str(self.kaynak), "--cikti", str(hedef)])
        for argv in ((f"--ci={hedef}",), ("--json", "--cik", str(hedef)), ("--bugun", "2026-11-05", "--cikti", str(hedef))):
            code, out, _ = self.cli("kb", "toplu-hazirla", str(self.kaynak), *argv)
            self.assertEqual(code, 0, (argv, out))
        self.ok("hazirla", "--yonetim")
        code, out, _ = self.cli("kb", "--yonetim", "toplu-hazirla", str(self.kaynak), "--cikti", str(hedef) + "-yonetim")
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads(out)["kok"], str(self.kok("yonetim")))

    def test_cikti_outside_gecici_or_relative_is_refused(self):
        (self.gecici / "bag").symlink_to(self.tmp)
        vakalar = (
            (("--cikti", str(self.tmp / "disari")), "geçici klasörünün altında"),
            (("--cikti", str(self.gecici)), "geçici klasörünün altında"),
            (("--cikti", str(self.gecici / ".." / "toplu")), "geçici klasörünün altında"),
            (("--cikti", str(self.gecici / "bag" / "toplu")), "geçici klasörünün altında"),
            (("--cikti", str(self.kok() / "toplu")), "geçici klasörünün altında"),
            ((f"--c={self.tmp / 'disari'}",), "geçici klasörünün altında"),
            (("--cikti", "toplu-1"), "mutlak"),
            ((), "tek bir --cikti"),
            (("--cikti",), "tek bir --cikti"),
            (("--cikti", str(self.gecici / "a"), "--cik", str(self.gecici / "b")), "tek bir --cikti"),
        )
        for argv, kelime in vakalar:
            self.assertIn(kelime, self.stop("kb", "toplu-hazirla", str(self.kaynak), *argv), argv)
        self.assertIn("mutlak", self.stop("kb", "toplu-hazirla", "artifaktlar", "--cikti", str(self.gecici / "a")))
        self.assertIn("en az bir", self.stop("kb", "toplu-hazirla", "--cikti", str(self.gecici / "a")))
        self.assertFalse((self.tmp / "disari").exists())

    def test_hazirla_gives_a_timestamp_for_the_staging_folder(self):
        self.assertRegex(self.ok("hazirla")["damga"], r"^\d{8}-\d{6}$")


class YazTest(Base):
    def setUp(self):
        super().setUp()
        os.environ["TF_BILGI_KISI"] = "ayse"
        self.ok("hazirla")

    def test_unresolved_person_is_refused(self):
        del os.environ["TF_BILGI_KISI"]  # gh girişi yok, git e-postası kisiler.json'da yok
        self.assertIn("Kim olduğunuz bulunamadı", self.stop("yaz", stdin=girdi_metni()))
        self.assertFalse((self.kok() / "girdiler/2026/11").exists())

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

    def test_three_digit_counter_and_own_name_only(self):
        result = self.ok("yaz", stdin=girdi_metni("B-20261105-ayse-100"))
        self.assertEqual(result["yol"], "girdiler/2026/11/B-20261105-ayse-100.md")
        os.environ["TF_BILGI_KISI"] = "mert"
        self.assertIn("kendi adınıza", self.stop("yaz", stdin=girdi_metni("B-20261105-ayse-02")))

    def test_id_prefix_must_match_repo(self):
        self.assertIn("öneki 'B'", self.stop("yaz", stdin=girdi_metni("BY-20261105-ayse-01")))

    def test_rejects_missing_or_bad_frontmatter(self):
        self.assertIn("frontmatter", self.stop("yaz", stdin="id: B-20261105-ayse-01\n"))
        self.assertIn("kapanmamış", self.stop("yaz", stdin="---\nid: B-20261105-ayse-01\n"))
        self.assertIn("sözleşmeye uymuyor", self.stop("yaz", stdin="---\nid: K-0001\n---\n"))


class KaydetTest(Base):
    def setUp(self):
        super().setUp()
        os.environ["TF_BILGI_KISI"] = "ayse"
        self.ok("hazirla")

    def published(self, rel, alan="ekip"):
        return subprocess.run(["git", "-C", str(self.bare[alan]), "cat-file", "-e", f"main:{rel}"],
                              capture_output=True).returncode == 0

    def onay_yaz(self, kisi, kaydeden=None, girdi="B-20261029-ayse-01"):
        rel = f"onaylar/{girdi}--{kisi}.md"
        (self.kok() / "onaylar").mkdir(exist_ok=True)
        (self.kok() / rel).write_text(f"---\ngirdi: {girdi}\nkisi: {kisi}\n"
                                      + (f"kaydeden: {kaydeden}\n" if kaydeden else "") + "tarih: 2026-11-05\n---\n")
        return rel

    def test_yonetim_commits_to_yonetim_and_refuses_ekip_ids(self):
        self.ok("hazirla", "--yonetim")
        ekip_once = git(self.bare["ekip"], "rev-parse", "main")
        metin = girdi_metni("BY-20261105-ayse-01").replace("alan: ekip", "alan: yonetim")
        entry = self.ok("yaz", "--yonetim", stdin=metin)["yol"]
        self.assertEqual(entry, "girdiler/2026/11/BY-20261105-ayse-01.md")
        result = self.ok("kaydet", "--yonetim", "--mesaj", "BY-20261105-ayse-01: Deneme", entry)
        self.assertTrue(result["gonderildi"])
        self.assertTrue(result["baglantilar"][0]["url"].startswith(
            "https://github.com/Teamfluencer-Dev/tf-bilgi-yonetim/blob/main/"))
        self.assertTrue(self.published(entry, "yonetim"))
        self.assertFalse(self.published(entry, "ekip"))
        self.assertEqual(git(self.bare["ekip"], "rev-parse", "main"), ekip_once)
        ekip_yolu = "girdiler/2026/11/B-20261105-ayse-01.md"  # ekip kimliği yönetim klonunda
        (self.kok("yonetim") / ekip_yolu).write_text(girdi_metni())
        out = self.stop("kaydet", "--yonetim", "--mesaj", "m", ekip_yolu)
        self.assertIn("bu deponun girdi öneki 'BY'", out)
        self.assertFalse(self.published(ekip_yolu, "yonetim"))

    def test_mesaj_dosyadan_ilk_satir(self):
        entry = self.ok("yaz", stdin=girdi_metni())["yol"]
        mesaj = self.cache / "gecici" / "paylas-1" / "mesaj.txt"
        mesaj.parent.mkdir(parents=True)
        mesaj.write_text("\n  B-20261105-ayse-01: Başlık 'tırnak' $(touch PWNED)\x07\nikinci satır\n", encoding="utf-8")
        disari = self.tmp / "mesaj.txt"
        disari.write_text("x\n")
        self.assertIn("geçici klasörünün altında", self.stop("kaydet", "--mesaj-dosya", str(disari), entry))
        self.ok("kaydet", "--mesaj-dosya", str(mesaj), entry)
        self.assertEqual(git(self.bare["ekip"], "log", "-1", "--format=%s", "main"),
                         "B-20261105-ayse-01: Başlık 'tırnak' $(touch PWNED)")
        self.assertFalse((self.kok() / "PWNED").exists())

    def test_gizli_girdiyle_ham_kaydedilmez(self):
        metin = girdi_metni().replace("tarih: 2026-11-05\n---", "gizli: true\nham: null\ntarih: 2026-11-05\n---")
        entry = self.ok("yaz", stdin=metin)["yol"]
        ham = "ham/2026/11/3f9a2c1e-gizli.txt"
        (self.kok() / ham).parent.mkdir(parents=True)
        (self.kok() / ham).write_text("gizli içerik\n")
        with open(self.kok() / tf_bilgi.DEFTER, "a") as defter:
            defter.write("3f9a2c1e" + "0" * 56 + f"\t{ham}\tB-20261105-ayse-01\t2026-11-05\n")
        out = self.stop("kaydet", "--mesaj", "m", entry, ham, tf_bilgi.DEFTER)
        self.assertIn("gizli girdiyle (B-20261105-ayse-01) ham/ dosyası kaydedilmez", out)
        self.assertFalse(self.published(ham))
        self.assertTrue(tf_bilgi.gizli_girdi_mi(metin))
        self.assertFalse(tf_bilgi.gizli_girdi_mi(girdi_metni()))
        self.assertFalse(tf_bilgi.gizli_girdi_mi("---\nid: x\n---\ngizli: true\n"))  # gövdede sayılmaz
        (self.kok() / ham).unlink()
        git(self.kok(), "checkout", "--", tf_bilgi.DEFTER)
        self.assertTrue(self.ok("kaydet", "--mesaj", "m", entry)["gonderildi"])  # yalnız girdi geçer

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
        onay = self.onay_yaz("mert")
        self.assertIn("`kaydeden: ayse` olmalı", self.stop("kaydet", "--mesaj", "x", onay))  # yazan ama işaretsiz
        os.environ["TF_BILGI_KISI"] = "mert"
        result = self.ok("kaydet", "--mesaj", "alindi: B-20261029-ayse-01 (mert)", onay)
        self.assertTrue(self.published(onay))
        self.assertEqual(result["baglantilar"][0]["yol"], onay)

    def test_yazan_baskasi_adina_onay_kaydeder(self):
        """ayse (.kb.json yazanlar) yazma yetkisi olmayan mert'in alındısını kaydeder; onayda kaydeden görünür."""
        onay = self.onay_yaz("mert", kaydeden="ayse")
        self.ok("kaydet", "--mesaj", "alindi: B-20261029-ayse-01 (mert, kaydeden ayse)", onay)
        self.assertTrue(self.published(onay))
        self.assertIn("kaydeden: ayse", git(self.bare["ekip"], "show", f"main:{onay}"))

    def test_yazan_olmayan_baskasi_adina_kaydedemez(self):
        os.environ["TF_BILGI_KISI"] = "mert"  # yazanlar'da değil
        before = git(self.bare["ekip"], "rev-parse", "main")
        for kaydeden in ("mert", None):
            onay = self.onay_yaz("ayse", kaydeden=kaydeden)
            self.assertIn("yalnız kendi adınıza kaydedilir", self.stop("kaydet", "--mesaj", "x", onay), kaydeden)
        kendi = self.onay_yaz("mert", kaydeden="ayse")  # kendi onayında başkası kaydeden olamaz
        self.assertIn("`kaydeden` siz olmalısınız", self.stop("kaydet", "--mesaj", "x", kendi))
        self.assertEqual(git(self.bare["ekip"], "rev-parse", "main"), before)

    def test_izinler_append_only_and_own_name(self):
        izin = self.kok() / "ham" / "IZINLER.tsv"
        bas = "sha256\tkategori\tonaylayan\ttarih\tgerekce\n"
        sha = "a" * 64
        izin.write_text(bas + f"{sha}\ttelefon\tmert\t2026-11-05\tsantral numarası\n", encoding="utf-8")
        os.environ["TF_BILGI_KISI"] = "ayse"
        self.assertIn("kendi adınıza", self.stop("kaydet", "--mesaj", "izin", "ham/IZINLER.tsv"))
        izin.write_text(bas + f"{sha}\ttelefon\tayse\t2026-11-05\tsantral numarası\n", encoding="utf-8")
        self.ok("kaydet", "--mesaj", "izin", "ham/IZINLER.tsv")
        self.assertTrue(self.published("ham/IZINLER.tsv"))
        izin.write_text(bas, encoding="utf-8")  # satır silmek yok
        self.assertIn("yalnız satır eklenebilir", self.stop("kaydet", "--mesaj", "izin", "ham/IZINLER.tsv"))

    def test_reports_unpushed_commit(self):
        os.environ["STUB_KB_PUSH_YOK"] = "1"
        entry = self.ok("yaz", stdin=girdi_metni())["yol"]
        result = self.ok("kaydet", "--mesaj", "m", entry)
        self.assertFalse(result["gonderildi"])
        self.assertTrue(result["notlar"])
        self.assertFalse(self.published(entry))

    def test_kb_failure_is_relayed(self):
        entry = self.ok("yaz", stdin=girdi_metni())["yol"]
        basarisiz = "import sys\nprint('itme reddedildi')\nsys.exit(1)\n"
        (self.kok() / "araclar" / "kb.py").write_text(basarisiz)
        with mock.patch.object(tf_bilgi, "KB_SHA256", (hashlib.sha256(basarisiz.encode()).hexdigest(),)):
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

    def test_maskele_into_run_folder_under_gecici_only(self):
        self.ok("hazirla")
        src = self.tmp / "notlar.txt"
        src.write_text("token GIZLI-ANAHTAR-123 burada\n")
        dizin = self.cache / "gecici" / "paylas-20261105-120000"
        result = self.ok("maskele", str(src), "--dizin", str(dizin))
        self.assertEqual(Path(result["yol"]), dizin / "maskeli-notlar.txt")
        for kotu in (str(self.tmp / "disari"), "goreli", str(self.cache / "gecici")):
            self.assertIn("--dizin", self.stop("maskele", str(src), "--dizin", kotu), kotu)
        self.assertFalse((self.tmp / "disari").exists())


class TemizleTest(Base):
    """Hazırlık klasörleri (belgelerin tam metin kopyaları) yalnız gecici/ altında silinir."""

    def setUp(self):
        super().setUp()
        self.gecici = self.cache / "gecici"
        self.d = self.gecici / "paylas-20261105-120000"
        (self.d / "alt").mkdir(parents=True)
        (self.d / "metin.txt").write_text("belge metni\n")
        (self.d / "alt" / "kaynak.pdf").write_bytes(b"%PDF")
        self.d2 = self.gecici / "toplu-20261105-120000-yonetim"
        self.d2.mkdir()
        self.disari = self.tmp / "disari"
        self.disari.mkdir()
        (self.disari / "kalmali.txt").write_text("x\n")

    def test_silinir_ve_olmayan_hata_degil(self):
        yok = self.gecici / "toplu-yok"
        result = self.ok("temizle", str(self.d), str(self.d2), str(yok))
        self.assertEqual(result, {"silinen": [str(self.d.resolve()), str(self.d2.resolve())], "yoktu": [str(yok.resolve())]})
        self.assertFalse(self.d.exists() or self.d2.exists())
        self.assertTrue(self.gecici.is_dir())

    def test_gecici_disi_reddedilir_ve_hicbiri_silinmez(self):
        (self.gecici / "bag").symlink_to(self.disari)
        self.ok("hazirla")
        for kotu in (str(self.gecici), str(self.gecici) + "/", str(self.gecici / ".."), str(self.disari),
                     str(self.gecici / ".." / "tf-bilgi"), str(self.kok()), str(self.gecici / "bag" / "kalmali.txt"),
                     "paylas-20261105-120000", str(self.d / "..")):
            out = self.stop("temizle", str(self.d), kotu)
            self.assertTrue("geçici klasörünün altındakileri" in out or "mutlak yol" in out, (kotu, out))
        self.assertTrue((self.d / "metin.txt").exists())
        self.assertTrue((self.disari / "kalmali.txt").exists())
        self.assertTrue((self.kok() / ".kb.json").exists())

    def test_baglanti_yalniz_kendisi_silinir(self):
        bag = self.gecici / "bag"
        bag.symlink_to(self.disari)
        self.assertEqual(self.ok("temizle", str(bag))["silinen"], [str(bag)])
        self.assertFalse(bag.is_symlink())
        self.assertTrue((self.disari / "kalmali.txt").exists())


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


class YetkiTest(Base):
    """Depoya yalnız .kb.json `yazanlar` yazar. Yazma işleri taslaktan önce durur, okuma çalışır; yazma yetkisi
    olmayanın alındısını `yazanlar`'daki biri onun adına kaydeder (onay dosyasında `kaydeden`)."""

    def setUp(self):
        super().setUp()
        self.github_uzak()
        os.environ["FAKE_GH_LOGIN"] = "ayse-gh"  # yazanlar'da

    def test_yetki_varsa_gecer(self):
        result = self.ok("hazirla", "--yazma")
        self.assertIs(result["yazabilir"], True)
        self.assertEqual(result["kisi"], "ayse")
        self.assertIn(["api", "repos/Teamfluencer-Dev/tf-bilgi", "--jq", ".permissions.push"], self.gh_calls())

    def test_kim_oldugu_bilinmiyorsa_yazma_durur(self):
        os.environ["FAKE_GH_LOGIN"] = "bilinmeyen-gh"
        self.assertIsNone(self.ok("hazirla")["kisi"])  # okuma yolu durmaz, kişi sorulur
        out = self.stop("hazirla", "--yazma")
        self.assertIn("Kim olduğunuz bulunamadı; depoya yalnız kendi adınıza yazılır", out)
        self.assertIn("export TF_BILGI_KISI=", out)

    def test_yetki_yoksa_yazma_durur_okuma_calisir(self):
        os.environ.update({"FAKE_GH_PUSH": "false", "FAKE_GH_LOGIN": "mert-gh"})
        self.assertIs(self.ok("hazirla")["yazabilir"], False)  # okuma yolu durmaz
        out = self.stop("hazirla", "--yazma")
        self.assertTrue(out.startswith("Bu depoya yalnız Ayşe yazabiliyor; paylaşmak istediğini Ayşe'ye ilet"), out)
        for parca in ("ona “alındı <girdi-id>” yaz; o `/bilgi alindi <girdi-id> --kisi mert` ile senin adına kaydeder",
                      "GitHub hesabının (mert-gh) Teamfluencer-Dev/tf-bilgi deposunda yazma yetkisi yok",
                      "/bilgi kuyrugum"):
            self.assertIn(parca, out)
        code, _, _ = self.cli("kb", "son", "--json")
        self.assertEqual(code, 0)
        onay = "onaylar/B-20261029-ayse-01--mert.md"
        (self.kok() / onay).parent.mkdir(parents=True)
        (self.kok() / onay).write_text("---\ngirdi: B-20261029-ayse-01\nkisi: mert\ntarih: 2026-11-05\n---\n")
        before = git(self.bare["ekip"], "rev-parse", "main")
        self.assertIn("yalnız Ayşe yazabiliyor", self.stop("kaydet", "--mesaj", "alindi", onay))
        self.assertEqual(git(self.bare["ekip"], "rev-parse", "main"), before)

    def test_yazan_yetkisizin_alindisini_kaydeder(self):
        """Mesajın söylediği yol uçtan uca: mert “alındı <id>” yazar, ayse kaydeder; onayda kaydeden: ayse."""
        self.assertIs(self.ok("hazirla", "--yazma")["yazabilir"], True)
        code, out, _ = self.cli("kb", "alindi", "B-20261029-ayse-01", "--kisi", "mert", "--json")
        self.assertEqual(code, 0, out)
        onay = json.loads(out)["yol"]
        result = self.ok("kaydet", "--mesaj", "alindi: B-20261029-ayse-01 (mert, kaydeden ayse)", onay)
        self.assertTrue(result["gonderildi"])
        yayinda = git(self.bare["ekip"], "show", f"main:{onay}")
        self.assertIn("kisi: mert", yayinda)
        self.assertIn("kaydeden: ayse", yayinda)

    def test_yazan_olmayan_baskasi_adina_kaydedemez(self):
        os.environ["FAKE_GH_LOGIN"] = "mert-gh"  # yetkisi olsa bile yazanlar'da değil
        self.ok("hazirla", "--yazma")
        self.assertIn("yalnız kendi adınıza", self.stop("kb", "alindi", "B-20261029-ayse-01", "--kisi", "ayse"))
        self.assertFalse((self.kok() / "onaylar").exists())

    def test_denetlenemezse_durmaz(self):
        os.environ["FAKE_GH_REPO_CIKIS"] = "1"
        result = self.ok("hazirla", "--yazma")
        self.assertIsNone(result["yazabilir"])
        self.assertTrue(any("denetlenemedi" in n for n in result["notlar"]), result["notlar"])

    def test_yazanlar_yoksa_genel_mesaj(self):
        self.seed_commit("ekip", ".kb.json", json.dumps({"alan": "ekip", "girdi_onek": "B",
                                                         "uzak": "Teamfluencer-Dev/tf-bilgi"}))
        os.environ["FAKE_GH_PUSH"] = "false"
        out = self.stop("hazirla", "--yazma")
        self.assertIn("deposunda yazma yetkisi yok; paylaşmak istediğini depoya yazabilen birine ilet", out)

    def test_yerel_uzakta_denetim_yok(self):
        os.environ["TF_BILGI_UZAK_EKIP"] = str(self.bare["ekip"])
        self.assertIsNone(self.ok("hazirla", "--yazma")["yazabilir"])
        self.assertFalse(any(c[:1] == ["api"] and c[1].startswith("repos/") for c in self.gh_calls()))

    def test_yonelme(self):
        self.assertEqual([tf_bilgi.yonelme(a) for a in ("Mert", "Can", "Ayşe", "Duru", "Işık")],
                         ["Mert'e", "Can'a", "Ayşe'ye", "Duru'ya", "Işık'a"])


class TercihTest(Base):
    def setUp(self):
        super().setUp()
        os.environ["FAKE_GH_LOGIN"] = "ayse-gh"
        self.ok("hazirla")

    def test_issue_yoksa_durur(self):
        self.seed_commit("ekip", ".kb.json", json.dumps({"alan": "ekip", "girdi_onek": "B", "uzak": "Teamfluencer-Dev/tf-bilgi",
                                                         "tercih_issue": None, "tercih_yoneticileri": ["ayse"]}))
        self.ok("hazirla")
        out = self.stop("tercih")
        self.assertIn("issue'su henüz açılmamış", out)
        self.assertIn("Ayşe'ye söyle", out)
        self.assertFalse(any(c[:2] == ["issue", "comment"] for c in self.gh_calls()))

    def test_okuma_varsayilan_ve_tercih(self):
        result = self.ok("tercih")
        self.assertEqual((result["kisi"], result["kanallar"], result["varsayilan"]), ("ayse", ["slack"], True))
        self.assertEqual(result["issue"], "https://github.com/Teamfluencer-Dev/tf-bilgi/issues/7")
        self.assertIn("e-postadan aranır", result["cozum"]["slack"])  # Slack kimliği kayıtlı değil, e-posta var
        self.assertEqual(result["cozum"]["mail"], "e-posta kayıtlı")
        self.assertIn("henüz kapalı", result["cozum"]["whatsapp"])
        self.yorum(yorum("ayse-gh", "tercih: kanal=slack,mail", 1),
                   yorum("ayse-gh", "tercih: kanal=whatsapp", 2, "2026-11-05T10:00:00Z", "2026-11-05T11:00:00Z"))
        result = self.ok("tercih")
        self.assertEqual((result["kanallar"], result["varsayilan"]), (["slack", "mail"], False))
        self.assertEqual(result["kaynak"], "yorum 2026-11-05 · ayse-gh")
        self.assertTrue(any("düzenlenmiş" in u for u in result["uyarilar"]))
        self.assertIn(["api", "--paginate", "repos/Teamfluencer-Dev/tf-bilgi/issues/7/comments?per_page=100",
                       "--jq", ".[]"], self.gh_calls())

    def test_kendi_adina_yazar(self):
        result = self.ok("tercih", "--kanal", "Slack, mail,slack")
        self.assertEqual((result["satir"], result["kanallar"]), ("tercih: kanal=slack,mail", ["slack", "mail"]))
        self.assertIn(["issue", "comment", "7", "-R", "Teamfluencer-Dev/tf-bilgi", "--body", "tercih: kanal=slack,mail"],
                      self.gh_calls())
        self.assertTrue(result["url"].endswith("#issuecomment-99"))
        self.assertIn("kanal anlaşılmadı", self.stop("tercih", "--kanal", "telefon").lower())

    def test_baskasi_adina_yalniz_yonetici(self):
        result = self.ok("tercih", "--kisi", "mert", "--kanal", "whatsapp")
        self.assertEqual(result["satir"], "tercih: kisi=mert kanal=whatsapp")
        os.environ["FAKE_GH_LOGIN"] = "mert-gh"
        out = self.stop("tercih", "--kisi", "ayse", "--kanal", "mail")
        self.assertIn("yalnız tercih yöneticileri yazar (Ayşe)", out)

    def test_github_hesabi_eslesmezse_yazmaz(self):
        os.environ.update({"FAKE_GH_LOGIN": "", "TF_BILGI_KISI": "mert"})
        out = self.stop("tercih", "--kanal", "mail")
        self.assertIn("GitHub girişin (yok) kisiler.json'daki hesabınla (mert-gh) aynı değil", out)
        self.assertFalse(any(c[:2] == ["issue", "comment"] for c in self.gh_calls()))

    def test_kurallar_bildir_ile_ayni(self):
        sonuc, uyarilar = tf_bilgi.tercih_coz([
            yorum("AYSE-GH", "tercih: kanal=mail", 1),
            yorum("mert-gh", "tercih: kisi=ayse kanal=slack", 2),      # yönetici değil
            yorum("ayse-gh", "tercih: kisi=mert kanal=whatsapp", 3),   # yönetici
            yorum("yabanci", "tercih: kanal=slack", 4),
            yorum("ayse-gh", "tercih: kanal=faks", 5)], KISILER["kisiler"], {"ayse"})
        self.assertEqual(sonuc, {"ayse": {"kanallar": ["mail"], "kaynak": "yorum 2026-11-05 · AYSE-GH"},
                                 "mert": {"kanallar": ["whatsapp"], "kaynak": "yorum 2026-11-05 · ayse-gh"}})
        self.assertEqual(len(uyarilar), 3)


class BildirimPlaniTest(Base):
    def setUp(self):
        super().setUp()
        kisiler = json.loads(json.dumps(KISILER))
        kisiler["kisiler"].update({
            "ali": {"ad": "Ali Örnek", "alanlar": ["ekip"], "slack": "U0ALI", "eposta": None, "github": None},
            "zeynep": {"ad": "Zeynep Örnek", "alanlar": ["ekip"], "slack": None, "eposta": None, "github": None},
            "can": {"ad": "Can Örnek", "alanlar": ["yonetim"], "slack": "U0CAN", "eposta": None, "github": None}})
        self.seed_commit("ekip", "kisiler.json", json.dumps(kisiler, ensure_ascii=False))
        self.ok("hazirla")

    def plan(self, *argv, an="2026-11-05T10:00:00+03:00"):
        os.environ["TF_BILGI_SIMDI"] = an
        return self.ok("bildirim-plani", "--yazar", "ayse", *argv)

    def test_hemen_simdi_ve_kanalsiz_kisi(self):
        r = self.plan("--tip", "BILGI", "--kimden", "ali,mert,zeynep,can,ayse", "--haber", "hemen")
        self.assertTrue(r["anlik"])
        self.assertEqual(r["satir"], "şimdi anlık: Ali (Slack), Mert (Slack/mail) · Can'a bildirim gitmez (ekip "
                                     "alanının üyesi değil) · sen (gönderen) bildirim almazsın · Zeynep: kayıtlı kanal "
                                     "yok (Slack kimliği ve e-posta), gönderimde dizinde bulunamazsa hiçbir şey gitmez")
        self.assertEqual([a["durum"] for a in r["alicilar"]], ["simdi", "simdi", "kanal-yok", "alan-disi", "gonderen"])

    def test_sessiz_saat_ve_ozet_zamani(self):
        r = self.plan("--tip", "BILGI", "--kimden", "ali", "--haber", "hemen", an="2026-11-05T19:30:00+03:00")
        self.assertEqual(r["satir"], "sessiz saat (Per 19:30): Ali (Slack) yarın 08:30 özetinde")
        r = self.plan("--tip", "BILGI", "--kimden", "ali", "--haber", "hemen", an="2026-11-06T20:00:00+03:00")
        self.assertIn("Pzt 08:30 özetinde", r["satir"])
        r = self.plan("--tip", "BILGI", "--kimden", "ali", an="2026-11-05T07:00:00+03:00")
        self.assertEqual((r["anlik"], r["satir"]), (False, "Ali (Slack) bugün 08:30 özetinde"))

    def test_acil_karar_haber_olmadan_da_anlik_ve_sinir(self):
        r = self.plan("--tip", "KARAR", "--kimden", "ali", "--son-tarih", "2026-11-06")
        self.assertTrue(r["anlik"])
        r = self.plan("--tip", "KARAR", "--kimden", "ali", "--son-tarih", "2026-11-20")
        self.assertFalse(r["anlik"])
        r = self.plan("--tip", "BILGI", "--kimden", "ali", "--haber", "hemen", "--adet", "5")
        self.assertIn("kişi başı günde en çok 3 anlık; kalan 2 girdi yarın 08:30 özetinde", r["satir"])

    def test_tercih_issueden_okunur(self):
        self.yorum(yorum("ayse-gh", "tercih: kisi=mert kanal=whatsapp"))
        r = self.plan("--tip", "BILGI", "--kimden", "mert", "--haber", "hemen")
        self.assertEqual(r["satir"], "şimdi anlık: Mert (mail) · WhatsApp henüz kapalı → mail")
        self.assertEqual(r["alicilar"][0]["tercih"], "issue")
        os.environ["FAKE_GH_YORUM_CIKIS"] = "1"
        r = self.plan("--tip", "BILGI", "--kimden", "mert", "--haber", "hemen")
        self.assertIn("Mert (Slack/mail)", r["satir"])
        self.assertTrue(any("okunamadı" in n for n in r["notlar"]))

    def test_bilinmeyen_kisi(self):
        self.assertIn("kimse", self.stop("bildirim-plani", "--tip", "BILGI", "--kimden", "kimse", "--yazar", "ayse"))


class GizliAlicilarTest(Base):
    """Gizli paylaşım: Drive'da paylaşılacak iş e-postaları kisiler.json'dan; adres yoksa tahmin edilmez."""

    def setUp(self):
        super().setUp()
        kisiler = json.loads(json.dumps(KISILER))
        kisiler["kisiler"]["zeynep"] = {"ad": "Zeynep Örnek", "alanlar": ["ekip"], "eposta": None, "github": None}
        for alan in ("ekip", "yonetim"):
            self.seed_commit(alan, "kisiler.json", json.dumps(kisiler, ensure_ascii=False))
        self.ok("hazirla")
        self.ok("hazirla", "--yonetim")

    def test_epostalar_ve_eksik(self):
        r = self.ok("gizli-alicilar", "--kimden", "mert,zeynep,mert")
        self.assertEqual([(a["kisi"], a["eposta"], a["alan_uyesi"]) for a in r["alicilar"]],
                         [("mert", "mert@ornek.test", True), ("zeynep", None, True)])
        self.assertEqual(r["satir"], "Mert: mert@ornek.test · Zeynep: e-postası kayıtlı değil (kisiler.json)")
        self.assertEqual(r["eksik_eposta"], ["Zeynep"])
        self.assertIn("tahmin edilmez", r["notlar"][0])

    def test_yonetim_alani_ve_bilinmeyen(self):
        r = self.ok("gizli-alicilar", "--yonetim", "--kimden", "ayse,mert")
        self.assertEqual([a["alan_uyesi"] for a in r["alicilar"]], [True, False])
        self.assertIn("Mert yonetim alanının üyesi değil", r["notlar"][0])
        self.assertIn("kimse", self.stop("gizli-alicilar", "--kimden", "ayse,kimse"))
        self.assertEqual(self.gh_calls(), [c for c in self.gh_calls() if c[:2] != ["issue", "comment"]])  # yazmaz


class CliTest(Base):
    def test_hazirla_prints_json(self):
        code, out, _ = self.cli("hazirla")
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads(out)["alan"], "ekip")

    def test_stop_exits_2_with_turkish_message(self):
        code, out, _ = self.cli_betik("kb", "son")
        self.assertEqual(code, 2)
        self.assertIn("önce", out)

    def test_real_entry_point_enforces_the_shipped_pin(self):
        self.ok("hazirla")  # stub kb.py, not the shipped hash
        code, out, _ = self.cli_betik("hazirla")
        self.assertEqual(code, 2)
        self.assertIn("eklentinin onayladığı sürüm değil", out)

    def test_usage(self):
        code, _, err = self.cli_betik()
        self.assertEqual(code, 64)
        self.assertIn("kullanım", err)
        self.assertIn("temizle", err)
        self.assertIn("gizli-alicilar", err)


if __name__ == "__main__":
    unittest.main()
