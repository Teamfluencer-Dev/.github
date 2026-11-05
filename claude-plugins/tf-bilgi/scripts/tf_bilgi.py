#!/usr/bin/env python3
"""Helper for the tf-bilgi `/paylas` and `/bilgi` skills (Teamfluencer-Dev).

TF Bilgi is the team's knowledge base in two private GitHub repos (ekip, yonetim).
This script keeps a local cache clone of each and drives the repo's own
`araclar/kb.py`, which owns every rule (ids, scanning, topic matching,
validation, commit/push). The plugin depends only on the kb.py commands, flags
and JSON shapes of the TF Bilgi contract (sections 9 and 11), never on its code.

  hazirla [--yonetim]            Clone or update the cache clone, resolve the
                                 person, print JSON (kok, alan, kisi, kb, uzak, ...).
  kb [--yonetim] <args...>       Run the cache's kb.py; stdout, stderr and exit
                                 code pass through. kaydet/yenile/ozet are refused.
  gecici AD                      Save stdin as <cache>/gecici/AD (scratch input for
                                 kb.py --dosya / tara; never inside a clone).
  maskele [--yonetim] DOSYA      kb.py tara --maskele -> masked copy in <cache>/gecici/.
  yaz [--yonetim] [--dosya F] [--uzerine]
                                 Write a new entry (stdin or F) to
                                 girdiler/YYYY/MM/<id>.md; published entries are
                                 never overwritten.
  kaydet [--yonetim] --mesaj M YOL...
                                 Contract section 10 guard (only new girdiler/,
                                 ham/, onaylar/ files and an append-only
                                 ham/DEFTER.tsv), then kb.py kaydet; prints links.
  prler [REF...] [--repo R]...   Read-only PR rows for a pr-listesi entry:
                                 claude-review state, merge state, stacking.

No model calls and no API keys: only git, the GitHub CLI and kb.py. Python 3.9+,
stdlib only. Messages for the user are Turkish; exit code 2 means "show this
message to the user as-is".
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
ORG = "Teamfluencer-Dev"
DAL = "main"
ALANLAR = {
    "ekip": {"klasor": "tf-bilgi", "ortam": "TF_BILGI_UZAK_EKIP", "uzak": f"{ORG}/tf-bilgi"},
    "yonetim": {"klasor": "tf-bilgi-yonetim", "ortam": "TF_BILGI_UZAK_YONETIM", "uzak": f"{ORG}/tf-bilgi-yonetim"},
}
SLUG_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
GITHUB_URL_RE = re.compile(r"github\.com[:/]+([^/\s]+/[^/\s]+?)(?:\.git)?/*$")
GIRDI_ID_RE = re.compile(r"^([A-Z]+)-(\d{4})(\d{2})\d{2}-([a-z][a-z0-9]*)-\d{2,3}$")
# Contract section 10: the only repo paths a /paylas or /bilgi session may add.
YENI_YOLLAR = (
    re.compile(r"^girdiler/\d{4}/\d{2}/[A-Z]+-\d{8}-[a-z][a-z0-9]*-\d{2,3}\.md$"),
    re.compile(r"^ham/\d{4}/\d{2}/[0-9a-f]{8}-[a-z0-9][a-z0-9.-]*$"),
    re.compile(r"^onaylar/[A-Z]+-\d{8}-[a-z][a-z0-9]*-\d{2,3}--[a-z][a-z0-9]*\.md$"),
)
ONAY_RE = re.compile(r"^onaylar/[A-Z]+-\d{8}-[a-z][a-z0-9]*-\d{2,3}--([a-z][a-z0-9]*)\.md$")
DEFTER = "ham/DEFTER.tsv"
# Sözleşme §10: /paylas ve /bilgi oturumunun kb.py'de çalıştırabildiği alt komutlar (yazanlar yalnız
# ham-ekle ve alindi; commit'i her zaman `tf_bilgi.py kaydet` yapar).
KB_IZINLI = ("taslak", "yeni-id", "eslestir", "tara", "dogrula", "ham-ekle", "son", "konu", "ara", "kuyruk", "alindi")
KOK_SECENEGI = re.compile(r"^--k(?:o(?:k)?)?(?:=|$)")        # --kok ve argparse kısaltmaları (--k, --ko)
DEGERLI_SECENEK = re.compile(r"^--b(?:u(?:g(?:u(?:n)?)?)?)?$")  # --bugun ve kısaltmaları değer alır
KISI_SECENEGI = re.compile(r"^--ki(?:s(?:i)?)?(?:=(.*))?$")   # alindi --kisi (ve kısaltmaları)
KB_YASAK = {
    "kaydet": "kb.py kaydet doğrudan çalıştırılmaz: `tf_bilgi.py kaydet` kullanın (önce yolları denetler).",
    "yenile": "kb.py yenile kütüphanecinin işi (KONULAR.md, SON.md, kuyruk/ gibi üretilen dosyaları yazar); "
              "/paylas ve /bilgi bunu çalıştırmaz.",
    "ozet": "kb.py ozet kütüphanecinin işi; /paylas ve /bilgi bunu çalıştırmaz.",
}
IKILI_UZANTILAR = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".key", ".numbers", ".pages", ".zip",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".heic", ".mp3", ".mp4", ".m4a", ".mov", ".ogg",
}
GUNLER = ("Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar")
REPO_KISALTMALARI = {
    "api": "teamfluencerapi",
    "web": "teamfluencer-web",
    "admin": "teamfluencer-admin-web",
    "app": "teamfluencerapp",
    "landing": "teamfluencer-landing",
}
PR_ALANLARI = "number,title,headRefName,baseRefName,url,state,isDraft,mergeStateStatus,statusCheckRollup"
CLAUDE_REVIEW = "claude-review"
MERGE_DURUMU_TR = {
    "CLEAN": "merge'e hazır",
    "HAS_HOOKS": "merge'e hazır",
    "BLOCKED": "engelli (çoğunlukla claude-review ya da onay eksik)",
    "BEHIND": "taban dalın gerisinde",
    "DIRTY": "çakışma var",
    "UNSTABLE": "bazı kontroller kırmızı ya da bekliyor",
    "DRAFT": "taslak",
    "UNKNOWN": "bilinmiyor",
}
ERISIM_IPUCU = ("Depo private: GitHub hesabınızın bu depoya okuma-yazma yetkisi olmalı (yoksa org "
                "yöneticisinden isteyin) ve `gh auth status` geçerli olmalı.")
REMOTE_MANIFEST = (
    "https://raw.githubusercontent.com/Teamfluencer-Dev/.github/main/"
    "claude-plugins/tf-bilgi/.claude-plugin/plugin.json"
)
which = shutil.which  # module-level so tests can replace it


class Stop(Exception):
    """A user-facing failure; the message is shown as-is (exit code 2)."""


# --- process helpers ---

def alt_ortam(kok=None):
    """Environment for child processes: never prompt (a prompt would hang the skill)."""
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env.setdefault("GH_PROMPT_DISABLED", "1")
    if kok is not None:
        env["TF_BILGI_KOK"] = str(kok)
        env["PYTHONDONTWRITEBYTECODE"] = "1"  # keep the clone free of __pycache__
    return env


def ayrinti(proc):
    return (proc.stderr or proc.stdout or "").strip()[-1500:]


def sh(cmd, cwd=None, check=True, timeout=120, env=None):
    try:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout,
                              env=env or alt_ortam(), stdin=subprocess.DEVNULL)
    except FileNotFoundError:
        raise Stop(f"`{cmd[0]}` bulunamadı. Kurup tekrar deneyin.")
    except subprocess.TimeoutExpired:
        raise Stop(f"Komut zaman aşımına uğradı: {' '.join(cmd[:4])} …")
    if check and proc.returncode != 0:
        raise Stop(f"Komut başarısız: {' '.join(cmd)}\n{ayrinti(proc)}")
    return proc


def git(kok, *args, check=True, timeout=120):
    return sh(["git", "-c", "core.quotepath=off", "-C", str(kok), *args], check=check, timeout=timeout)


def gh_json(*args):
    out = sh(["gh", *args], timeout=60).stdout
    return json.loads(out) if out.strip() else None


def gh_login():
    """GitHub login of the current gh user, or None (no gh, not logged in, offline)."""
    if not which("gh"):
        return None
    proc = sh(["gh", "api", "user", "--jq", ".login"], check=False, timeout=20)
    login = proc.stdout.strip()
    return login if proc.returncode == 0 and login else None


def surum_notu(github):
    if not github or os.environ.get("TF_BILGI_SURUM_KONTROLU") == "0":
        return None
    try:
        local = json.loads((PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text())["version"]
        with urllib.request.urlopen(REMOTE_MANIFEST, timeout=3) as resp:
            remote = json.load(resp)["version"]
    except Exception:
        return None
    as_tuple = lambda v: tuple(int(x) for x in re.findall(r"\d+", v))  # noqa: E731
    if as_tuple(remote) > as_tuple(local):
        return (f"tf-bilgi eklentisi güncel değil ({local} → {remote}). Terminalde: claude plugin "
                "marketplace update teamfluencer && claude plugin update tf-bilgi@teamfluencer")
    return None


# --- checks and resolution ---

def on_kontrol(github):
    if sys.version_info < (3, 9):
        raise Stop(f"Python 3.9 ya da üstü gerekli (şu an {sys.version.split()[0]}). Güncel bir python3 kurun.")
    if not which("git"):
        raise Stop("git bulunamadı. Kurun (macOS: `xcode-select --install`, diğerleri: https://git-scm.com) "
                   "ve tekrar deneyin.")
    if github:
        if not which("gh"):
            raise Stop("GitHub CLI (gh) bulunamadı. Kurun: https://cli.github.com — sonra terminalde "
                       "`gh auth login` yapıp tekrar deneyin.")
        if sh(["gh", "auth", "status", "--hostname", "github.com"], check=False, timeout=30).returncode != 0:
            raise Stop("GitHub CLI giriş yapmamış (`gh auth status` başarısız). Terminalde `gh auth login` "
                       "yapıp tekrar deneyin.")


def alan_sec(yonetim):
    return "yonetim" if yonetim else "ekip"


def uzak_kaynagi(alan):
    """(value, is_github_slug): env override (a slug, a git URL or a local path) or the default slug."""
    deger = os.environ.get(ALANLAR[alan]["ortam"], "").strip() or ALANLAR[alan]["uzak"]
    return deger, bool(SLUG_RE.match(deger)) and not os.path.exists(deger)


def onbellek_koku():
    return Path(os.environ.get("TF_BILGI_DIZIN") or (Path.home() / ".tf-bilgi")).expanduser()


def klon_yolu(alan):
    return onbellek_koku() / ALANLAR[alan]["klasor"]


def ayni_uzak(origin_url, deger, github):
    if github:
        match = GITHUB_URL_RE.search(origin_url or "")
        return bool(match) and match.group(1).lower() == deger.lower()

    def norm(url):
        url = url[7:] if url.startswith("file://") else url
        if os.path.exists(url):
            return os.path.realpath(url).rstrip("/")
        url = url.rstrip("/")
        return url[:-4] if url.endswith(".git") else url

    return bool(origin_url) and norm(origin_url) == norm(deger)


def depo_ayari(kok, alan):
    """Read .kb.json and refuse a clone whose area is not the expected one (no cross-area writes)."""
    try:
        ayar = json.loads((kok / ".kb.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise Stop(f"{kok} içinde .kb.json yok: depo henüz boş ya da kurulmamış olabilir, ya da bu klasör bir "
                   "TF Bilgi deposu değil.")
    except ValueError:
        raise Stop(f"{kok}/.kb.json okunamadı (geçersiz JSON).")
    if ayar.get("alan") != alan:
        raise Stop(f"{kok} deposunun alanı '{ayar.get('alan')}', beklenen '{alan}'. Yanlış depoya yazmamak için "
                   f"durdum; {ALANLAR[alan]['ortam']} ve TF_BILGI_DIZIN ayarlarını kontrol edin.")
    return ayar


def kb_yolu(kok):
    kb = kok / "araclar" / "kb.py"
    if not kb.is_file():
        raise Stop(f"Depoda araclar/kb.py yok ({kok}). Depo henüz kurulmamış olabilir; TF Bilgi sorumlusuna haber verin.")
    return kb


def mevcut_kok(alan):
    """The existing cache clone of `alan` (hazirla must have run)."""
    kok = klon_yolu(alan)
    if not (kok / ".git").exists():
        bayrak = " --yonetim" if alan == "yonetim" else ""
        raise Stop(f"TF Bilgi önbelleği yok ({kok}); önce `tf_bilgi.py hazirla{bayrak}` çalışmalı.")
    depo_ayari(kok, alan)
    return kok


def uzak_slug(ayar, alan):
    return ayar.get("uzak") or ALANLAR[alan]["uzak"]


def baglanti(uzak, yol):
    return f"https://github.com/{uzak}/blob/{DAL}/{urllib.parse.quote(yol, safe='/')}"


def kisileri_oku(kok):
    try:
        data = json.loads((kok / "kisiler.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}
    kisiler = data.get("kisiler") if isinstance(data, dict) else None
    return kisiler if isinstance(kisiler, dict) else {}


def kisi_bul(kok, notlar):
    """gh login ↔ kisiler.json `github` > TF_BILGI_KISI > git user.email ↔ `eposta` > None.

    TF_BILGI_KISI yalnız gh girişi bir kişiye eşlenemiyorsa geçerlidir; eşlenen kişiyle çelişirse durur
    (başkası adına paylaşmayı önler). Bu bir hata önleyicidir, kötü niyetli yazara karşı koruma değildir."""
    kisiler = kisileri_oku(kok)
    if not kisiler:
        notlar.append("kisiler.json okunamadı; kim olduğunuz otomatik bulunamadı.")
    login = gh_login()
    gh_kisi = None
    if login:
        for anahtar in sorted(kisiler):
            if str(kisiler[anahtar].get("github") or "").lower() == login.lower():
                gh_kisi = anahtar
                break
    ortam = os.environ.get("TF_BILGI_KISI", "").strip()
    if ortam:
        if ortam in kisiler:
            if gh_kisi and gh_kisi != ortam:
                raise Stop(f"TF_BILGI_KISI='{ortam}' ama GitHub girişin ({login}) kisiler.json'da '{gh_kisi}'. "
                           "Başkası adına paylaşılmaz: TF_BILGI_KISI'yi düzelt ya da kaldır.")
            return ortam, "TF_BILGI_KISI"
        notlar.append(f"TF_BILGI_KISI='{ortam}' kisiler.json'da yok; diğer yollarla arandı.")
    if gh_kisi:
        return gh_kisi, "github"
    eposta = git(kok, "config", "user.email", check=False).stdout.strip().lower()
    if eposta:
        for anahtar in sorted(kisiler):
            if str(kisiler[anahtar].get("eposta") or "").lower() == eposta:
                return anahtar, "git-eposta"
    return None, None


def bugun():
    sabit = os.environ.get("TF_BILGI_BUGUN")  # tests pin the date
    if sabit:
        return datetime.date.fromisoformat(sabit)
    try:
        from zoneinfo import ZoneInfo
        return datetime.datetime.now(ZoneInfo("Europe/Istanbul")).date()
    except Exception:
        return datetime.date.today()


# --- cache clone ---

def gh_kimlik_ayari(kok):
    """Let plain git fetch/push in the cache use gh's login over HTTPS (repo-local, idempotent)."""
    anahtar = "credential.https://github.com.helper"
    mevcut = git(kok, "config", "--local", "--get-all", anahtar, check=False).stdout.splitlines()
    if "!gh auth git-credential" in (s.strip() for s in mevcut):
        return
    git(kok, "config", "--local", "--replace-all", anahtar, "")
    git(kok, "config", "--local", "--add", anahtar, "!gh auth git-credential")


def klonla(deger, github, kok):
    kok.parent.mkdir(parents=True, exist_ok=True)
    if github:
        proc = sh(["gh", "repo", "clone", deger, str(kok), "--", "-q"], check=False, timeout=600)
    else:
        proc = sh(["git", "clone", "-q", deger, str(kok)], check=False, timeout=600)
    if proc.returncode != 0 or not (kok / ".git").exists():
        raise Stop(f"{deger} klonlanamadı. {ERISIM_IPUCU}\nAyrıntı: {ayrinti(proc)}")
    if github:
        gh_kimlik_ayari(kok)


def guncelle(kok, deger, github, notlar):
    if not (kok / ".git").exists():
        raise Stop(f"{kok} bir git klonu değil. Klasörü başka yere taşıyın ya da TF_BILGI_DIZIN ile başka bir "
                   "önbellek klasörü seçin.")
    origin = git(kok, "config", "--get", "remote.origin.url", check=False).stdout.strip()
    if not ayni_uzak(origin, deger, github):
        raise Stop(f"Önbellek klonu ({kok}) başka bir depoya bağlı: {origin or 'origin yok'} (beklenen: {deger}). "
                   "Klasörü başka yere taşıyın ya da TF_BILGI_DIZIN ile başka bir önbellek klasörü seçin.")
    if git(kok, "rev-parse", "--verify", "-q", "HEAD", check=False).returncode != 0:
        # Cloned while the KB repo was still empty: just try to get its first commits.
        proc = git(kok, "pull", "-q", "origin", DAL, check=False, timeout=300)
        if proc.returncode != 0:
            raise Stop(f"TF Bilgi deposu ({deger}) henüz boş ya da '{DAL}' dalı yok. Depo kurulunca tekrar deneyin.\n"
                       f"Ayrıntı: {ayrinti(proc)}")
        return "guncellendi"
    kirli = [satir[3:] for satir in git(kok, "status", "--porcelain", "--untracked-files=no").stdout.splitlines()]
    if kirli:
        raise Stop(f"TF Bilgi önbelleğinde commit'lenmemiş değişiklik var ({kok}): {', '.join(kirli[:10])}. "
                   "Yarım kalmış bir paylaşım olabilir; üzerine çekmedim. Bakmak için: "
                   f"git -C \"{kok}\" status — değişikliği saklayıp devam etmek için: git -C \"{kok}\" stash, "
                   "sonra komutu tekrar çalıştırın.")
    dal = git(kok, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if dal != DAL:
        raise Stop(f"Önbellek klonu '{dal}' dalında, '{DAL}' bekleniyordu. Düzeltmek için: git -C \"{kok}\" switch {DAL}")
    if github:
        gh_kimlik_ayari(kok)
    once = git(kok, "rev-parse", "HEAD").stdout.strip()
    proc = git(kok, "pull", "--rebase", "-q", "origin", DAL, check=False, timeout=300)
    if proc.returncode != 0:
        git(kok, "rebase", "--abort", check=False)
        raise Stop(f"TF Bilgi önbelleği güncellenemedi (git pull --rebase başarısız). {ERISIM_IPUCU}\n"
                   f"Ayrıntı: {ayrinti(proc)}")
    sonra = git(kok, "rev-parse", "HEAD").stdout.strip()
    ileride = git(kok, "rev-list", "--count", f"origin/{DAL}..HEAD", check=False).stdout.strip()
    if ileride.isdigit() and int(ileride) > 0:
        notlar.append(f"Önbellekte GitHub'a gönderilmemiş {ileride} commit var; bir sonraki kayıt bunları da gönderir.")
    yetim = git(kok, "ls-files", "--others", "--exclude-standard", "--", "girdiler", "ham", "onaylar",
                check=False).stdout.split()
    if yetim:
        notlar.append("Önbellekte commit'lenmemiş yeni dosya var (yarım kalmış paylaşım olabilir): "
                      + ", ".join(yetim[:5]))
    return "guncellendi" if once != sonra else "guncel"


def hazirla(argv):
    parser = argparse.ArgumentParser(prog="tf_bilgi.py hazirla")
    parser.add_argument("--yonetim", action="store_true")
    alan = alan_sec(parser.parse_args(argv).yonetim)
    deger, github = uzak_kaynagi(alan)
    on_kontrol(github)
    notlar = [n for n in (surum_notu(github),) if n]
    kok = klon_yolu(alan)
    if kok.exists():
        islem = guncelle(kok, deger, github, notlar)
    else:
        klonla(deger, github, kok)
        islem = "klonlandi"
    ayar = depo_ayari(kok, alan)
    kb = kb_yolu(kok)
    kisi, kaynak = kisi_bul(kok, notlar)
    kisiler = kisileri_oku(kok)
    uzak = uzak_slug(ayar, alan)
    if kisi is None:
        notlar.append("Kim olduğunuz bulunamadı; bir kez sorulacak. Kalıcı olsun diye kabuk profilinize "
                      "`export TF_BILGI_KISI=<kisiler.json anahtarınız>` ekleyin.")
    elif alan not in (kisiler.get(kisi, {}).get("alanlar") or []):
        notlar.append(f"kisiler.json'da '{kisi}' bu alana ({alan}) kayıtlı değil; okuma kuyruğunuz burada üretilmez.")
    gun = bugun()
    sonuc = {
        "kok": str(kok), "alan": alan, "kisi": kisi, "kb": str(kb), "uzak": uzak,
        "kisi_kaynagi": kaynak,
        "baglanti_koku": f"https://github.com/{uzak}/blob/{DAL}/",
        "bugun": gun.isoformat(), "bugun_gun": GUNLER[gun.weekday()],
        "takvim": [f"{(gun + datetime.timedelta(days=i)).isoformat()} "
                   f"{GUNLER[(gun + datetime.timedelta(days=i)).weekday()]}" for i in range(1, 15)],
        "gecici": str(onbellek_koku() / "gecici"),
        "islem": islem, "notlar": notlar,
    }
    if kisi is None:
        sonuc["kisiler"] = [{"anahtar": k, "ad": (v or {}).get("ad")} for k, v in sorted(kisiler.items())]
    return sonuc


# --- kb.py pass-through and scratch files ---

def alan_ayikla(argv):
    if argv and argv[0] == "--yonetim":
        return "yonetim", argv[1:]
    return "ekip", argv


def kb_alt_komutu(argv):
    """kb.py'nin argparse'ı gibi: seçenekleri (değer alanlarıyla) atlayıp ilk konumsal sözcüğü bulur."""
    i = 0
    while i < len(argv):
        t = argv[i]
        if t == "--":
            return argv[i + 1] if i + 1 < len(argv) else None
        if t.startswith("-") and t != "-":
            i += 2 if DEGERLI_SECENEK.match(t) else 1
            continue
        return t
    return None


def alindi_kisisi(argv):
    for i, t in enumerate(argv):
        m = KISI_SECENEGI.match(t)
        if m:
            return m.group(1) if m.group(1) is not None else (argv[i + 1] if i + 1 < len(argv) else None)
    return None


def kendi_kisin(kok):
    """Çözülen kişi; çözülemiyorsa yazma işlemi durur."""
    kisi, _ = kisi_bul(kok, [])
    if not kisi:
        raise Stop("Kim olduğunuz bulunamadı; bu işlem yalnız kendi adınıza yapılır. Kabuk profilinize "
                   "`export TF_BILGI_KISI=<kisiler.json anahtarınız>` ekleyin.")
    return kisi


def kb_calistir(argv):
    alan, argv = alan_ayikla(argv)
    if not argv:
        raise Stop("kullanım: tf_bilgi.py kb [--yonetim] <kb.py komutu> [argümanlar]")
    if any(KOK_SECENEGI.match(t) for t in argv):
        raise Stop("--kok verilemez: kb.py her zaman TF Bilgi önbellek klonunda çalışır.")
    komut = kb_alt_komutu(argv)
    if komut in KB_YASAK:
        raise Stop(KB_YASAK[komut])
    if komut not in KB_IZINLI:
        raise Stop(f"kb.py alt komutu izinli değil: {komut!r} (izinliler: {', '.join(KB_IZINLI)}).")
    kok = mevcut_kok(alan)
    kb = kb_yolu(kok)
    if komut == "alindi":
        istenen, kisi = alindi_kisisi(argv), kendi_kisin(kok)
        if istenen != kisi:
            raise Stop(f"'Alındı' yalnız kendi adınıza yazılır: --kisi {istenen!r} ama siz '{kisi}'.")
    sys.stdout.flush()
    return subprocess.run([sys.executable, str(kb), *argv], cwd=kok, env=alt_ortam(kok)).returncode


def guvenli_ad(ad):
    temiz = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(ad).name).strip(".-")
    if not temiz:
        raise Stop(f"Geçersiz dosya adı: {ad!r}")
    return temiz


def gecici_dizin():
    yol = onbellek_koku() / "gecici"
    yol.mkdir(parents=True, exist_ok=True)
    return yol


def gecici(argv):
    parser = argparse.ArgumentParser(prog="tf_bilgi.py gecici")
    parser.add_argument("ad")
    hedef = gecici_dizin() / guvenli_ad(parser.parse_args(argv).ad)
    metin = sys.stdin.read()
    hedef.write_text(metin, encoding="utf-8")
    return {"yol": str(hedef), "karakter": len(metin)}


def ikili_mi(yol):
    if yol.suffix.lower() in IKILI_UZANTILAR:
        return True
    with open(yol, "rb") as dosya:
        return b"\0" in dosya.read(8192)


def maskele(argv):
    alan, argv = alan_ayikla(argv)
    parser = argparse.ArgumentParser(prog="tf_bilgi.py maskele")
    parser.add_argument("dosya")
    kaynak = Path(parser.parse_args(argv).dosya).expanduser()
    if not kaynak.is_file():
        raise Stop(f"Dosya bulunamadı: {kaynak}")
    if ikili_mi(kaynak):
        raise Stop(f"{kaynak.name} metin dosyası değil; maskelenemez. Bu dosyayı ham/'a almayın: girdide `ham: null` "
                   "ve `ham_notu: \"sır içerdiği için depoya alınmadı\"` yazın.")
    kok = mevcut_kok(alan)
    proc = sh([sys.executable, str(kb_yolu(kok)), "tara", str(kaynak.resolve()), "--maskele"],
              cwd=kok, check=False, timeout=120, env=alt_ortam(kok))
    if proc.returncode not in (0, 3):
        raise Stop(f"kb.py tara --maskele başarısız (çıkış {proc.returncode}).\n{ayrinti(proc)}")
    hedef = gecici_dizin() / f"maskeli-{guvenli_ad(kaynak.name)}"
    hedef.write_text(proc.stdout, encoding="utf-8")
    return {"yol": str(hedef), "bulgu": proc.returncode == 3}


# --- writing and committing ---

def frontmatter_id(metin):
    satirlar = metin.lstrip("﻿").splitlines()
    if not satirlar or satirlar[0].strip() != "---":
        raise Stop("Girdi '---' satırıyla başlayan YAML frontmatter ile başlamalı.")
    girdi_id = None
    for satir in satirlar[1:]:
        if satir.strip() == "---":
            if not girdi_id:
                raise Stop("Frontmatter'da `id:` alanı yok.")
            return girdi_id
        match = re.match(r"""^id:\s*["']?([^"'\s#]+)""", satir)
        if match and girdi_id is None:
            girdi_id = match.group(1)
    raise Stop("Frontmatter kapanmamış (ikinci '---' satırı yok).")


def yayimlanmis_mi(kok, yol):
    """True if `yol` exists on origin/main, i.e. it is published and must not change."""
    return git(kok, "cat-file", "-e", f"origin/{DAL}:{yol}", check=False).returncode == 0


def yaz(argv):
    alan, argv = alan_ayikla(argv)
    parser = argparse.ArgumentParser(prog="tf_bilgi.py yaz")
    parser.add_argument("--dosya")
    parser.add_argument("--uzerine", action="store_true")
    args = parser.parse_args(argv)
    metin = Path(args.dosya).expanduser().read_text(encoding="utf-8") if args.dosya else sys.stdin.read()
    girdi_id = frontmatter_id(metin)
    match = GIRDI_ID_RE.match(girdi_id)
    if not match:
        raise Stop(f"Girdi kimliği sözleşmeye uymuyor: {girdi_id} (beklenen: <önek>-YYYYMMDD-<kisi>-NN).")
    kok = mevcut_kok(alan)
    ayar = depo_ayari(kok, alan)
    kisi, _ = kisi_bul(kok, [])
    yazar = re.search(r"""(?m)^yazar:\s*["']?([a-z][a-z0-9]*)""", metin)
    if kisi and (not yazar or yazar.group(1) != kisi or match.group(4) != kisi):
        raise Stop(f"Girdi yalnız kendi adınıza yazılır: kimlikteki ve `yazar` alanındaki kişi '{kisi}' olmalı.")
    onek = ayar.get("girdi_onek")
    if onek and match.group(1) != onek:
        raise Stop(f"{girdi_id} bu depoya ait değil: bu deponun girdi öneki '{onek}'. Kimliği `kb taslak` ile "
                   "bu depodan alın.")
    yol = f"girdiler/{match.group(2)}/{match.group(3)}/{girdi_id}.md"
    hedef = kok / yol
    if yayimlanmis_mi(kok, yol):
        raise Stop(f"{girdi_id} zaten yayımlanmış; yayımlanmış girdi değiştirilmez. Düzeltme yeni bir girdi olur "
                   "(`gecersiz_kildigi` ile).")
    if hedef.exists() and not args.uzerine:
        raise Stop(f"{yol} zaten var (henüz commit'lenmemiş). Bu taslağı düzeltiyorsanız --uzerine ekleyin; "
                   "değilse yeni bir kimlik alın.")
    hedef.parent.mkdir(parents=True, exist_ok=True)
    hedef.write_text(metin if metin.endswith("\n") else metin + "\n", encoding="utf-8")
    return {"id": girdi_id, "yol": yol, "tam_yol": str(hedef), "url": baglanti(uzak_slug(ayar, alan), yol)}


def goreli(kok, yol):
    yol_p = Path(yol).expanduser()
    if yol_p.is_absolute():
        try:
            return yol_p.resolve().relative_to(kok.resolve()).as_posix()
        except ValueError:
            raise Stop(f"{yol} önbellek deposunun ({kok}) dışında.")
    norm = os.path.normpath(yol).replace(os.sep, "/")
    if norm.startswith("../") or norm == "..":
        raise Stop(f"{yol} önbellek deposunun ({kok}) dışında.")
    return norm


def defter_yalniz_ekleme_mi(kok):
    yeni = (kok / DEFTER).read_text(encoding="utf-8")
    proc = git(kok, "show", f"origin/{DAL}:{DEFTER}", check=False)
    return proc.returncode != 0 or yeni.startswith(proc.stdout)


def kaydet(argv):
    alan, argv = alan_ayikla(argv)
    parser = argparse.ArgumentParser(prog="tf_bilgi.py kaydet")
    parser.add_argument("--mesaj", required=True)
    parser.add_argument("yollar", nargs="+")
    args = parser.parse_args(argv)
    kok = mevcut_kok(alan)
    ayar = depo_ayari(kok, alan)
    yollar = list(dict.fromkeys(goreli(kok, y) for y in args.yollar))
    sorunlar = []
    for yol in yollar:
        if not (kok / yol).is_file():
            sorunlar.append(f"{yol}: dosya yok")
        elif yol == DEFTER:
            if not defter_yalniz_ekleme_mi(kok):
                sorunlar.append(f"{DEFTER}: yalnız satır eklenebilir; mevcut satırlar değişmiş")
        elif not any(desen.match(yol) for desen in YENI_YOLLAR):
            sorunlar.append(f"{yol}: /paylas bu yola yazamaz (yalnız yeni girdiler/, ham/, onaylar/ dosyaları ve "
                            f"{DEFTER}; geri kalanı kütüphanecinin)")
        elif yayimlanmis_mi(kok, yol):
            sorunlar.append(f"{yol}: zaten yayımlanmış; yayımlanmış dosya değiştirilmez")
        elif ONAY_RE.match(yol) and ONAY_RE.match(yol).group(1) != kendi_kisin(kok):
            sorunlar.append(f"{yol}: 'alındı' yalnız kendi adınıza kaydedilir")
    hazir = [y for y in git(kok, "diff", "--cached", "--name-only").stdout.splitlines() if y and y not in yollar]
    if hazir:
        sorunlar.append(f"başka dosyalar commit için hazırlanmış: {', '.join(hazir[:5])} — önce: "
                        f"git -C \"{kok}\" restore --staged <dosya>")
    if sorunlar:
        raise Stop("Kayıt yapılmadı:\n- " + "\n- ".join(sorunlar))
    for anahtar in ("user.name", "user.email"):
        if not git(kok, "config", anahtar, check=False).stdout.strip():
            raise Stop(f"git kimliği eksik ({anahtar}). Terminalde: git config --global {anahtar} \"...\" "
                       "yapıp tekrar deneyin.")
    proc = sh([sys.executable, str(kb_yolu(kok)), "kaydet", "--mesaj", args.mesaj, *yollar],
              cwd=kok, check=False, timeout=600, env=alt_ortam(kok))
    cikti = "\n".join(x for x in (proc.stdout.strip(), proc.stderr.strip()) if x)[-2000:]
    if proc.returncode != 0:
        raise Stop(f"kb.py kaydet başarısız (çıkış {proc.returncode}). Dosyalar önbellekte duruyor ({kok}). "
                   f"Sorun giderilince aynı komutla tekrar deneyin.\n{cikti}")
    notlar = []
    ileride = git(kok, "rev-list", "--count", f"origin/{DAL}..HEAD", check=False).stdout.strip()
    gonderildi = ileride == "0"
    if not gonderildi:
        notlar.append("Commit yerelde kaldı, GitHub'a gönderilemedi. Bir sonraki kayıt gönderir; hemen göndermek "
                      f"için: git -C \"{kok}\" pull --rebase origin {DAL} && git -C \"{kok}\" push origin {DAL}")
    uzak = uzak_slug(ayar, alan)
    return {
        "commit": git(kok, "rev-parse", "HEAD").stdout.strip(),
        "gonderildi": gonderildi,
        "baglantilar": [{"yol": y, "url": baglanti(uzak, y)} for y in yollar if y != DEFTER],
        "cikti": cikti, "notlar": notlar,
    }


# --- PR rows for pr-listesi entries (read-only gh) ---

def repo_coz(ad):
    ad = ad.strip()
    if "/" in ad:
        return ad
    return f"{ORG}/{REPO_KISALTMALARI.get(ad.lower(), ad)}"


def kisa_ad(slug, numara):
    repo = slug.split("/", 1)[1]
    ters = {v: k for k, v in REPO_KISALTMALARI.items()}
    return f"{ters.get(repo, repo)}#{numara}"


def pr_ref_coz(ref, repolar):
    ref = ref.strip()
    match = re.search(r"github\.com/([^/\s]+/[^/\s]+)/pull/(\d+)", ref)
    if match:
        return match.group(1), int(match.group(2))
    match = re.fullmatch(r"([A-Za-z0-9_./-]+?)\s*#\s*(\d+)", ref)
    if match:
        return repo_coz(match.group(1)), int(match.group(2))
    match = re.fullmatch(r"#?(\d+)", ref)
    if match:
        if len(repolar) != 1:
            raise Stop(f"'{ref}' hangi repoda? api#123 gibi yazın ya da tek bir --repo verin.")
        return repolar[0], int(match.group(1))
    raise Stop(f"PR anlaşılamadı: {ref!r}. Örnek: api#1976, teamfluencer-web#689, PR linki ya da @me.")


def claude_review_durumu(rollup):
    for kontrol in rollup or []:
        if (kontrol.get("context") or kontrol.get("name")) != CLAUDE_REVIEW:
            continue
        durum = str(kontrol.get("state") or kontrol.get("conclusion") or kontrol.get("status") or "").upper()
        if durum == "SUCCESS":
            return "basarili"
        if durum in ("FAILURE", "ERROR", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED", "STARTUP_FAILURE"):
            return "basarisiz"
        return "bekliyor"
    return "yok"


def pr_satiri(slug, pr):
    merge = pr.get("mergeStateStatus") or "UNKNOWN"
    return {
        "pr": kisa_ad(slug, pr["number"]), "repo": slug, "numara": pr["number"], "baslik": pr.get("title"),
        "dal": pr.get("headRefName"), "taban": pr.get("baseRefName"), "url": pr.get("url"),
        "durum": pr.get("state"), "taslak": bool(pr.get("isDraft")),
        "claude_review": claude_review_durumu(pr.get("statusCheckRollup")),
        "merge_durumu": merge, "merge_durumu_tr": MERGE_DURUMU_TR.get(merge, merge.lower()),
        "bagimli": None,
    }


def prler(argv):
    parser = argparse.ArgumentParser(prog="tf_bilgi.py prler")
    parser.add_argument("refs", nargs="*")
    parser.add_argument("--repo", action="append", default=[])
    args = parser.parse_args(argv)
    on_kontrol(github=True)
    repolar = [repo_coz(r) for r in args.repo]
    refs = args.refs or ["@me"]
    satirlar, hatalar, gorulen = [], [], set()

    def ekle(slug, pr):
        anahtar = (slug.lower(), pr["number"])
        if anahtar not in gorulen:
            gorulen.add(anahtar)
            satirlar.append(pr_satiri(slug, pr))

    for ref in refs:
        if ref == "@me":
            for slug in repolar or [repo_coz(k) for k in REPO_KISALTMALARI]:
                try:
                    for pr in gh_json("pr", "list", "-R", slug, "--author", "@me", "--state", "open",
                                      "--limit", "50", "--json", PR_ALANLARI) or []:
                        ekle(slug, pr)
                except Stop as exc:
                    hatalar.append(f"{slug}: {str(exc).splitlines()[-1][:200]}")
            continue
        slug, numara = pr_ref_coz(ref, repolar)
        try:
            ekle(slug, gh_json("pr", "view", str(numara), "-R", slug, "--json", PR_ALANLARI))
        except Stop as exc:
            hatalar.append(f"{kisa_ad(slug, numara)}: {str(exc).splitlines()[-1][:200]}")
    # Stacked PRs: a PR whose base branch is another listed PR's head branch depends on it.
    dallar = {(s["repo"].lower(), s["dal"]): s["pr"] for s in satirlar}
    for satir in satirlar:
        satir["bagimli"] = dallar.get((satir["repo"].lower(), satir["taban"]))
    return {"satirlar": satirlar, "hatalar": hatalar}


KOMUTLAR = {"hazirla": hazirla, "gecici": gecici, "maskele": maskele, "yaz": yaz, "kaydet": kaydet, "prler": prler}
KULLANIM = ("kullanım: tf_bilgi.py hazirla [--yonetim] | kb [--yonetim] <komut> ... | gecici AD | "
            "maskele [--yonetim] DOSYA | yaz [--yonetim] [--dosya F] [--uzerine] | "
            "kaydet [--yonetim] --mesaj M YOL... | prler [REF...] [--repo R]")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv or (argv[0] not in KOMUTLAR and argv[0] != "kb"):
        print(KULLANIM, file=sys.stderr)
        return 64
    try:
        if argv[0] == "kb":
            return kb_calistir(argv[1:])
        sonuc = KOMUTLAR[argv[0]](argv[1:])
    except Stop as exc:
        print(str(exc))
        return 2
    print(json.dumps(sonuc, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
