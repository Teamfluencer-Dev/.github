#!/usr/bin/env python3
"""Helper for the tf-bilgi `/paylas` and `/bilgi` skills (Teamfluencer-Dev).

TF Bilgi is the team's knowledge base in two private GitHub repos (ekip, yonetim).
This script keeps a local cache clone of each and drives the repo's own
`araclar/kb.py`, which owns every rule (ids, scanning, topic matching,
validation, commit/push). The plugin depends only on the kb.py commands, flags
and JSON shapes of the TF Bilgi contract (sections 9 and 11), never on its code.
kb.py runs on every user's machine, so the plugin runs only the kb.py whose
sha256 is in KB_SHA256, in isolated mode (python3 -I). The pin is reviewed here;
the pinned kb.py itself is reviewed in a pull request on the KB repo, and the
plugin PR that adds a hash links that KB PR and its head SHA (KB CLAUDE.md §12).

  hazirla [--yonetim] [--yazma]  Clone or update the cache clone, resolve the
                                 person, print JSON (kok, alan, kisi, kb, uzak,
                                 yazabilir, ...). --yazma (/paylas, /toplu-paylas,
                                 /bilgi alindi): stop if GitHub says the user cannot
                                 push to the KB repo (only the people in its
                                 .kb.json `yazanlar` can) or if the person is unknown.
  kb [--yonetim] <args...>       Run the cache's kb.py; stdout, stderr and exit
                                 code pass through. kaydet/yenile/ozet are refused.
                                 alindi/izin-ekle only in your own name; a member
                                 of `yazanlar` may record alindi for someone else
                                 (--kaydeden <you> is added). toplu-hazirla
                                 (/toplu-paylas) needs absolute source paths and
                                 one --cikti strictly under <cache>/gecici/.
  gecici AD                      Save stdin as <cache>/gecici/AD (scratch input for
                                 kb.py --dosya / tara; never inside a clone).
  maskele [--yonetim] DOSYA [--dizin D]
                                 kb.py tara --maskele -> masked copy in <cache>/gecici/
                                 (or in D, a folder under it).
  temizle YOL...                 Delete staging folders/files; only strictly under
                                 <cache>/gecici/ (full-text copies of documents).
  yaz [--yonetim] [--dosya F] [--uzerine]
                                 Write a new entry (stdin or F) to
                                 girdiler/YYYY/MM/<id>.md, only in your own name;
                                 published entries are never overwritten.
  kaydet [--yonetim] (--mesaj M | --mesaj-dosya F) YOL...
                                 Contract section 10 guard (only new girdiler/,
                                 ham/, onaylar/ files and an append-only
                                 ham/DEFTER.tsv; no raw file or ledger row for a
                                 gizli entry, also across calls), then kb.py
                                 kaydet; prints links.
                                 F: first line of a file under <cache>/gecici/.
  prler [REF...] [--repo R]...   Read-only PR rows for a pr-listesi entry:
                                 claude-review state, merge state, stacking.
  bildirim-plani [--yonetim] --tip T --kimden a,b --yazar K [--son-tarih D]
                 [--haber hemen|gunluk] [--adet N]
                                 Read-only: who gets an instant notification now
                                 and who only the 08:30 digest, on which channel,
                                 and who gets nothing (one Turkish line for the card).
  tercih [--kanal slack,mail,whatsapp] [--kisi K]
                                 Notification channel preference: read it from the
                                 "Bildirim tercihleri" issue, or post one
                                 `tercih: kanal=...` comment there (gh issue comment;
                                 read access is enough, no push).
  gizli-alicilar [--yonetim] --kimden a,b
                                 Read-only, for a confidential (gizli) share: each
                                 recipient's work e-mail from kisiler.json (the
                                 address to add in Google Drive "Paylaş"), or null
                                 when none is recorded, and whether they are a member
                                 of the area. Never guesses an address.

No model calls and no API keys: only git, the GitHub CLI and kb.py. Python 3.9+,
stdlib only. Messages for the user are Turkish; exit code 2 means "show this
message to the user as-is".
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
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
KIMLIK_ONEKI_RE = re.compile(r"^(?:girdiler/\d{4}/\d{2}/|onaylar/)([A-Z]+)-")  # girdi/onay kimliğinin alan öneki
DEFTER = "ham/DEFTER.tsv"
IZINLER = "ham/IZINLER.tsv"  # insanın onayladığı yanlış alarmlar: yalnız satır eklenir, onaylayan = sen
# Sözleşme §10: /paylas ve /bilgi oturumunun kb.py'de çalıştırabildiği alt komutlar (yazanlar yalnız
# ham-ekle ve alindi; commit'i her zaman `tf_bilgi.py kaydet` yapar).
KB_IZINLI = ("taslak", "yeni-id", "eslestir", "tara", "dogrula", "ham-ekle", "son", "konu", "ara", "kuyruk", "alindi",
             "izin-ekle", "toplu-hazirla")
KENDI_ADINA = ("alindi", "izin-ekle")  # --kisi çözülen kişi olmalı (alindi: yazanlar başkası adına da, kaydeden ile)
# Sözleşme: eklenti yalnız bu sha256'lardan birine sahip araclar/kb.py'yi çalıştırır (ekip ve yönetim kopyası bayt bayt
# aynı). kb.py değişikliği KB deposunda PR ile incelenir; yeni hash'i buraya ekleyen eklenti PR'ı o KB PR'ını ve head
# SHA'sını gösterir (/pr-review, sürüm artar). İki PR aynı gün merge edilir: KB PR'ı eklenti merge'ünün hemen ardından;
# eski eklenti o andan sonra durur (kapalı kalır). Geçişte eski ve yeni hash birlikte durur, eski hash bir sonraki sürümde
# çıkar (KB CLAUDE.md §12).
# 0.4.0 geçişi: ilki GitHub'daki KB deposunda bugün duran kb.py (0.3.1'in sabiti), ikincisi gizli paylaşımlı kb.py
# (taslak --gizli, §4.6): Teamfluencer-Dev/tf-bilgi#2, head 76fd0e76a10aec6a7d14424062cb1fb68bd216c2. Ara sürümler hiç
# yayınlanmadı, sabitlenmez. Yönetim deposu (tf-bilgi-yonetim) GitHub'da henüz yok: hiçbir 0.3.1 kullanıcısı ona
# erişemedi; açıldığında ilk push'u bu yeni kb.py ile yapılır.
KB_SHA256 = (
    "76677edd9f348d1dea7827f3449cf8fb6b8767705b896264129260329a27da23",  # 0.3.1: GitHub'daki KB deposunun kb.py'si
    "e6b4e22430ee55666e55e620969f8df67bd37d17991fdeac8660bec964eddaa6",  # 0.4.0: tf-bilgi#2 head 76fd0e7
)
KOK_SECENEGI = re.compile(r"^--k(?:o(?:k)?)?(?:=|$)")        # --kok ve argparse kısaltmaları (--k, --ko)
DEGERLI_SECENEK = re.compile(r"^--b(?:u(?:g(?:u(?:n)?)?)?)?$")  # --bugun ve kısaltmaları değer alır
KISI_SECENEGI = re.compile(r"^--ki(?:s(?:i)?)?(?:=(.*))?$")   # alindi --kisi (ve kısaltmaları)
KAYDEDEN_SECENEGI = re.compile(r"^--ka(?:y(?:d(?:e(?:d(?:e(?:n)?)?)?)?)?)?(?:=(.*))?$")  # alindi --kaydeden
KONTROL_KARAKTER_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]")
CIKTI_SECENEGI = re.compile(r"^--c(?:i(?:k(?:t(?:i)?)?)?)?(?:=(.*))?$")  # toplu-hazirla --cikti (ve kısaltmaları)
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
KIM_BILINMIYOR = ("Kim olduğunuz bulunamadı; depoya yalnız kendi adınıza yazılır. Kabuk profilinize "
                  "`export TF_BILGI_KISI=<kisiler.json anahtarınız>` ekleyip Claude Code'u yeniden başlatın (ya da "
                  "`gh auth login` ile kisiler.json'daki GitHub hesabınıza geçin).")
REMOTE_MANIFEST = (
    "https://raw.githubusercontent.com/Teamfluencer-Dev/.github/main/"
    "claude-plugins/tf-bilgi/.claude-plugin/plugin.json"
)
KANALLAR = ("slack", "mail", "whatsapp")
ISTEK_TIPLERI = ("EYLEM", "KARAR", "INCELE", "BILGI")
ACIL_TIPLER = ("EYLEM", "KARAR")
# KB deposundaki araclar/bildir.py ile aynı kurallar (sözleşme §10): tercih satırı, sessiz saat, günlük sınır.
TERCIH_RE = re.compile(r"^tercih:\s*(?:kisi=([a-z][a-z0-9]*)\s+)?kanal=([a-z]+(?:\s*,\s*[a-z]+)*)\s*$")
SESSIZ_BAS, SESSIZ_BIT = (19, 0), (8, 30)
ANLIK_GUNLUK_SINIR, ANLIK_GUN_ESIGI = 3, 2
GUN_KISA = ("Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz")
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
        env["TF_BILGI_GECICI"] = str(onbellek_koku() / "gecici")  # kb.py --*-dosya buradan okuyabilir
    return env


def kb_komutu(kb, *args):
    """kb.py'yi yalıtılmış çalıştır: -I betik klasörünü sys.path'e koymaz (araclar/'a konan bir json.py ya da yaml.py
    kb.py'nin içe aktarmasını değiştiremez) ve PYTHON* değişkenlerini yok sayar; -B klona __pycache__ yazmaz."""
    return [sys.executable, "-I", "-B", str(kb), *args]


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
    """Klonun kb.py'si; yalnız eklentinin onayladığı sürüm (KB_SHA256) çalıştırılır."""
    kb = kok / "araclar" / "kb.py"
    if not kb.is_file():
        raise Stop(f"Depoda araclar/kb.py yok ({kok}). Depo henüz kurulmamış olabilir; TF Bilgi sorumlusuna haber verin.")
    ozet = hashlib.sha256(kb.read_bytes()).hexdigest()
    if ozet not in KB_SHA256:
        raise Stop("KB aracı (araclar/kb.py) eklentinin onayladığı sürüm değil; güvenlik için çalıştırmadım "
                   f"(sha256 {ozet[:12]}…). Eklentiyi güncelle: claude plugin marketplace update teamfluencer && "
                   "claude plugin update tf-bilgi@teamfluencer — sonra Claude Code'u yeniden başlat. Güncel "
                   "eklentide de sürerse TF Bilgi sorumlusuna haber ver.")
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
    # kb.py gibi: nesne olmayan kayıt (ör. null) kişi sayılmaz
    return {k: v for k, v in kisiler.items() if isinstance(v, dict)} if isinstance(kisiler, dict) else {}


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


def damga():
    """YYYYMMDD-HHMMSS (Europe/Istanbul): /toplu-paylas hazırlık klasörünün adı için."""
    try:
        from zoneinfo import ZoneInfo
        simdi = datetime.datetime.now(ZoneInfo("Europe/Istanbul"))
    except Exception:
        simdi = datetime.datetime.now()
    return simdi.strftime("%Y%m%d-%H%M%S")


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


def ilk_ad(kisiler, anahtar):
    return (str((kisiler.get(anahtar) or {}).get("ad") or anahtar).split() or [anahtar])[0]


def yonelme(ad):
    """Türkçe yönelme hâli: Mert → Mert'e, Can → Can'a, Ayşe → Ayşe'ye, Duru → Duru'ya."""
    unlu = "aeıioöuüAEIİOÖUÜ"
    son = next((c for c in reversed(ad) if c in unlu), "e")
    return ad + "'" + ("y" if ad[-1:] and ad[-1] in unlu else "") + ("a" if son in "aıouAIOU" else "e")


def adlari_bagla(adlar):
    return adlar[0] if len(adlar) == 1 else ", ".join(adlar[:-1]) + " ve " + adlar[-1]


def yazma_yetkisi(deger, github):
    """GitHub'a göre push yetkisi: True/False; None = denetlenemedi ya da GitHub dışı (yerel) uzak."""
    if not github or not which("gh"):
        return None
    proc = sh(["gh", "api", f"repos/{deger}", "--jq", ".permissions.push"], check=False, timeout=30)
    deger = proc.stdout.strip().lower() if proc.returncode == 0 else ""
    return {"true": True, "false": False}.get(deger)


def yazan_mi(ayar, kisi):
    """kisi .kb.json `yazanlar` listesinde mi (başkası adına alındı yalnız onlara açık)."""
    yazanlar = ayar.get("yazanlar")
    return bool(kisi) and isinstance(yazanlar, list) and kisi in yazanlar


def yetkisiz_mesaj(kok, ayar, uzak):
    """Yazma yetkisi olmayana: kimin yazabildiği (.kb.json yazanlar, adlar kisiler.json'dan) ve ne yapacağı."""
    kisiler = kisileri_oku(kok)
    yazanlar = [k for k in (ayar.get("yazanlar") or []) if isinstance(k, str) and k in kisiler]
    login = gh_login()
    hesap = f"GitHub hesabının ({login}) " if login else "GitHub hesabının "
    okuma = "Okuma çalışmaya devam eder: /bilgi kuyrugum, /bilgi son, /bilgi konu, /bilgi ara."
    if yazanlar:
        try:
            ben = kisi_bul(kok, [])[0]
        except Stop:
            ben = None
        adlar = [ilk_ad(kisiler, k) for k in yazanlar]
        return (f"Bu depoya yalnız {adlari_bagla(adlar)} yazabiliyor; paylaşmak istediğini {yonelme(adlar[0])} ilet "
                f"(belgeyi ya da bağlantısını gönder), o kaydeder. Devir ya da karar için 'alındı' demek istiyorsan "
                f"ona “alındı <girdi-id>” yaz; o `/bilgi alindi <girdi-id> --kisi {ben or '<anahtarın>'}` ile senin "
                f"adına kaydeder. {hesap}{uzak} deposunda yazma yetkisi yok. {okuma}")
    return (f"{hesap}{uzak} deposunda yazma yetkisi yok; paylaşmak istediğini depoya yazabilen birine ilet. {okuma}")


def hazirla(argv):
    parser = argparse.ArgumentParser(prog="tf_bilgi.py hazirla")
    parser.add_argument("--yonetim", action="store_true")
    parser.add_argument("--yazma", action="store_true",
                        help="yazacak iş (/paylas, /toplu-paylas, /bilgi alindi): yazma yetkisi yoksa dur")
    args = parser.parse_args(argv)
    alan = alan_sec(args.yonetim)
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
    yazabilir = yazma_yetkisi(deger, github)
    if args.yazma and yazabilir is False:
        raise Stop(yetkisiz_mesaj(kok, ayar, uzak_slug(ayar, alan)))
    if args.yazma and github and yazabilir is None:
        notlar.append("Yazma yetkin denetlenemedi (gh api yanıt vermedi); kayıtta GitHub reddederse paylaşmak "
                      "istediğini depoya yazabilen birine ilet.")
    kisi, kaynak = kisi_bul(kok, notlar)
    kisiler = kisileri_oku(kok)
    uzak = uzak_slug(ayar, alan)
    if args.yazma and kisi is None:
        raise Stop(KIM_BILINMIYOR)
    if kisi is None:
        notlar.append("Kim olduğunuz bulunamadı; bir kez sorulacak. Kalıcı olsun diye kabuk profilinize "
                      "`export TF_BILGI_KISI=<kisiler.json anahtarınız>` ekleyin.")
    elif alan not in (kisiler.get(kisi, {}).get("alanlar") or []):
        notlar.append(f"kisiler.json'da '{kisi}' bu alana ({alan}) kayıtlı değil; okuma kuyruğunuz burada üretilmez.")
    gun = bugun()
    sonuc = {
        "kok": str(kok), "alan": alan, "kisi": kisi, "kb": str(kb), "uzak": uzak, "yazabilir": yazabilir,
        "damga": damga(),
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


def secenek_degeri(argv, desen):
    for i, t in enumerate(argv):
        m = desen.match(t)
        if m:
            return m.group(1) if m.group(1) is not None else (argv[i + 1] if i + 1 < len(argv) else None)
    return None


def alindi_kisisi(argv):
    return secenek_degeri(argv, KISI_SECENEGI)


def toplu_hazirla_denetle(argv):
    """toplu-hazirla: hazırlık klasörü yalnız eklentinin gecici/ klasörünün altında, yollar mutlak.

    kb.py önbellek klonunda (cwd) çalıştığı için göreli yol klonun içine çözülürdü; mutlak yol istenir."""
    ciktilar, kaynaklar, komut_gecti, i = [], [], False, 0
    while i < len(argv):
        t = argv[i]
        m = CIKTI_SECENEGI.match(t)
        if m:
            deger = m.group(1) if m.group(1) is not None else (argv[i + 1] if i + 1 < len(argv) else "")
            ciktilar.append(deger)
            i += 1 if m.group(1) is not None else 2
        elif DEGERLI_SECENEK.match(t):
            i += 2
        elif t.startswith("-") and t != "-":
            i += 1
        else:
            if komut_gecti:
                kaynaklar.append(t)
            komut_gecti = True
            i += 1
    gecici = gecici_dizin().resolve()
    if len(ciktilar) != 1 or not ciktilar[0]:
        raise Stop(f"toplu-hazirla için tek bir --cikti klasörü gerekli: {gecici}/toplu-<damga>")
    cikti = Path(ciktilar[0]).expanduser()
    if not cikti.is_absolute():
        raise Stop(f"--cikti mutlak yol olmalı: {ciktilar[0]} (örnek: {gecici}/toplu-<damga>)")
    if gecici not in cikti.resolve().parents:
        raise Stop(f"--cikti yalnız eklentinin geçici klasörünün altında olabilir ({gecici}/…): {ciktilar[0]}")
    if not kaynaklar:
        raise Stop("toplu-hazirla için en az bir dosya ya da klasör yolu gerekli.")
    for k in kaynaklar:
        if not Path(k).expanduser().is_absolute():
            raise Stop(f"Kaynak yolu mutlak olmalı: {k} (kb.py önbellek klonunda çalışır; göreli yol orada çözülür)")


def kendi_kisin(kok):
    """Çözülen kişi; çözülemiyorsa yazma işlemi durur."""
    kisi, _ = kisi_bul(kok, [])
    if not kisi:
        raise Stop(KIM_BILINMIYOR)
    return kisi


def alindi_argumanlari(kok, alan, argv, istenen, ben):
    """alindi: kendi adına; `yazanlar`'daki biri başkası adına da (kaydeden = o). Gerekirse --kaydeden eklenir."""
    kaydeden = secenek_degeri(argv, KAYDEDEN_SECENEGI)
    if kaydeden not in (None, ben):
        raise Stop(f"'alindi' kaydını yalnız kendiniz kaydedersiniz: --kaydeden {kaydeden!r} ama siz '{ben}'.")
    if istenen == ben:
        return argv
    if not yazan_mi(depo_ayari(kok, alan), ben):
        raise Stop(f"'alindi' yalnız kendi adınıza yazılır: --kisi {istenen!r} ama siz '{ben}'. Başkası adına alındıyı "
                   "yalnız deponun `yazanlar` listesindekiler kaydeder; onlardan birine “alındı <girdi-id>” yazın.")
    return argv if kaydeden else [*argv, "--kaydeden", ben]  # `--` reddedildi: sona eklemek güvenli


def kb_calistir(argv):
    alan, argv = alan_ayikla(argv)
    if not argv:
        raise Stop("kullanım: tf_bilgi.py kb [--yonetim] <kb.py komutu> [argümanlar]")
    if any(KOK_SECENEGI.match(t) for t in argv):
        raise Stop("--kok verilemez: kb.py her zaman TF Bilgi önbellek klonunda çalışır.")
    adlar = [t.split("=", 1)[0] for t in argv if t.startswith("--") and t != "--"]
    if len(adlar) != len(set(adlar)) or any(sum(1 for t in argv if desen.match(t)) > 1
                                            for desen in (KISI_SECENEGI, KAYDEDEN_SECENEGI)):
        raise Stop("Aynı seçenek iki kez verilemez (ör. --kisi). Komutu tek seçenekle tekrar yazın.")
    komut = kb_alt_komutu(argv)
    if komut in KB_YASAK:
        raise Stop(KB_YASAK[komut])
    if komut not in KB_IZINLI:
        raise Stop(f"kb.py alt komutu izinli değil: {komut!r} (izinliler: {', '.join(KB_IZINLI)}).")
    kok = mevcut_kok(alan)
    kb = kb_yolu(kok)
    if komut in KENDI_ADINA:
        if "--" in argv:
            raise Stop(f"'{komut}' komutunda `--` kullanılmaz; seçenekleri doğrudan yazın.")
        istenen, kisi = alindi_kisisi(argv), kendi_kisin(kok)
        if istenen is None:
            raise Stop(f"'{komut}' için --kisi gerekli (sizin anahtarınız: {kisi}).")
        if komut == "alindi":
            argv = alindi_argumanlari(kok, alan, argv, istenen, kisi)
        elif istenen != kisi:
            raise Stop(f"'{komut}' yalnız kendi adınıza yazılır: --kisi {istenen!r} ama siz '{kisi}'.")
    if komut == "toplu-hazirla":
        toplu_hazirla_denetle(argv)
    sys.stdout.flush()
    return subprocess.run(kb_komutu(kb, *argv), cwd=kok, env=alt_ortam(kok)).returncode


def guvenli_ad(ad):
    temiz = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(ad).name).strip(".-")
    if not temiz:
        raise Stop(f"Geçersiz dosya adı: {ad!r}")
    return temiz


def gecici_dizin():
    yol = onbellek_koku() / "gecici"
    yol.mkdir(parents=True, exist_ok=True)
    return yol


def gecici_alti(yol, ne):
    """`yol` mutlak ve eklentinin geçici klasörünün (gecici/) kesinlikle altında (bağlantıyla dışarı çıkmadan)."""
    gecici = gecici_dizin().resolve()
    p = Path(yol).expanduser()
    if not p.is_absolute():
        raise Stop(f"{ne} mutlak yol olmalı: {yol} (örnek: {gecici}/paylas-<damga>)")
    if gecici not in p.resolve().parents:
        raise Stop(f"{ne} yalnız eklentinin geçici klasörünün altında olabilir ({gecici}/…): {yol}")
    return p.resolve()


def dosyadan_satir(yol, azami=200):
    """Dosyanın ilk dolu satırı, kontrol karakterleri atılmış (güvenilmeyen metin kabuk argümanına girmesin diye)."""
    for satir in Path(yol).read_text(encoding="utf-8").splitlines():
        satir = KONTROL_KARAKTER_RE.sub("", satir).strip()
        if satir:
            return satir[:azami]
    return ""


def temizle(argv):
    """Hazırlık klasörlerini ve geçici dosyaları siler; yalnız gecici/'nin kesinlikle altındakileri (belgelerin tam
    metin kopyaları KVKK açısından bekletilmez). Önce hepsi denetlenir, sonra silinir; olmayan yol hata değildir."""
    parser = argparse.ArgumentParser(prog="tf_bilgi.py temizle")
    parser.add_argument("yollar", nargs="+")
    args = parser.parse_args(argv)
    gecici = gecici_dizin().resolve()
    hedefler = []
    for yol in args.yollar:
        p = Path(yol).expanduser()
        if not p.is_absolute():
            raise Stop(f"temizle için mutlak yol gerekli: {yol} (örnek: {gecici}/paylas-<damga>)")
        ust = p.parent.resolve()
        if p.name in ("", ".", "..") or not (ust == gecici or gecici in ust.parents):
            raise Stop(f"temizle yalnız eklentinin geçici klasörünün altındakileri siler ({gecici}/…): {yol}")
        hedefler.append(ust / p.name)
    silinen, yoktu = [], []
    for p in hedefler:
        if p.is_symlink() or p.is_file():
            p.unlink()  # bağlantının yalnız kendisi silinir, gösterdiği yer değil
        elif p.is_dir():
            shutil.rmtree(p)
        else:
            yoktu.append(str(p))
            continue
        silinen.append(str(p))
    return {"silinen": silinen, "yoktu": yoktu}


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
    parser.add_argument("--dizin", help="maskeli kopyanın klasörü (gecici/ altında; ör. /paylas hazırlık klasörü)")
    args = parser.parse_args(argv)
    kaynak = Path(args.dosya).expanduser()
    if not kaynak.is_file():
        raise Stop(f"Dosya bulunamadı: {kaynak}")
    if ikili_mi(kaynak):
        raise Stop(f"{kaynak.name} metin dosyası değil; maskelenemez. Bu dosyayı ham/'a almayın: girdide `ham: null` "
                   "ve `ham_notu: \"sır içerdiği için depoya alınmadı\"` yazın.")
    dizin = gecici_alti(args.dizin, "--dizin") if args.dizin else gecici_dizin()
    kok = mevcut_kok(alan)
    proc = sh(kb_komutu(kb_yolu(kok), "tara", str(kaynak.resolve()), "--maskele"),
              cwd=kok, check=False, timeout=120, env=alt_ortam(kok))
    if proc.returncode not in (0, 3):
        raise Stop(f"kb.py tara --maskele başarısız (çıkış {proc.returncode}).\n{ayrinti(proc)}")
    dizin.mkdir(parents=True, exist_ok=True)
    hedef = dizin / f"maskeli-{guvenli_ad(kaynak.name)}"
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
    kisi = kendi_kisin(kok)  # çözülemeyen kişiyle yazılmaz: girdi yalnız kendi adınıza
    yazar = re.search(r"""(?m)^yazar:\s*["']?([a-z][a-z0-9]*)""", metin)
    if not yazar or yazar.group(1) != kisi or match.group(4) != kisi:
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


def defter_yalniz_ekleme_mi(kok, yol=DEFTER):
    yeni = (kok / yol).read_text(encoding="utf-8")
    proc = git(kok, "show", f"origin/{DAL}:{yol}", check=False)
    return proc.returncode != 0 or yeni.startswith(proc.stdout)


def yeni_satirlar(kok, yol):
    """origin'dekine göre bir yalnız-ekleme defterine (DEFTER.tsv, IZINLER.tsv) eklenen satırlar (başlık hariç)."""
    yeni = (kok / yol).read_text(encoding="utf-8").splitlines()
    proc = git(kok, "show", f"origin/{DAL}:{yol}", check=False)
    eski = proc.stdout.splitlines() if proc.returncode == 0 else yeni[:1]
    return yeni[len(eski):]


def izinler_yeni_satirlari(kok):
    """origin'dekine göre IZINLER.tsv'ye eklenen satırlar (başlık hariç)."""
    return yeni_satirlar(kok, IZINLER)


def gizli_kimlik_mi(kok, girdi_id):
    """Bu kimlikteki girdi gizli mi: klonda (commit'lenmemiş dahil) ya da origin/main'de `gizli: true`."""
    m = GIRDI_ID_RE.match(girdi_id or "")
    if not m:
        return False
    yol = f"girdiler/{m.group(2)}/{m.group(3)}/{girdi_id}.md"
    if (kok / yol).is_file() and gizli_girdi_mi((kok / yol).read_text(encoding="utf-8")):
        return True
    proc = git(kok, "show", f"origin/{DAL}:{yol}", check=False)
    return proc.returncode == 0 and gizli_girdi_mi(proc.stdout)


def gizli_ham_sorunlari(kok, yollar):
    """Gizli girdiye ham dosya bağlanamaz (belge hiçbir depoya girmez), ayrı kaydet çağrılarında da: aynı çağrıdaki gizli
    girdi, DEFTER.tsv'ye eklenen satırın `girdi` sütunu ve verilen ham/ yolunun yerel defterdeki satırı denetlenir."""
    sorunlar = []
    gizliler = [y for y in yollar if y.startswith("girdiler/") and (kok / y).is_file()
                and gizli_girdi_mi((kok / y).read_text(encoding="utf-8"))]
    hamlar = [y for y in yollar if y.startswith("ham/") and y not in (DEFTER, IZINLER)]
    if gizliler and hamlar:
        sorunlar.append(f"gizli girdiyle ({', '.join(Path(y).stem for y in gizliler)}) ham/ dosyası kaydedilmez: "
                        f"belge hiçbir depoya girmez ({', '.join(hamlar[:3])})")
    defter = kok / DEFTER
    satirlar = [s.split("\t") for s in defter.read_text(encoding="utf-8").splitlines()[1:]] if defter.is_file() else []
    if DEFTER in yollar and defter.is_file():
        yeni = sorted({p[2] for p in (s.split("\t") for s in yeni_satirlar(kok, DEFTER)) if len(p) >= 3
                       and gizli_kimlik_mi(kok, p[2])})
        if yeni:
            sorunlar.append(f"{DEFTER}: gizli girdiye ({', '.join(yeni)}) ham dosya satırı eklenemez: belge hiçbir "
                            "depoya girmez")
    defter_girdi = {p[1]: p[2] for p in satirlar if len(p) >= 3}
    bagli = sorted({y for y in hamlar if gizli_kimlik_mi(kok, defter_girdi.get(y))})
    if bagli:
        sorunlar.append(f"{', '.join(bagli)}: defterde gizli bir girdiye bağlı; gizli girdinin ham dosyası kaydedilmez")
    return sorunlar


def onay_kaydeden(metin):
    """Onay dosyasının frontmatter'ındaki `kaydeden` (yoksa None)."""
    satirlar = metin.lstrip("﻿").splitlines()
    if not satirlar or satirlar[0].strip() != "---":
        return None
    for satir in satirlar[1:]:
        if satir.strip() in ("---", "..."):
            break
        m = re.match(r"""^kaydeden:\s*["']?([^"'\s#]*)""", satir)
        if m:
            return None if m.group(1) in ("", "null", "~") else m.group(1)
    return None


def gizli_girdi_mi(metin):
    """Frontmatter'da `gizli: true` var mı (gizli girdi: belge hiçbir depoya girmez, KB CLAUDE.md §4.6)."""
    satirlar = metin.lstrip("\ufeff").splitlines()
    if not satirlar or satirlar[0].strip() != "---":
        return False
    for satir in satirlar[1:]:
        if satir.strip() in ("---", "..."):
            return False
        if re.match(r"^gizli:\s*true\s*(?:#.*)?$", satir.strip(), re.I):
            return True
    return False


def onay_sorunu(kok, ayar, yol):
    """onaylar/<id>--<kisi>.md: kendi adınıza; başkası adına yalnız `yazanlar`'dan ve `kaydeden: <siz>` ile."""
    kisi = ONAY_RE.match(yol).group(1)
    ben = kendi_kisin(kok)
    kaydeden = onay_kaydeden((kok / yol).read_text(encoding="utf-8"))
    if kisi == ben:
        return None if kaydeden in (None, ben) else f"{yol}: `kaydeden` siz olmalısınız ('{ben}'), dosyada '{kaydeden}'"
    if not yazan_mi(ayar, ben):
        return (f"{yol}: 'alındı' yalnız kendi adınıza kaydedilir (başkası adına yalnız deponun `yazanlar` "
                "listesindekiler kaydeder)")
    if kaydeden != ben:
        return (f"{yol}: başkası adına alındıda `kaydeden: {ben}` olmalı; dosyayı `tf_bilgi.py kb alindi <girdi-id> "
                f"--kisi {kisi}` yazar")
    return None


def kaydet(argv):
    alan, argv = alan_ayikla(argv)
    parser = argparse.ArgumentParser(prog="tf_bilgi.py kaydet")
    grup = parser.add_mutually_exclusive_group(required=True)
    grup.add_argument("--mesaj")
    grup.add_argument("--mesaj-dosya", dest="mesaj_dosya",
                      help="commit mesajı bu dosyanın ilk satırından (gecici/ altında; başlık kabuğa girmez)")
    parser.add_argument("yollar", nargs="+")
    args = parser.parse_args(argv)
    if args.mesaj_dosya is not None:
        mesaj_dosyasi = gecici_alti(args.mesaj_dosya, "--mesaj-dosya")
        if not mesaj_dosyasi.is_file():
            raise Stop(f"Mesaj dosyası yok: {args.mesaj_dosya}")
        args.mesaj = dosyadan_satir(mesaj_dosyasi)
    if not args.mesaj.strip():
        raise Stop("Commit mesajı boş.")
    kok = mevcut_kok(alan)
    ayar = depo_ayari(kok, alan)
    kb = kb_yolu(kok)  # onaylanmamış kb.py'de yolları denetlemeye bile başlamadan dur
    if yazma_yetkisi(*uzak_kaynagi(alan)) is False:
        raise Stop(yetkisiz_mesaj(kok, ayar, uzak_slug(ayar, alan)))
    yollar = list(dict.fromkeys(goreli(kok, y) for y in args.yollar))
    onek = ayar.get("girdi_onek")
    sorunlar = []
    for yol in yollar:
        if not (kok / yol).is_file():
            sorunlar.append(f"{yol}: dosya yok")
        elif yol == DEFTER:
            if not defter_yalniz_ekleme_mi(kok):
                sorunlar.append(f"{DEFTER}: yalnız satır eklenebilir; mevcut satırlar değişmiş")
        elif yol == IZINLER:
            if not defter_yalniz_ekleme_mi(kok, IZINLER):
                sorunlar.append(f"{IZINLER}: yalnız satır eklenebilir; mevcut satırlar değişmiş")
            elif any((s.split("\t") + ["", "", ""])[2] != kendi_kisin(kok) for s in izinler_yeni_satirlari(kok)):
                sorunlar.append(f"{IZINLER}: yanlış alarm onayı yalnız kendi adınıza eklenir")
        elif not any(desen.match(yol) for desen in YENI_YOLLAR):
            sorunlar.append(f"{yol}: /paylas bu yola yazamaz (yalnız yeni girdiler/, ham/, onaylar/ dosyaları ve "
                            f"{DEFTER}; geri kalanı kütüphanecinin)")
        elif yayimlanmis_mi(kok, yol):
            sorunlar.append(f"{yol}: zaten yayımlanmış; yayımlanmış dosya değiştirilmez")
        elif onek and KIMLIK_ONEKI_RE.match(yol) and KIMLIK_ONEKI_RE.match(yol).group(1) != onek:
            sorunlar.append(f"{yol}: bu deponun girdi öneki '{onek}'; bu kimlik başka alana ait (ekip ve yönetim "
                            "girdileri birbirinin deposuna yazılmaz)")
        elif ONAY_RE.match(yol):
            sorun = onay_sorunu(kok, ayar, yol)
            if sorun:
                sorunlar.append(sorun)
    sorunlar += gizli_ham_sorunlari(kok, yollar)
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
    proc = sh(kb_komutu(kb, "kaydet", "--mesaj", args.mesaj, *yollar),
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


# --- notification preferences and plan (read-only except `tercih --kanal`) ---

def tercih_coz(yorumlar, kisiler, yoneticiler):
    """Issue yorumları → ({kisi: {kanallar, kaynak}}, uyarılar). bildir.py tercihleri_coz ile aynı kurallar: yazarı
    kisiler.json `github` hesabı olan, düzenlenmemiş yorum; en son kazanır; başkası adına yalnız yöneticiler."""
    gh_kisi = {str(v.get("github")).lower(): k for k, v in kisiler.items() if isinstance(v, dict) and v.get("github")}
    sonuc, uyarilar = {}, []
    for y in sorted(yorumlar, key=lambda y: (str(y.get("created_at") or ""), y.get("id") or 0)):
        satirlar = [s.strip() for s in str(y.get("body") or "").splitlines() if s.strip().lower().startswith("tercih:")]
        if not satirlar:
            continue
        login = str((y.get("user") or {}).get("login") or "")
        yer = f"yorum {y.get('id')} ({login or '?'})"
        if y.get("updated_at") and y.get("created_at") and y["updated_at"] != y["created_at"]:
            uyarilar.append(f"{yer} düzenlenmiş; sayılmaz")
            continue
        yazar = gh_kisi.get(login.lower())
        if not yazar:
            uyarilar.append(f"{yer} kisiler.json'daki bir GitHub hesabından değil; sayılmaz")
            continue
        for satir in satirlar:
            m = TERCIH_RE.match(satir.lower())
            kanallar = list(dict.fromkeys(k.strip() for k in m.group(2).split(","))) if m else []
            if not m or any(k not in KANALLAR for k in kanallar):
                uyarilar.append(f"{yer} bozuk satır; sayılmaz")
                continue
            hedef = m.group(1) or yazar
            if hedef != yazar and yazar not in yoneticiler:
                uyarilar.append(f"{yer} başkası ({hedef}) adına; yalnız tercih yöneticileri yazabilir")
                continue
            if hedef not in kisiler:
                uyarilar.append(f"{yer} kişi kisiler.json'da yok ({hedef})")
                continue
            sonuc[hedef] = {"kanallar": kanallar, "kaynak": f"yorum {str(y.get('created_at') or '')[:10]} · {login}"}
    return sonuc, uyarilar


def tercih_yeri(ayar, alan):
    no = ayar.get("tercih_issue")
    return (no if isinstance(no, int) and not isinstance(no, bool) and no > 0 else None,
            ayar.get("tercih_deposu") or uzak_slug(ayar, alan))


def issue_yorumlari(repo, no):
    proc = sh(["gh", "api", "--paginate", f"repos/{repo}/issues/{no}/comments?per_page=100", "--jq", ".[]"],
              check=False, timeout=60)
    if proc.returncode != 0:
        raise Stop(f"Bildirim tercihleri okunamadı ({repo} issue #{no}). {ERISIM_IPUCU}\nAyrıntı: {ayrinti(proc)}")
    return [json.loads(satir) for satir in proc.stdout.splitlines() if satir.strip()]


def tercihleri_getir(kok, ayar, alan, notlar):
    no, repo = tercih_yeri(ayar, alan)
    if not no:
        notlar.append("Bildirim tercihleri issue'su henüz yok: herkes varsayılanla (Slack, yoksa mail) alır.")
        return {}
    if not which("gh"):
        notlar.append("gh yok: bildirim tercihleri okunamadı, varsayılan (Slack, yoksa mail) gösterildi.")
        return {}
    try:
        sonuc, _ = tercih_coz(issue_yorumlari(repo, no), kisileri_oku(kok), set(ayar.get("tercih_yoneticileri") or []))
    except Stop:
        notlar.append(f"Bildirim tercihleri okunamadı ({repo} issue #{no}); varsayılan (Slack, yoksa mail) gösterildi.")
        return {}
    return sonuc


def simdi():
    sabit = os.environ.get("TF_BILGI_SIMDI")  # tests pin the moment
    if sabit:
        return datetime.datetime.fromisoformat(sabit)
    try:
        from zoneinfo import ZoneInfo
        return datetime.datetime.now(ZoneInfo("Europe/Istanbul"))
    except Exception:
        return datetime.datetime.now()


def sessiz_mi(an):
    return an.weekday() >= 5 or (an.hour, an.minute) >= SESSIZ_BAS or (an.hour, an.minute) < SESSIZ_BIT


def ozet_zamani(an):
    """Bir sonraki 08:30 günlük özetinin adı: 'bugün 08:30', 'yarın 08:30' ya da 'Pzt 08:30'."""
    gun = an.date()
    if gun.weekday() < 5 and (an.hour, an.minute) < SESSIZ_BIT:
        return "bugün 08:30"
    gun += datetime.timedelta(days=1)
    while gun.weekday() >= 5:
        gun += datetime.timedelta(days=1)
    return "yarın 08:30" if gun == an.date() + datetime.timedelta(days=1) else f"{GUN_KISA[gun.weekday()]} 08:30"


def kanal_etiketi(bilgi, kanallar):
    """kisiler.json'a göre beklenen kanallar ("Slack+mail" …) ve notlar. Gönderimde Slack/Workspace araması daha
    fazlasını bulabilir; burada yalnız depoda kayıtlı olana bakılır."""
    etiketler, notlar = [], []
    for k in kanallar:
        if k == "slack":
            e = "Slack" if bilgi.get("slack") else ("Slack/mail" if bilgi.get("eposta") else None)
        elif k == "mail":
            e = "mail" if bilgi.get("eposta") else None
        else:
            e = "mail" if bilgi.get("eposta") else None
            notlar.append("WhatsApp henüz kapalı → mail")
        if e and e not in etiketler:
            etiketler.append(e)
    return "+".join(etiketler), notlar


def bildirim_plani(argv):
    parser = argparse.ArgumentParser(prog="tf_bilgi.py bildirim-plani")
    parser.add_argument("--yonetim", action="store_true")
    parser.add_argument("--tip", required=True, choices=ISTEK_TIPLERI)
    parser.add_argument("--kimden", required=True, help="kişi anahtarları, virgülle")
    parser.add_argument("--yazar", required=True)
    parser.add_argument("--son-tarih", dest="son_tarih")
    parser.add_argument("--haber", choices=("hemen", "gunluk"), default="gunluk")
    parser.add_argument("--adet", type=int, default=1, help="aynı alıcılara giden girdi sayısı (toplu paylaşım)")
    args = parser.parse_args(argv)
    alan = alan_sec(args.yonetim)
    kok = mevcut_kok(alan)
    ayar = depo_ayari(kok, alan)
    kisiler = kisileri_oku(kok)
    alicilar = list(dict.fromkeys(k.strip() for k in args.kimden.split(",") if k.strip()))
    bilinmeyen = [k for k in alicilar + [args.yazar] if k not in kisiler]
    if not alicilar or bilinmeyen:
        raise Stop(f"Kişi anahtarı kisiler.json'da yok: {', '.join(bilinmeyen) or '(boş)'}")
    son = datetime.date.fromisoformat(args.son_tarih) if args.son_tarih else None
    an = simdi()
    sessiz = sessiz_mi(an)
    acil = args.tip in ACIL_TIPLER and son is not None and (son - an.date()).days <= ANLIK_GUN_ESIGI
    anlik = args.haber == "hemen" or acil
    zaman = ozet_zamani(an)
    notlar = []
    tercihler = tercihleri_getir(kok, ayar, alan, notlar)
    kisi_satirlari, gidecek, yok, parcalar, ek_notlar = [], [], [], [], []
    for k in alicilar:
        bilgi, ad = kisiler[k], ilk_ad(kisiler, k)
        t = tercihler.get(k)
        kanallar = t["kanallar"] if t else ["slack"]
        if k == args.yazar:
            durum, etiket = "gonderen", ""
            parcalar.append("sen (gönderen) bildirim almazsın")
        elif alan not in (bilgi.get("alanlar") or []):
            durum, etiket = "alan-disi", ""
            parcalar.append(f"{yonelme(ad)} bildirim gitmez ({alan} alanının üyesi değil)")
        else:
            etiket, kn = kanal_etiketi(bilgi, kanallar)
            ek_notlar += [n for n in kn if n not in ek_notlar]
            if etiket:
                durum = "simdi" if anlik and not sessiz else "ozet"
                gidecek.append(f"{ad} ({etiket})")
            else:
                durum = "kanal-yok"
                yok.append(ad)
        kisi_satirlari.append({"kisi": k, "ad": ad, "kanallar": kanallar, "tercih": "issue" if t else "varsayilan",
                               "etiket": etiket, "durum": durum})
    if gidecek:
        adlar = ", ".join(gidecek)
        if anlik and not sessiz:
            parcalar.insert(0, f"şimdi anlık: {adlar}")
        elif anlik:
            parcalar.insert(0, f"sessiz saat ({GUN_KISA[an.weekday()]} {an:%H:%M}): {adlar} {zaman} özetinde")
        else:
            parcalar.insert(0, f"{adlar} {zaman} özetinde")
    for ad in yok:
        parcalar.append(f"{ad}: kayıtlı kanal yok (Slack kimliği ve e-posta), gönderimde dizinde bulunamazsa "
                        "hiçbir şey gitmez")
    if anlik and not sessiz and args.adet > ANLIK_GUNLUK_SINIR:
        parcalar.append(f"kişi başı günde en çok {ANLIK_GUNLUK_SINIR} anlık; kalan {args.adet - ANLIK_GUNLUK_SINIR} "
                        f"girdi {zaman} özetinde")
    parcalar += ek_notlar
    return {"anlik": anlik, "sessiz": sessiz, "saat": f"{an:%H:%M}", "ozet_zamani": zaman,
            "alicilar": kisi_satirlari, "satir": " · ".join(parcalar), "notlar": notlar}


def kanal_cozumu(bilgi):
    """/bilgi tercih: depoda kayıtlı olana göre her kanalın çözülüp çözülmediği."""
    slack = ("Slack kimliği kayıtlı" if bilgi.get("slack") else
             "Slack kimliği kayıtlı değil: gönderimde e-postadan aranır, bulunamazsa mail" if bilgi.get("eposta") else
             "Slack kimliği ve e-posta kayıtlı değil: gönderimde Workspace dizininden aranır")
    mail = ("e-posta kayıtlı" if bilgi.get("eposta") else
            "e-posta kayıtlı değil: gönderimde Slack profilinden ya da Workspace dizininden aranır")
    whatsapp = ("henüz kapalı (hat ve sağlayıcı kararı bekliyor): o süre mail gider; telefon depoda tutulmaz, "
                "gönderimde Slack profilinden ya da Workspace dizininden okunur")
    return {"slack": slack, "mail": mail, "whatsapp": whatsapp}


def tercih(argv):
    parser = argparse.ArgumentParser(prog="tf_bilgi.py tercih")
    parser.add_argument("--kanal", help="slack, mail, whatsapp; virgülle birden çok")
    parser.add_argument("--kisi", help="başkası adına (yalnız tercih yöneticileri)")
    args = parser.parse_args(argv)
    kok = mevcut_kok("ekip")  # tercihler ekip deposundaki issue'da durur (iki alan için tek tercih)
    ayar = depo_ayari(kok, "ekip")
    kisiler = kisileri_oku(kok)
    yoneticiler = [k for k in (ayar.get("tercih_yoneticileri") or []) if isinstance(k, str)]
    no, repo = tercih_yeri(ayar, "ekip")
    if not no:
        kim = next((ilk_ad(kisiler, k) for k in yoneticiler + list(ayar.get("yazanlar") or []) if k in kisiler), None)
        raise Stop("Bildirim tercihleri issue'su henüz açılmamış (.kb.json tercih_issue boş). "
                   + (f"{yonelme(kim)} söyle: issue'yu o açıp numarasını .kb.json'a yazacak." if kim else
                      "Depo yöneticisine söyle: issue'yu açıp numarasını .kb.json'a yazacak."))
    ben = kendi_kisin(kok)
    hedef = args.kisi or ben
    if hedef not in kisiler:
        raise Stop(f"Kişi anahtarı kisiler.json'da yok: {hedef}")
    issue_url = f"https://github.com/{repo}/issues/{no}"
    if args.kanal is None:
        sonuc, uyarilar = tercih_coz(issue_yorumlari(repo, no), kisiler, set(yoneticiler))
        t = sonuc.get(hedef)
        return {"kisi": hedef, "kanallar": t["kanallar"] if t else ["slack"], "varsayilan": t is None,
                "kaynak": t["kaynak"] if t else "tercih yok: varsayılan Slack, Slack kimliği çözülemezse mail",
                "cozum": kanal_cozumu(kisiler[hedef]), "issue": issue_url, "uyarilar": uyarilar}
    kanallar = list(dict.fromkeys(k.strip().lower() for k in args.kanal.split(",") if k.strip()))
    if not kanallar or any(k not in KANALLAR for k in kanallar):
        raise Stop(f"Kanal anlaşılmadı: {args.kanal!r}. Seçenekler: slack, mail, whatsapp (virgülle birden çok).")
    if hedef != ben and ben not in yoneticiler:
        adlar = [ilk_ad(kisiler, k) for k in yoneticiler if k in kisiler]
        raise Stop("Başkası adına tercih yalnız tercih yöneticileri yazar"
                   + (f" ({adlari_bagla(adlar)})" if adlar else "") + f"; {ilk_ad(kisiler, hedef)} kendi tercihini "
                   "`/bilgi tercih <kanal>` ile yazabilir.")
    hesap, login = str(kisiler[ben].get("github") or ""), gh_login()
    if not hesap:
        raise Stop("kisiler.json'da GitHub kullanıcı adın yok, bu yüzden yorumun sayılmaz. Tercihini bir tercih "
                   "yöneticisine söyle; senin adına yazar.")
    if not login or login.lower() != hesap.lower():
        raise Stop(f"GitHub girişin ({login or 'yok'}) kisiler.json'daki hesabınla ({hesap}) aynı değil; yorum sayılmaz. "
                   "`gh auth login` ile doğru hesaba geç.")
    satir = f"tercih: kanal={','.join(kanallar)}" if hedef == ben else f"tercih: kisi={hedef} kanal={','.join(kanallar)}"
    proc = sh(["gh", "issue", "comment", str(no), "-R", repo, "--body", satir], check=False, timeout=60)
    if proc.returncode != 0:
        raise Stop(f"Tercih yorumu yazılamadı ({repo} issue #{no}). {ERISIM_IPUCU}\nAyrıntı: {ayrinti(proc)}")
    url = next((x for x in reversed(proc.stdout.split()) if x.startswith("https://")), issue_url)
    return {"yazildi": True, "kisi": hedef, "kanallar": kanallar, "satir": satir, "url": url,
            "cozum": kanal_cozumu(kisiler[hedef])}


# --- confidential (gizli) share: recipients' Drive addresses (read-only) ---

def gizli_alicilar(argv):
    """Gizli paylaşım (KB CLAUDE.md §4.6): Drive'da "Paylaş"a eklenecek iş e-postaları kisiler.json'dan. Adres yoksa
    null döner; tahmin edilmez (yanlış adrese paylaşmak belgeyi başkasına açar)."""
    parser = argparse.ArgumentParser(prog="tf_bilgi.py gizli-alicilar")
    parser.add_argument("--yonetim", action="store_true")
    parser.add_argument("--kimden", required=True, help="kişi anahtarları, virgülle")
    args = parser.parse_args(argv)
    alan = alan_sec(args.yonetim)
    kok = mevcut_kok(alan)
    kisiler = kisileri_oku(kok)
    anahtarlar = list(dict.fromkeys(k.strip() for k in args.kimden.split(",") if k.strip()))
    bilinmeyen = [k for k in anahtarlar if k not in kisiler]
    if not anahtarlar or bilinmeyen:
        raise Stop(f"Kişi anahtarı kisiler.json'da yok: {', '.join(bilinmeyen) or '(boş)'}")
    satirlar, parcalar, notlar = [], [], []
    for k in anahtarlar:
        bilgi, ad = kisiler[k], ilk_ad(kisiler, k)
        eposta = str(bilgi.get("eposta") or "").strip() or None
        uye = alan in (bilgi.get("alanlar") or [])
        satirlar.append({"kisi": k, "ad": ad, "eposta": eposta, "alan_uyesi": uye})
        parcalar.append(f"{ad}: {eposta}" if eposta else f"{ad}: e-postası kayıtlı değil (kisiler.json)")
        if not uye:
            notlar.append(f"{ad} {alan} alanının üyesi değil: bu alandan ona bildirim gitmez")
    eksik = [s["ad"] for s in satirlar if not s["eposta"]]
    if eksik:
        notlar.append(f"{adlari_bagla(eksik)} için e-posta kayıtlı değil: Drive'da adıyla aranıp iş adresi seçilmeli ya "
                      "da adres kişinin kendisine sorulmalı; tahmin edilmez.")
    return {"alicilar": satirlar, "eksik_eposta": eksik, "satir": " · ".join(parcalar), "notlar": notlar}


KOMUTLAR = {"hazirla": hazirla, "gecici": gecici, "maskele": maskele, "temizle": temizle, "yaz": yaz,
            "kaydet": kaydet, "prler": prler, "bildirim-plani": bildirim_plani, "tercih": tercih,
            "gizli-alicilar": gizli_alicilar}
KULLANIM = ("kullanım: tf_bilgi.py hazirla [--yonetim] [--yazma] | kb [--yonetim] <komut> ... | gecici AD | "
            "maskele [--yonetim] DOSYA [--dizin D] | temizle YOL... | yaz [--yonetim] [--dosya F] [--uzerine] | "
            "kaydet [--yonetim] (--mesaj M | --mesaj-dosya F) YOL... | prler [REF...] [--repo R] | "
            "bildirim-plani [--yonetim] --tip T --kimden a,b --yazar K [--son-tarih D] [--haber hemen|gunluk] [--adet N] | "
            "tercih [--kanal slack,mail,whatsapp] [--kisi K] | gizli-alicilar [--yonetim] --kimden a,b")


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
