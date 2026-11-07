"""Tests for tf_bilgi.py — real git repos with local bare remotes, a fake gh, a stub kb.py.

Run: python3 -m unittest discover -s claude-plugins/tf-bilgi/tests -v

Nothing here touches the network: GitHub URLs are rewritten to local bare repos
(url.<path>.insteadOf) and git may only use the file protocol (GIT_ALLOW_PROTOCOL).
All people, logins and addresses below are fictional.
"""
import base64
import contextlib
import datetime
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unicodedata
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
    if "TARANAMADI" in metin:
        print(json.dumps({"taranamadi": True, "neden": "metin katmani yok"}))
        sys.exit(5)
    if "TARA-COKTU" in metin:
        sys.exit(1)
    bulgu = "GIZLI-ANAHTAR" in metin
    kisisel = "KISISEL-VERI" in metin
    if "--maskele" in args:
        sys.stdout.write(metin.replace("GIZLI-ANAHTAR-123", "[maskelendi]"))
    else:
        print(json.dumps({"bulgular": ([{"tur": "sir", "satir": 1}] if bulgu else [])
                          + ([{"tur": "kisisel", "ad": "telefon", "satir": 2}] if kisisel else [])}))
    sys.exit(3 if bulgu or kisisel else 0)
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
if args[:1] == ["api"]:  # REST: push yetkisi, issue/yorum/etiket (FAKE_GH_ISSUES durum dosyası)
    i, yol, alanlar, yontem = 1, None, {}, "GET"
    while i < len(args):
        if args[i] in ("-X", "--input", "-f", "--jq"):
            if args[i] == "-X":
                yontem = args[i + 1]
            if args[i] == "-f":
                k, _, v = args[i + 1].partition("=")
                alanlar[k] = v
            i += 2
        elif args[i].startswith("-"):
            i += 1
        else:
            yol = yol or args[i]
            i += 1
    yol = yol.split("?", 1)[0]
    parca = yol.split("/")
    durum = json.load(open(os.environ["FAKE_GH_ISSUES"]))
    def kaydet():
        json.dump(durum, open(os.environ["FAKE_GH_ISSUES"], "w"), ensure_ascii=False)
    def cik(ad):
        if os.environ.get(ad):
            print("HTTP 500", file=sys.stderr)
            sys.exit(int(os.environ[ad]))
    if yol == "search/issues":
        cik("FAKE_GH_ARAMA_CIKIS")
        if durum.get("arama_hata_kalan"):  # geçici arama hatası: ilk N arama düşer
            durum["arama_hata_kalan"] -= 1
            kaydet()
            print("HTTP 502", file=sys.stderr)
            sys.exit(1)
        aranan = alanlar["q"].split('"')[1].strip("[]")
        ogeler = [x for x in durum["issues"] if aranan in x["title"] and not x.get("aramada_yok")]
        print(json.dumps({"total_count": len(ogeler), "items": ogeler,
                          "incomplete_results": bool(os.environ.get("FAKE_GH_ARAMA_EKSIK"))}))
        sys.exit(0)
    if len(parca) == 3:  # repos/<sahip>/<ad>: push yetkisi
        if os.environ.get("FAKE_GH_REPO_404") or parca[2] in os.environ.get("FAKE_GH_404_DEPOLAR", "").split(","):
            # depo bu hesaba görünmüyor (private, erişim yok); FAKE_GH_404_DEPOLAR: yalnız bu depo adları
            print("gh: Not Found (HTTP 404)", file=sys.stderr)
            sys.exit(1)
        cik("FAKE_GH_REPO_CIKIS")
        push = os.environ.get("FAKE_GH_PUSH", "true")
        print(push)
        sys.exit(0)
    if parca[3] == "labels":
        if yontem == "POST":
            cik("FAKE_GH_ETIKET_CIKIS")
            durum["labels"].append(json.load(sys.stdin)["name"])
            kaydet()
            sys.exit(0)
        if parca[4] in durum["labels"]:
            print(parca[4])
            sys.exit(0)
        print("HTTP 404: Not Found", file=sys.stderr)
        sys.exit(1)
    if parca[3] == "issues" and len(parca) == 4:
        if yontem == "GET":
            cik("FAKE_GH_LISTE_CIKIS")
            print(json.dumps(sorted(durum["issues"], key=lambda x: -x["number"])[:100]))
            sys.exit(0)
        cik("FAKE_GH_YAZ_CIKIS")
        govde = json.load(sys.stdin)
        no = durum["next"]
        durum["next"] += 1
        etiketler = [{"name": e} for e in govde.get("labels", [])
                     if e in durum["labels"] and os.environ.get("FAKE_GH_PUSH", "true") == "true"]
        issue = {"number": no, "title": govde["title"], "body": govde["body"], "state": "open", "comments": 0,
                 "labels": etiketler, "user": {"login": os.environ.get("FAKE_GH_LOGIN", ""), "type": "User"},
                 "html_url": "https://github.com/%s/%s/issues/%d" % (parca[1], parca[2], no)}
        durum["issues"].append(issue)
        kaydet()
        print(json.dumps(issue))
        sys.exit(0)
    if parca[3] == "issues" and parca[5:] == ["comments"]:
        no = parca[4]
        if yontem == "POST":
            cik("FAKE_GH_YAZ_CIKIS")
            cik("FAKE_GH_YORUM_YAZ_CIKIS")  # sayfa açılır ama yorum yazılamaz (ör. kilitli)
            yorum = {"id": 900 + len(durum["comments"].get(no, [])), "body": json.load(sys.stdin)["body"],
                     "user": {"login": os.environ.get("FAKE_GH_LOGIN", ""), "type": "User"},
                     "created_at": "2026-11-05T09:30:00Z", "updated_at": "2026-11-05T09:30:00Z"}
            yorum["html_url"] = "https://github.com/%s/%s/issues/%s#issuecomment-%d" % (parca[1], parca[2], no, yorum["id"])
            durum["comments"].setdefault(no, []).append(yorum)
            kaydet()
            print(json.dumps(yorum))
            sys.exit(0)
        if no in durum["comments"]:
            cik("FAKE_GH_SAYFA_OKU_CIKIS")
            liste = durum["comments"][no]
        else:  # tercih issue'su
            cik("FAKE_GH_YORUM_CIKIS")
            liste = json.load(open(os.environ["FAKE_GH_YORUMLAR"]))
        for yorum in liste:  # --paginate --jq .[]
            print(json.dumps(yorum))
        sys.exit(0)
    print("unexpected gh api call: " + " ".join(args), file=sys.stderr)
    sys.exit(99)
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
        ag = mock.patch.object(tf_bilgi.urllib.request, "urlopen", side_effect=AssertionError("testte ağ yok"))
        ag.start()  # sahte köprü yamalanmadıysa gerçek köprüye (script.google.com, workers.dev) gidilmez
        self.addCleanup(ag.stop)
        self.yorumlar = self.tmp / "yorumlar.json"
        self.yorumlar.write_text("[]")
        os.environ["FAKE_GH_YORUMLAR"] = str(self.yorumlar)
        self.issues = self.tmp / "issues.json"
        self.issues.write_text(json.dumps({"issues": [], "comments": {}, "labels": [], "next": 20}))
        os.environ["FAKE_GH_ISSUES"] = str(self.issues)
        for name in ("TF_BILGI_KISI", "STUB_KB_CIKIS", "STUB_KB_PUSH_YOK", "GIT_DIR", "GIT_WORK_TREE", "FAKE_GH_PUSH",
                     "FAKE_GH_404_DEPOLAR",
                     "FAKE_GH_REPO_CIKIS", "FAKE_GH_YORUM_CIKIS", "TF_BILGI_SIMDI", "FAKE_GH_ARAMA_CIKIS",
                     "FAKE_GH_LISTE_CIKIS", "FAKE_GH_YAZ_CIKIS", "FAKE_GH_ETIKET_CIKIS", "FAKE_GH_ARAMA_EKSIK",
                     "FAKE_GH_YORUM_YAZ_CIKIS", "FAKE_GH_SAYFA_OKU_CIKIS", "TF_BILGI_YOL", "TF_BILGI_KOPRU_URL",
                     "FAKE_GH_REPO_404"):
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
        self.assertEqual(result["uzak"], "eneskrblt/tf-bilgi-yonetim")  # 7 Kas: yönetim deposu org dışında
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
        """Geçişte eski ve yeni kb.py birlikte sabitlenir (KB §12): main'deki 0.7.0 kb.py'si (tf-bilgi#6 head e59a23b)
        ve 0.9.0'ın bitiş tasarımı kb.py'si (KB PR'ı merge edilene kadar eski de geçer). 0.4.0 ve 0.6.0 çıktı."""
        self.assertEqual(GERCEK_KB_SHA256, ("c9fd7f6a98eabadd35bb17b055b8b887b80fb160c347c10d8a736359f418e30e",
                                            "fcbd94e25e361d4b4777337b2d30832c8aad5e9059cba34dbccbb5a908006b71"))
        for cikan in ("e6b4e22430ee55666e55e620969f8df67bd37d17991fdeac8660bec964eddaa6",   # 0.4.0
                      "74ae1f87de1bf3d2422e4b91444d356381d495beb0a51a1cb75e20564ef6852f"):  # 0.6.0
            self.assertNotIn(cikan, GERCEK_KB_SHA256)
        self.assertNotIn("76677edd9f348d1dea7827f3449cf8fb6b8767705b896264129260329a27da23", GERCEK_KB_SHA256)  # 0.3.1
        self.assertNotIn("107e6ad85b374af69b69fc67e27380bd11d33a1afc7c0112188661feb4e07785", GERCEK_KB_SHA256)  # yayınlanmadı
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
            "https://github.com/eneskrblt/tf-bilgi-yonetim/blob/main/"))
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

    def gizli_yaz(self):
        metin = girdi_metni().replace("tarih: 2026-11-05\n---", "gizli: true\nham: null\ntarih: 2026-11-05\n---")
        return self.ok("yaz", stdin=metin)["yol"]

    def ham_ve_defter(self, girdi="B-20261105-ayse-01", ad="gizli"):
        ham = f"ham/2026/11/3f9a2c1e-{ad}.txt"
        (self.kok() / ham).parent.mkdir(parents=True, exist_ok=True)
        (self.kok() / ham).write_text("gizli içerik\n")
        with open(self.kok() / tf_bilgi.DEFTER, "a") as defter:
            defter.write("3f9a2c1e" + ad.encode().hex()[:8].ljust(56, "0") + f"\t{ham}\t{girdi}\t2026-11-05\n")
        return ham

    def test_gizli_girdiye_yalniz_defter_satiri_de_eklenmez(self):
        entry = self.gizli_yaz()
        self.ham_ve_defter()
        out = self.stop("kaydet", "--mesaj", "m", entry, tf_bilgi.DEFTER)  # ham dosyası yok, yalnız defter satırı
        self.assertIn("gizli girdiye (B-20261105-ayse-01) ham dosya satırı eklenemez", out)
        self.assertFalse(self.published(entry))

    def test_gizli_girdiye_sonradan_ham_eklenmez(self):
        entry = self.gizli_yaz()
        self.assertTrue(self.ok("kaydet", "--mesaj", "m", entry)["gonderildi"])
        ham = self.ham_ve_defter()
        out = self.stop("kaydet", "--mesaj", "m", ham, tf_bilgi.DEFTER)  # ikinci çağrı: girdi artık yayımlanmış
        self.assertIn("gizli girdiye (B-20261105-ayse-01) ham dosya satırı eklenemez", out)
        out = self.stop("kaydet", "--mesaj", "m", ham)  # defter verilmese de yerel defterdeki satır bağlar
        self.assertIn("defterde gizli bir girdiye bağlı", out)
        self.assertFalse(self.published(ham))
        (self.kok() / entry).unlink()  # yalnız origin/main'de: yine gizli sayılır
        self.assertTrue(tf_bilgi.gizli_kimlik_mi(self.kok(), "B-20261105-ayse-01"))
        git(self.kok(), "checkout", "--", entry)
        self.assertFalse(tf_bilgi.gizli_kimlik_mi(self.kok(), "B-20261029-ayse-01"))  # gizli olmayan yayımlanmış girdi
        self.assertFalse(tf_bilgi.gizli_kimlik_mi(self.kok(), "-"))

    def test_gizli_olmayan_girdinin_ham_dosyasi_gecer(self):
        entry = self.ok("yaz", stdin=girdi_metni("B-20261105-ayse-02"))["yol"]
        ham = self.ham_ve_defter("B-20261105-ayse-02", "acik")
        self.assertTrue(self.ok("kaydet", "--mesaj", "m", entry, ham, tf_bilgi.DEFTER)["gonderildi"])

    def test_gizli_girdi_mi_kenarlari(self):
        fm = lambda *satir: "---\nid: B-20261105-ayse-01\n" + "".join(s + "\n" for s in satir) + "---\ngövde\n"  # noqa: E731
        self.assertTrue(tf_bilgi.gizli_girdi_mi(fm("gizli: true")))
        self.assertTrue(tf_bilgi.gizli_girdi_mi(fm("gizli: True # yorum")))
        self.assertTrue(tf_bilgi.gizli_girdi_mi("\ufeff" + fm("gizli: true")))  # BOM'lu dosya
        self.assertTrue(tf_bilgi.gizli_girdi_mi(fm("istek:", "  gizli: true")))  # iç içe anahtar: güvenli tarafta kalır
        self.assertFalse(tf_bilgi.gizli_girdi_mi(fm("gizli: false")))
        self.assertFalse(tf_bilgi.gizli_girdi_mi(fm('gizli: "true"')))  # tırnaklı değer: kb.py dogrula zaten HATA verir
        self.assertFalse(tf_bilgi.gizli_girdi_mi("gizli: true\n"))  # frontmatter yok

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
    """Depoya yalnız .kb.json `yazanlar` (ve Slack'teki TF Bilgi botu) yazar. Yazma işleri taslaktan önce durur ve
    belgeyi bota göndermeyi söyler (kişi adı yok); okuma ve yorum çalışır. `yazanlar`'daki biri başkasının alındısını
    onun adına kaydedebilir (onay dosyasında `kaydeden`)."""

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
        self.assertTrue(out.startswith("Senin paylaşımın TF Bilgi köprüsünden gider (depoya köprüyle kütüphaneci "
                                       "yazar). Slack'te TF Bilgi botuna `anahtar` yaz ve gelen satırı terminale "
                                       "yapıştır"), out)
        for parca in ("GitHub hesabının (mert-gh) Teamfluencer-Dev/tf-bilgi deposunda yazma yetkisi yok (depoya yalnız "
                      "`.kb.json` `yazanlar` listesindekiler yazar)", "/bilgi kuyrugum", "/bilgi yorum",
                      "Slack'teki TF Bilgi botuna gönder", "'aldım <kod>'",
                      "ya da depoya yazabilen biriyle paylaş; alındı için ona 'alındı <kod>' yaz, o `/bilgi alindi <kod> "
                      "--kisi <anahtarın>` ile senin adına kaydeder."):
            self.assertIn(parca, out)
        for ad in ("Ayşe", "ayse", "Mert"):  # kişi adı verilmez
            self.assertNotIn(ad, out)
        code, _, _ = self.cli("kb", "son", "--json")
        self.assertEqual(code, 0)
        onay = "onaylar/B-20261029-ayse-01--mert.md"
        (self.kok() / onay).parent.mkdir(parents=True)
        (self.kok() / onay).write_text("---\ngirdi: B-20261029-ayse-01\nkisi: mert\ntarih: 2026-11-05\n---\n")
        before = git(self.bare["ekip"], "rev-parse", "main")
        self.assertIn("TF Bilgi botuna `anahtar` yaz", self.stop("kaydet", "--mesaj", "alindi", onay))
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
        out = self.stop("kb", "alindi", "B-20261029-ayse-01", "--kisi", "ayse")
        self.assertIn("yalnız kendi adınıza", out)
        self.assertIn("TF Bilgi botuna 'aldım <kod>' yazarak ya da depoya yazabilen birine 'alındı <kod>' diye", out)
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
        self.assertIn("Slack'te TF Bilgi botuna `anahtar` yaz", out)
        self.assertIn("deposunda yazma yetkisi yok. Okuma ve yorum çalışmaya devam eder", out)
        self.assertNotIn("yazanlar", out)

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
        self.assertEqual(r["satir"], "dosyalanınca hemen: Ali (Slack), Mert (Slack/mail) · Can'a bildirim gitmez (ekip "
                                     "alanının üyesi değil) · sen (gönderen) bildirim almazsın · Zeynep: kayıtlı kanal "
                                     "yok (Slack kimliği ve e-posta), gönderimde dizinde bulunamazsa hiçbir şey gitmez")
        self.assertEqual([a["durum"] for a in r["alicilar"]], ["simdi", "simdi", "kanal-yok", "alan-disi", "gonderen"])

    def test_yedi_yirmi_dort_sessiz_saat_ozet_ve_sinir_yok(self):
        """0.9.0 (bitiş tasarımı §7): sessiz saat, günlük özet ve günlük anlık sınırı yok; --haber/--adet eski çağrılar
        bozulmasın diye kabul edilir, sonucu değiştirmez."""
        for an in ("2026-11-05T19:30:00+03:00", "2026-11-07T03:00:00+03:00", "2026-11-05T10:00:00+03:00"):
            for ek in ((), ("--haber", "gunluk"), ("--haber", "simdi", "--adet", "9")):
                r = self.plan("--tip", "BILGI", "--kimden", "ali", *ek, an=an)
                self.assertEqual((r["anlik"], r["satir"]), (True, "dosyalanınca hemen: Ali (Slack)"), (an, ek))
                self.assertEqual(set(r), {"anlik", "alicilar", "satir", "notlar"})
        r = self.plan("--tip", "KARAR", "--kimden", "ali", "--son-tarih", "2026-11-20")
        self.assertEqual(r["alicilar"][0]["durum"], "simdi")
        self.assertIn("kimse", self.stop("bildirim-plani", "--tip", "BILGI", "--kimden", "kimse", "--yazar", "ayse"))

    def test_tercih_issueden_okunur(self):
        self.yorum(yorum("ayse-gh", "tercih: kisi=mert kanal=whatsapp"))
        r = self.plan("--tip", "BILGI", "--kimden", "mert", "--haber", "hemen")
        self.assertEqual(r["satir"], "dosyalanınca hemen: Mert (mail) · WhatsApp henüz kapalı → mail")
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
        self.assertIn("(boş)", self.stop("gizli-alicilar", "--kimden", ","))
        self.assertFalse([c for c in self.gh_calls() if c[:2] == ["issue", "comment"]])  # yorum yazmaz
        self.assertEqual(git(self.kok(), "status", "--porcelain"), "")  # klona yazmaz

    def test_kisi_degeri_null_ve_hazirla_once(self):
        kisiler = json.loads(json.dumps(KISILER))
        kisiler["kisiler"]["bos"] = None
        self.seed_commit("ekip", "kisiler.json", json.dumps(kisiler, ensure_ascii=False))
        self.ok("hazirla")
        self.assertIn("kisiler.json'da yok: bos", self.stop("gizli-alicilar", "--kimden", "bos"))  # null kişi değil
        self.assertEqual(self.ok("gizli-alicilar", "--kimden", "ayse")["alicilar"][0]["eposta"], "ayse@ornek.test")
        shutil.rmtree(self.kok())
        self.assertIn("önce `tf_bilgi.py hazirla", self.stop("gizli-alicilar", "--kimden", "ayse"))


YORUM_GIRDI = "B-20261105-ayse-01"
YONETIM_GIRDI = "BY-20261105-ayse-01"
YORUM_GIRDI_METNI = ("---\nid: B-20261105-ayse-01\nbaslik: \"Abonelik planı v2\"\ntur: analiz\nkonu: K-0001\nalan: ekip\n"
                     "hedef_kitle: [dev]\nistek:\n  tip: INCELE\n  kimden: [mert, zeynep]\n  son_tarih: null\n"
                     "tldr: \"Growth 14.990'a çıksın mı? @mert bakmalı.\"\ndurum: yayinda\nyazar: ayse\n"
                     "tarih: 2026-11-05\n---\n**Sonuç:** deneme\n")
GIZLI_GIRDI_METNI = ("---\nid: B-20261105-ayse-02\nbaslik: \"Gizli belge\"\ntur: analiz\nkonu: GIZLI\nalan: ekip\n"
                     "hedef_kitle: [mert]\nistek:\n  tip: BILGI\n  kimden: mert\n  son_tarih: null\n"
                     "tldr: \"Gizli belge; içerik yalnız alıcılarla Drive'da paylaşıldı.\"\ndurum: yayinda\nyazar: ayse\n"
                     "gizli: true\ngizli_link: \"https://drive.google.com/file/d/abc/view\"\nham: null\n"
                     "tarih: 2026-11-05\n---\n**Sonuç:** Gizli belge.\n")
SAYFA_URL = "https://github.com/Teamfluencer-Dev/tf-bilgi/issues/%d"


def gh_issue(no, baslik, acan="ayse-gh", pr=False, aramada_yok=False):
    issue = {"number": no, "title": baslik, "body": "", "state": "open", "comments": 0, "labels": [],
             "user": {"login": acan, "type": "User"}, "html_url": SAYFA_URL % no}
    if pr:
        issue["pull_request"] = {"url": "x"}
    if aramada_yok:
        issue["aramada_yok"] = True  # arama dizini henüz görmedi
    return issue


def gh_yorum(no, login, govde, zaman, tip="User", duzenlendi=None):
    return {"id": no, "user": {"login": login, "type": tip}, "body": govde, "created_at": zaman,
            "updated_at": duzenlendi or zaman, "html_url": "https://github.com/x#issuecomment-%d" % no}


class YorumTest(Base):
    """/bilgi yorum ve /bilgi yorumlar: girdi başına bir GitHub issue (yorum sayfası), ilk yorumda açılır; okuma
    yetkisi yeter, kişinin kendi gh hesabıyla; metin yalnız dosyayla; gizli girdide durur; yönetim girdisi yönetim
    deposunun sayfalarına gider (o depoyu okuyabilene)."""

    def setUp(self):
        super().setUp()
        kisiler = json.loads(json.dumps(KISILER))
        kisiler["kisiler"].update({
            "zeynep": {"ad": "Zeynep Örnek", "alanlar": ["ekip"], "eposta": None, "github": None},
            "can": {"ad": "Can Örnek", "alanlar": ["yonetim"], "eposta": None, "github": "can-gh"}})
        self.seed_commit("ekip", "kisiler.json", json.dumps(kisiler, ensure_ascii=False))
        self.seed_commit("ekip", "girdiler/2026/11/B-20261105-ayse-01.md", YORUM_GIRDI_METNI)
        self.seed_commit("ekip", "girdiler/2026/11/B-20261105-ayse-02.md", GIZLI_GIRDI_METNI)
        os.environ.update({"FAKE_GH_LOGIN": "mert-gh", "FAKE_GH_PUSH": "false",
                           "TF_BILGI_SIMDI": "2026-11-05T10:00:00+03:00"})
        bekleme = mock.patch.object(tf_bilgi, "ARAMA_TEKRAR_BEKLE", 0)
        bekleme.start()
        self.addCleanup(bekleme.stop)
        self.ok("hazirla")
        self.dosya = self.yorum_dosyasi("Bence 14.990 doğru.\nAma yıllıkta indirim şart.")

    def yorum_dosyasi(self, metin, ad="yorum-1"):
        yol = self.cache / "gecici" / ad / "yorum.md"
        yol.parent.mkdir(parents=True, exist_ok=True)
        yol.write_text(metin, encoding="utf-8")
        return str(yol)

    def durum(self):
        return json.loads(self.issues.read_text())

    def issue_ekle(self, *issuelar, yorumlar=None, etiketler=()):
        d = self.durum()
        d["issues"] += list(issuelar)
        d["comments"].update({str(k): v for k, v in (yorumlar or {}).items()})
        d["labels"] += list(etiketler)
        self.issues.write_text(json.dumps(d, ensure_ascii=False))

    def api_cagrilari(self, yontem=None):
        cagrilar = [c for c in self.gh_calls() if c[:1] == ["api"] and c[1:2] != ["user"]]
        return [c for c in cagrilar if yontem is None or (yontem == "POST") == ("POST" in c)]

    def test_plan_salt_okuma_yeni_sayfa_ve_bildirim(self):
        r = self.ok("yorum", YORUM_GIRDI, "--dosya", self.dosya)
        self.assertFalse(r["yazildi"])
        self.assertIsNone(r["sayfa"])
        self.assertEqual(r["yeni_sayfa"]["baslik"], "[B-20261105-ayse-01] Abonelik planı v2")
        self.assertIn("etiketsiz (depoya yazma yetkin yok", r["yeni_sayfa"]["etiket"])
        self.assertEqual(r["ben"], {"login": "mert-gh", "kisi": "mert", "ben": "mert"})
        self.assertEqual([(a["kisi"], a["neden"]) for a in r["alicilar"]], [("ayse", "yazar"), ("zeynep", "alıcı")])
        self.assertEqual(r["bildirim"], "şimdi: Ayşe (yazar), Zeynep (alıcı) (kanal tercihine göre) · bildirim KB "
                                        "deposundaki bildirim iş akışı açıkken gider")
        self.assertEqual(r["karakter"], len("Bence 14.990 doğru.\nAma yıllıkta indirim şart."))
        self.assertEqual(self.api_cagrilari("POST"), [])  # plan hiçbir şey yazmaz
        arama = [c for c in self.api_cagrilari() if "search/issues" in c][0]
        self.assertIn('q=repo:Teamfluencer-Dev/tf-bilgi is:issue in:title "[B-20261105-ayse-01]"', arama)
        os.environ["TF_BILGI_SIMDI"] = "2026-11-07T23:00:00+03:00"  # Cumartesi gecesi: 7/24, sessiz saat yok
        r = self.ok("yorum", YORUM_GIRDI, "--dosya", self.dosya)
        self.assertTrue(r["bildirim"].startswith("şimdi: Ayşe (yazar), Zeynep (alıcı) (kanal tercihine göre)"),
                        r["bildirim"])

    def test_gonder_sayfayi_acar_sonra_ayni_sayfaya_yazar(self):
        r = self.ok("yorum", YORUM_GIRDI, "--dosya", self.dosya, "--gonder")
        self.assertEqual((r["yazildi"], r["yeni_sayfa"], r["sayfa"]["numara"]), (True, True, 20))
        self.assertIn("etiketsiz (depoya yazma yetkin yok", r["etiket"])
        self.assertEqual(r["yorum_url"], "https://github.com/Teamfluencer-Dev/tf-bilgi/issues/20#issuecomment-900")
        d = self.durum()
        issue = d["issues"][0]
        self.assertEqual(issue["title"], "[B-20261105-ayse-01] Abonelik planı v2")
        self.assertEqual(issue["labels"], [])
        self.assertIn("Girdi: https://github.com/Teamfluencer-Dev/tf-bilgi/blob/main/girdiler/2026/11/"
                      "B-20261105-ayse-01.md\nTL;DR: Growth 14.990'a çıksın mı? @​mert bakmalı.", issue["body"])
        self.assertEqual(d["comments"]["20"][0]["body"], "Bence 14.990 doğru.\nAma yıllıkta indirim şart.")
        self.assertEqual(d["comments"]["20"][0]["user"]["login"], "mert-gh")  # kişinin kendi gh hesabı
        self.assertFalse([c for c in self.api_cagrilari("POST") if "labels" in c[-3]])
        # ikinci yorum (ayse, sayfa arama dizininde henüz yok: son issue'lar listesinden bulunur)
        d["issues"][0]["aramada_yok"] = True
        self.issues.write_text(json.dumps(d, ensure_ascii=False))
        os.environ["FAKE_GH_LOGIN"] = "ayse-gh"
        dosya = self.yorum_dosyasi("Yıllık için Can'a soralım.", "yorum-2")
        plan = self.ok("yorum", YORUM_GIRDI, "--dosya", dosya)
        self.assertEqual(plan["sayfa"]["numara"], 20)
        self.assertEqual([(a["kisi"], a["neden"]) for a in plan["alicilar"]],
                         [("mert", "alıcı"), ("zeynep", "alıcı")])  # ayse yazan; mert önceki yorumcu da
        r = self.ok("yorum", YORUM_GIRDI, "--dosya", dosya, "--gonder")
        self.assertEqual((r["yeni_sayfa"], r["etiket"], r["sayfa"]["numara"]), (False, None, 20))
        self.assertEqual(len(self.durum()["issues"]), 1)
        self.assertEqual([y["body"] for y in self.durum()["comments"]["20"]],
                         ["Bence 14.990 doğru.\nAma yıllıkta indirim şart.", "Yıllık için Can'a soralım."])

    def test_yetkisi_olan_etiketi_olusturur_ve_ekler(self):
        os.environ.update({"FAKE_GH_LOGIN": "ayse-gh", "FAKE_GH_PUSH": "true"})
        self.assertIn("`yorum` etiketiyle", self.ok("yorum", YORUM_GIRDI, "--dosya", self.dosya)["yeni_sayfa"]["etiket"])
        r = self.ok("yorum", YORUM_GIRDI, "--dosya", self.dosya, "--gonder")
        self.assertEqual(r["etiket"], "`yorum` etiketi oluşturuldu ve eklendi")
        self.assertEqual(self.durum()["labels"], ["yorum"])
        self.assertEqual(self.durum()["issues"][0]["labels"], [{"name": "yorum"}])
        # etiket varken yeniden oluşturulmaz; oluşturulamazsa sayfa etiketsiz açılır
        self.seed_commit("ekip", "girdiler/2026/11/B-20261105-ayse-03.md",
                         YORUM_GIRDI_METNI.replace("ayse-01", "ayse-03"))
        self.ok("hazirla")
        r = self.ok("yorum", "B-20261105-ayse-03", "--dosya", self.dosya, "--gonder")
        self.assertEqual(r["etiket"], "`yorum` etiketiyle (etiket yoksa oluşturulur)")
        self.assertEqual(len([c for c in self.api_cagrilari("POST") if c[-3].endswith("/labels")]), 1)
        d = self.durum()
        d["labels"] = []
        self.issues.write_text(json.dumps(d))
        self.seed_commit("ekip", "girdiler/2026/11/B-20261105-ayse-04.md",
                         YORUM_GIRDI_METNI.replace("ayse-01", "ayse-04"))
        self.ok("hazirla")
        os.environ["FAKE_GH_ETIKET_CIKIS"] = "1"
        r = self.ok("yorum", "B-20261105-ayse-04", "--dosya", self.dosya, "--gonder")
        self.assertEqual(r["etiket"], "etiketsiz (`yorum` etiketi oluşturulamadı)")
        self.assertEqual(self.durum()["issues"][-1]["labels"], [])

    def test_sayfa_basligi_birebir_denetlenir(self):
        self.issue_ekle(gh_issue(5, "[B-20261105-ayse-011] başka girdi"),
                        gh_issue(6, "Re: [B-20261105-ayse-01] alıntı"),
                        gh_issue(8, "[B-20261105-ayse-01] PR", pr=True),
                        gh_issue(9, "[B-20261105-ayse-01]bitişik"),
                        gh_issue(12, "[B-20261105-ayse-01] ikinci sayfa", acan="ayse-gh"),
                        gh_issue(10, "[B-20261105-ayse-01] Abonelik planı v2", acan="can-gh"),
                        yorumlar={10: [gh_yorum(1, "ayse-gh", "İlk.", "2026-11-05T08:00:00Z"),
                                       gh_yorum(2, "dependabot[bot]", "Bot.", "2026-11-05T08:10:00Z", tip="Bot")],
                                  12: []})
        r = self.ok("yorum", YORUM_GIRDI, "--dosya", self.dosya)
        self.assertEqual(r["sayfa"]["numara"], 10)
        self.assertIsNone(r["yeni_sayfa"])
        self.assertIn("Bu girdinin 2 yorum sayfası var (#10, #12); yorum en eskisine (#10) yazılır.", r["notlar"])
        # sayfayı açan Can (yalnız yönetim) önceki yorumcu: ekip alanından bildirim almaz
        self.assertEqual([(a["kisi"], a["neden"], a["alan_uyesi"]) for a in r["alicilar"]],
                         [("ayse", "yazar", True), ("zeynep", "alıcı", True), ("can", "önceki yorumcu", False)])
        self.assertIn("Can'a bildirim gitmez (ekip alanının üyesi değil)", r["bildirim"])
        self.assertTrue(tf_bilgi.sayfa_basligi_mi("[B-20261105-ayse-01]", YORUM_GIRDI))
        self.assertFalse(tf_bilgi.sayfa_basligi_mi("[B-20261105-ayse-01]x", YORUM_GIRDI))

    def aramalar(self):
        return [c for c in self.api_cagrilari() if "search/issues" in c]

    def test_arama_yanit_vermezse_ikinci_sayfa_acilmaz(self):
        os.environ["FAKE_GH_ARAMA_CIKIS"] = "1"
        self.assertIn("ikinci bir sayfa açmamak için yazmadım",
                      self.stop("yorum", YORUM_GIRDI, "--dosya", self.dosya, "--gonder"))
        self.assertEqual(len(self.aramalar()), 2)  # bir kez daha bakıldı
        self.assertEqual(self.api_cagrilari("POST"), [])
        self.issue_ekle(gh_issue(10, "[B-20261105-ayse-01] Abonelik planı v2"), yorumlar={10: []})
        r = self.ok("yorum", YORUM_GIRDI, "--dosya", self.dosya, "--gonder")  # son issue'larda bulunur
        self.assertEqual((r["sayfa"]["numara"], r["yeni_sayfa"]), (10, False))
        os.environ["FAKE_GH_LISTE_CIKIS"] = "1"
        self.assertIn("Yorum sayfası aranamadı", self.stop("yorumlar", YORUM_GIRDI))  # ikisi de düştü

    def test_liste_yanit_vermezse_yeni_sayfa_acilmaz(self):
        # #10 var ama arama dizini henüz görmedi; son issue listesi düştü
        self.issue_ekle(gh_issue(10, "[B-20261105-ayse-01] Abonelik planı v2", aramada_yok=True), yorumlar={10: []})
        os.environ["FAKE_GH_LISTE_CIKIS"] = "1"
        self.assertIn("ikinci bir sayfa açmamak", self.stop("yorum", YORUM_GIRDI, "--dosya", self.dosya, "--gonder"))
        self.assertEqual(self.api_cagrilari("POST"), [])
        self.assertEqual(len(self.durum()["issues"]), 1)
        # liste düşse de arama sayfayı görüyorsa yorum o sayfaya yazılır
        d = self.durum()
        d["issues"][0].pop("aramada_yok")
        self.issues.write_text(json.dumps(d, ensure_ascii=False))
        r = self.ok("yorum", YORUM_GIRDI, "--dosya", self.dosya, "--gonder")
        self.assertEqual((r["sayfa"]["numara"], r["yeni_sayfa"]), (10, False))

    def test_arama_eksik_donerse_yeni_sayfa_acilmaz(self):
        os.environ["FAKE_GH_ARAMA_EKSIK"] = "1"
        self.assertIn("eksik döndü", self.stop("yorum", YORUM_GIRDI, "--dosya", self.dosya, "--gonder"))
        self.assertEqual(self.durum()["issues"], [])
        self.assertIn("ikinci bir sayfa açmamak", self.stop("yorum", YORUM_GIRDI, "--dosya", self.dosya))  # plan da

    def test_arama_bir_kez_duserse_yeniden_bakar_ve_acar(self):
        d = self.durum()
        d["arama_hata_kalan"] = 1
        self.issues.write_text(json.dumps(d))
        r = self.ok("yorum", YORUM_GIRDI, "--dosya", self.dosya, "--gonder")
        self.assertEqual((r["yeni_sayfa"], r["sayfa"]["numara"]), (True, 20))
        self.assertEqual(len(self.aramalar()), 2)
        self.assertEqual(len(self.durum()["issues"]), 1)

    def test_yazma_reddedilirse(self):
        os.environ["FAKE_GH_YAZ_CIKIS"] = "1"  # sayfa açılamaz (403, issue'lar kapalı)
        out = self.stop("yorum", YORUM_GIRDI, "--dosya", self.dosya, "--gonder")
        self.assertIn("Yorum sayfası açma yapılamadı", out)
        self.assertIn("okuma yetkisi olmalı", out)
        self.assertEqual(self.durum()["issues"], [])
        os.environ.pop("FAKE_GH_YAZ_CIKIS")
        os.environ["FAKE_GH_YORUM_YAZ_CIKIS"] = "1"  # sayfa açılır, yorum yazılamaz (kilitli)
        out = self.stop("yorum", YORUM_GIRDI, "--dosya", self.dosya, "--gonder")
        self.assertIn("Yorum yazma yapılamadı", out)
        self.assertIn("Sayfa kilitliyse yorum yazılamaz", out)
        self.assertEqual(len(self.durum()["issues"]), 1)
        os.environ.pop("FAKE_GH_YORUM_YAZ_CIKIS")
        r = self.ok("yorum", YORUM_GIRDI, "--dosya", self.dosya, "--gonder")  # sonraki çalıştırma aynı sayfayı bulur
        self.assertEqual((r["yeni_sayfa"], r["sayfa"]["numara"]), (False, 20))
        self.assertEqual(len(self.durum()["issues"]), 1)

    def test_okuma_hatasinda_dogru_ipucu(self):
        self.issue_ekle(gh_issue(10, "[B-20261105-ayse-01] Abonelik planı v2"), yorumlar={10: []})
        os.environ["FAKE_GH_SAYFA_OKU_CIKIS"] = "1"
        for argv in (("yorumlar", YORUM_GIRDI), ("yorum", YORUM_GIRDI, "--dosya", self.dosya)):
            out = self.stop(*argv)
            self.assertIn("Yorum sayfası okunamadı", out)
            self.assertIn("yorum için yazma yetkisi gerekmez", out)
            self.assertNotIn("okuma-yazma", out)

    def test_tarama_yapilamazsa_yazmaz(self):
        for metin, cikis in (("TARANAMADI", 5), ("TARA-COKTU", 1)):
            out = self.stop("yorum", YORUM_GIRDI, "--dosya", self.yorum_dosyasi(metin, "t%d" % cikis), "--gonder")
            self.assertIn(f"Yorum taranamadı (kb.py tara çıkış {cikis}); yorumu yazmadım", out)
        self.assertEqual(self.api_cagrilari("POST"), [])

    def test_gizli_girdi_reddedilir_githuba_gidilmez(self):
        out = self.stop("yorum", "B-20261105-ayse-02", "--dosya", self.dosya, "--gonder")
        self.assertIn("B-20261105-ayse-02 gizli bir girdi: yorum yazılmaz", out)
        self.assertIn("Görüşünü göndericiye (Ayşe) doğrudan ilet", out)
        out = self.stop("yorumlar", "B-20261105-ayse-02")
        self.assertIn("herkese açık yorum sayfası yok", out)
        self.assertEqual(self.api_cagrilari(), [])

    def yonetim_girdisi(self):
        kisiler = json.loads(json.dumps(KISILER))
        kisiler["kisiler"]["zeynep"] = {"ad": "Zeynep Örnek", "alanlar": ["ekip"], "eposta": None, "github": None}
        self.seed_commit("yonetim", "kisiler.json", json.dumps(kisiler, ensure_ascii=False))
        metin = YORUM_GIRDI_METNI.replace("B-20261105-ayse-01", YONETIM_GIRDI).replace("alan: ekip", "alan: yonetim")
        self.seed_commit("yonetim", f"girdiler/2026/11/{YONETIM_GIRDI}.md", metin)

    def test_yonetim_girdisi_yonetim_deposunda(self):
        """7 Kas: yönetim deposu (eneskrblt/tf-bilgi-yonetim) GitHub'da. Yönetim girdisinin yorumu o deponun sayfasına
        gider (BY- kimliği ya da --yonetim); ekip deposuna hiçbir şey yazılmaz; alıcı yönetim üyeliğine göre."""
        self.yonetim_girdisi()
        r = self.ok("yorum", YONETIM_GIRDI, "--dosya", self.dosya)  # --yonetim yok: kimlik önekinden
        self.assertEqual((r["alan"], r["depo"], r["yazildi"]), ("yonetim", "eneskrblt/tf-bilgi-yonetim", False))
        self.assertTrue(self.kok("yonetim").is_dir())
        self.assertEqual(r["girdi_url"], "https://github.com/eneskrblt/tf-bilgi-yonetim/blob/main/girdiler/2026/11/"
                                         f"{YONETIM_GIRDI}.md")
        self.assertEqual([(a["kisi"], a["alan_uyesi"]) for a in r["alicilar"]], [("ayse", True), ("zeynep", False)])
        self.assertIn("Zeynep'e bildirim gitmez (yonetim alanının üyesi değil)", r["bildirim"])
        arama = [c for c in self.api_cagrilari() if "search/issues" in c][0]
        self.assertIn(f'q=repo:eneskrblt/tf-bilgi-yonetim is:issue in:title "[{YONETIM_GIRDI}]"', arama)
        r = self.ok("yorum", YONETIM_GIRDI, "--yonetim", "--dosya", self.dosya, "--gonder")
        self.assertTrue(r["yazildi"])
        yazilanlar = [c for c in self.api_cagrilari("POST") if any("/issues" in x for x in c)]
        self.assertTrue(yazilanlar)
        for c in yazilanlar:  # sayfa ve yorum yalnız yönetim deposuna
            self.assertTrue(any(x.startswith("repos/eneskrblt/tf-bilgi-yonetim/issues") for x in c), c)
        y = self.ok("yorumlar", YONETIM_GIRDI, "--yonetim")
        self.assertEqual((y["toplam"], y["yorumlar"][0]["metin"]), (1, "Bence 14.990 doğru.\nAma yıllıkta indirim şart."))
        self.assertIn("yönetim deposunun girdisi değil", self.stop("yorum", YORUM_GIRDI, "--yonetim", "--dosya", self.dosya))
        self.assertIn("bulunamadı", self.stop("yorumlar", "B-20261105-ayse-77"))
        self.assertIn("anlaşılmadı", self.stop("yorumlar", "B-1; rm -rf ~"))

    def test_yonetim_deposuna_erisimi_olmayan(self):
        del os.environ["TF_BILGI_UZAK_YONETIM"]  # varsayılan GitHub deposu; okuma yetkisi yok (repos/<depo> 404)
        self.set_git_config(f"url.{self.bare['yonetim']}.insteadOf", "https://github.com/eneskrblt/tf-bilgi-yonetim.git")
        os.environ["FAKE_GH_REPO_CIKIS"] = "1"  # geçici hata (HTTP 500): "erişimin yok" denmez, tekrar dene denir
        out = self.stop("yorumlar", "BY-20261029-ayse-01")
        self.assertIn("Yönetim deposuna erişimin denetlenemedi", out)
        self.assertNotIn("yalnız yönetim deposuna erişimi olanlar", out)
        self.assertFalse(self.kok("yonetim").exists())
        del os.environ["FAKE_GH_REPO_CIKIS"]
        os.environ["FAKE_GH_REPO_404"] = "1"
        for argv in (("yorum", "BY-20261029-ayse-01", "--dosya", self.dosya, "--gonder"),
                     ("yorum", YORUM_GIRDI, "--yonetim", "--dosya", self.dosya),
                     ("yorumlar", "BY-20261029-ayse-01"), ("yorumlar", YORUM_GIRDI, "--yonetim")):
            self.assertEqual(self.stop(*argv).strip(), "Yönetim yorumları yalnız yönetim deposuna erişimi olanlar içindir.",
                             argv)
        self.assertFalse(self.kok("yonetim").exists())  # klonlanmadı
        self.assertEqual([c for c in self.api_cagrilari() if "issues" in " ".join(c)], [])  # sayfa aranmadı, yazılmadı
        del os.environ["FAKE_GH_REPO_404"]  # erişim gelince aynı varsayılan depodan klonlanır
        self.yonetim_girdisi()
        self.assertEqual(self.ok("yorumlar", YONETIM_GIRDI)["toplam"], 0)
        self.assertTrue(self.kok("yonetim").is_dir())

    def test_kimlik(self):
        os.environ["TF_BILGI_KISI"] = "ayse"  # gh girişi mert-gh
        self.assertIn("Başkası adına paylaşılmaz", self.stop("yorum", YORUM_GIRDI, "--dosya", self.dosya, "--gonder"))
        os.environ.update({"TF_BILGI_KISI": "mert", "FAKE_GH_LOGIN": "baska-gh"})
        self.assertIn("GitHub girişin (baska-gh) kisiler.json'daki hesabınla (mert-gh) aynı değil",
                      self.stop("yorum", YORUM_GIRDI, "--dosya", self.dosya, "--gonder"))
        os.environ["FAKE_GH_LOGIN"] = ""
        self.assertIn("GitHub girişin okunamadı", self.stop("yorum", YORUM_GIRDI, "--dosya", self.dosya))
        self.assertEqual(self.api_cagrilari("POST"), [])
        os.environ.update({"TF_BILGI_KISI": "zeynep", "FAKE_GH_LOGIN": "zeynep-gh"})  # kisiler.json'da github yok
        r = self.ok("yorum", YORUM_GIRDI, "--dosya", self.dosya)
        self.assertEqual(r["ben"], {"login": "zeynep-gh", "kisi": None, "ben": "zeynep"})
        self.assertTrue(any("kisiler.json'da kayıtlı değil" in n for n in r["notlar"]))
        self.assertIn("kendi yorumunun bildirimi sana da gider", r["bildirim"])

    def test_metin_yalniz_dosyadan_taranir_kabuga_girmez(self):
        tehlikeli = "Fiyat 'yüksek'; $(rm -rf ~) `x` \"y\" && echo z\n\nİkinci paragraf."
        dosya = self.yorum_dosyasi(tehlikeli + "\x07", "yorum-3")
        r = self.ok("yorum", YORUM_GIRDI, "--dosya", dosya, "--gonder")
        self.assertEqual(self.durum()["comments"][str(r["sayfa"]["numara"])][0]["body"], tehlikeli)
        for cagri in self.gh_calls():  # metin hiçbir gh argümanında yok: gövde stdin'den
            self.assertFalse(any("rm -rf" in a or "İkinci paragraf" in a for a in cagri), cagri)
        self.assertIn("geçici klasörünün altında", self.stop("yorum", YORUM_GIRDI, "--dosya", str(self.tmp / "x.md")))
        self.assertIn("Yorum boş", self.stop("yorum", YORUM_GIRDI, "--dosya", self.yorum_dosyasi(" \n\t", "bos")))
        self.assertIn("Yorum çok uzun", self.stop("yorum", YORUM_GIRDI, "--dosya",
                                                  self.yorum_dosyasi("a" * 10001, "uzun")))
        once = len(self.api_cagrilari("POST"))
        out = self.stop("yorum", YORUM_GIRDI, "--dosya", self.yorum_dosyasi("anahtar GIZLI-ANAHTAR-123", "sir"),
                        "--gonder")
        self.assertIn("Yorumda sır ya da kişisel veri olabilir (sir); yorumu yazmadım", out)
        self.assertNotIn("GIZLI-ANAHTAR-123", out)
        self.assertEqual(len(self.api_cagrilari("POST")), once)

    def test_yorumlar_birden_cok_sayfa_birlesir(self):
        self.issue_ekle(gh_issue(12, "[B-20261105-ayse-01] ikinci sayfa"), gh_issue(10, "[B-20261105-ayse-01] ilk"),
                        yorumlar={10: [gh_yorum(1, "ayse-gh", "A1", "2026-11-05T06:00:00Z"),
                                       gh_yorum(3, "ayse-gh", "A3", "2026-11-05T08:00:00Z")],
                                  12: [gh_yorum(2, "mert-gh", "B2", "2026-11-05T07:00:00Z")]})
        r = self.ok("yorumlar", YORUM_GIRDI)
        self.assertEqual([(y["metin"], y["sayfa"]) for y in r["yorumlar"]], [("A1", 10), ("B2", 12), ("A3", 10)])
        self.assertEqual([s["numara"] for s in r["sayfalar"]], [10, 12])
        self.assertEqual(r["sayfa"]["numara"], 10)
        self.assertIn("Bu girdinin 2 yorum sayfası var; hepsinin yorumları birlikte gösterildi, yeni yorum #10'e yazılır.",
                      r["notlar"])

    def test_yorumlar_eskiden_yeniye_adlarla(self):
        self.assertEqual(self.ok("yorumlar", YORUM_GIRDI)["satir"],
                         "Henüz yorum yok. Yazmak için: /bilgi yorum B-20261105-ayse-01 <yorumun>")
        self.issue_ekle(gh_issue(10, "[B-20261105-ayse-01] Abonelik planı v2"), yorumlar={10: [
            gh_yorum(3, "mert-gh", "Üçüncü.", "2026-11-05T09:00:00Z", duzenlendi="2026-11-05T09:05:00Z"),
            gh_yorum(1, "AYSE-GH", "Birinci.", "2026-11-04T17:00:00Z"),
            gh_yorum(2, "yabanci", "İkinci.", "2026-11-05T06:00:00Z"),
            gh_yorum(4, "dependabot[bot]", "Bot.", "2026-11-05T09:10:00Z", tip="Bot")]})
        r = self.ok("yorumlar", YORUM_GIRDI)
        self.assertEqual(r["sayfa"]["url"], SAYFA_URL % 10)
        self.assertEqual([(y["ad"], y["tarih"], y["duzenlendi"], y["bot"]) for y in r["yorumlar"]],
                         [("Ayşe", "4 Kas Çar 20:00", False, False), ("yabanci", "5 Kas Per 09:00", False, False),
                          ("Mert", "5 Kas Per 12:00", True, False), ("dependabot[bot]", "5 Kas Per 12:10", False, True)])
        self.assertEqual((r["toplam"], r["onceki"], r["satir"]), (4, 0, ""))
        r = self.ok("yorumlar", YORUM_GIRDI, "--son", "2")
        self.assertEqual(([y["metin"] for y in r["yorumlar"]], r["onceki"]), (["Üçüncü.", "Bot."], 2))
        self.assertEqual(self.api_cagrilari("POST"), [])
        self.assertEqual(git(self.kok(), "status", "--porcelain"), "")  # klona yazmaz


KOPRU_GIZLI = "0123456789abcdef" * 4
KOPRU_DAGITIM = "AKfycbSahteDagitim_0123-456789"
KOPRU_ANAHTAR = f"tfb1.{KOPRU_DAGITIM}.{KOPRU_GIZLI}"


class KopruRet(Exception):
    """Sahte köprünün işlem içinden reddi: (hata, kod)."""


class SahteKopru:
    """Köprü sözleşmesi v1'in sahte karşılığı (ağ yok): tf_bilgi.kopru_tasi yerine çağrılır."""

    def __init__(self, dosyalar):
        self.dosyalar = dict(dosyalar)
        self.cagrilar, self.adresler = [], []
        self.kayitlar = {}
        self.hatalar = {}        # islem → (hata, kod): köprünün reddi
        self.kopuk = {}          # islem → kaç kez bağlantı hatası
        self.ozel = {}           # islem → yanıt sözlüğü
        self.kayip = {}          # islem → kaç kez: köprü işler ama yanıt istemciye ulaşmaz (bağlantı kopar)
        self.eski_bitir = False  # eski köprü: ikinci bitir "zaten tamamlandı" (durum) der
        self.parca_bayt = 5

    def islemler(self, ad=None):
        return [c for c in self.cagrilar if ad is None or c["islem"] == ad]

    def __call__(self, adres, veri, zaman_asimi):
        govde = json.loads(veri.decode("utf-8"))
        self.adresler.append(adres)
        self.cagrilar.append(govde)
        islem = govde["islem"]
        if self.kopuk.get(islem):
            self.kopuk[islem] -= 1
            raise tf_bilgi.urllib.error.URLError("bağlantı koptu")
        if govde.get("anahtar") != KOPRU_GIZLI or govde.get("s") != 1:
            return self.yanit({"tamam": False, "hata": "Anahtar tanınmadı.", "kod": "anahtar"})
        if islem in self.hatalar:
            hata, kod = self.hatalar[islem]
            return self.yanit({"tamam": False, "hata": hata, "kod": kod})
        if islem in self.ozel:
            return self.yanit({"tamam": True, **self.ozel[islem]})
        try:
            yanit = {"tamam": True, **getattr(self, "i_" + islem.replace("-", "_"))(govde)}
        except KopruRet as e:
            yanit = {"tamam": False, "hata": e.args[0], "kod": e.args[1]}
        if self.kayip.get(islem):
            self.kayip[islem] -= 1
            raise tf_bilgi.urllib.error.URLError("yanıt yolda kayboldu")
        return self.yanit(yanit)

    @staticmethod
    def yanit(veri):
        return json.dumps(veri, ensure_ascii=False).encode("utf-8")

    def i_kim(self, g):
        return {"kisi": "mert", "ad": "Mert Örnek", "depo": "Teamfluencer-Dev/tf-bilgi", "surum": "1",
                "kopru_github": "kopru-bot", "sinirlar": {"parca_bayt": self.parca_bayt}}

    def i_oku(self, g):
        sonuc = []
        for yol in g["yollar"]:
            if yol.endswith("-02.md") and yol.startswith("girdiler/"):
                sonuc.append({"yol": yol, "icerik": None, "gizli": True, "hata": "gizli",
                              "mesaj": "B-20261105-ayse-02 gizli bir belge; yalnız alıcıları görür."})
            elif yol in self.dosyalar:
                sonuc.append({"yol": yol, "icerik": self.dosyalar[yol]})
            else:
                sonuc.append({"yol": yol, "icerik": None, "hata": "yok", "mesaj": f"{yol} bulunamadı."})
        return {"dosyalar": sonuc}

    def i_baslat(self, g):
        kod = "G-abc%03d" % len(self.kayitlar)
        self.kayitlar[kod] = {"taslak": g["taslak"], "beyan": {d["ad"]: d for d in g["dosyalar"]},
                              "veri": {d["ad"]: b"" for d in g["dosyalar"]}, "sira": {}, "bitti": False}
        return {"kod": kod, "kayit": f"20261105-101500-mert-{kod[2:]}", "parca_bayt": self.parca_bayt}

    def i_parca(self, g):
        k = self.kayitlar[g["kod"]]
        beklenen = k["sira"].get(g["ad"], 0)
        if g["sira"] < beklenen:
            return {"kod": g["kod"], "ad": g["ad"], "sira": g["sira"], "alinan": len(k["veri"][g["ad"]]), "bitti": False}
        assert g["sira"] == beklenen, "sıra dışı parça"
        k["veri"][g["ad"]] += base64.b64decode(g["veri"])
        k["sira"][g["ad"]] = beklenen + 1
        return {"kod": g["kod"], "ad": g["ad"], "sira": g["sira"], "alinan": len(k["veri"][g["ad"]])}

    def i_bitir(self, g):
        k = self.kayitlar[g["kod"]]
        if k["bitti"]:  # köprü gibi: ikinci bitir aynı yanıt (idempotent); eski köprü "zaten tamamlandı" derdi
            if self.eski_bitir:
                raise KopruRet(g["kod"] + " zaten tamamlandı.", "durum")
            return {"kod": g["kod"], "kayit": "kayit", "dosyalar": list(k["beyan"]), "dosyalama": "yarın 09:05",
                    "tekrar": True}
        for ad, beyan in k["beyan"].items():
            assert hashlib.sha256(k["veri"][ad]).hexdigest() == beyan["sha256"], ad
            assert len(k["veri"][ad]) == beyan["boyut"], ad
        k["bitti"] = True
        return {"kod": g["kod"], "kayit": "kayit", "dosyalar": list(k["beyan"]), "dosyalama": "yarın 09:05"}

    def i_geri_al(self, g):
        bitti = g["hedef"] in self.kayitlar and self.kayitlar[g["hedef"]]["bitti"]
        if g["hedef"] in self.kayitlar and not bitti:
            return {"sonuc": "durduruldu", "hedef": g["hedef"]}
        return {"sonuc": "kaydedildi", "hedef": g["hedef"], "kod": "G-zzz999", "kayit": "k", "dosyalama": "bugün 15:05"}

    def i_alindi(self, g):
        return {"kod": "G-alnd01", "kayit": "k", "dosyalama": "bugün 11:05"}

    def i_ara(self, g):
        return {"kaynak": "github-arama", "toplam": 1, "sonuclar": [{"id": "B-20261029-ayse-01", "baslik": "Deneme",
                                                                    "tldr": "Kısa özet.", "gizli": False}]}

    def i_tercih(self, g):
        if g.get("kanal"):
            return {"yazildi": True, "kisi": "mert", "kanallar": g["kanal"].split(","),
                    "satir": "tercih: kisi=mert kanal=" + g["kanal"], "url": "https://github.com/x#issuecomment-5"}
        return {"kisi": "mert", "kanallar": ["mail"], "varsayilan": False, "kaynak": "yorum 2026-11-05 · kopru-bot",
                "issue": "https://github.com/Teamfluencer-Dev/tf-bilgi/issues/7"}

    def i_yorum(self, g):
        if g["gonder"]:
            return {"yazildi": True, "sayfa": {"numara": 31, "url": SAYFA_URL % 31}, "yeni_sayfa": True,
                    "yorum_url": SAYFA_URL % 31 + "#issuecomment-1"}
        return {"girdi": {"id": g["girdi"], "baslik": "Abonelik planı v2", "url": "https://github.com/x/girdi",
                          "yazar": "ayse", "kimden": ["mert", "zeynep"], "alan": "ekip"},
                "sayfa": None, "sayfa_sayisi": 0, "onceki": ["can", "yabanci-gh"]}

    def i_yorumlar(self, g):
        return {"girdi": g["girdi"], "baslik": "Abonelik planı v2", "girdi_url": "u",
                "sayfa": {"numara": 31, "url": SAYFA_URL % 31}, "sayfalar": [{"numara": 31, "url": SAYFA_URL % 31}],
                "toplam": 2, "onceki": 0, "notlar": [],
                "yorumlar": [{"sayfa": 31, "kisi": "ayse", "ad": "Ayşe", "login": "kopru-bot", "bot": False,
                              "kopru": True, "zaman": "2026-11-04T17:00:00Z", "duzenlendi": False, "metin": "Birinci.",
                              "url": "u1"},
                             {"sayfa": 31, "kisi": None, "ad": None, "login": "yabanci", "bot": False, "kopru": False,
                              "zaman": "2026-11-05T06:00:00Z", "duzenlendi": False, "metin": "İkinci.", "url": "u2"}]}


class KopruTest(Base):
    """Köprü yolu (0.6.0): anahtar dosyası varsa paylaşım ve okuma GitHub'sız, köprü üzerinden."""

    def setUp(self):
        super().setUp()
        kisiler = json.loads(json.dumps(KISILER))
        kisiler["kisiler"].update({"zeynep": {"ad": "Zeynep Örnek", "alanlar": ["ekip"], "eposta": None, "github": None},
                                   "can": {"ad": "Can Örnek", "alanlar": ["ekip"], "eposta": None, "github": "can-gh"}})
        self.kopru = SahteKopru({
            ".kb.json": json.dumps({"alan": "ekip", "girdi_onek": "B", "uzak": "Teamfluencer-Dev/tf-bilgi",
                                    "yazanlar": ["ayse"], "tercih_issue": 7, "kontrol_kisi": "ayse"}),
            "kisiler.json": json.dumps(kisiler, ensure_ascii=False), "projeler.json": '{"projeler": {}}',
            "KONULAR.md": "# Konular\n", "araclar/kb.py": STUB_KB, "sablonlar/analiz.md": "**Sonuç:** {{x}}\n",
            "SON.md": "# Son\n- B-20261029-ayse-01\n",
            "girdiler/2026/10/B-20261029-ayse-01.md": girdi_metni("B-20261029-ayse-01")})
        tasi = mock.patch.object(tf_bilgi, "kopru_tasi", self.kopru)
        tasi.start()
        self.addCleanup(tasi.stop)
        bekle = mock.patch.object(tf_bilgi, "KOPRU_BEKLE", 0)
        bekle.start()
        self.addCleanup(bekle.stop)
        self.cache.mkdir(parents=True, exist_ok=True)
        (self.cache / "anahtar").write_text(KOPRU_ANAHTAR + "\n")
        self.gecici = self.cache / "gecici" / "paylas-1"
        self.gecici.mkdir(parents=True)

    def dosya(self, ad, metin, yer=None):
        yol = (yer or self.gecici) / ad
        yol.write_text(metin, encoding="utf-8")
        return str(yol)

    def taslak(self, **alanlar):
        veri = {"tur": "analiz", "baslik": "Abonelik ×3 özeti", "tldr": "Kısa.", "konu_onerisi": "AYIKLA",
                "istek": {"tip": "BILGI", "kimden": ["ayse"], "son_tarih": None}, "haber": "hemen",
                "hedef_kitle": ["dev"], "uretim": "claude"}
        veri.update(alanlar)
        return self.dosya("taslak.json", json.dumps(veri, ensure_ascii=False))

    def hazir(self):
        return self.ok("hazirla", "--yazma")

    def test_yol_secimi(self):
        self.assertEqual(tf_bilgi.yol_sec(), "kopru")
        os.environ["TF_BILGI_YOL"] = "dogrudan"
        self.assertEqual(tf_bilgi.yol_sec(), "dogrudan")
        os.environ["TF_BILGI_YOL"] = "bilmem"
        self.assertIn("TF_BILGI_YOL anlaşılmadı", self.stop("hazirla"))
        os.environ["TF_BILGI_YOL"] = "kopru"
        (self.cache / "anahtar").unlink()
        self.assertIn("Köprü anahtarın yok", self.stop("hazirla"))
        del os.environ["TF_BILGI_YOL"]
        self.assertEqual(tf_bilgi.yol_sec(), "dogrudan")
        (self.cache / "anahtar").write_text("tfb1.kisa.abc\n")
        os.environ["TF_BILGI_YOL"] = "kopru"
        self.assertIn("Köprü anahtarı bozuk", self.stop("hazirla"))

    def test_kur_dosyadan_dogrular_kaydeder_ve_siler(self):
        (self.cache / "anahtar").unlink()
        durum = self.ok("kur")
        self.assertEqual((durum["anahtar"], durum["dosya_yeri"]), (False, str(self.cache / "gecici" / "anahtar.txt")))
        f = self.dosya("anahtar.txt", f"Anahtarın: {KOPRU_ANAHTAR}  (kimseyle paylaşma)\n", self.cache / "gecici")
        code, out = self.run_main("kur", "--dosya", f)
        self.assertEqual(code, 0, out)
        self.assertNotIn(KOPRU_GIZLI, out)
        r = json.loads(out)
        self.assertEqual((r["kuruldu"], r["kisi"], r["yol"]), (True, "mert", "kopru"))
        anahtar = self.cache / "anahtar"
        self.assertEqual(anahtar.read_text(), KOPRU_ANAHTAR + "\n")
        self.assertEqual(anahtar.stat().st_mode & 0o777, 0o600)
        self.assertFalse(Path(f).exists())  # anahtar geçici dosyada kalmaz
        self.assertEqual(self.kopru.adresler[-1], f"https://script.google.com/macros/s/{KOPRU_DAGITIM}/exec")
        self.assertNotIn(KOPRU_GIZLI, self.kopru.adresler[-1])  # gizli kısım adreste değil, gövdede
        self.assertTrue(self.ok("kur")["anahtar"])
        self.assertTrue(self.ok("kur", "--sil")["silindi"])
        self.assertFalse(anahtar.exists())

    def test_kur_reddedince_kaydetmez_dosyayi_siler(self):
        (self.cache / "anahtar").unlink()
        f = self.dosya("anahtar.txt", "merhaba", self.cache / "gecici")
        self.assertIn("köprü anahtarı değil", self.stop("kur", "--dosya", f))
        self.assertFalse(Path(f).exists())
        baska = "tfb1.%s.%s" % (KOPRU_DAGITIM, "f" * 64)
        f = self.dosya("anahtar.txt", baska, self.cache / "gecici")
        out = self.stop("kur", "--dosya", f)
        self.assertIn("Anahtar tanınmadı.", out)
        self.assertNotIn("f" * 64, out)
        self.assertFalse(Path(f).exists())
        self.assertFalse((self.cache / "anahtar").exists())
        dis = self.tmp / "anahtar.txt"
        dis.write_text(KOPRU_ANAHTAR)
        self.assertIn("geçici klasörünün altında", self.stop("kur", "--dosya", str(dis)))

    def test_hazirla_aynayi_kurar_github_istemez(self):
        os.environ["TF_BILGI_SIMDI"] = "2026-11-07T11:00:00+03:00"  # Cumartesi
        r = self.hazir()
        ayna = self.cache / "kopru"
        self.assertEqual((r["yol"], r["kok"], r["kisi"], r["alan"], r["kisi_kaynagi"]),
                         ("kopru", str(ayna), "mert", "ekip", "kopru"))
        self.assertFalse({"sessiz", "sessiz_neden", "saat", "ozet_zamani"} & set(r))  # 7/24: mesai bilgisi yok
        self.assertEqual(r["kopru"]["sinirlar"]["parca_bayt"], 5)
        for rel in (".kb.json", "kisiler.json", "KONULAR.md", "araclar/kb.py", "sablonlar/analiz.md", ".kopru.json"):
            self.assertTrue((ayna / rel).is_file(), rel)
        self.assertEqual(hashlib.sha256((ayna / "araclar/kb.py").read_bytes()).hexdigest(), STUB_SHA256)
        self.assertTrue(any("şablonları vermedi" in n for n in r["notlar"]))
        self.assertEqual(self.gh_calls(), [])                      # GitHub'a hiç gidilmedi
        self.assertFalse(self.kok().exists())                      # git klonu yok
        self.assertNotIn(KOPRU_GIZLI, json.dumps(r))
        os.environ["TF_BILGI_KISI"] = "ayse"
        self.assertIn("köprü anahtarın 'mert' kişisine ait", self.stop("hazirla"))
        del os.environ["TF_BILGI_KISI"]
        self.assertIn("Yönetim belgeleri köprüden okunmaz", self.stop("hazirla", "--yonetim"))

    def test_hazirla_onaysiz_kb_py_calistirmaz(self):
        self.kopru.dosyalar["araclar/kb.py"] = STUB_KB + "# değişti\n"
        self.assertIn("eklentinin onayladığı sürüm değil", self.stop("hazirla"))
        del self.kopru.dosyalar["kisiler.json"]
        self.assertIn("kisiler.json dosyasını vermedi", self.stop("hazirla"))

    def test_kb_yalniz_izinli_komutlar_aynada(self):
        self.hazir()
        code, out, _ = self.cli("kb", "eslestir", "--metin", "x", "--json")
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads(out)["kok"], str(self.cache / "kopru"))
        for argv in (("kb", "son", "--json"), ("kb", "alindi", "B-1", "--kisi", "mert"), ("kb", "kaydet", "--mesaj", "x")):
            self.assertEqual(self.cli(*argv)[0], 2, argv)
        self.assertIn("Yönetim belgeleri köprüden okunmaz", self.stop("kb", "--yonetim", "tara", "/x"))

    def test_gonder_parcali_yukler_ve_tek_satir_makbuz(self):
        self.hazir()
        ek = self.tmp / "Çalışma Notu.md"
        ek.write_text("Rapor içeriği, beş bayttan uzun.", encoding="utf-8")
        r = self.ok("gonder", "--taslak", self.taslak(), "--metin", self.dosya("taslak.md", "**Sonuç:** x\n"),
                    "--govde", self.dosya("govde.md", "Ayşe'ye bilgi"), "--ek", str(ek))
        self.assertEqual(r["kod"], "G-abc000")
        self.assertEqual(r["satir"], 'Gönderildi: G-abc000 · "Abonelik ×3 özeti" → Ayşe (haber dosyalanınca gider) · '
                                     "kütüphaneci yarın 09:05 turunda dosyalar · geri almak için: /paylas geri-al G-abc000")
        kayit = self.kopru.kayitlar["G-abc000"]
        self.assertTrue(kayit["bitti"])
        self.assertEqual(list(kayit["veri"]), ["taslak.md", "govde.md", "Calisma-Notu.md"])
        self.assertEqual(kayit["veri"]["Calisma-Notu.md"], ek.read_bytes())
        self.assertGreater(len(self.kopru.islemler("parca")), 5)  # 5 baytlık parçalar
        t = kayit["taslak"]
        self.assertEqual((t["kisisel_veri"], t["haber"], t["istek"]["kimden"], t["gizli"], t["gizli_link"]),
                         (False, "hemen", ["ayse"], False, None))
        self.assertEqual(set(t), set(tf_bilgi.TASLAK_ANAHTARLARI))  # her anahtar var
        self.assertNotIn(KOPRU_GIZLI, json.dumps(r))

    def test_gonder_sir_ve_taranamayan_dosya_engellemez(self):
        """7 Kas kararı: sır, taranamayan dosya ve tarama hatası paylaşımı durdurmaz (özel depo, iç kullanım)."""
        self.hazir()
        ek = self.tmp / "rapor.md"
        ek.write_text("token GIZLI-ANAHTAR-123", encoding="utf-8")
        r = self.ok("gonder", "--taslak", self.taslak(), "--metin", self.dosya("taslak.md", "x"), "--ek", str(ek))
        self.assertEqual(self.kopru.kayitlar[r["kod"]]["veri"]["rapor.md"], b"token GIZLI-ANAHTAR-123")
        self.ok("gonder", "--taslak", self.taslak(tldr="GIZLI-ANAHTAR-1"), "--metin", self.dosya("taslak.md", "x"))
        for icerik in ("TARANAMADI", "TARA-COKTU"):
            ek.write_text(icerik, encoding="utf-8")
            r = self.ok("gonder", "--taslak", self.taslak(), "--metin", self.dosya("taslak.md", "x"), "--ek", str(ek))
            self.assertTrue(self.kopru.kayitlar[r["kod"]]["bitti"], icerik)
        self.assertEqual(len(self.kopru.islemler("baslat")), 4)

    def test_gonder_kisisel_veri_etiketlenir_engellenmez(self):
        self.hazir()
        r = self.ok("gonder", "--taslak", self.taslak(istek=None, haber=None),
                    "--metin", self.dosya("taslak.md", "Müşteri tel KISISEL-VERI"))
        self.assertTrue(r["kisisel_veri"])
        self.assertTrue(self.kopru.kayitlar[r["kod"]]["taslak"]["kisisel_veri"])
        self.assertIn("→ bildirimsiz · kişisel veri var (etiketlendi)", r["satir"])
        self.assertEqual(self.kopru.kayitlar[r["kod"]]["veri"]["taslak.md"], "Müşteri tel KISISEL-VERI".encode())

    def test_gonder_gizli_dosyasiz_belge_okunmaz(self):
        self.hazir()
        gizli = dict(tur="analiz", baslik="", tldr="", konu_onerisi="GIZLI", gizli=True,
                     gizli_link="https://drive.google.com/file/d/abc/view", hedef_kitle=["ayse"])
        belge = self.tmp / "gizli.pdf"
        belge.write_text("GIZLI-ANAHTAR-123")
        out = self.stop("gonder", "--taslak", self.taslak(**gizli), "--ek", str(belge))
        self.assertIn("Gizli paylaşımda belge, gövde ya da not gönderilmez", out)
        r = self.ok("gonder", "--taslak", self.taslak(**gizli))
        self.assertIn('"Gizli belge" → Ayşe (haber dosyalanınca gider) · gizli: içerik depoya girmez', r["satir"])
        self.assertEqual(self.kopru.islemler("baslat")[-1]["dosyalar"], [])
        self.assertIn("tldr boş olmalı", self.stop("gonder", "--taslak", self.taslak(**{**gizli, "tldr": "özet"})))
        self.assertIn("gizli_link", self.stop("gonder", "--taslak", self.taslak(**{**gizli, "gizli_link": "http://x"})))

    def test_taslak_dogrulama(self):
        self.hazir()
        metin = self.dosya("taslak.md", "x")
        for alanlar, parca in (({"tur": "rapor"}, "tur geçersiz"),
                               ({"istek": {"tip": "BILGI", "kimden": ["kimse"]}}, "kisiler.json'da yok: kimse"),
                               ({"istek": None}, "haber yalnız istek varken"),
                               ({"gecersiz_kildigi": ["B-20261029-ayse-01"]}, "yalnız kendi girdilerinin"),
                               ({"konu_onerisi": "K-12"}, "konu_onerisi geçersiz"),
                               ({"baslik": "x" * 121}, "baslik en çok 120")):
            out = self.stop("gonder", "--taslak", self.taslak(**alanlar), "--metin", metin)
            self.assertIn(parca, out, alanlar)
        self.assertIn("girdi gövdesi", self.stop("gonder", "--taslak", self.taslak()).lower())
        dis = self.tmp / "taslak.json"
        dis.write_text("{}")
        self.assertIn("geçici klasörünün altında", self.stop("gonder", "--taslak", str(dis), "--metin", metin))
        self.assertEqual(self.kopru.islemler("baslat"), [])

    def test_gonder_yarida_kalirsa_kaydi_durdurur_baglanti_hatasini_yeniden_dener(self):
        self.hazir()
        self.kopru.kopuk["parca"] = 1  # ilk parça bir kez kopar, yeniden denenir
        r = self.ok("gonder", "--taslak", self.taslak(), "--metin", self.dosya("taslak.md", "kısa"))
        self.assertTrue(self.kopru.kayitlar[r["kod"]]["bitti"])
        self.kopru.hatalar["bitir"] = ("Dosya eksik geldi.", "durum")
        out = self.stop("gonder", "--taslak", self.taslak(), "--metin", self.dosya("taslak.md", "kısa"))
        self.assertIn("Gönderim yarıda kaldı: Dosya eksik geldi. — kaydı durdurdum (G-abc001)", out)
        self.assertEqual(self.kopru.islemler("geri-al")[-1]["hedef"], "G-abc001")

    def test_geri_al(self):
        r = self.ok("geri-al", "G-abc123")
        self.assertIn("Geri alma isteği kaydedildi: G-abc123 · kütüphaneci bugün 15:05 turunda işler", r["satir"])
        self.assertIn("anlaşılmadı", self.stop("geri-al", "G-1; rm -rf ~"))
        os.environ["TF_BILGI_YOL"] = "dogrudan"  # doğrudan yolu seçen yazan da kendi girdisini köprüyle geri alır
        self.assertEqual(self.ok("geri-al", "B-20261105-mert-01")["sonuc"], "kaydedildi")
        (self.cache / "anahtar").unlink()
        # G- kodu: gh kurulu ama oturum kapalı ve anahtar yok → hizli ile aynı: oturum mesajı (yazanın kodu olabilir)
        self.assertIn("GitHub oturumun kapalı ya da bağlantı yok", self.stop("geri-al", "G-abc123"))
        with mock.patch.object(tf_bilgi, "which", lambda ad: None if ad == "gh" else shutil.which(ad)):
            self.assertIn("köprü anahtarın yok", self.stop("geri-al", "G-abc123"))  # gh hiç yok: köprü mesajı
        self.assertIn("köprü anahtarın yok", self.stop("geri-al", "B-20261105-mert-01"))  # girdi kimliği: yalnız köprü
        # anahtarsız doğrudan yolda makbuz geri-al vaat etmez: hazirla geri_al=false (KopruDogrudanYolTest, hijyen testi)

    def test_okuma_ara_girdi_alindi(self):
        self.hazir()
        self.assertEqual(self.ok("oku", "SON.md")["dosyalar"][0]["icerik"], "# Son\n- B-20261029-ayse-01\n")
        self.assertIn("Geçersiz yol", self.stop("oku", "../x"))
        g = self.ok("girdi", "B-20261105-ayse-02")
        self.assertEqual((g["gizli"], g["icerik"]), (True, None))
        self.assertIn("yalnız alıcıları görür", g["mesaj"])
        self.assertIn("id: B-20261029-ayse-01", self.ok("girdi", "B-20261029-ayse-01")["icerik"])
        self.assertIn("bulunamadı", self.stop("girdi", "B-20261029-ayse-09"))
        self.assertEqual(self.ok("ara", "abonelik", "planı")["sonuclar"][0]["id"], "B-20261029-ayse-01")
        self.assertEqual(self.kopru.islemler("ara")[-1]["sorgu"], "abonelik planı")
        self.assertIn("Alındın gönderildi: B-20261029-ayse-01 · kütüphaneci bugün 11:05",
                      self.ok("alindi", "B-20261029-ayse-01")["satir"])
        self.kopru.hatalar["alindi"] = ("Bu belgenin alıcısı değilsin.", "alici")
        self.assertIn("alıcısı değilsin", self.stop("alindi", "B-20261029-ayse-01"))
        (self.cache / "anahtar").unlink()
        self.assertIn("köprü yolunda çalışır", self.stop("oku", "SON.md"))
        self.assertIn("köprü yolunda çalışır", self.stop("alindi", "B-20261029-ayse-01"))

    def test_yorum_koprude_once_yerel_tarama_sonra_kopru(self):
        self.hazir()
        os.environ["TF_BILGI_SIMDI"] = "2026-11-05T10:00:00+03:00"
        dosya = self.dosya("yorum.md", "Bence 14.990 doğru.")
        r = self.ok("yorum", "B-20261105-ayse-01", "--dosya", dosya)
        self.assertEqual([(a["kisi"], a["neden"]) for a in r["alicilar"]],
                         [("ayse", "yazar"), ("zeynep", "alıcı"), ("can", "önceki yorumcu")])  # mert kendisi
        self.assertFalse(r["yazildi"])
        self.assertEqual(r["yeni_sayfa"]["baslik"], "[B-20261105-ayse-01] Abonelik planı v2")
        r = self.ok("yorum", "B-20261105-ayse-01", "--dosya", dosya, "--gonder")
        self.assertEqual((r["yazildi"], r["yeni_sayfa"], r["sayfa"]["numara"]), (True, True, 31))
        self.assertEqual(self.kopru.islemler("yorum")[-1]["metin"], "Bence 14.990 doğru.")
        once = len(self.kopru.islemler("yorum"))
        out = self.stop("yorum", "B-20261105-ayse-01", "--dosya", self.dosya("sir.md", "GIZLI-ANAHTAR-123"), "--gonder")
        self.assertIn("Yorumda sır ya da kişisel veri olabilir", out)
        self.assertEqual(len(self.kopru.islemler("yorum")), once)  # metin makineden çıkmadı
        for argv in (("yorum", "BY-20261105-ayse-01", "--dosya", dosya), ("yorum", YORUM_GIRDI, "--yonetim", "--dosya", dosya)):
            self.assertIn("Yönetim yorumları yalnız yönetim deposuna erişimi olanlar içindir.", self.stop(*argv))
        self.kopru.hatalar["yorum"] = ("B-20261105-ayse-02 gizli bir girdi: yorum yazılmaz.", "gizli")
        self.assertIn("gizli bir girdi", self.stop("yorum", "B-20261105-ayse-02", "--dosya", dosya))

    def test_yorumlar_ve_tercih_koprude(self):
        self.hazir()
        r = self.ok("yorumlar", "B-20261105-ayse-01")
        self.assertEqual([(y["ad"], y["tarih"], y["kopru"]) for y in r["yorumlar"]],
                         [("Ayşe", "4 Kas Çar 20:00", True), ("yabanci", "5 Kas Per 09:00", False)])
        t = self.ok("tercih")
        self.assertEqual((t["kanallar"], t["varsayilan"], t["yol"]), (["mail"], False, "kopru"))
        self.assertEqual(t["cozum"]["mail"], "e-posta kayıtlı")
        t = self.ok("tercih", "--kanal", "Slack,mail")
        self.assertEqual((t["satir"], t["kanallar"]), ("tercih: kisi=mert kanal=slack,mail", ["slack", "mail"]))
        self.assertEqual(self.kopru.islemler("tercih")[-1]["kanal"], "slack,mail")
        self.assertIn("yalnız kendi adına", self.stop("tercih", "--kisi", "ayse", "--kanal", "mail"))
        self.assertIn("Kanal anlaşılmadı", self.stop("tercih", "--kanal", "faks"))
        self.assertEqual(self.gh_calls(), [])

    def test_kopru_yaniti_bozuksa_ya_da_http_hatasi(self):
        self.assertTrue(self.ok("kur")["gecerli"])
        f = lambda: self.dosya("anahtar.txt", KOPRU_ANAHTAR, self.cache / "gecici")  # noqa: E731
        with mock.patch.object(tf_bilgi, "kopru_tasi", lambda *a: b"<html>Sign in</html>"):
            durum = self.ok("kur")  # durum çağrısı kurulumu kilitlemez (review 1)
            self.assertEqual((durum["anahtar"], durum["gecerli"]), (True, None))
            self.assertIn("yanıtı anlaşılamadı", durum["uyari"])
            self.assertIn("yanıtı anlaşılamadı", self.stop("kur", "--dosya", f()))  # kurulum köprüyle doğrular

        def http_hatasi(*a):
            raise tf_bilgi.urllib.error.HTTPError("u", 500, "x", {}, None)
        with mock.patch.object(tf_bilgi, "kopru_tasi", http_hatasi):
            self.assertIn("yanıt vermedi (HTTP 500)", self.ok("kur")["uyari"])
            self.assertIn("yanıt vermedi (HTTP 500)", self.stop("kur", "--dosya", f()))
        self.assertEqual((self.cache / "anahtar").read_text(), KOPRU_ANAHTAR + "\n")  # eski anahtar yerinde

        def yarim(*a):
            raise tf_bilgi.http.client.IncompleteRead(b"{", 10)
        with mock.patch.object(tf_bilgi, "kopru_tasi", yarim):
            self.assertIn("köprüsüne ulaşılamadı (IncompleteRead", self.stop("oku", "SON.md"))  # traceback değil

    def test_bitir_yaniti_kaybolursa_yeniden_dener_geri_almaz(self):
        self.hazir()
        self.kopru.kayip["bitir"] = 1  # köprü kaydı tamamladı, yanıt istemciye ulaşmadı
        r = self.ok("gonder", "--taslak", self.taslak(), "--metin", self.dosya("taslak.md", "kısa"))
        self.assertTrue(self.kopru.kayitlar[r["kod"]]["bitti"])
        self.assertEqual(len(self.kopru.islemler("bitir")), 2)
        self.assertEqual(self.kopru.islemler("geri-al"), [])  # tamamlanan paylaşım geri alınmaz
        self.assertIn("yarın 09:05 turunda", r["satir"])
        self.kopru.kayip["bitir"] = 1
        self.kopru.eski_bitir = True  # eski köprü: ikinci bitir "zaten tamamlandı"
        r = self.ok("gonder", "--taslak", self.taslak(), "--metin", self.dosya("taslak.md", "kısa"))
        self.assertTrue(self.kopru.kayitlar[r["kod"]]["bitti"])
        self.assertEqual(self.kopru.islemler("geri-al"), [])
        self.assertIn("kütüphaneci bir sonraki turunda dosyalar", r["satir"])

    def test_gonder_kopru_anahtarini_paylasmaz(self):
        self.hazir()
        ek = self.tmp / "kurulum.md"
        ek.write_text("Anahtarım: " + KOPRU_ANAHTAR, encoding="utf-8")
        metin = self.dosya("taslak.md", "**Sonuç:** x")
        for argv in (("--ek", str(ek)), ("--ek", str(self.cache / "anahtar")),
                     ("--govde", self.dosya("govde.md", "anahtarım " + KOPRU_ANAHTAR))):
            out = self.stop("gonder", "--taslak", self.taslak(), "--metin", metin, *argv)
            self.assertNotIn(KOPRU_GIZLI, out)
            self.assertTrue("Köprü anahtarı paylaşılmaz" in out or "kendi klasöründeki" in out, out)
        aynadaki = self.cache / "kopru" / "KONULAR.md"  # önbellek klasörünün altındaki her dosya
        self.assertIn("kendi klasöründeki", self.stop("gonder", "--taslak", self.taslak(), "--metin", metin,
                                                      "--ek", str(aynadaki)))
        notlu = self.taslak(notlar=["anahtar " + KOPRU_ANAHTAR])
        self.assertIn("Köprü anahtarı paylaşılmaz", self.stop("gonder", "--taslak", notlu, "--metin", metin))
        self.assertEqual(self.kopru.islemler("baslat"), [])

    def test_toplu_paylas_hazirligindaki_ek_gider_anahtar_gitmez(self):
        """/toplu-paylas köprü yolu: ham dosya gecici/toplu-<damga>/<klasor>/kaynak.<uz>'dadır (~/.tf-bilgi altı); klasör
        kuralı gecici/'yi muaf tutar. Oraya kopyalanmış anahtar içerik taramasıyla, gecici/'den anahtara giden bağlantı
        gerçek yoluyla yakalanır (inceleme 2: .github#12)."""
        self.hazir()
        metin = self.dosya("taslak.md", "**Sonuç:** x")
        oge = self.cache / "gecici" / "toplu-20261107-100000" / "001-rapor"
        oge.mkdir(parents=True)
        kaynak = oge / "kaynak.html"
        kaynak.write_text("<h1>Rapor</h1><p>Abonelik ×3 özeti.</p>", encoding="utf-8")
        sonuc = self.ok("gonder", "--taslak", self.taslak(), "--metin", metin, "--ek", str(kaynak))
        self.assertEqual([d["ad"] for d in sonuc["dosyalar"]], ["taslak.md", "kaynak.html"])
        self.assertEqual([d["ad"] for d in self.kopru.islemler("baslat")[-1]["dosyalar"]], ["taslak.md", "kaynak.html"])
        baslat_sayisi = len(self.kopru.islemler("baslat"))
        kopya = oge / "kopya.md"
        kopya.write_text("kurulum notu " + KOPRU_ANAHTAR, encoding="utf-8")
        out = self.stop("gonder", "--taslak", self.taslak(), "--metin", metin, "--ek", str(kopya))
        self.assertIn("Köprü anahtarı paylaşılmaz", out)
        self.assertNotIn(KOPRU_GIZLI, out)
        bag = oge / "anahtar-baglantisi.txt"
        bag.symlink_to(self.cache / "anahtar")
        out = self.stop("gonder", "--taslak", self.taslak(), "--metin", metin, "--ek", str(bag))
        self.assertTrue("kendi klasöründeki" in out or "Köprü anahtarı paylaşılmaz" in out, out)
        self.assertNotIn(KOPRU_GIZLI, out)
        for yasak in (self.cache / "kopru" / "KONULAR.md", self.cache / "anahtar"):
            self.assertIn("kendi klasöründeki", self.stop("gonder", "--taslak", self.taslak(), "--metin", metin,
                                                          "--ek", str(yasak)))
        self.assertEqual(len(self.kopru.islemler("baslat")), baslat_sayisi)

    def test_gonder_sinirlar_ve_adlar(self):
        self.hazir()
        metin = self.dosya("taslak.md", "**Sonuç:** x")
        ekler = []
        for i in range(10):
            e = self.tmp / f"ek{i}.md"
            e.write_text("içerik " + str(i), encoding="utf-8")
            ekler += ["--ek", str(e)]
        self.assertIn("en çok 10 dosya", self.stop("gonder", "--taslak", self.taslak(), "--metin", metin, *ekler))
        buyuk = self.tmp / "buyuk.md"
        buyuk.write_text("x" * 64, encoding="utf-8")
        with mock.patch.dict(tf_bilgi.KOPRU_SINIRLAR, {"dosya_azami_bayt": 32}):
            self.kopru.ozel["kim"] = {**self.kopru.i_kim({}), "sinirlar": {"dosya_azami_bayt": 32}}
            self.hazir()
            self.assertIn("buyuk.md çok büyük", self.stop("gonder", "--taslak", self.taslak(), "--metin", metin,
                                                          "--ek", str(buyuk)))
        self.kopru.ozel["kim"] = {**self.kopru.i_kim({}), "sinirlar": {"kayit_azami_bayt": 40}}
        self.hazir()
        self.assertIn("toplamı çok büyük", self.stop("gonder", "--taslak", self.taslak(), "--metin", metin,
                                                     "--ek", str(buyuk)))
        self.assertEqual(self.kopru.islemler("baslat"), [])
        del self.kopru.ozel["kim"]
        self.hazir()
        ad1, alt, ad3 = self.tmp / "Çalışma.md", self.tmp / "alt", self.tmp / "meta.json"
        ad1.write_text("bir", encoding="utf-8")
        alt.mkdir()
        (alt / "Calisma.md").write_text("iki", encoding="utf-8")
        ad3.write_text("{}", encoding="utf-8")
        r = self.ok("gonder", "--taslak", self.taslak(), "--metin", metin, "--ek", str(ad1),
                    "--ek", str(alt / "Calisma.md"), "--ek", str(ad3))
        adlar = list(self.kopru.kayitlar[r["kod"]]["veri"])
        self.assertEqual(adlar, ["taslak.md", "Calisma.md", "Calisma-2.md", "meta-2.json"])  # çakışma ve ayrılmış ad

    def test_mesai_yok(self):
        """0.9.0: 7/24; mesai ve sessiz saat yardımcıları kalktı."""
        for ad in ("mesai_durumu", "sessiz_mi", "ozet_zamani", "sonraki_tur", "SESSIZ_BAS", "TUR_SAATLERI"):
            self.assertFalse(hasattr(tf_bilgi, ad), ad)


class KopruAnahtarYenilemeTest(KopruTest):
    """Review (.github#12): anahtar yenilenince ya da bozulunca `/bilgi kur` kilitlenmez."""

    def test_eski_anahtar_gecersizken_yeni_anahtar_kurulur(self):
        eski = "tfb1." + KOPRU_DAGITIM + "." + "e" * 64 + "\n"  # anahtarUret eskisini sildi
        (self.cache / "anahtar").write_text(eski)
        code, out = self.run_main("kur")  # Kur 1. adım kurulumu kilitlememeli
        self.assertEqual(code, 0, out)
        durum = json.loads(out)
        self.assertEqual((durum["anahtar"], durum["gecerli"]), (True, False))
        self.assertEqual(durum["dosya_yeri"], str(self.cache / "gecici" / "anahtar.txt"))
        self.assertIn("Anahtar tanınmadı.", durum["uyari"])
        self.assertNotIn("e" * 64, out)
        f = self.dosya("anahtar.txt", KOPRU_ANAHTAR, self.cache / "gecici")
        r = self.ok("kur", "--dosya", f)
        self.assertEqual((r["kuruldu"], r["kisi"]), (True, "mert"))
        self.assertEqual((self.cache / "anahtar").read_text(), KOPRU_ANAHTAR + "\n")
        (self.cache / "anahtar").write_text("tfb1.kisa.abc\n")  # bozuk dosya da aynı yoldan düzelir
        code, out = self.run_main("kur")
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads(out)["gecerli"], False)
        self.assertIn("bozuk", json.loads(out)["uyari"])
        r = self.ok("kur", "--dosya", self.dosya("anahtar.txt", KOPRU_ANAHTAR, self.cache / "gecici"))
        self.assertTrue(r["kuruldu"])

    def test_kopru_kapaliyken_durum_dosya_yerini_verir(self):
        self.kopru.kopuk["kim"] = 5
        durum = self.ok("kur")
        self.assertEqual((durum["anahtar"], durum["gecerli"]), (True, None))
        self.assertIn("ulaşılamadı", durum["uyari"])
        self.assertTrue(durum["dosya_yeri"].endswith("gecici/anahtar.txt"))


# Ortak vektörler: KB deposundaki kopruler/paylas/test_vektorleri.json'dan AYNEN kopyalandı (köprü Code.gs ve KB
# bildir.py aynı vektörleri kullanır). KB'de değişirse buraya da kopyalanır.
KOPRU_VEKTORLERI = json.loads('{"aciklama": "Köprü yorumu ve tercih satırı için ortak test vektörleri: kopruler/paylas/test_code.js (yorumYazari_, tercihCoz_) ve araclar/test_bildir.py (yorum_kisisi, tercihleri_coz) aynı sonucu vermeli. Eklentideki kopru_yorum_kisisi aynı kuralı izler.", "kopru": "tf-kopru", "kisiler": {"ayse": {"ad": "Ayşe Örnek", "alanlar": ["ekip"], "github": "ayse-gh"}, "mert": {"ad": "Mert Örnek", "alanlar": ["ekip"], "github": null}, "can": {"ad": "Can Örnek", "alanlar": ["ekip"], "github": "tf-kopru"}}, "yorum_yazari": [{"ad": "köprü yorumu: ilk satır kisi=, ardından bir boş satır atılır", "login": "tf-kopru", "govde": "kisi=mert · Mert (TF Bilgi köprüsü)\\n\\nFiyatı 12.990 yapalım.", "kisi": "mert", "metin": "Fiyatı 12.990 yapalım."}, {"ad": "köprü girişi büyük harfle de eşleşir; boş satır yoksa metin ikinci satırdan", "login": "TF-Kopru", "govde": "kisi=mert\\nKısa not.", "kisi": "mert", "metin": "Kısa not."}, {"ad": "yalnız bir boş satır atılır", "login": "tf-kopru", "govde": "kisi=mert · Mert\\n\\n\\nİkinci paragraf.", "kisi": "mert", "metin": "\\nİkinci paragraf."}, {"ad": "kisi= anahtarından sonra boşluk ya da · gelmeli (kisi=mert-x sayılmaz); köprü girişi kisiler.json\'da can", "login": "tf-kopru", "govde": "kisi=mert-x · ?\\n\\nX", "kisi": "can", "metin": "kisi=mert-x · ?\\n\\nX"}, {"ad": "kisiler.json\'da olmayan kişi: köprü girişinin kendi eşlemesi", "login": "tf-kopru", "govde": "kisi=kimse · ?\\n\\nX", "kisi": "can", "metin": "kisi=kimse · ?\\n\\nX"}, {"ad": "köprü olmayan hesabın kisi= satırı sayılmaz", "login": "ayse-gh", "govde": "kisi=mert · sahte\\n\\nX", "kisi": "ayse", "metin": "kisi=mert · sahte\\n\\nX"}, {"ad": "tanınmayan hesap", "login": "yabanci", "govde": "Merhaba", "kisi": null, "metin": "Merhaba"}], "tercih": {"yoneticiler": ["ayse"], "yorumlar": [{"id": 1, "user": {"login": "tf-kopru"}, "body": "tercih: kisi=mert kanal=mail", "created_at": "2026-11-05T09:00:00Z", "updated_at": "2026-11-05T09:00:00Z"}, {"id": 2, "user": {"login": "tf-kopru"}, "body": "tercih: kanal=whatsapp", "created_at": "2026-11-05T09:10:00Z", "updated_at": "2026-11-05T09:10:00Z"}, {"id": 3, "user": {"login": "ayse-gh"}, "body": "tercih: kanal=slack,mail", "created_at": "2026-11-05T09:20:00Z", "updated_at": "2026-11-05T09:20:00Z"}, {"id": 4, "user": {"login": "tf-kopru"}, "body": "tercih: kisi=kimse kanal=mail", "created_at": "2026-11-05T09:30:00Z", "updated_at": "2026-11-05T09:30:00Z"}, {"id": 5, "user": {"login": "tf-kopru"}, "body": "tercih: kisi=ayse kanal=mail", "created_at": "2026-11-05T09:40:00Z", "updated_at": "2026-11-05T12:00:00Z"}, {"id": 6, "user": {"login": "yabanci"}, "body": "tercih: kisi=mert kanal=slack", "created_at": "2026-11-05T09:50:00Z", "updated_at": "2026-11-05T09:50:00Z"}], "beklenen": {"mert": {"kanallar": ["mail"], "kaynak": "yorum 2026-11-05 · tf-kopru"}, "can": {"kanallar": ["whatsapp"], "kaynak": "yorum 2026-11-05 · tf-kopru"}, "ayse": {"kanallar": ["slack", "mail"], "kaynak": "yorum 2026-11-05 · ayse-gh"}}}}')


class KopruVektorTest(unittest.TestCase):
    def test_kopru_yorumu_ve_tercih_ortak_vektorler(self):
        v = KOPRU_VEKTORLERI
        kopru = tf_bilgi.kopru_girisi({"kopru_github": v["kopru"]})
        gh_kisi = {str(b["github"]).lower(): k for k, b in v["kisiler"].items() if b.get("github")}
        for d in v["yorum_yazari"]:
            y = {"user": {"login": d["login"]}, "body": d["govde"]}
            kopru_kisi = tf_bilgi.kopru_yorum_kisisi(y, kopru, v["kisiler"])
            self.assertEqual(kopru_kisi or gh_kisi.get(d["login"].lower()), d["kisi"], d["ad"])
            metin = tf_bilgi.kopru_metni(d["govde"]) if kopru_kisi else d["govde"]
            self.assertEqual(metin, d["metin"], d["ad"])
        t = v["tercih"]
        sonuc, _ = tf_bilgi.tercih_coz(t["yorumlar"], v["kisiler"], set(t["yoneticiler"]), kopru)
        self.assertEqual(sonuc, t["beklenen"])


class KopruHttpTest(unittest.TestCase):
    """Gerçek urllib: Apps Script gibi POST'a 302 ile başka adresi gösteren yerel sunucu (yalnız 127.0.0.1)."""

    def test_post_302_yonlendirmesini_izler_gizli_adreste_yok(self):
        import http.server
        import threading
        gorulen = []

        class Isleyici(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                govde = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                gorulen.append(("POST", self.path, govde["islem"], govde["anahtar"]))
                self.send_response(302)
                self.send_header("Location", "/echo?k=1")
                self.end_headers()

            def do_GET(self):
                gorulen.append(("GET", self.path, None, None))
                veri = json.dumps({"tamam": True, "kisi": "mert"}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(veri)))
                self.end_headers()
                self.wfile.write(veri)

        sunucu = http.server.HTTPServer(("127.0.0.1", 0), Isleyici)
        threading.Thread(target=sunucu.serve_forever, daemon=True).start()
        self.addCleanup(sunucu.server_close)
        self.addCleanup(sunucu.shutdown)
        with mock.patch.dict(os.environ, {"TF_BILGI_KOPRU_URL": "http://127.0.0.1:%d/exec" % sunucu.server_port}):
            r = tf_bilgi.kopru_cagir("kim", anahtar=(KOPRU_DAGITIM, KOPRU_GIZLI))
        self.assertEqual(r["kisi"], "mert")
        self.assertEqual(gorulen, [("POST", "/exec", "kim", KOPRU_GIZLI), ("GET", "/echo?k=1", None, None)])


class KopruDogrudanYolTest(Base):
    """Doğrudan yolda köprü yorumları ve tercihleri (`.kb.json` `kopru_github`) gerçek kişiye sayılır."""

    def setUp(self):
        super().setUp()
        self.seed_commit("ekip", ".kb.json", json.dumps({"alan": "ekip", "girdi_onek": "B", "uzak": "Teamfluencer-Dev/tf-bilgi",
                                                         "yazanlar": ["ayse"], "tercih_issue": 7,
                                                         "tercih_yoneticileri": ["ayse"], "kopru_github": "Kopru-Bot"}))

    def test_tercih_kopru_satiri(self):
        sonuc, uyarilar = tf_bilgi.tercih_coz([
            yorum("kopru-bot", "tercih: kisi=mert kanal=mail", 1),
            yorum("kopru-bot", "tercih: kanal=slack", 2),               # köprüde kisi= şart
            yorum("baska-bot", "tercih: kisi=ayse kanal=slack", 3)], KISILER["kisiler"], set(), "kopru-bot")
        self.assertEqual(sonuc, {"mert": {"kanallar": ["mail"], "kaynak": "yorum 2026-11-05 · kopru-bot"}})
        self.assertEqual(len(uyarilar), 2)
        self.assertEqual(tf_bilgi.kopru_girisi({"kopru_github": "Kopru-Bot"}), "kopru-bot")

    def test_yorumlar_ve_onceki_yorumcular_kopru_kisisine(self):
        os.environ.update({"FAKE_GH_LOGIN": "mert-gh", "FAKE_GH_PUSH": "false",
                           "TF_BILGI_SIMDI": "2026-11-05T10:00:00+03:00"})
        self.seed_commit("ekip", "girdiler/2026/11/B-20261105-ayse-01.md", YORUM_GIRDI_METNI)
        hazir = self.ok("hazirla")
        self.assertEqual(hazir["yol"], "dogrudan")
        durum = json.loads(self.issues.read_text())
        durum["issues"].append(gh_issue(10, "[B-20261105-ayse-01] Abonelik planı v2", acan="kopru-bot"))
        durum["comments"]["10"] = [gh_yorum(1, "kopru-bot", "kisi=ayse · Ayşe (TF Bilgi köprüsü)\n\nKöprüden yazdım.",
                                            "2026-11-05T06:00:00Z"),
                                   gh_yorum(2, "mert-gh", "kisi=ayse sahte", "2026-11-05T07:00:00Z")]
        self.issues.write_text(json.dumps(durum, ensure_ascii=False))
        r = self.ok("yorumlar", YORUM_GIRDI)
        self.assertEqual([(y["ad"], y["kopru"], y["metin"]) for y in r["yorumlar"]],
                         [("Ayşe", True, "Köprüden yazdım."), ("Mert", False, "kisi=ayse sahte")])
        yol = self.cache / "gecici" / "y" / "yorum.md"
        yol.parent.mkdir(parents=True)
        yol.write_text("Katılıyorum.")
        plan = self.ok("yorum", YORUM_GIRDI, "--dosya", str(yol))
        # köprünün açtığı sayfa "açan" sayılmaz; köprü yorumu ayse'ye sayılır (yazar olarak zaten var)
        self.assertEqual([(a["kisi"], a["neden"]) for a in plan["alicilar"]], [("ayse", "yazar"), ("zeynep", "alıcı")])

    def test_dogrudan_geri_al_bayragi_ve_girdi(self):
        os.environ["FAKE_GH_LOGIN"] = "ayse-gh"
        self.seed_commit("ekip", "girdiler/2026/11/B-20261105-ayse-01.md", YORUM_GIRDI_METNI)
        h = self.ok("hazirla")
        self.assertEqual((h["yol"], h["geri_al"]), ("dogrudan", False))  # anahtarsız: makbuz geri-al vaat etmez
        g = self.ok("girdi", "B-20261105-ayse-01")  # /bilgi oku: doğrudan yolda origin/main'den
        self.assertIn("id: B-20261105-ayse-01", g["icerik"])
        self.assertEqual((g["gizli"], g["url"]), (False, "https://github.com/Teamfluencer-Dev/tf-bilgi/blob/main/"
                                                          "girdiler/2026/11/B-20261105-ayse-01.md"))
        self.assertIn("bulunamadı", self.stop("girdi", "B-20261105-ayse-09"))
        self.assertIn("köprü anahtarın yok", self.stop("geri-al", "B-20261105-ayse-01"))
        self.cache.mkdir(parents=True, exist_ok=True)
        (self.cache / "anahtar").write_text(KOPRU_ANAHTAR + "\n")
        os.environ["TF_BILGI_YOL"] = "dogrudan"  # anahtarı olan yazan doğrudan yolu seçti
        h = self.ok("hazirla")
        self.assertEqual((h["yol"], h["geri_al"]), ("dogrudan", True))
        kopru = SahteKopru({})
        with mock.patch.object(tf_bilgi, "kopru_tasi", kopru):
            self.assertEqual(self.ok("geri-al", "B-20261105-ayse-01")["sonuc"], "kaydedildi")
        self.assertEqual(kopru.islemler("geri-al")[0]["hedef"], "B-20261105-ayse-01")  # geri-al köprüye gider

    def test_bildirim_plani_gece_de_hemen(self):
        os.environ["FAKE_GH_LOGIN"] = "ayse-gh"
        self.ok("hazirla")
        os.environ["TF_BILGI_SIMDI"] = "2026-11-05T22:00:00+03:00"
        for haber in ("simdi", "hemen"):
            r = self.ok("bildirim-plani", "--tip", "BILGI", "--kimden", "mert", "--yazar", "ayse", "--haber", haber)
            self.assertTrue(r["anlik"])
            self.assertTrue(r["satir"].startswith("dosyalanınca hemen: Mert"), r["satir"])
        self.assertNotIn("sessiz_neden", self.ok("hazirla"))


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
        self.assertIn("yorumlar GIRDI_ID", err)


class KopruTekrarTest(unittest.TestCase):
    """Parça yüklemesi: köprünün geçici Drive hatasında (kod drive) aynı parça yeniden gönderilir; diğer retler durur."""

    def test_drive_hatasinda_yeniden_dener_digerinde_durur(self):
        cagrilar = []

        def sahte(islem, alanlar=None, zaman_asimi=None, anahtar=None):
            cagrilar.append(alanlar["sira"])
            if len(cagrilar) == 1:
                raise tf_bilgi.KopruHatasi("Drive geçici hata", "drive")
            return {"tamam": True}

        with mock.patch.object(tf_bilgi, "kopru_cagir", sahte), mock.patch.object(tf_bilgi, "KOPRU_BEKLE", 0):
            self.assertEqual(tf_bilgi.kopru_cagir_tekrarla("parca", {"sira": 0}, 1), {"tamam": True})
        self.assertEqual(cagrilar, [0, 0])

        def red(islem, alanlar=None, zaman_asimi=None, anahtar=None):
            cagrilar.append("red")
            raise tf_bilgi.KopruHatasi("Sıra dışı parça", "durum")

        with mock.patch.object(tf_bilgi, "kopru_cagir", red), mock.patch.object(tf_bilgi, "KOPRU_BEKLE", 0):
            with self.assertRaises(tf_bilgi.KopruHatasi):
                tf_bilgi.kopru_cagir_tekrarla("parca", {"sira": 1}, 1)
        self.assertEqual(cagrilar.count("red"), 1)


class SahteGitHub:
    """GitHub REST'in (dal, contents, git data) ağsız karşılığı: tf_bilgi.gh_api yerine çağrılır. Ağaçlar düz
    yol → blob haritasıdır; contents'in verdiği klasör sha'ları `git/trees/<sha>` ile açılır."""

    def __init__(self, depolar):
        self.depolar, self.cagrilar, self.yaris, self.hatalar, self.klasorler = {}, [], {}, {}, {}
        self.etiketler = {}  # (slug, issue no) → etiketler (zil)
        for slug, dosyalar in depolar.items():
            self.depo_kur(slug, dosyalar)

    def depo_kur(self, slug, dosyalar):
        d = {"blobs": {}, "trees": {}, "commits": {}, "ref": None}
        self.depolar[slug] = d
        agac = self._tree(d, {y: self._blob(d, self._bayt(v)) for y, v in dosyalar.items()})
        d["ref"] = self._commit(d, agac, [], "tohum")

    @staticmethod
    def _bayt(v):
        return v.encode("utf-8") if isinstance(v, str) else v

    @staticmethod
    def _blob(d, veri):
        sha = hashlib.sha1(b"blob %d\0" % len(veri) + veri).hexdigest()
        d["blobs"][sha] = veri
        return sha

    @staticmethod
    def _tree(d, harita):
        sha = hashlib.sha1(json.dumps(sorted(harita.items())).encode()).hexdigest()
        d["trees"][sha] = dict(harita)
        return sha

    @staticmethod
    def _commit(d, agac, ebeveynler, mesaj):
        sha = hashlib.sha1(json.dumps([agac, ebeveynler, mesaj, len(d["commits"])]).encode()).hexdigest()
        d["commits"][sha] = {"tree": agac, "parents": list(ebeveynler), "message": mesaj}
        return sha

    def harita(self, slug, ref=None):
        d = self.depolar[slug]
        return d["trees"][d["commits"][ref or d["ref"]]["tree"]]

    def dosyalar(self, slug):
        d = self.depolar[slug]
        return {y: d["blobs"][s] for y, s in self.harita(slug).items()}

    def mesajlar(self, slug):
        d, sonuc, c = self.depolar[slug], [], self.depolar[slug]["ref"]
        while c:
            sonuc.append(d["commits"][c]["message"])
            c = (d["commits"][c]["parents"] or [None])[0]
        return sonuc  # en yeni önce

    def baskasi_yazar(self, slug, degisiklik, mesaj="başkası"):
        """Başkasının push'u (ör. kütüphaneci): {yol: içerik | None (sil)}."""
        d = self.depolar[slug]
        harita = dict(self.harita(slug))
        for y, v in degisiklik.items():
            if v is None:
                harita.pop(y, None)
            else:
                harita[y] = self._blob(d, self._bayt(v))
        d["ref"] = self._commit(d, self._tree(d, harita), [d["ref"]], mesaj)

    def klasor_sha(self, agac, yol):
        sha = hashlib.sha1(f"{agac}:{yol}".encode()).hexdigest()
        self.klasorler[sha] = (agac, yol)
        return sha

    def agac_ogeleri(self, d, agac, onek, ozyineli):
        """Düz haritadan git trees API görünümü: onek klasörünün doğrudan (ya da özyineli) öğeleri."""
        on = onek + "/" if onek else ""
        ogeler, klasorler = [], set()
        for y, sha in sorted(d["trees"][agac].items()):
            if not y.startswith(on):
                continue
            kalan = y[len(on):]
            parcalar = kalan.split("/")
            if ozyineli:
                ogeler.append({"path": kalan, "mode": "100644", "type": "blob", "sha": sha})
                klasorler.update("/".join(parcalar[:i + 1]) for i in range(len(parcalar) - 1))
            elif len(parcalar) > 1:
                klasorler.add(parcalar[0])
            else:
                ogeler.append({"path": kalan, "mode": "100644", "type": "blob", "sha": sha})
        return ogeler + [{"path": k, "mode": "040000", "type": "tree", "sha": self.klasor_sha(agac, on + k)}
                         for k in sorted(klasorler)]

    @staticmethod
    def atalar(d, c):
        gorulen = set()
        while c and c not in gorulen:
            gorulen.add(c)
            c = (d["commits"][c]["parents"] or [None])[0]
        return gorulen

    def __call__(self, yontem, yol, govde=None, zaman_asimi=60):
        govde = json.loads(json.dumps(govde)) if govde is not None else None  # gerçek istek gibi JSON'dan geçer
        self.cagrilar.append((yontem, yol, govde))
        yol0, _, sorgu = yol.partition("?")
        p = yol0.split("/")
        slug = "/".join(p[1:3])
        for (y_, onek), http in self.hatalar.items():
            if y_ == yontem and yol0.startswith(onek):
                raise tf_bilgi.GhHatasi(f"gh: sahte hata (HTTP {http})", http)
        if p[0] != "repos" or slug not in self.depolar:
            raise tf_bilgi.GhHatasi("gh: Not Found (HTTP 404)", 404)
        d, r = self.depolar[slug], p[3:]
        if yontem == "GET" and r == ["branches", "main"]:
            return {"name": "main", "commit": {"sha": d["ref"], "commit": {"tree": {"sha": d["commits"][d["ref"]]["tree"]}}}}
        if yontem == "GET" and r[:1] == ["contents"]:
            ref = dict(x.split("=", 1) for x in sorgu.split("&") if x).get("ref", "main")
            c = d["ref"] if ref == "main" else ref
            harita, hedef = d["trees"][d["commits"][c]["tree"]], "/".join(r[1:])
            if hedef in harita:
                return {"type": "file", "name": r[-1], "path": hedef, "sha": harita[hedef], "encoding": "base64",
                        "content": base64.b64encode(d["blobs"][harita[hedef]]).decode("ascii")}
            cocuklar = {}
            for y in harita:
                if y.startswith(hedef + "/"):
                    kalan = y[len(hedef) + 1:]
                    cocuklar[kalan.split("/")[0]] = "dir" if "/" in kalan else "file"
            if not cocuklar:
                raise tf_bilgi.GhHatasi("gh: Not Found (HTTP 404)", 404)
            agac = d["commits"][c]["tree"]
            return [{"name": ad, "path": f"{hedef}/{ad}", "type": tur,
                     "sha": self.klasor_sha(agac, f"{hedef}/{ad}") if tur == "dir" else harita[f"{hedef}/{ad}"]}
                    for ad, tur in sorted(cocuklar.items())]
        if yontem == "GET" and r[:2] == ["git", "trees"]:
            agac, onek = (r[2], "") if r[2] in d["trees"] else self.klasorler[r[2]]
            return {"sha": r[2], "truncated": False,
                    "tree": self.agac_ogeleri(d, agac, onek, ozyineli="recursive=1" in sorgu)}
        if yontem == "POST" and r == ["git", "blobs"]:
            assert govde["encoding"] == "base64"
            return {"sha": self._blob(d, base64.b64decode(govde["content"]))}
        if yontem == "POST" and r == ["git", "trees"]:
            harita = dict(d["trees"][govde["base_tree"]])
            for g in govde["tree"]:
                assert g["type"] == "blob" and g["mode"] in ("100644", "100755"), g
                if "content" in g:
                    harita[g["path"]] = self._blob(d, g["content"].encode("utf-8"))
                elif g["sha"] is None:
                    if g["path"] not in harita:
                        raise tf_bilgi.GhHatasi("gh: GitRPC::BadObjectState (HTTP 422)", 422)
                    del harita[g["path"]]
                else:
                    assert g["sha"] in d["blobs"], g
                    harita[g["path"]] = g["sha"]
            return {"sha": self._tree(d, harita)}
        if yontem == "POST" and r == ["git", "commits"]:
            assert govde["tree"] in d["trees"] and all(x in d["commits"] for x in govde["parents"])
            return {"sha": self._commit(d, govde["tree"], govde["parents"], govde["message"])}
        if yontem == "PATCH" and r == ["git", "refs", "heads", "main"]:
            assert govde["force"] is False
            if self.yaris.get(slug):  # tam bu anda başkası push eder
                self.yaris[slug] -= 1
                self.baskasi_yazar(slug, {f"baska/{len(d['commits'])}.md": "başkası"})
            if d["ref"] not in self.atalar(d, govde["sha"]):
                raise tf_bilgi.GhHatasi("gh: Update is not a fast forward (HTTP 422)", 422)
            d["ref"] = govde["sha"]
            return {"ref": "refs/heads/main", "object": {"sha": govde["sha"]}}
        if r[:1] == ["issues"] and len(r) in (3, 4) and r[2] == "labels":  # zil: etiket kaldır / ekle
            etiketler = self.etiketler.setdefault((slug, int(r[1])), set())
            if yontem == "DELETE" and len(r) == 4:
                if r[3] not in etiketler:
                    raise tf_bilgi.GhHatasi("gh: Label does not exist (HTTP 404)", 404)
                etiketler.discard(r[3])
                return [{"name": e} for e in sorted(etiketler)]
            if yontem == "POST" and len(r) == 3:
                etiketler.update(govde["labels"])
                return [{"name": e} for e in sorted(etiketler)]
        raise AssertionError(f"beklenmeyen GitHub çağrısı: {yontem} {yol}")


HIZLI_TASLAK = {"hizli": True, "tur": "", "baslik": "", "tldr": "", "konu_onerisi": "AYIKLA", "konu_kaynagi": "claude",
                "aday_konular": [], "istek": None, "haber": "hemen", "kisisel_veri": False, "birim": [], "proje": None,
                "hedef_kitle": [], "belge_tarihi": None, "uretim": "insan",
                "baglantilar": {"jira": [], "pr": [], "hatirlatma": [], "cl": []}, "gecersiz_kildigi": [], "gizli": False,
                "gizli_link": None, "notlar": []}
META_ANAHTARLARI = ["kaynak_kanal", "gonderen", "gonderen_ham", "alinma", "dosyalar", "alan", "tur", "mesaj_kimligi",
                    "konu_satiri", "aciklama", "haber", "atlanan_dosyalar"]


class HizliTest(Base):
    """/paylas hızlı yolu (0.7.0): klon yok, kb.py yok, soru yok. Yazan GitHub Git Data API'siyle tek commit atar;
    yazamayan köprü anahtarıyla köprüden gönderir; ikisi de yoksa ne yapacağını söyler."""
    EKIP, YONETIM = "Teamfluencer-Dev/tf-bilgi", "eneskrblt/tf-bilgi-yonetim"

    def setUp(self):
        super().setUp()
        for ad in ("TF_BILGI_UZAK_EKIP", "TF_BILGI_UZAK_YONETIM"):
            os.environ.pop(ad, None)  # varsayılan GitHub depoları (sahte GitHub'da)
        os.environ.update({"FAKE_GH_LOGIN": "ayse-gh", "TF_BILGI_SIMDI": "2026-11-05T12:30:00+03:00"})  # Perşembe
        tohum = {"kisiler.json": json.dumps(KISILER, ensure_ascii=False), "00-gelen/.gitkeep": "", "README.md": "# KB\n"}
        self.gh = SahteGitHub({self.EKIP: tohum, self.YONETIM: tohum})
        for ad, deger in (("gh_api", self.gh), ("HIZLI_BEKLE", 0), ("KOPRU_BEKLE", 0), ("KB_SHA256", ())):
            yama = mock.patch.object(tf_bilgi, ad, deger)  # KB_SHA256 boş: hızlı yol kb.py'ye hiç dokunmaz
            yama.start()
            self.addCleanup(yama.stop)
        self.ekler = self.tmp / "ekler"
        self.ekler.mkdir()

    def ek(self, ad, icerik):
        yol = self.ekler / ad
        yol.parent.mkdir(parents=True, exist_ok=True)
        yol.write_bytes(icerik if isinstance(icerik, bytes) else icerik.encode("utf-8"))
        return str(yol)

    def hizli(self, *argv, not_metni=""):
        return self.ok("hizli", *argv, stdin=not_metni)

    def anahtar_kur(self):
        self.cache.mkdir(parents=True, exist_ok=True)
        (self.cache / "anahtar").write_text(KOPRU_ANAHTAR + "\n")

    def kayit(self, slug, kod):
        """Sahte depoda kodun 00-gelen klasörü → {dosya adı: bayt}."""
        sonuc = {}
        for yol, veri in self.gh.dosyalar(slug).items():
            parca = yol.split("/")
            if parca[0] == "00-gelen" and len(parca) == 3 and parca[1].endswith("-" + kod[2:]):
                sonuc[parca[2]] = veri
        return sonuc

    def yetki_cagrilari(self, slug):
        return [c for c in self.gh_calls() if c[:2] == ["api", f"repos/{slug}"]]

    def zil_cagrilari(self):
        return [(c[0], c[1]) for c in self.gh.cagrilar if "/labels" in c[1]]

    def test_yazan_tek_commit_klonsuz_kb_pysiz_makbuz(self):
        pdf = self.ek("Çalışma Notu.pdf", b"%PDF-1.4 \x00\x01\xff ikili")
        md = self.ek("rapor.md", "Bağlantı: mongodb://u:hunter2@db GIZLI-ANAHTAR-123 KISISEL-VERI")  # sır engellemez
        notu = "Ayşe ve Mert'e: Cuma'ya bakılsın\n\nikinci satır\n"
        once = self.gh.depolar[self.EKIP]["ref"]
        r = self.hizli("--ek", pdf, "--ek", md, not_metni=notu)
        kod = r["kod"]
        self.assertRegex(kod, r"^G-[a-z0-9]{6}$")
        self.assertEqual((r["alan"], r["yol"], r["dosyalar"], r["notlar"]),
                         ("ekip", "writer", ["govde.md", "Calisma-Notu.pdf", "rapor.md"], []))
        self.assertEqual(r["satir"], f"Gönderildi ✓ {kod} · Çalışma Notu.pdf, rapor.md + not · ekip · kütüphaneci birkaç "
                                     f"dakika içinde dosyalar, alıcılara o an haber gider · geri al: /paylas geri-al {kod}")
        self.assertEqual(r["alicilar"], ["mert"])  # §3: gönderen (ayse) alıcı sayılmaz; Mert ekipte → ekip
        self.assertEqual(self.zil_cagrilari(), [("DELETE", f"repos/{self.EKIP}/issues/9/labels/zil"),
                                                ("POST", f"repos/{self.EKIP}/issues/9/labels")])
        self.assertEqual(self.gh.etiketler[(self.EKIP, 9)], {"zil"})
        kayit = self.kayit(self.EKIP, kod)
        self.assertEqual(sorted(kayit), ["Calisma-Notu.pdf", "govde.md", "meta.json", "rapor.md"])
        klasor = f"00-gelen/20261105-123000-ayse-{kod[2:]}"
        self.assertIn(f"{klasor}/meta.json", self.gh.dosyalar(self.EKIP))
        self.assertEqual(kayit["Calisma-Notu.pdf"], Path(pdf).read_bytes())
        self.assertEqual(kayit["rapor.md"], Path(md).read_bytes())
        self.assertEqual(kayit["govde.md"].decode("utf-8"), notu)  # kullanıcının sözleri aynen
        self.assertIn("Mert'e", kayit["meta.json"].decode("utf-8"))  # UTF-8 (ensure_ascii False)
        meta = json.loads(kayit["meta.json"])
        self.assertEqual(list(meta), META_ANAHTARLARI)
        self.assertEqual(meta, {"kaynak_kanal": "claude-code", "gonderen": "ayse", "gonderen_ham": "github:ayse-gh",
                                "alinma": "2026-11-05T12:30:00+03:00",
                                "dosyalar": ["govde.md", "Calisma-Notu.pdf", "rapor.md"], "alan": "ekip",
                                "tur": "girdi", "mesaj_kimligi": kod, "konu_satiri": "Ayşe ve Mert'e: Cuma'ya bakılsın",
                                "aciklama": "Ayşe ve Mert'e: Cuma'ya bakılsın\nikinci satır", "haber": "hemen",
                                "atlanan_dosyalar": []})
        d = self.gh.depolar[self.EKIP]
        self.assertEqual(d["commits"][d["ref"]]["parents"], [once])  # tek commit
        self.assertEqual(self.gh.mesajlar(self.EKIP)[0], f"gelen: {kod} · ayse · 3 dosya")
        self.assertEqual(len([c for c in self.gh.cagrilar if c[1].endswith("/git/blobs")]), 2)  # not ve meta satır içi
        self.assertFalse(self.kok().exists())  # klon yok
        self.assertFalse((self.cache / "kopru").exists())
        self.assertEqual(len(self.yetki_cagrilari(self.EKIP)), 1)
        self.assertEqual((self.cache / "hizli.json").stat().st_mode & 0o777, 0o600)
        r2 = self.hizli("--haber", "simdi", not_metni="Hemen haber ver\n")
        self.assertEqual(len(self.yetki_cagrilari(self.EKIP)), 1)  # yetki bir gün önbellekte
        self.assertEqual(sum("/contents/kisiler.json" in c[1] for c in self.gh.cagrilar), 1)  # kisiler.json da
        self.assertIn(f" {r2['kod']} · not · ekip · ", r2["satir"])
        meta2 = json.loads(self.kayit(self.EKIP, r2["kod"])["meta.json"])
        self.assertEqual((meta2["haber"], meta2["dosyalar"]), ("simdi", ["govde.md"]))
        self.assertEqual(self.gh.mesajlar(self.EKIP)[0], f"gelen: {r2['kod']} · ayse · 1 dosya")
        ob = json.loads((self.cache / "hizli.json").read_text())
        ob["yetki"]["ayse-gh|teamfluencer-dev/tf-bilgi"]["zaman"] -= 2 * 86400  # bayatladı
        (self.cache / "hizli.json").write_text(json.dumps(ob))
        r3 = self.hizli("--ek", pdf)
        self.assertEqual(len(self.yetki_cagrilari(self.EKIP)), 2)
        self.assertEqual(json.loads(self.kayit(self.EKIP, r3["kod"])["meta.json"])["konu_satiri"], "Çalışma Notu.pdf")
        self.assertIn(" · Çalışma Notu.pdf · ekip · ", r3["satir"])

    def test_not_dosyasi_tek_satir_komut(self):
        """Skill notu Write ile gecici/'ye yazar ve tek satırlık komuta --not-dosya ile verir (heredoc yok); dosya
        gönderimden sonra silinir; stdin yalnız yedektir."""
        gecici = self.cache / "gecici"
        gecici.mkdir(parents=True)
        not_yolu = gecici / "not-20261105-123000.txt"
        not_yolu.write_text("Ayşe'ye: `rm -rf ~` $(id) bakılsın\n", encoding="utf-8")
        r = self.ok("hizli", "--not-dosya", str(not_yolu), "--ek", self.ek("a.md", "a"), stdin="stdin yok sayılır")
        kayit = self.kayit(self.EKIP, r["kod"])
        self.assertEqual(kayit["govde.md"].decode("utf-8"), "Ayşe'ye: `rm -rf ~` $(id) bakılsın\n")  # aynen, kabuksuz
        self.assertEqual(json.loads(kayit["meta.json"])["konu_satiri"], "Ayşe'ye: `rm -rf ~` $(id) bakılsın")
        self.assertFalse(not_yolu.exists())  # gönderildi: silindi
        self.assertTrue((self.ekler / "a.md").exists())
        self.assertIn("Not dosyası yok", self.stop("hizli", "--not-dosya", str(not_yolu)))
        dis = self.tmp / "not.txt"
        dis.write_text("x")
        self.assertIn("geçici klasörünün altında", self.stop("hizli", "--not-dosya", str(dis)))
        bag = gecici / "bag.txt"
        bag.symlink_to(self.cache / "hizli.json")  # gecici/'den dışarı bağlantı
        self.assertIn("geçici klasörünün altında", self.stop("hizli", "--not-dosya", str(bag)))
        anahtarli = gecici / "not-anahtar.txt"
        anahtarli.write_text("anahtar " + KOPRU_ANAHTAR)
        out = self.stop("hizli", "--not-dosya", str(anahtarli))
        self.assertIn("Köprü anahtarı paylaşılmaz: notun", out)
        self.assertNotIn(KOPRU_GIZLI, out)
        self.assertTrue(anahtarli.exists())  # gönderilmedi: silinmedi
        bos = gecici / "not-bos.txt"
        bos.write_text("  \n")
        self.assertIn("Paylaşılacak bir şey yok", self.stop("hizli", "--not-dosya", str(bos)))

    def test_stdin_yedegi_bos_borada_beklemez(self):
        oku, yaz = os.pipe()
        with os.fdopen(oku, "r", encoding="utf-8") as boru, mock.patch.object(sys, "stdin", boru):
            once = datetime.datetime.now()
            self.assertEqual(tf_bilgi.stdin_metni(), "")  # açık ama boş stdin: asılmaz
            self.assertLess((datetime.datetime.now() - once).total_seconds(), 3)
            os.write(yaz, "not ✓\n".encode("utf-8"))
            os.close(yaz)
            self.assertEqual(tf_bilgi.stdin_metni(), "not ✓\n")

    def test_dosya_adlari_temizlenir_ve_tekrar_etmez(self):
        adlar = ["Çalışma Notu.pdf", unicodedata.normalize("NFD", "Şeker Ölçüm.xlsx"), "meta.json", "govde.md",
                 "alt/rapor.md", "rapor.md", "café déjà vu.txt", ".env", "İçerik (son) v2!.md"]
        ekler = []
        for ad in adlar:
            ekler += ["--ek", self.ek(ad, ad)]
        ekler += ["--ek", str(self.ekler / "rapor.md")]  # aynı dosya iki kez: bir kez gider
        r = self.hizli(*ekler, not_metni="not")
        beklenen = ["govde.md", "Calisma-Notu.pdf", "Seker-Olcum.xlsx", "meta-2.json", "govde-2.md", "rapor.md",
                    "rapor-2.md", "cafe-deja-vu.txt", "env", "Icerik-son-v2.md"]
        self.assertEqual(r["dosyalar"], beklenen)
        for ad in beklenen:
            self.assertRegex(ad, r"^[A-Za-z0-9._-]+$")
        kayit = self.kayit(self.EKIP, r["kod"])
        self.assertEqual(sorted(kayit), sorted(beklenen + ["meta.json"]))
        self.assertEqual(kayit["meta-2.json"], b"meta.json")  # kullanıcının meta.json'u kaydın meta'sını ezmez
        self.assertEqual(json.loads(kayit["meta.json"])["mesaj_kimligi"], r["kod"])
        self.assertIn(" · Çalışma Notu.pdf, Şeker Ölçüm.xlsx, meta.json +6 dosya + not · ", unicodedata.normalize("NFC", r["satir"]))

    def test_boyut_sinirlari_agdan_once(self):
        with mock.patch.object(tf_bilgi, "YUKLEME_DOSYA_AZAMI", 10), mock.patch.object(tf_bilgi, "YUKLEME_KAYIT_AZAMI", 15):
            self.assertIn("buyuk.bin çok büyük", self.stop("hizli", "--ek", self.ek("buyuk.bin", b"x" * 11)))
            a, b = self.ek("a.md", "x" * 8), self.ek("b.md", "y" * 8)
            self.assertIn("toplamı çok büyük", self.stop("hizli", "--ek", a, "--ek", b))
            self.assertIn("toplamı çok büyük", self.stop("hizli", "--ek", a, stdin="z" * 8))  # not da sayılır
            self.assertIn("notun çok büyük", self.stop("hizli", stdin="n" * 11))
        self.assertEqual(self.gh.cagrilar, [])
        self.assertEqual(self.yetki_cagrilari(self.EKIP), [])
        self.assertEqual((tf_bilgi.HIZLI_DOSYA_AZAMI, tf_bilgi.HIZLI_KAYIT_AZAMI), (50 * 1048576, 100 * 1048576))
        self.assertEqual((tf_bilgi.YUKLEME_DOSYA_AZAMI, tf_bilgi.YUKLEME_KAYIT_AZAMI), (90 * 1048576, 900 * 1048576))
        with mock.patch.object(tf_bilgi, "HIZLI_DOSYA_AZAMI", 10):  # yazan yolu (GitHub blob): yazmadan önce durur
            self.assertIn("buyuk.bin çok büyük", self.stop("hizli", "--ek", self.ek("buyuk.bin", b"x" * 11)))
        self.assertFalse([c for c in self.gh.cagrilar if c[0] in ("POST", "PATCH")])
        self.assertIn("Paylaşılacak bir şey yok", self.stop("hizli", stdin=" \n\n"))
        self.assertIn("Ek bulunamadı", self.stop("hizli", "--ek", str(self.ekler / "yok.pdf")))
        self.assertIn("mutlak yol", self.stop("hizli", "--ek", "goreli.pdf"))
        self.assertIn("/toplu-paylas", self.stop("hizli", "--ek", str(self.ekler)))

    def test_ileri_sarilamazsa_dal_basini_yeniden_okur(self):
        self.gh.yaris[self.EKIP] = 2  # iki kez tam o anda başkası push eder
        r = self.hizli(not_metni="yarış")
        self.assertEqual(len([c for c in self.gh.cagrilar if c[0] == "PATCH"]), 3)
        dosyalar = self.gh.dosyalar(self.EKIP)
        self.assertEqual(len([y for y in dosyalar if y.startswith("baska/")]), 2)  # başkasının işi korunur
        self.assertEqual(self.kayit(self.EKIP, r["kod"])["govde.md"], b"yar\xc4\xb1\xc5\x9f")
        self.assertEqual(self.gh.mesajlar(self.EKIP)[1], "başkası")  # bizimki onun üstüne
        self.gh.yaris[self.EKIP] = 4  # ilk deneme + 3 yeniden deneme de yetişemez
        once = len([c for c in self.gh.cagrilar if c[0] == "PATCH"])
        out = self.stop("hizli", stdin="yine")
        self.assertIn("Gönderilemedi", out)
        self.assertIn("Hiçbir şey kaydedilmedi", out)
        self.assertEqual(len([c for c in self.gh.cagrilar if c[0] == "PATCH"]) - once, 4)
        self.assertFalse(any(y.endswith("/govde.md") and v == b"yine" for y, v in self.gh.dosyalar(self.EKIP).items()))

    def test_kopru_yolu_en_kucuk_taslak_klonsuz(self):
        os.environ["FAKE_GH_LOGIN"] = ""  # GitHub girişi yok
        self.anahtar_kur()
        kopru = SahteKopru({})
        with mock.patch.object(tf_bilgi, "kopru_tasi", kopru):
            r = self.hizli("--ek", self.ek("Çalışma.md", "içerik GIZLI-ANAHTAR-1"), not_metni="Mert'e bilgi\n")
            self.assertEqual((r["kod"], r["yol"], r["alan"], r["dosyalar"]),
                             ("G-abc000", "kopru", "ekip", ["govde.md", "Calisma.md"]))
            self.assertEqual(r["satir"], "Gönderildi ✓ G-abc000 · Çalışma.md + not · ekip · kütüphaneci yarın 09:05 turunda "
                                         "dosyalar, alıcılara o an haber gider · geri al: /paylas geri-al G-abc000")
            islemler = [c["islem"] for c in kopru.cagrilar]
            self.assertEqual((islemler[:2], islemler[-1], set(islemler)),  # protokolsüz eski köprü: önce kim, eski akış
                             (["kim", "baslat"], "bitir", {"kim", "baslat", "parca", "bitir"}))
            self.assertNotIn("alan", kopru.islemler("baslat")[0])  # eski köprüye yeni alanlar gitmez
            self.assertEqual(kopru.islemler("baslat")[0]["taslak"], HIZLI_TASLAK)  # sözleşme: aynen bu taslak
            self.assertEqual(kopru.kayitlar["G-abc000"]["veri"],
                             {"govde.md": "Mert'e bilgi\n".encode(), "Calisma.md": "içerik GIZLI-ANAHTAR-1".encode()})
            r = self.hizli("--haber", "simdi", "--ek", self.ek("x.pdf", b"%PDF"))
            self.assertEqual(kopru.islemler("baslat")[-1]["taslak"], {**HIZLI_TASLAK, "haber": "simdi"})
            self.assertEqual([d["ad"] for d in kopru.islemler("baslat")[-1]["dosyalar"]], ["x.pdf"])  # notsuz: govde yok
            # Yalnız not: köprü hızlı kayıtta en az bir dosya ister → not govde.md olarak gider (KB tf-bilgi#6)
            gecici = self.cache / "gecici"
            gecici.mkdir(parents=True, exist_ok=True)
            (gecici / "not-1.txt").write_text("Yalnız not: Mert'e Cuma'ya kadar\n", encoding="utf-8")
            yalniz_not = self.ok("hizli", "--not-dosya", str(gecici / "not-1.txt"))
            self.assertEqual(yalniz_not["dosyalar"], ["govde.md"])
            self.assertIn(" · not · ekip · ", yalniz_not["satir"])
            baslat = kopru.islemler("baslat")[-1]
            self.assertEqual([d["ad"] for d in baslat["dosyalar"]], ["govde.md"])
            self.assertEqual(kopru.kayitlar[yalniz_not["kod"]]["veri"],
                             {"govde.md": "Yalnız not: Mert'e Cuma'ya kadar\n".encode()})
            self.assertFalse((gecici / "not-1.txt").exists())
            self.assertIn("Paylaşılacak bir şey yok", self.stop("hizli", stdin=" \n"))  # boş: köprüye hiç gitmez
            self.assertEqual(len(kopru.islemler("baslat")), 3)
            self.assertEqual(r["dosyalar"], ["x.pdf"])
            self.assertIn(" · x.pdf · ekip · ", r["satir"])
            self.assertIn("Bu köprü anahtarı eski: yönetime gönderemez", self.stop("hizli", "--yonetim",
                                                                                     stdin="yönetim için"))
            with mock.patch.dict(tf_bilgi.KOPRU_SINIRLAR, {"dosya_azami_bayt": 4}):
                self.assertIn("x.pdf çok büyük", self.stop("hizli", "--ek", self.ek("x.pdf", b"%PDF-1")))
        self.assertEqual(self.gh.cagrilar, [])  # GitHub'a gidilmedi
        self.assertFalse((self.cache / "kopru").exists())  # köprü aynası ve kb.py gerekmedi
        self.assertEqual(json.loads((self.cache / "hizli.json").read_text())["gonderilen"]["G-abc000"]["yol"], "kopru")

    def test_kopru_taslagi_dogrulamasi(self):
        taslak, notlar = tf_bilgi.taslak_dogrula(dict(HIZLI_TASLAK), {}, None)
        self.assertEqual((taslak, notlar), (HIZLI_TASLAK, []))
        for degisiklik, parca in (({"hizli": False}, "tur geçersiz"), ({"hizli": False, "tur": "analiz"}, "haber yalnız"),
                                  ({"gizli": True}, "hizli taslak gizli olamaz"), ({"hizli": "evet"}, "hizli true")):
            with self.assertRaises(tf_bilgi.Stop) as ctx:
                tf_bilgi.taslak_dogrula({**HIZLI_TASLAK, **degisiklik}, {}, None)
            self.assertIn(parca, str(ctx.exception), degisiklik)
        normal, _ = tf_bilgi.taslak_dogrula({**HIZLI_TASLAK, "hizli": False, "tur": "analiz", "haber": None}, {}, None)
        self.assertNotIn("hizli", normal)  # yalnız hızlı taslakta gider

    def test_ne_yazan_ne_kopru(self):
        mesaj = ("Slack'te TF Bilgi botuna `anahtar` yaz; gelen satırı terminale yapıştır, sonra /paylas'ı tekrar "
                 "dene.")
        os.environ["FAKE_GH_PUSH"] = "false"
        self.assertEqual(self.stop("hizli", stdin="not").strip(), mesaj)
        self.assertEqual(self.stop("hizli", stdin="not").strip(), mesaj)
        self.assertEqual(len(self.yetki_cagrilari(self.EKIP)), 2)  # önbellekteki "yok" bir kez taze denetlenir
        code, out, _ = self.cli("hizli", stdin="gerçek stdin ile\n")
        self.assertEqual((code, out.strip()), (2, mesaj))
        os.environ["FAKE_GH_PUSH"] = "true"
        with mock.patch.object(tf_bilgi, "which", lambda ad: None if ad == "gh" else shutil.which(ad)):
            self.assertEqual(self.stop("hizli", stdin="not").strip(), mesaj)  # gh kurulu değil: GitHub'sız kişi
        os.environ["FAKE_GH_LOGIN"] = ""  # gh var, oturum yok, bu makinede yazan görülmedi: anahtar yolu
        (self.cache / "hizli.json").unlink()
        self.assertEqual(self.stop("hizli", stdin="not").strip(), mesaj)
        os.environ["FAKE_GH_LOGIN"] = "ayse-gh"
        os.environ["TF_BILGI_YOL"] = "dogrudan"
        os.environ["FAKE_GH_PUSH"] = "false"
        self.anahtar_kur()
        self.assertEqual(self.stop("hizli", stdin="not").strip(), mesaj)  # anahtar var ama yol doğrudana zorlandı
        self.assertFalse([c for c in self.gh.cagrilar if c[0] != "GET"])  # yalnız kisiler.json okundu
        self.assertFalse(self.zil_cagrilari())

    def test_yonetim_kendi_deposuna(self):
        r = self.hizli("--yonetim", "--ek", self.ek("butce.xlsx", b"PK\x03\x04"), not_metni="C-level için bütçe\n")
        self.assertEqual((r["alan"], r["yol"]), ("yonetim", "writer"))
        self.assertIn(" · butce.xlsx + not · yönetim · kütüphaneci birkaç dakika içinde ", r["satir"])
        self.assertEqual(self.zil_cagrilari()[-1], ("POST", f"repos/{self.EKIP}/issues/10/labels"))  # yönetim zili
        meta = json.loads(self.kayit(self.YONETIM, r["kod"])["meta.json"])
        self.assertEqual((meta["alan"], meta["gonderen"]), ("yonetim", "ayse"))
        self.assertEqual(self.kayit(self.EKIP, r["kod"]), {})  # ekip deposuna hiçbir şey girmedi
        self.assertEqual(self.gh.mesajlar(self.EKIP), ["tohum"])
        self.assertEqual(len(self.yetki_cagrilari(self.YONETIM)), 1)
        del self.gh.depolar[self.YONETIM]  # depo henüz açılmadı: yetki denetlenemez, yazma denenir ve söylenir
        os.environ["FAKE_GH_REPO_CIKIS"] = "1"
        (self.cache / "hizli.json").unlink()
        out = self.stop("hizli", "--yonetim", stdin="yönetime")
        self.assertIn("eneskrblt/tf-bilgi-yonetim deposu bulunamadı ya da erişimin yok", out)

    def test_kopru_anahtari_ve_tf_bilgi_klasoru_paylasilmaz(self):
        anahtarli = self.ek("kurulum.md", "anahtarım " + KOPRU_ANAHTAR)
        ikili = self.ek("x.bin", b"\x00\x01" + KOPRU_ANAHTAR.encode() + b"\xff")
        self.anahtar_kur()
        klon = self.cache / "tf-bilgi" / "kisiler.json"
        klon.parent.mkdir(parents=True)
        klon.write_text("{}")
        bag = self.tmp / "bag.md"
        bag.symlink_to(self.cache / "anahtar")
        gecici_not = self.cache / "gecici" / "not.md"
        gecici_not.parent.mkdir(parents=True)
        gecici_not.write_text("not")
        bag2 = self.tmp / "bag2.md"
        bag2.symlink_to(gecici_not)
        for argv, stdin, parca in ((("--ek", anahtarli), "", "Köprü anahtarı paylaşılmaz: kurulum.md"),
                                   (("--ek", ikili), "", "Köprü anahtarı paylaşılmaz: x.bin"),
                                   ((), "anahtar: " + KOPRU_ANAHTAR, "Köprü anahtarı paylaşılmaz: notun"),
                                   (("--ek", str(self.cache / "anahtar")), "", "anahtar: TF Bilgi'nin kendi klasöründeki"),
                                   (("--ek", str(klon)), "", "kisiler.json: TF Bilgi'nin kendi klasöründeki"),
                                   (("--ek", str(bag)), "", "bag.md: TF Bilgi'nin kendi klasöründeki"),
                                   (("--ek", str(bag2)), "", "bag2.md: TF Bilgi'nin kendi klasöründeki")):
            out = self.stop("hizli", *argv, stdin=stdin)
            self.assertIn(parca, out, argv)
            self.assertNotIn(KOPRU_GIZLI, out)
            self.assertIn("Hiçbir şey gönderilmedi", out)
        self.assertEqual(self.gh.cagrilar, [])
        self.assertEqual(self.yetki_cagrilari(self.EKIP), [])
        # gecici/'deki dosya (ör. /paylas'ın yazdığı özet) gider ve gönderildikten sonra silinir; sır engellemez
        r = self.hizli("--ek", str(gecici_not), "--ek", self.ek("env.txt", "OPENAI_API_KEY=sk-proj-abcdefghijklmnopqrstu"),
                       not_metni="şifre: 1234")
        self.assertEqual(self.kayit(self.EKIP, r["kod"])["not.md"], b"not")
        self.assertFalse(gecici_not.exists())
        self.assertTrue((self.ekler / "env.txt").exists())  # kullanıcının kendi dosyası silinmez

    def test_kisi_cozulemezse_ya_da_baskasi_adina_durur(self):
        os.environ["FAKE_GH_LOGIN"] = "yabanci-gh"
        self.assertIn("Kim olduğunuz bulunamadı", self.stop("hizli", stdin="not"))
        self.assertEqual(sum("/contents/kisiler.json" in c[1] for c in self.gh.cagrilar), 2)  # bir kez taze bakıldı
        os.environ["TF_BILGI_KISI"] = "mert"
        r = self.hizli(not_metni="mert olarak")  # gh girişi eşlenmiyorsa TF_BILGI_KISI geçerli
        self.assertEqual(json.loads(self.kayit(self.EKIP, r["kod"])["meta.json"])["gonderen"], "mert")
        os.environ["FAKE_GH_LOGIN"] = "ayse-gh"
        self.assertIn("Başkası adına paylaşılmaz", self.stop("hizli", stdin="not"))

    def test_zorlanan_yol(self):
        self.anahtar_kur()
        kopru = SahteKopru({})
        with mock.patch.object(tf_bilgi, "kopru_tasi", kopru):
            self.assertEqual(self.hizli(not_metni="yazan, anahtarı da var")["yol"], "writer")  # yazan önce gelir
            os.environ["TF_BILGI_YOL"] = "kopru"
            self.assertEqual(self.hizli(not_metni="köprüye zorla")["yol"], "kopru")
            os.environ["TF_BILGI_YOL"] = "bilmem"
            self.assertIn("TF_BILGI_YOL anlaşılmadı", self.stop("hizli", stdin="x"))
        self.assertEqual(len(kopru.islemler("baslat")), 1)

    def test_geri_al_dosyalanmamis_kaydi_siler(self):
        r = self.hizli("--ek", self.ek("a.md", "a"), not_metni="geri alacağım")
        kod = r["kod"]
        self.assertEqual(len(self.kayit(self.EKIP, kod)), 3)
        g = self.ok("geri-al", kod)
        self.assertEqual((g["sonuc"], g["yol"], g["alan"]), ("silindi", "writer", "ekip"))
        self.assertEqual(g["satir"], f"Geri alındı: {kod} dosyalanmadan önce kaldırıldı (içerik git geçmişinde durur; "
                                     "gerekiyorsa Enes'e haber ver).")
        self.assertEqual(self.kayit(self.EKIP, kod), {})
        self.assertEqual(self.gh.mesajlar(self.EKIP)[:2], [f"gelen: {kod} geri alındı", f"gelen: {kod} · ayse · 2 dosya"])
        self.assertIn("00-gelen/.gitkeep", self.gh.dosyalar(self.EKIP))  # yalnız o klasör silindi
        r = self.hizli("--yonetim", not_metni="yönetim")
        self.assertEqual(self.ok("geri-al", r["kod"])["alan"], "yonetim")
        self.assertEqual(self.kayit(self.YONETIM, r["kod"]), {})

    def test_geri_al_dosyalanmissa_kayit_yazar(self):
        r = self.hizli(not_metni="dosyalanacak")
        kod = r["kod"]
        klasor = f"00-gelen/20261105-123000-ayse-{kod[2:]}"
        kayit = self.kayit(self.EKIP, kod)
        self.gh.baskasi_yazar(self.EKIP, {**{f"{klasor}/{a}": None for a in kayit},
                                          **{f"arsiv/{klasor}/{a}": v for a, v in kayit.items()}},
                              "kutuphaneci: dosyala")  # kütüphaneci dosyaladı ve arşivledi
        os.environ["TF_BILGI_SIMDI"] = "2026-11-05T14:00:00+03:00"
        g = self.ok("geri-al", kod)
        self.assertEqual((g["sonuc"], g["yol"]), ("kaydedildi", "writer"))
        self.assertEqual(g["satir"], "Geri alma isteği kaydedildi; kütüphaneci sonraki turda girdiyi iptal eder.")
        yeni = self.kayit(self.EKIP, g["kod"])
        self.assertEqual(list(yeni), ["meta.json"])
        self.assertIn(f"00-gelen/20261105-140000-ayse-{g['kod'][2:]}/meta.json", self.gh.dosyalar(self.EKIP))
        meta = json.loads(yeni["meta.json"])
        self.assertEqual(set(meta), set(META_ANAHTARLARI) | {"geri_alinan"})
        self.assertEqual((meta["tur"], meta["geri_alinan"], meta["dosyalar"], meta["gonderen"], meta["mesaj_kimligi"],
                          meta["alinma"], meta["alan"]),
                         ("geri-al", kod, [], "ayse", g["kod"], "2026-11-05T14:00:00+03:00", "ekip"))
        self.assertEqual(self.gh.mesajlar(self.EKIP)[0], f"gelen: {g['kod']} · ayse · geri-al {kod}")

    def test_geri_al_baska_makinedeki_kod(self):
        """Bu makinede gönderilmemiş kod: 00-gelen'de yoksa anahtarlıda önce köprüye sorulur; köprü tanımazsa kayıt."""
        self.gh.baskasi_yazar(self.EKIP, {"00-gelen/20261105-090000-ayse-q1w2e3/meta.json": "{}",
                                          "00-gelen/20261105-090000-mert-z9z9z9/meta.json": "{}"})
        self.assertEqual(self.ok("geri-al", "G-q1w2e3")["sonuc"], "silindi")  # yerel geçmiş olmadan da bulunur
        once = self.gh.depolar[self.EKIP]["ref"]
        self.assertEqual(self.stop("geri-al", "G-z9z9z9").strip(), "Bu kod senin paylaşımın değil.")  # başkasının kaydı
        self.assertEqual(self.gh.depolar[self.EKIP]["ref"], once)  # ne silindi ne geri-al kaydı yazıldı
        self.assertIn("00-gelen/20261105-090000-mert-z9z9z9/meta.json", self.gh.dosyalar(self.EKIP))
        self.anahtar_kur()
        kopru = SahteKopru({})
        with mock.patch.object(tf_bilgi, "kopru_tasi", kopru):
            self.assertEqual(self.ok("geri-al", "G-abc123")["yol"], "kopru")  # köprü kaydıymış
            kopru.hatalar["geri-al"] = ("G-yok999 bulunamadı (kod yanlış ya da çok eski).", "yok")
            g = self.ok("geri-al", "G-yok999")
            self.assertEqual((g["yol"], g["sonuc"]), ("writer", "kaydedildi"))
            self.assertEqual(json.loads(self.kayit(self.EKIP, g["kod"])["meta.json"])["geri_alinan"], "G-yok999")
            kopru.hatalar["geri-al"] = ("Anahtar geçersiz.", "anahtar")
            self.assertIn("Anahtar geçersiz", self.stop("geri-al", "G-baska1"))
            os.environ["FAKE_GH_PUSH"] = "false"
            (self.cache / "hizli.json").unlink()
            del kopru.hatalar["geri-al"]
            self.assertEqual(self.ok("geri-al", "G-abc123")["yol"], "kopru")  # yazan değil: bugünkü köprü akışı
        self.assertEqual(len(kopru.islemler("geri-al")), 4)


    # .github#13 review: yanlış dosya sessizce gitmez, başkasının kodu geri alınmaz, oturum kapalı mesajı.

    def test_otomatik_yalniz_belge_benzeri_dosya(self):
        mesaj = "Hangi dosyayı paylaşacağımı bilemedim; dosya yolunu yaz: /paylas <dosya> …"
        for ad in (".env", ".env.local", "id_rsa", "server.pem", "anahtar.key", "app.py", "index.ts", "ayar.json",
                   "ci.yml", "Makefile", ".gizli.md"):
            self.assertEqual(self.stop("hizli", "--otomatik", "--ek", self.ek(ad, "x"), stdin="toplantı bitti").strip(),
                             mesaj, ad)
        bag = self.ekler / "rapor.md"
        bag.symlink_to(self.ek(".env", "SIR=1"))  # belge adlı bağlantı .env'e gidiyor
        self.assertEqual(self.stop("hizli", "--otomatik", "--ek", str(bag)).strip(), mesaj)
        self.assertEqual(self.gh.cagrilar, [])  # hiçbir şey gönderilmedi
        adlar = ["Rapor.HTML", "sunum.pdf", "ozet.md", "not.txt", "teklif.docx", "deste.pptx", "tablo.xlsx", "veri.csv",
                 "ekran.png", "foto.JPG", "foto2.jpeg", "anim.gif", "gorsel.webp", "eski.htm"]
        for ad in adlar:
            self.assertTrue(tf_bilgi.belge_mi(ad), ad)
        r = self.hizli("--otomatik", "--ek", self.ek("Haftalık Rapor (v3).html", "<h1>x</h1>"), not_metni="Ayşe'ye\n")
        self.assertIn(" · Haftalık Rapor (v3).html + not · ", r["satir"])
        r = self.hizli("--ek", self.ek("app.py", "print(1)"))  # açıkça verilen yol: her tür gider
        self.assertIn(" · app.py · ekip · ", r["satir"])

    def test_makbuz_dosya_adlari_kisaltilir(self):
        uzun = "Q4 2026 Türkiye pazarı kampanya performans analizi ve öneriler son hali.pdf"
        r = self.hizli("--ek", self.ek(uzun, "%PDF"), "--ek", self.ek("b.md", "b"), "--ek", self.ek("c.md", "c"),
                       "--ek", self.ek("d.md", "d"))
        bolum = r["satir"].split(" · ")[1]
        ilk = bolum.split(", ")[0]
        self.assertEqual(len(ilk), 40)
        self.assertTrue(ilk.endswith("….pdf") and ilk.startswith("Q4 2026 Türkiye"), ilk)
        self.assertEqual(bolum, f"{ilk}, b.md, c.md +1 dosya")
        self.assertEqual(tf_bilgi.kisalt_ad("satir\nkir.md"), "satir kir.md")  # kontrol karakteri tek satıra iner

    def test_geri_al_baskasinin_kodu_reddedilir(self):
        """Bekleyen (00-gelen) ve dosyalanmış (arsiv/00-gelen) başkasının kaydı: çıkış 2, commit yok, meta yok."""
        self.gh.baskasi_yazar(self.EKIP, {"00-gelen/20261105-090000-mert-m1m1m1/meta.json": "{}",
                                          "00-gelen/20261105-090000-mert-m1m1m1/govde.md": "mert'in notu",
                                          "arsiv/00-gelen/20261104-090000-mert-a1a1a1/meta.json": "{}"})
        self.anahtar_kur()  # anahtar olsa da köprüye sorulmaz: kod depoda başkasının
        kopru = SahteKopru({})
        once = self.gh.depolar[self.EKIP]["ref"]
        with mock.patch.object(tf_bilgi, "kopru_tasi", kopru):
            for kod in ("G-m1m1m1", "G-a1a1a1"):
                self.assertEqual(self.stop("geri-al", kod).strip(), "Bu kod senin paylaşımın değil.", kod)
        self.assertEqual(self.gh.depolar[self.EKIP]["ref"], once)
        self.assertEqual(kopru.cagrilar, [])
        self.assertFalse([c for c in self.gh.cagrilar if c[0] in ("POST", "PATCH")])
        # kendi dosyalanmış kaydı: geri-al kaydı yazılır (kütüphaneci GOREV 2.G.0 klasörü -<gonderen>-<kimlik> ister)
        self.gh.baskasi_yazar(self.EKIP, {"arsiv/00-gelen/20261104-100000-ayse-k1k1k1/meta.json": "{}"})
        g = self.ok("geri-al", "G-k1k1k1")
        self.assertEqual((g["sonuc"], g["yol"]), ("kaydedildi", "writer"))
        meta = json.loads(self.kayit(self.EKIP, g["kod"])["meta.json"])
        self.assertEqual((meta["gonderen"], meta["geri_alinan"]), ("ayse", "G-k1k1k1"))

    def test_arsiv_bin_kayittan_buyuk_olsa_da_bulunur(self):
        """arsiv/00-gelen git trees API ile okunur (contents API klasör başına 1000 öğe döner)."""
        dosyalar = {f"arsiv/00-gelen/20261001-{i:06d}-mert-{i:06d}/meta.json": "{}" for i in range(1100)}
        dosyalar["arsiv/00-gelen/20261105-235959-ayse-zz9999/meta.json"] = "{}"
        self.gh.baskasi_yazar(self.EKIP, dosyalar)
        self.assertEqual(self.ok("geri-al", "G-zz9999")["sonuc"], "kaydedildi")
        self.assertFalse([c for c in self.gh.cagrilar if "/contents/arsiv" in c[1] or "/contents/00-gelen" in c[1]])

    def test_gh_oturumu_kapali_yazan(self):
        mesaj = "GitHub oturumun kapalı ya da bağlantı yok: `gh auth login` yap, sonra tekrar /paylas."
        self.hizli(not_metni="önce yazan olarak bir paylaşım")  # bu makinede yetki önbellekte
        os.environ["FAKE_GH_LOGIN"] = ""  # gh kurulu, oturum kapalı ya da çevrimdışı
        self.assertEqual(self.stop("hizli", stdin="not").strip(), mesaj)  # anahtar yok: "yetkin yok" denmez
        self.assertEqual(self.stop("geri-al", "G-abcdef").strip(), mesaj)
        self.anahtar_kur()
        self.assertEqual(self.stop("hizli", "--yonetim", stdin="yönetim").strip(), mesaj)  # yazan: köprü mesajı değil
        kopru = SahteKopru({})
        with mock.patch.object(tf_bilgi, "kopru_tasi", kopru):
            self.assertEqual(self.hizli(not_metni="ekip")["yol"], "kopru")  # ekipte köprü yine çalışır
            (self.cache / "hizli.json").unlink()  # yazan olduğu bilinmeyen makine + eski anahtar (protokolsüz) + yönetim
            self.assertIn("Bu köprü anahtarı eski: yönetime gönderemez",
                          self.stop("hizli", "--yonetim", stdin="yönetim"))

    # --- 0.9.0: bağlantılar notta, zil, alan kuralı ---

    def test_baglantilar_notta_gider_indirilmez(self):
        """Claude artifact ve Google bağlantıları notun parçasıdır: eksiz de gider, hiçbir şey indirilmez."""
        for baglanti in ("https://claude.ai/artifact/OrnekArtifactKimligi01", "https://claude.ai/code/artifact/ab-12",
                         "https://claude.ai/public/artifacts/0b1c2d3e", "https://claude.site/artifacts/xyz",
                         "https://docs.google.com/spreadsheets/d/1AbC/edit"):
            r = self.hizli(not_metni=f"Ilgım baksın {baglanti}\n")
            kayit = self.kayit(self.EKIP, r["kod"])
            self.assertEqual(sorted(kayit), ["govde.md", "meta.json"], baglanti)
            self.assertIn(baglanti, kayit["govde.md"].decode("utf-8"))
        self.assertFalse(hasattr(tf_bilgi, "ARTIFACT_EKSIZ"))

    def test_zil_hatasi_paylasimi_bozmaz(self):
        self.gh.hatalar[("POST", f"repos/{self.EKIP}/issues/9/labels")] = 500
        r = self.hizli(not_metni="zil bozuk")
        self.assertEqual(r["notlar"], ["Zil çalınamadı; kütüphaneci bir sonraki turda dosyalar."])
        self.assertIn(" · kütüphaneci bir sonraki turunda dosyalar, ", r["satir"])
        self.assertEqual(sorted(self.kayit(self.EKIP, r["kod"])), ["govde.md", "meta.json"])  # paylaşım yazıldı
        self.gh.etiketler[(self.EKIP, 9)] = {"zil"}
        del self.gh.hatalar[("POST", f"repos/{self.EKIP}/issues/9/labels")]
        r = self.hizli(not_metni="zil çalar")
        self.assertEqual(r["notlar"], [])
        self.assertEqual(self.zil_cagrilari()[-2:], [("DELETE", f"repos/{self.EKIP}/issues/9/labels/zil"),
                                                     ("POST", f"repos/{self.EKIP}/issues/9/labels")])
        with mock.patch.object(tf_bilgi, "gh_api", side_effect=OSError("beklenmeyen")):
            notlar = []
            self.assertFalse(tf_bilgi.zil_cal("ekip", notlar))  # her hata yutulur
        self.assertEqual(notlar, ["Zil çalınamadı; kütüphaneci bir sonraki turda dosyalar."])

    def test_rehber_okunamazsa_yazan_ekibe_yazmaz(self):
        """review #15: kisiler.json GitHub'dan o an okunamazsa "Dilara'ya …" sessizce ekibe gitmez; durur."""
        kisiler = json.loads(json.dumps(KISILER))
        kisiler["kisiler"]["dilara"] = {"ad": "Dilara Örnek", "alanlar": ["ekip", "yonetim"]}
        self.gh.baskasi_yazar(self.EKIP, {"kisiler.json": json.dumps(kisiler, ensure_ascii=False)})
        once = {s: self.gh.depolar[s]["ref"] for s in (self.EKIP, self.YONETIM)}
        self.gh.hatalar[("GET", f"repos/{self.EKIP}/contents/kisiler.json")] = 502
        out = self.stop("hizli", stdin="Dilara'ya bütçe tablosu\n")
        self.assertIn("Kişi listesi GitHub'dan okunamadı", out)
        self.assertIn("hiçbir şey gönderilmedi", out)
        self.assertEqual({s: self.gh.depolar[s]["ref"] for s in once}, once)  # iki depoya da commit yok
        self.assertEqual(self.zil_cagrilari(), [])
        del self.gh.hatalar[("GET", f"repos/{self.EKIP}/contents/kisiler.json")]
        r = self.hizli(not_metni="Dilara'ya bütçe tablosu\n")  # GitHub düzelince yönetime
        self.assertEqual((r["alan"], r["alicilar"]), ("yonetim", ["dilara"]))
        self.assertEqual(self.gh.depolar[self.EKIP]["ref"], once[self.EKIP])
        # depo görünmüyor (404): okuyamayan ve anahtarsız kişi zaten gönderemez, tek satırla durur
        self.gh.hatalar[("GET", f"repos/{self.EKIP}/contents/kisiler.json")] = 404
        (self.cache / "hizli.json").unlink()
        os.environ["FAKE_GH_PUSH"] = "false"
        self.assertEqual(self.stop("hizli", stdin="Dilara'ya bütçe\n").strip(), tf_bilgi.HIZLI_YOL_YOK)

    def test_alan_kurali_yazanda(self):
        """§3: --yonetim/--ekip verilmezse alan nottan, gönderenden ve kisiler.json'dan seçilir."""
        kisiler = json.loads(json.dumps(KISILER))
        kisiler["kisiler"].update({"dilara": {"ad": "Dilara Örnek", "alanlar": ["ekip", "yonetim"]},
                                   "ilgim": {"ad": "Ilgım Örnek", "alanlar": ["ekip", "yonetim"]}})
        self.gh.baskasi_yazar(self.EKIP, {"kisiler.json": json.dumps(kisiler, ensure_ascii=False)})
        for notu, alan, alicilar in (("Yöneticilere haftalık özet", "yonetim", None),
                                     ("Dilara'ya sunum, Cuma'ya kadar", "ekip", ["dilara"]),  # ekipten yöneticiye ekipte kalır
                                     ("Ilgım'a karar lazım", "ekip", ["ilgim"]),
                                     ("Dilara ve Mert'e", "ekip", ["dilara", "mert"]),
                                     ("ekip için Dilara'ya", "ekip", None),
                                     ("Yönetim paneli hatası", "ekip", []),
                                     ("Pazartesi notları", "ekip", [])):
            r = self.hizli(not_metni=notu + "\n")
            self.assertEqual((r["alan"], r["alicilar"]), (alan, alicilar), notu)
            depo = self.YONETIM if alan == "yonetim" else self.EKIP
            self.assertEqual(json.loads(self.kayit(depo, r["kod"])["meta.json"])["alan"], alan, notu)
            self.assertEqual(self.zil_cagrilari()[-1][1], f"repos/{self.EKIP}/issues/{9 if alan == 'ekip' else 10}/labels")
        r = self.hizli("--ekip", not_metni="Dilara'ya")  # bayrak kuralı ezer
        self.assertEqual((r["alan"], r["alicilar"]), ("ekip", None))
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            tf_bilgi.main(["hizli", "--ekip", "--yonetim"])  # ikisi birden olmaz


class HizliYardimciTest(unittest.TestCase):
    def test_gh_api_komutu_govde_stdin_ve_http_kodu(self):
        cagrilar = []

        def sahte_sh(cmd, cwd=None, check=True, timeout=120, env=None, girdi=None):
            cagrilar.append((cmd, girdi))
            if cmd[2].endswith("/refs/heads/main"):
                return subprocess.CompletedProcess(cmd, 1, stdout='{"message": "Update is not a fast forward"}',
                                                   stderr="gh: Update is not a fast forward (HTTP 422)\n")
            if cmd[2] == "repos/o/r/bozuk":
                return subprocess.CompletedProcess(cmd, 0, stdout="<html>", stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout='{"sha": "abc"}', stderr="")

        with mock.patch.object(tf_bilgi, "sh", sahte_sh):
            self.assertEqual(tf_bilgi.gh_api("POST", "repos/o/r/git/trees", {"tree": [{"content": "Çalışma ✓"}]}),
                             {"sha": "abc"})
            with self.assertRaises(tf_bilgi.GhHatasi) as ctx:
                tf_bilgi.gh_api("PATCH", "repos/o/r/git/refs/heads/main", {"sha": "abc", "force": False})
            self.assertEqual(ctx.exception.http, 422)
            self.assertIsInstance(ctx.exception, tf_bilgi.Stop)
            self.assertEqual(tf_bilgi.gh_api("GET", "repos/o/r/branches/main"), {"sha": "abc"})
            with self.assertRaises(tf_bilgi.GhHatasi):
                tf_bilgi.gh_api("GET", "repos/o/r/bozuk")
        (cmd, girdi), (cmd2, girdi2), (cmd3, girdi3) = cagrilar[:3]
        self.assertEqual(cmd, ["gh", "api", "repos/o/r/git/trees", "-X", "POST", "--input", "-"])
        self.assertTrue(girdi.isascii())  # gövde ASCII kaçışlı JSON: yerel kodlamadan bağımsız
        self.assertEqual(json.loads(girdi)["tree"][0]["content"], "Çalışma ✓")
        self.assertEqual(json.loads(girdi2), {"sha": "abc", "force": False})
        self.assertEqual((cmd3, girdi3), (["gh", "api", "repos/o/r/branches/main", "-X", "GET"], None))

    def test_dosyalama_metni_ve_not_ozeti(self):
        for d, beklenen in (("10 dk içinde", "10 dk içinde"), ("bugün 15:05", "bugün 15:05 turunda"),
                            ("Pzt 09:05", "Pzt 09:05 turunda"), (None, "bir sonraki turunda"), ("", "bir sonraki turunda")):
            self.assertEqual(tf_bilgi.dosyalama_metni(d), beklenen, d)
        self.assertEqual(tf_bilgi.not_ozeti("\n Birinci satır \n\nikinci\n3\n4\n5\n6\n", "x.pdf"),
                         ("Birinci satır", "Birinci satır\nikinci\n3\n4\n5"))
        self.assertEqual(tf_bilgi.not_ozeti("  \n", "Çalışma Notu.pdf"), ("Çalışma Notu.pdf", ""))



ALICI_VEKTORLERI = json.loads((Path(__file__).resolve().parent / "alici_vektorleri.json").read_text(encoding="utf-8"))


class AlanKuraliTest(unittest.TestCase):
    """Bitiş tasarımı §3: ekip mi yönetim mi. KB araclar/alici.py ile ortak vektörler (tests/alici_vektorleri.json)."""

    def test_ortak_vektorler(self):
        v = ALICI_VEKTORLERI
        self.assertGreaterEqual(len(v["vektorler"]), 30)
        for d in v["vektorler"]:
            sonuc = tf_bilgi.alan_sec(d["metin"], d["gonderen"], v["kisiler"])
            self.assertEqual((sonuc["alan"], sonuc["alicilar"]), (d["alan"], d["alicilar"]), d)
            self.assertTrue(sonuc["neden"].startswith("kural "), d)

    def test_kural_parametreleri_ortak_dosyayla_ayni(self):
        v = ALICI_VEKTORLERI
        self.assertEqual(tf_bilgi.YONETIM_KISILERI, frozenset(v["yonetim_kisileri"]))
        self.assertEqual(tf_bilgi.YONETIMI_GORENLER, frozenset(v["yonetimi_gorenler"]))
        self.assertEqual(tf_bilgi.YALNIZ_YONETIM, frozenset(v["yalniz_yonetim"]))
        self.assertEqual(tuple(tf_bilgi.YONETIM_KELIMELERI), tuple(v["yonetim_kelimeleri"]))
        self.assertEqual(tuple(tf_bilgi.YONETIM_TAMLAMA_BASI), tuple(v["yonetim_tamlama_basi"]))
        self.assertEqual(tuple(tf_bilgi.YONETIM_IYELIK_BELIRSIZ), tuple(v["yonetim_iyelik_belirsiz"]))
        self.assertEqual(tuple(tf_bilgi.YONETIM_BELIRTME_ONCESI), tuple(v["yonetim_belirtme_oncesi"]))
        self.assertEqual(tuple(tf_bilgi.YONETIM_BELIRTME_FIILLERI), tuple(v["yonetim_belirtme_fiilleri"]))
        self.assertEqual(tuple(tf_bilgi.AD_EKLERI), tuple(v["ekler"]))

    def test_yonetim_kelimesi_cekimleri(self):
        """review tf-bilgi#11: ekli biçimler yönetim; iyelik/tamlama biçimleri değil."""
        for metin in ("Yönetimle paylaşılsın", "Yöneticiye iletir misin", "Yönetimin bilgisine", "yönetimde konuşalım",
                      "yöneticilerimize", "Lütfen yönetimi bilgilendir", "yöneticileri toplayalım"):
            self.assertEqual(tf_bilgi.alan_sec(metin, "nil", {})["alan"], "yonetim", metin)
        for metin in ("Hesap yöneticisine devir", "proje yöneticimiz", "Kampanya yönetimi notu", "yönetim panelinde",
                      "Proje yöneticileri için", "kampanya yönetiminde"):
            self.assertEqual(tf_bilgi.alan_sec(metin, "nil", {})["alan"], "ekip", metin)
        self.assertEqual(tf_bilgi.yonetim_kelimesi("Yöneticilere"), "yöneticilere")
        # hizli_alan kelimeyi görünce kişi listesine bakmadan yönetim der
        self.assertTrue(tf_bilgi.yonetim_kelimesi("yönetimle"))

    def test_kisiler_bos_ya_da_bilinmeyen(self):
        self.assertEqual(tf_bilgi.alan_sec("Enes'e", None, {})["alan"], "ekip")  # rehber yok: alıcı bulunamaz
        self.assertEqual(tf_bilgi.alan_sec("yönetim için", None, {})["alan"], "yonetim")
        self.assertEqual(tf_bilgi.alan_sec("", "ogi", {})["alan"], "yonetim")
        self.assertEqual(tf_bilgi.alan_sec("x", None, {"_not": "yorum", "enes": None})["alan"], "ekip")


KOPRU_CF_GIZLI = "fedcba9876543210" * 4
KOPRU_CF_ANAHTAR = f"tfb1.cf1.{KOPRU_CF_GIZLI}"
OKUMA_YOK = "Okuma köprüde yok: belgeler sana Slack'ten bağlantıyla gelir."


class SahteWorker:
    """Cloudflare Worker köprüsünün (cf1) ağsız karşılığı: JSON işlemler `kopru_tasi`, ham parçalar `kopru_ham_tasi`
    yerine çağrılır. Belirteçler sahte ama opak: istemci yalnız geri getirir."""

    def __init__(self):
        self.cagrilar, self.adresler, self.parcalar, self.kayitlar = [], [], [], {}
        self.hatalar = {}        # islem → (mesaj, kod)
        self.parca_kopuk = {}    # (ad, sira) → kaç kez bağlantı hatası
        self.parca_drive = {}    # (ad, sira) → kaç kez geçici Drive hatası
        self.parca_red = {}      # (ad, sira) → (mesaj, kod): kalıcı ret
        self.parca_bayt = 4
        self.ben = "mert"
        self.kisiler = {"ayse": {"ad": "Ayşe Örnek", "alanlar": ["ekip", "yonetim"]},
                        "mert": {"ad": "Mert Örnek", "alanlar": ["ekip"]},
                        "dilara": {"ad": "Dilara Örnek", "alanlar": ["ekip", "yonetim"]},
                        "ilgim": {"ad": "Ilgım Örnek", "alanlar": ["ekip", "yonetim"]}}

    @staticmethod
    def yanit(veri):
        return json.dumps(veri, ensure_ascii=False).encode("utf-8")

    @staticmethod
    def red(mesaj, kod):
        return {"tamam": False, "kod": kod, "mesaj": mesaj, "hata": mesaj}

    def islemler(self, ad=None):
        return [c for c in self.cagrilar if ad is None or c["islem"] == ad]

    def __call__(self, adres, veri, zaman_asimi):
        g = json.loads(veri.decode("utf-8"))
        self.adresler.append(adres)
        self.cagrilar.append(g)
        if g.get("anahtar") != KOPRU_CF_GIZLI or g.get("s") != 1:
            return self.yanit(self.red("Anahtar tanınmadı.", "anahtar"))
        islem = g["islem"]
        if islem in self.hatalar:
            return self.yanit(self.red(*self.hatalar[islem]))
        if islem in ("oku", "ara", "yorumlar", "yorum", "tercih"):
            return self.yanit(self.red(OKUMA_YOK, "desteklenmiyor"))
        return self.yanit({"tamam": True, **getattr(self, "i_" + islem.replace("-", "_"))(g)})

    def ham(self, adres, veri, basliklar, zaman_asimi):
        self.parcalar.append((adres, dict(basliklar), len(veri)))
        if basliklar.get("Authorization") != f"Bearer {KOPRU_CF_ANAHTAR}":
            return self.yanit(self.red("Anahtar tanınmadı.", "anahtar"))
        _, kod, ad = basliklar["X-Tfb-Yukleme"].split("|")
        sira = int(basliklar["X-Tfb-Sira"])
        if self.parca_kopuk.get((ad, sira)):
            self.parca_kopuk[(ad, sira)] -= 1
            raise tf_bilgi.urllib.error.URLError("bağlantı koptu")
        if self.parca_drive.get((ad, sira)):
            self.parca_drive[(ad, sira)] -= 1
            return self.yanit(self.red("Drive yüklemesi kesildi; aynı parçayı yeniden gönder.", "drive"))
        if (ad, sira) in self.parca_red:
            return self.yanit(self.red(*self.parca_red[(ad, sira)]))
        k = self.kayitlar[kod]
        beklenen = k["sira"].get(ad, 0)
        if sira >= beklenen:
            assert sira == beklenen, "sıra dışı parça"
            assert basliklar["Content-Type"] == "application/octet-stream"
            k["veri"][ad] += veri
            k["sira"][ad] = sira + 1
        alinan = len(k["veri"][ad])
        return self.yanit({"tamam": True, "kod": kod, "ad": ad, "sira": sira, "alinan": alinan,
                           "bitti": alinan == k["beyan"][ad]["boyut"]})

    def i_kim(self, g):
        return {"kisi": self.ben, "ad": self.kisiler[self.ben]["ad"], "dagitim": "cf1", "surum": "1", "okuma": False,
                "depo": "Teamfluencer-Dev/tf-bilgi", "kisiler": self.kisiler,
                "sinirlar": {"parca_bayt": self.parca_bayt, "dosya_azami_bayt": 94371840,
                             "kayit_azami_bayt": 943718400, "dosya_azami_sayi": 10}}

    def i_baslat(self, g):
        assert g["alan"] in ("ekip", "yonetim")
        kod = "G-cf%04d" % len(self.kayitlar)
        self.kayitlar[kod] = {"g": g, "beyan": {d["ad"]: d for d in g["dosyalar"]},
                              "veri": {d["ad"]: b"" for d in g["dosyalar"]}, "sira": {}, "bitti": False}
        return {"kod": kod, "kayit": f"20261107-210000-{self.ben}-{kod[2:]}", "alan": g["alan"],
                "parca_bayt": self.parca_bayt, "durum": f"durum|{kod}",
                "yuklemeler": {d["ad"]: f"yk|{kod}|{d['ad']}" for d in g["dosyalar"]}, "dosyalama": "10 dk içinde"}

    def i_bitir(self, g):
        k = self.kayitlar[g["kod"]]
        assert g["durum"] == "durum|" + g["kod"]
        for ad, beyan in k["beyan"].items():
            assert len(k["veri"][ad]) == beyan["boyut"], ad
            assert hashlib.sha256(k["veri"][ad]).hexdigest() == beyan["sha256"], ad
        k["bitti"] = True
        return {"kod": g["kod"], "kayit": "kayit", "alan": k["g"]["alan"], "dosyalar": list(k["beyan"]),
                "dosyalama": "10 dk içinde"}

    def i_geri_al(self, g):
        k = self.kayitlar.get(g["hedef"])
        if k and not k["bitti"]:
            return {"sonuc": "durduruldu", "hedef": g["hedef"]}
        return {"sonuc": "kaydedildi", "hedef": g["hedef"], "kod": "G-cfgeri", "kayit": "k", "dosyalama": "10 dk içinde"}

    def i_alindi(self, g):
        return {"kod": "G-cfalnd", "kayit": "k", "dosyalama": "10 dk içinde"}


class WorkerKopruTest(Base):
    """0.9.0: GitHub'ı olmayan herkes Slack botunun verdiği `tfb1.cf1.…` anahtarıyla Worker köprüsünden paylaşır."""
    EKIP = "Teamfluencer-Dev/tf-bilgi"

    def setUp(self):
        super().setUp()
        for ad in ("TF_BILGI_UZAK_EKIP", "TF_BILGI_UZAK_YONETIM"):
            os.environ.pop(ad, None)
        os.environ.update({"FAKE_GH_LOGIN": "", "TF_BILGI_SIMDI": "2026-11-07T21:00:00+03:00"})  # Cumartesi gecesi
        self.gh = SahteGitHub({self.EKIP: {"kisiler.json": json.dumps(KISILER, ensure_ascii=False)}})
        self.worker = SahteWorker()
        for ad, deger in (("gh_api", self.gh), ("KOPRU_BEKLE", 0), ("KB_SHA256", ()), ("kopru_tasi", self.worker),
                          ("kopru_ham_tasi", self.worker.ham)):
            yama = mock.patch.object(tf_bilgi, ad, deger)
            yama.start()
            self.addCleanup(yama.stop)
        self.cache.mkdir(parents=True, exist_ok=True)
        (self.cache / "anahtar").write_text(KOPRU_CF_ANAHTAR + "\n")  # Slack botunun tek satırlık kurulumu
        self.ekler = self.tmp / "ekler"
        self.ekler.mkdir()

    def ek(self, ad, icerik):
        yol = self.ekler / ad
        yol.write_bytes(icerik if isinstance(icerik, bytes) else icerik.encode("utf-8"))
        return str(yol)

    def test_anahtar_bicimi_ve_adres(self):
        self.assertEqual(tf_bilgi.anahtar_coz(KOPRU_CF_ANAHTAR), ("cf1", KOPRU_CF_GIZLI))
        self.assertIsNone(tf_bilgi.anahtar_coz(f"tfb1.c1.{KOPRU_CF_GIZLI}"))  # dağıtım kimliği en az 3 karakter
        self.assertEqual(tf_bilgi.ANAHTAR_ARA_RE.findall(f"x {KOPRU_CF_ANAHTAR} y"), [KOPRU_CF_ANAHTAR])
        self.assertTrue(tf_bilgi.KOPRU_CF_ADRES.startswith("https://tf-bilgi-kopru."))
        self.assertTrue(tf_bilgi.KOPRU_CF_ADRES.endswith(".workers.dev"))
        self.assertEqual(tf_bilgi.kopru_adresi("cf1"), tf_bilgi.KOPRU_CF_ADRES)
        self.assertEqual(tf_bilgi.kopru_parca_adresi("cf1"), tf_bilgi.KOPRU_CF_ADRES + "/parca")
        self.assertEqual(tf_bilgi.kopru_adresi(KOPRU_DAGITIM), f"https://script.google.com/macros/s/{KOPRU_DAGITIM}/exec")
        os.environ["TF_BILGI_KOPRU_URL"] = "https://ornek.test/kopru/"
        self.assertEqual((tf_bilgi.kopru_adresi("cf1"), tf_bilgi.kopru_parca_adresi("cf1")),
                         ("https://ornek.test/kopru/", "https://ornek.test/kopru/parca"))

    def test_paylas_ham_parcalar_ve_makbuz(self):
        pdf = self.ek("Çalışma Notu.pdf", b"%PDF-1.4 \x00\x01\xff ikili veri")
        bos = self.ek("bos.txt", b"")
        r = self.ok("hizli", "--ek", pdf, "--ek", bos, stdin="Ayşe'ye bilgi\nikinci satır\n")
        kod = r["kod"]
        self.assertEqual((kod, r["yol"], r["alan"], r["alicilar"], r["dosyalar"], r["notlar"]),
                         ("G-cf0000", "kopru", "ekip", ["ayse"], ["govde.md", "Calisma-Notu.pdf", "bos.txt"], []))
        self.assertEqual(r["satir"], f"Gönderildi ✓ {kod} · Çalışma Notu.pdf, bos.txt + not · ekip · kütüphaneci 10 dk "
                                     f"içinde dosyalar, alıcılara o an haber gider · geri al: /paylas geri-al {kod}")
        self.assertEqual([c["islem"] for c in self.worker.cagrilar], ["kim", "baslat", "bitir"])  # kim bir kez
        self.assertEqual(set(self.worker.adresler), {tf_bilgi.KOPRU_CF_ADRES})
        b = self.worker.islemler("baslat")[0]
        self.assertEqual(b["taslak"], HIZLI_TASLAK)
        self.assertEqual((b["alan"], b["konu_satiri"], b["aciklama"]),
                         ("ekip", "Ayşe'ye bilgi", "Ayşe'ye bilgi\nikinci satır"))
        self.assertEqual(self.worker.islemler("bitir")[0]["durum"], f"durum|{kod}")
        kayit = self.worker.kayitlar[kod]
        self.assertTrue(kayit["bitti"])
        self.assertEqual(kayit["veri"], {"govde.md": "Ayşe'ye bilgi\nikinci satır\n".encode(),
                                         "Calisma-Notu.pdf": Path(pdf).read_bytes(), "bos.txt": b""})
        for adres, basliklar, uzunluk in self.worker.parcalar:  # ham gövde, base64 yok, anahtar başlıkta
            self.assertEqual(adres, tf_bilgi.KOPRU_CF_ADRES + "/parca")
            self.assertLessEqual(uzunluk, 4)
            self.assertEqual(basliklar["Authorization"], f"Bearer {KOPRU_CF_ANAHTAR}")
        self.assertEqual([p[1]["X-Tfb-Sira"] for p in self.worker.parcalar if p[1]["X-Tfb-Yukleme"].endswith("|bos.txt")],
                         ["0"])  # boş dosya: tek boş parça
        self.assertNotIn(KOPRU_CF_GIZLI, json.dumps(r))
        self.assertFalse([c for c in self.gh.cagrilar])  # GitHub'a gidilmedi
        self.assertFalse((self.cache / "kopru").exists())  # ayna, kb.py yok
        self.assertEqual(json.loads((self.cache / "hizli.json").read_text())["gonderilen"][kod]["yol"], "kopru")

    def test_alan_kurali_koprude_kim_rehberiyle(self):
        for notu, alan, alicilar in (("Ilgım'a karar lazım", "ekip", ["ilgim"]), ("Dilara'ya sunum", "ekip", ["dilara"]),
                                     ("Pazartesi notları", "ekip", []), ("C-level özeti", "yonetim", None)):
            r = self.ok("hizli", stdin=notu + "\n")
            self.assertEqual((r["alan"], r["alicilar"]), (alan, alicilar), notu)
            self.assertEqual(self.worker.islemler("baslat")[-1]["alan"], alan, notu)
        self.worker.ben = "dilara"  # kural 3: alıcısız, gönderen yalnız yönetimde
        self.assertEqual(self.ok("hizli", stdin="toplantı notları")["alan"], "yonetim")
        r = self.ok("hizli", "--ekip", stdin="Dilara'ya")
        self.assertEqual((r["alan"], self.worker.islemler("baslat")[-1]["alan"]), ("ekip", "ekip"))
        r = self.ok("hizli", "--yonetim", "--ek", self.ek("a.md", "a"))  # Worker anahtarı yönetime de gönderir
        self.assertEqual(self.worker.islemler("baslat")[-1]["alan"], "yonetim")

    def test_parca_yeniden_denenir_kalici_hata_geri_alir(self):
        dosya = self.ek("rapor.md", "0123456789abc")  # 4 baytlık parçalar: 0..3
        self.worker.parca_kopuk[("rapor.md", 1)] = 1
        self.worker.parca_drive[("rapor.md", 2)] = 2
        r = self.ok("hizli", "--ekip", "--ek", dosya)
        self.assertEqual(self.worker.kayitlar[r["kod"]]["veri"]["rapor.md"], b"0123456789abc")
        siralar = [p[1]["X-Tfb-Sira"] for p in self.worker.parcalar]
        self.assertEqual(siralar, ["0", "1", "1", "2", "2", "2", "3"])
        self.worker.parca_red[("rapor.md", 1)] = ("rapor.md: sıra dışı parça (beklenen 0, gelen 1).", "durum")
        out = self.stop("hizli", "--ekip", "--ek", dosya)
        self.assertIn("Gönderim yarıda kaldı: rapor.md: sıra dışı parça", out)
        self.assertIn("kaydı durdurdum (G-cf0001), hiçbir şey dosyalanmayacak", out)
        self.assertEqual(self.worker.islemler("geri-al")[-1]["hedef"], "G-cf0001")
        self.assertFalse(self.worker.kayitlar["G-cf0001"]["bitti"])
        with mock.patch.object(self.worker, "i_baslat", lambda g: {"kod": "G-cf0009", "parca_bayt": 4, "durum": "d",
                                                                   "yuklemeler": {}}):
            out = self.stop("hizli", "--ekip", "--ek", dosya)  # eksik belirteç: yanıt anlaşılmadı, kayıt durdurulur
        self.assertIn("yanıtı anlaşılamadı", out)
        self.assertEqual(self.worker.islemler("geri-al")[-1]["hedef"], "G-cf0009")

    def test_kopru_url_ezer_ve_ayar_hatasi_aynen(self):
        os.environ["TF_BILGI_KOPRU_URL"] = "https://ornek.test/k"
        self.ok("hizli", "--ekip", stdin="not")
        self.assertEqual(set(self.worker.adresler), {"https://ornek.test/k"})
        self.assertEqual({p[0] for p in self.worker.parcalar}, {"https://ornek.test/k/parca"})
        self.worker.hatalar["kim"] = ("Köprü kurulumu bitmedi; Enes'e haber ver.", "ayar")
        self.assertEqual(self.stop("hizli", "--ekip", stdin="not").strip(), "Köprü kurulumu bitmedi; Enes'e haber ver.")

    def test_okuma_desteklenmiyor_sade_cumle(self):
        self.assertEqual(self.stop("hazirla").strip(), OKUMA_YOK)  # ağa gitmeden
        self.assertEqual(self.stop("hazirla", "--yazma").strip(),
                         "Köprü anahtarıyla yalnız /paylas çalışır: dosyaları /paylas ile ya da Slack'te TF Bilgi "
                         "botuna gönder.")
        self.assertEqual(self.worker.cagrilar, [])
        self.assertEqual(self.stop("ara", "abonelik").strip(), OKUMA_YOK)  # Worker'ın desteklenmiyor yanıtı
        self.assertEqual(self.stop("oku", "SON.md").strip(), OKUMA_YOK)
        self.assertEqual(self.stop("tercih").strip(), OKUMA_YOK)
        self.assertIn("yalnız /paylas çalışır", self.stop("gonder", "--taslak", "/x/taslak.json"))
        self.assertEqual(self.worker.islemler("ara")[0]["sorgu"], "abonelik")
        g = self.ok("alindi", "B-20261029-ayse-01")  # alındı Worker'da var
        self.assertEqual(g["satir"], "Alındın gönderildi: B-20261029-ayse-01 · kütüphaneci 10 dk içinde kaydeder.")
        g = self.ok("geri-al", "G-cf7777")
        self.assertEqual((g["yol"], g["sonuc"]), ("kopru", "kaydedildi"))
        self.assertIn("kütüphaneci 10 dk içinde işler", g["satir"])

    def test_okuma_gh_girisi_varsa_dogrudan(self):
        self.assertEqual(tf_bilgi.yol_sec(), "kopru")
        os.environ["FAKE_GH_LOGIN"] = "mert-gh"
        self.assertEqual(tf_bilgi.yol_sec(), "dogrudan")  # Worker anahtarı okumaz; GitHub'dan okuyabilen okur
        os.environ["TF_BILGI_YOL"] = "kopru"
        self.assertEqual(tf_bilgi.yol_sec(), "kopru")

    def test_gh_girisi_var_ama_yazamiyor_koprude_kalir(self):
        """review #15: anahtar sahibinin gh girişi tek başına doğrudan yol değildir; push doğrulanmalı."""
        os.environ.update({"FAKE_GH_LOGIN": "mert-gh", "FAKE_GH_PUSH": "false"})
        self.assertEqual(tf_bilgi.yol_sec(), "kopru")
        self.assertEqual(self.stop("hazirla", "--yazma").strip(), tf_bilgi.KOPRU_YALNIZ_PAYLAS)
        self.assertEqual(self.stop("hazirla").strip(), OKUMA_YOK)
        self.assertNotIn(tf_bilgi.BOT_YOLU, self.stop("hazirla", "--yazma"))

    def test_parca_http_hatasi_mesaji(self):
        dosya = self.ek("r.md", "0123")

        def ham_502(adres, veri, basliklar, zaman_asimi):
            raise tf_bilgi.urllib.error.HTTPError(adres, 502, "Bad Gateway", {}, None)

        with mock.patch.object(tf_bilgi, "kopru_ham_tasi", ham_502):
            out = self.stop("hizli", "--ekip", "--ek", dosya)
        self.assertIn("Gönderim yarıda kaldı: TF Bilgi köprüsü yanıt vermedi (HTTP 502)", out)
        self.assertIn("kaydı durdurdum", out)

    def test_kur_cf1_anahtari(self):
        (self.cache / "anahtar").unlink()
        dosya = self.cache / "gecici" / "anahtar.txt"
        dosya.parent.mkdir(parents=True, exist_ok=True)
        dosya.write_text("Botun gönderdiği: " + KOPRU_CF_ANAHTAR + "\n")
        r = self.ok("kur", "--dosya", str(dosya))
        self.assertEqual((r["kuruldu"], r["kisi"]), (True, "mert"))
        self.assertEqual(r["satir"], "Köprü anahtarı kuruldu: Mert Örnek (mert). /paylas artık GitHub'sız çalışır; "
                                     "belgeler sana Slack'ten bağlantıyla gelir.")
        self.assertEqual((self.cache / "anahtar").read_text().strip(), KOPRU_CF_ANAHTAR)
        self.assertEqual((self.cache / "anahtar").stat().st_mode & 0o777, 0o600)
        self.assertFalse(dosya.exists())
        self.assertEqual(self.worker.adresler, [tf_bilgi.KOPRU_CF_ADRES])
        self.assertNotIn(KOPRU_CF_GIZLI, json.dumps(r))
        durum = self.ok("kur")
        self.assertEqual((durum["anahtar"], durum["gecerli"], durum["kisi"]), (True, True, "mert"))

    def test_ne_yazan_ne_anahtar_tek_satir(self):
        (self.cache / "anahtar").unlink()
        code, out = self.run_main("hizli", stdin="not")
        self.assertEqual((code, out), (2, "Slack'te TF Bilgi botuna `anahtar` yaz; gelen satırı terminale yapıştır, "
                                          "sonra /paylas'ı tekrar dene.\n"))



AKTARICI_DAGITIM = "AKfycbAktariciSahte_0123-456789"
AKTARICI_ANAHTAR = f"tfb1.{AKTARICI_DAGITIM}.{KOPRU_CF_GIZLI}"  # gizli kısım dağıtımdan bağımsız
AKTARICI_ADRES = f"https://script.google.com/macros/s/{AKTARICI_DAGITIM}/exec"


class SahteAktarici(SahteWorker):
    """Türkiye'den *.workers.dev engelli: Apps Script ince aktarıcısı (protokol 2). Parçalar JSON/base64 `parca` ile
    gelir (ham gövde yok), parça boyu kim'de 3 MB; Worker'a ulaşamazsa `kod: drive`."""

    def __init__(self):
        super().__init__()
        self.parca_bayt = 3 * 1048576

    def i_kim(self, g):
        return {**super().i_kim(g), "protokol": 2, "parca_json": True}

    def i_baslat(self, g):
        assert g["parca_bayt"] == 3 * 1048576  # istemci kim'deki parça boyunu bildirir
        return super().i_baslat(g)

    def i_parca(self, g):
        _, kod, ad = g["yukleme"].split("|")
        sira = g["sira"]
        if self.parca_drive.get((ad, sira)):
            self.parca_drive[(ad, sira)] -= 1
            raise KopruRet("TF Bilgi köprüsü Worker'a ulaşamadı; aynı parçayı yeniden gönder.", "drive")
        veri = base64.b64decode(g["veri"])
        self.parcalar.append((ad, sira, len(veri)))
        k = self.kayitlar[kod]
        if sira >= k["sira"].get(ad, 0):
            assert sira == k["sira"].get(ad, 0), "sıra dışı parça"
            k["veri"][ad] += veri
            k["sira"][ad] = sira + 1
        alinan = len(k["veri"][ad])
        return {"kod": kod, "ad": ad, "sira": sira, "alinan": alinan, "bitti": alinan == k["beyan"][ad]["boyut"]}

    def __call__(self, adres, veri, zaman_asimi):
        try:
            return super().__call__(adres, veri, zaman_asimi)
        except KopruRet as e:
            return self.yanit(self.red(*e.args))

    def ham(self, adres, veri, basliklar, zaman_asimi):
        raise AssertionError("aktarıcıya ham parça gitmez")


class AktariciKopruTest(WorkerKopruTest):
    """Protokol 2: Apps Script aktarıcısı (script.google.com) → Worker. WorkerKopruTest'in yardımcılarını kullanır."""

    def setUp(self):
        super().setUp()
        self.worker = SahteAktarici()
        for ad, deger in (("kopru_tasi", self.worker), ("kopru_ham_tasi", self.worker.ham)):
            yama = mock.patch.object(tf_bilgi, ad, deger)
            yama.start()
            self.addCleanup(yama.stop)
        (self.cache / "anahtar").write_text(AKTARICI_ANAHTAR + "\n")

    # WorkerKopruTest'in cf1'e özgü testleri burada çalışmaz: yalnız aşağıdakiler
    test_anahtar_bicimi_ve_adres = test_paylas_ham_parcalar_ve_makbuz = test_parca_yeniden_denenir_kalici_hata_geri_alir = None
    test_kopru_url_ezer_ve_ayar_hatasi_aynen = test_kur_cf1_anahtari = test_okuma_desteklenmiyor_sade_cumle = None
    test_parca_http_hatasi_mesaji = None  # aktarıcıya ham parça gitmez

    def test_aktarici_json_parcalar_uc_uca(self):
        buyuk = bytes(range(256)) * (3 * 4096 + 17)  # 3 MB'tan büyük: 2 parça
        dosya = self.ek("sunum.pdf", buyuk)
        self.worker.parca_drive[("sunum.pdf", 1)] = 1  # aktarıcı Worker'a ulaşamadı: aynı sıra yeniden gider
        r = self.ok("hizli", "--ek", dosya, stdin="Dilara'ya sunum\n")
        kod = r["kod"]
        self.assertEqual((r["yol"], r["alan"], r["alicilar"]), ("kopru", "yonetim", ["dilara"]))
        self.assertIn(" · yönetim · kütüphaneci 10 dk içinde dosyalar", r["satir"])
        self.assertEqual(set(self.worker.adresler), {AKTARICI_ADRES})  # yalnız script.google.com
        islemler = [c["islem"] for c in self.worker.cagrilar]
        self.assertEqual(islemler.count("kim"), 1)  # kim bir çalıştırmada bir kez
        self.assertEqual([i for i in islemler if i != "parca"], ["kim", "baslat", "bitir"])
        b = self.worker.islemler("baslat")[0]
        self.assertEqual((b["alan"], b["konu_satiri"], b["parca_bayt"], b["taslak"]),
                         ("yonetim", "Dilara'ya sunum", 3 * 1048576, HIZLI_TASLAK))
        parcalar = [(c["yukleme"].split("|")[2], c["sira"]) for c in self.worker.islemler("parca")]
        self.assertEqual(parcalar, [("govde.md", 0), ("sunum.pdf", 0), ("sunum.pdf", 1), ("sunum.pdf", 1)])
        self.assertTrue(all(c["anahtar"] == KOPRU_CF_GIZLI and c["s"] == 1 for c in self.worker.islemler("parca")))
        self.assertEqual([n for a, _, n in self.worker.parcalar if a == "sunum.pdf"],
                         [3 * 1048576, len(buyuk) - 3 * 1048576])
        self.assertEqual(self.worker.kayitlar[kod]["veri"]["sunum.pdf"], buyuk)
        self.assertEqual(self.worker.islemler("bitir")[0]["durum"], f"durum|{kod}")
        self.assertTrue(self.worker.kayitlar[kod]["bitti"])

    def test_aktarici_okuma_ve_yol(self):
        self.assertEqual(self.stop("hazirla").strip(), OKUMA_YOK)  # kim protokol 2 → sade cümle
        self.assertIn("yalnız /paylas çalışır", self.stop("hazirla", "--yazma"))
        self.assertEqual(self.stop("ara", "abonelik").strip(), OKUMA_YOK)
        self.assertIn("yalnız /paylas çalışır", self.stop("gonder", "--taslak", "/x/taslak.json"))
        os.environ["FAKE_GH_LOGIN"] = "mert-gh"
        self.assertEqual(tf_bilgi.yol_sec(), "dogrudan")  # yeni köprü + depoya yazan (push doğrulandı): doğrudan
        os.environ["FAKE_GH_LOGIN"] = ""
        (self.cache / "hizli.json").unlink()  # yazan önbelleği bu makineden silinir: aşağısı GitHub'sız kişi
        self.worker.cagrilar.clear()
        r = self.ok("hizli", "--yonetim", stdin="bütçe")  # aktarıcı anahtarı yönetime de gönderir
        self.assertEqual((r["alan"], self.worker.islemler("baslat")[0]["alan"]), ("yonetim", "yonetim"))
        self.assertEqual(len(self.worker.islemler("kim")), 1)

    def test_kur_aktarici_anahtari(self):
        (self.cache / "anahtar").unlink()
        dosya = self.cache / "gecici" / "anahtar.txt"
        dosya.parent.mkdir(parents=True, exist_ok=True)
        dosya.write_text(AKTARICI_ANAHTAR + "\n")
        r = self.ok("kur", "--dosya", str(dosya))
        self.assertIn("belgeler sana Slack'ten bağlantıyla gelir", r["satir"])
        self.assertEqual(self.worker.adresler, [AKTARICI_ADRES])
        self.assertEqual(len(self.worker.islemler("kim")), 1)

    def test_kim_hatasi_yonetimde_aynen_soylenir(self):
        self.worker.hatalar["kim"] = ("Köprü kurulumu bitmedi; Enes'e haber ver.", "ayar")
        out = self.stop("hizli", stdin="yönetim için bütçe\n").strip()
        self.assertEqual(out, "Köprü kurulumu bitmedi; Enes'e haber ver.")  # "anahtar eski" değil
        self.assertEqual(len(self.worker.islemler("kim")), 1)

    def test_rehber_yuklenemezse_ekibe_dusmez(self):
        gercek_kim, sayac = self.worker.i_kim, {"n": 0}

        def ilk_kim_duser(g):
            sayac["n"] += 1
            if sayac["n"] == 1:
                raise KopruRet("Worker'a ulaşılamadı.", "drive")
            return gercek_kim(g)

        self.worker.i_kim = ilk_kim_duser
        code, out = self.run_main("hizli", stdin="Dilara'ya bütçe tablosu\n")
        self.assertFalse([b for b in self.worker.islemler("baslat") if b.get("alan") == "ekip"], out)
        self.assertTrue(code == 2 or json.loads(out)["alan"] == "yonetim", out)
        self.assertEqual((code, out.strip()), (2, "Worker'a ulaşılamadı."))
        self.assertEqual(self.worker.islemler("baslat"), [])
        self.assertEqual(len(self.worker.islemler("kim")), 1)  # hata da önbellekte: aynı çalıştırmada yeniden sorulmaz
        r = self.ok("hizli", stdin="Dilara'ya bütçe tablosu\n")  # sonraki çalıştırma: köprü düzeldi
        self.assertEqual((r["alan"], r["alicilar"]), ("yonetim", ["dilara"]))

    def test_kim_ag_hatasi_bir_kez_ve_kisa_zaman_asimi(self):
        asimlar = []

        def kopuk(adres, veri, zaman_asimi):
            asimlar.append(zaman_asimi)
            raise tf_bilgi.urllib.error.URLError("bağlantı koptu")

        with mock.patch.object(tf_bilgi, "kopru_tasi", kopuk):
            out = self.stop("hizli", stdin="Dilara'ya bütçe\n")
        self.assertIn("TF Bilgi köprüsüne ulaşılamadı", out)
        self.assertEqual(asimlar, [tf_bilgi.KIM_ZAMAN_ASIMI])  # kim bir kez, kısa zaman aşımıyla
        self.assertEqual(tf_bilgi.KIM_ZAMAN_ASIMI, 20)
        with mock.patch.object(tf_bilgi, "kopru_tasi", kopuk):
            self.assertIn("TF Bilgi köprüsüne ulaşılamadı", self.stop("hazirla"))  # "anahtar eski" ya da önbellek değil

    def test_alan_komutu_gizli_icin(self):
        notu = self.cache / "gecici" / "not.txt"
        notu.parent.mkdir(parents=True, exist_ok=True)
        notu.write_text("gizli: Dilara'ya, yalnız o görsün\n")
        r = self.ok("alan", "--not-dosya", str(notu))
        self.assertEqual((r["alan"], r["alicilar"]), ("ekip", ["dilara"]))  # ekipten yöneticiye: ekip
        self.assertTrue(r["neden"].startswith("kural 2"))
        self.assertEqual(self.ok("alan", "--ekip", "--not-dosya", str(notu))["alan"], "ekip")
        self.worker.hatalar["kim"] = ("Köprü kurulumu bitmedi; Enes'e haber ver.", "ayar")
        self.assertEqual(self.stop("alan", "--not-dosya", str(notu)).strip(), "Köprü kurulumu bitmedi; Enes'e haber ver.")

    def test_kim_onbellegi_calistirma_basina(self):
        self.ok("hizli", "--ekip", stdin="bir")
        self.ok("hizli", "--ekip", stdin="iki")
        self.assertEqual(len(self.worker.islemler("kim")), 2)  # her çalıştırma bir kez sorar, aralarında saklanmaz


if __name__ == "__main__":
    unittest.main()
