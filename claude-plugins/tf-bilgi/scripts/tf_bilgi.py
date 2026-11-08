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
                                 Read-only: who gets a notification (at once, 7/24;
                                 no quiet hours, no digest) on which channel, and who
                                 gets nothing (one Turkish line for the card).
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
  yorum GIRDI_ID --dosya F [--gonder] [--yonetim]
                                 Entry discussion page (one GitHub issue per entry,
                                 title "[<id>] <başlık>", label `yorum` only when the
                                 user can push). F: the comment, written under
                                 <cache>/gecici/ with the Write tool (never a shell
                                 argument). Without --gonder: read-only plan (page or
                                 page to open, who is notified). With --gonder: scan
                                 with kb.py tara, open the page if missing, post the
                                 comment with the user's own gh login (read access is
                                 enough). Refused for gizli entries. A yönetim entry (--yonetim
                                 or a non-ekip id prefix) uses the yönetim repo's own pages,
                                 only for people who can read that repo.
  yorumlar GIRDI_ID [--son N] [--yonetim]
                                 Read-only: the page's comments, oldest first, names
                                 from kisiler.json `github`. Gizli: no public page.

Hızlı paylaşım (/paylas), 0.7.0; 0.9.0 (Claude Code herkes için):

  hizli [--yonetim | --ekip] [--otomatik] [--not-dosya F] [--ek PATH]...
                                 F: the user's own words, written verbatim under <cache>/gecici/
                                 with the Write tool (stdin is a fallback); deleted after a
                                 successful send, like --ek files under gecici/. --otomatik
                                 (the skill picked the file itself): only document-like files
                                 (html, pdf, md, txt, office, csv, images). The receipt names
                                 the files sent.
                                 One command, no questions, no draft, 7/24: the files and the
                                 words (govde.md) go to the inbox, the librarian classifies them.
                                 Links (Claude artifacts, Google Docs) are part of the words; they
                                 are never downloaded. The area (ekip | yonetim) is decided here,
                                 deterministically (contract §3, alan_sec), from the words, the
                                 sender and kisiler.json unless --yonetim / --ekip is given.
                                 A writer (push permission, checked with gh and cached for a day
                                 in ~/.tf-bilgi/hizli.json) gets one commit on main through the
                                 GitHub Git Data API (no clone, no kb.py):
                                 00-gelen/<YYYYMMDD-HHMMSS>-<kisi>-<rnd6>/ (files, govde.md,
                                 meta.json), then rings the bell (label `zil` removed and re-added
                                 on tf-bilgi issue #9 ekip / #10 yönetim) so the librarian runs at
                                 once; a bell failure never breaks the share. Everyone else sends
                                 it with a köprü key through the TF Bilgi Worker (Cloudflare,
                                 deployment `cf1`) into the Drive inbox, ekip or yönetim. Neither:
                                 one line telling them to write `anahtar` to the Slack bot.
                                 Secrets and personal data do not block; only the köprü key itself
                                 and files under ~/.tf-bilgi (except gecici/) are refused.
                                 Prints {kod, alan, alicilar, yol, dosyalar, satir, notlar}.

Köprü (bridge) path, 0.6.0; 0.9.0. A person with a köprü key (~/.tf-bilgi/anahtar, one
pasted string `tfb1.<deployment>.<secret>`, written by the Slack bot's one-line setup or by
`/bilgi kur`) works without GitHub. The bridge is a Cloudflare Worker that only takes shares
(kim, baslat, chunks, bitir, geri-al, alindi) and answers every read with `desteklenmiyor`;
reads come to people as Slack links. Deployment `cf1` talks to the Worker directly
(KOPRU_CF_ADRES; raw /parca chunks). Any other deployment is a Google Apps Script web app
(*.workers.dev is blocked from Turkey): `kim` first; `protokol >= 2` means a thin relay to
the Worker (same flow, chunks as JSON/base64 `parca` when `parca_json`); no `protokol` means
the old Apps Script bridge (old JSON flow, also serves reads). TF_BILGI_KOPRU_URL overrides
the address. For /paylas (hizli, geri-al) a writer
(KB push) wins over the köprü key. For the other commands the path is `TF_BILGI_YOL`
(kopru | dogrudan) or, when unset, köprü if the key file exists (a `cf1` key: the direct
GitHub path when `gh` is logged in), else the direct (GitHub) path above.

  kur [--dosya F | --sil]        Install the key from F (under <cache>/gecici/, written
                                 with the Write tool; never a shell argument), check it
                                 with the bridge, save it 0600 and delete F. No option:
                                 status. --sil: remove the key.
  gonder --taslak F.json [--metin F.md] [--govde F.md] [--ek PATH]...
                                 Köprü share (/toplu-paylas, gizli): validate the draft
                                 (contract §5), scan every file with the pinned kb.py only to
                                 tag personal data (kisisel_veri; nothing is refused for a
                                 secret since 0.7.0), upload in chunks, print a one-line
                                 receipt with the code for `geri-al`.
  geri-al HEDEF                  Withdraw a share (G-…) or one's own entry (B-…). A writer's
                                 own hızlı share still in 00-gelen/ is removed in one commit;
                                 once filed, a geri-al record is written for the librarian;
                                 someone else's code is refused. Otherwise through the bridge
                                 (köprü key).
  oku YOL...                     Köprü: allow-listed repo files (gizli entries only for
                                 their recipients).
  ara SORGU...                   Köprü: search entries.
  girdi GIRDI_ID [--yonetim]     One entry (köprü: through the bridge; direct: the cache).
  alindi GIRDI_ID                Köprü: acknowledge a handoff (the librarian records it).
  yorum / yorumlar / tercih      On the köprü path these go through the bridge too.

No model calls and no API keys: only git, the GitHub CLI, kb.py and the TF Bilgi
bridge. Python 3.9+, stdlib only. Messages for the user are Turkish; exit code 2
means "show this message to the user as-is".
"""
from __future__ import annotations

import argparse
import base64
import datetime
import hashlib
import http.client
import io
import json
import os
import re
import secrets
import select
import shutil
import subprocess
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
ORG = "Teamfluencer-Dev"
DAL = "main"
ALANLAR = {
    "ekip": {"klasor": "tf-bilgi", "ortam": "TF_BILGI_UZAK_EKIP", "uzak": f"{ORG}/tf-bilgi"},
    # Yönetim deposu org'da değil, Enes'in hesabında (7 Kas kararı).
    "yonetim": {"klasor": "tf-bilgi-yonetim", "ortam": "TF_BILGI_UZAK_YONETIM", "uzak": "eneskrblt/tf-bilgi-yonetim"},
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
# 0.5.0: 0.4.0 geçişi bitti (tf-bilgi#2 merge edildi; KB main'deki kb.py gizli paylaşımlı sürüm), 0.3.1'in hash'i
# çıktı. Yönetim deposu (tf-bilgi-yonetim) GitHub'da henüz yok; açıldığında ilk push'u bu kb.py ile yapılır.
# 0.6.0: köprü yolu. kb.py `haber: simdi` ve `kisisel_veri` alanını öğrendi, dogrula kişisel veriyi UYARI ve köprü
# anahtarını (tfb1.) sır sayar (Teamfluencer-Dev/tf-bilgi#5 head d24c0a4); geçişte eski (0.4.0) ve yeni hash birlikte
# durur, eski hash bir sonraki sürümde çıkar. Köprü yolunda kb.py köprüden indirilir ve aynı pinle denetlenir (~/.tf-bilgi/kopru/araclar/kb.py).
# 0.7.0: hızlı yol ve raflar (Teamfluencer-Dev/tf-bilgi#6 head e59a23b; #7'yi de içerir, ekip ve yönetim kopyası bayt bayt
# aynı). KB PR'ı merge edilene kadar eklenti eski kb.py ile de çalışsın diye 0.4.0 ve 0.6.0 hash'leri de durur. Hızlı
# /paylas kb.py'ye hiç dokunmaz; pin gizli paylaşım, /toplu-paylas ve /bilgi içindir.
# 0.9.0: bitiş tasarımı kb.py'si (köprü anahtarı taraması `tfb1.cf1.<64 onaltılık>` Worker anahtarlarını da yakalar).
# 0.7.0 geçişi bitti (tf-bilgi#6 merge edildi; ekip ve yönetim deposunun main'indeki kb.py c9fd…): 0.4.0 ve 0.6.0 çıktı.
# KB PR'ı merge edilene kadar main'deki 0.7.0 kb.py'si de geçer; o hash bir sonraki sürümde çıkar.
KB_SHA256 = (
    "c9fd7f6a98eabadd35bb17b055b8b887b80fb160c347c10d8a736359f418e30e",  # 0.7.0: tf-bilgi#6 head e59a23b (main)
    "fcbd94e25e361d4b4777337b2d30832c8aad5e9059cba34dbccbb5a908006b71",  # 0.9.0: bitiş tasarımı kb.py
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
# 6 Kas kararı: depoya yalnız `yazanlar` ve kütüphaneci (bot) yazar. Yazma yetkisi olmayan herkes Claude Code'dan köprü
# anahtarıyla paylaşır (0.9.0: anahtarı Slack'teki TF Bilgi botu `anahtar` komutuyla verir). Yedek yollar: Slack'teki
# TF Bilgi botu ya da depoya yazabilen biri. /bilgi okuma ve /bilgi yorum okuma yetkisiyle çalışır.
BOT_YOLU = ("Senin paylaşımın TF Bilgi köprüsünden gider (depoya köprüyle kütüphaneci yazar). Slack'te TF Bilgi botuna "
            "`anahtar` yaz ve gelen satırı terminale yapıştır: /paylas ondan sonra GitHub'sız ve sorusuz çalışır. "
            "O zamana kadar belgeyi Slack'teki TF Bilgi botuna gönder (kime, ne lazım, son tarih; aldığını "
            "bildirmek için bota 'aldım <kod>') ya da depoya yazabilen biriyle paylaş; alındı için ona 'alındı <kod>' "
            "yaz, o `/bilgi alindi <kod> --kisi <anahtarın>` ile senin adına kaydeder.")
OKUMA_YOLU = ("Okuma ve yorum çalışmaya devam eder: /bilgi kuyrugum, /bilgi son, /bilgi konu, /bilgi ara, "
              "/bilgi yorum, /bilgi yorumlar.")
KIM_BILINMIYOR = ("Kim olduğunuz bulunamadı; depoya yalnız kendi adınıza yazılır. Kabuk profilinize "
                  "`export TF_BILGI_KISI=<kisiler.json anahtarınız>` ekleyip Claude Code'u yeniden başlatın (ya da "
                  "`gh auth login` ile kisiler.json'daki GitHub hesabınıza geçin).")
REMOTE_MANIFEST = (
    "https://raw.githubusercontent.com/Teamfluencer-Dev/.github/main/"
    "claude-plugins/tf-bilgi/.claude-plugin/plugin.json"
)
KANALLAR = ("slack", "mail", "whatsapp")
ISTEK_TIPLERI = ("EYLEM", "KARAR", "INCELE", "BILGI")
# KB deposundaki araclar/bildir.py ile aynı kurallar (sözleşme §10): tercih satırı. 0.9.0 (bitiş tasarımı §7): sessiz saat,
# günlük anlık sınırı ve pilot yok; alıcılı her girdi anında, 7/24 bildirilir.
TERCIH_RE = re.compile(r"^tercih:\s*(?:kisi=([a-z][a-z0-9]*)\s+)?kanal=([a-z]+(?:\s*,\s*[a-z]+)*)\s*$")
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


def sh(cmd, cwd=None, check=True, timeout=120, env=None, girdi=None):
    """girdi: alt sürecin stdin'i (ör. `gh api --input -` JSON gövdesi); yoksa stdin kapalı."""
    akis = {"stdin": subprocess.DEVNULL} if girdi is None else {"input": girdi}
    try:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout,
                              env=env or alt_ortam(), **akis)
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


def alan_bayrak(yonetim):
    return "yonetim" if yonetim else "ekip"


# --- alan kuralı (bitiş tasarımı §3): ekip mi yönetim mi, deterministik ---
#
# KB deposundaki araclar/alici.py ile aynı kural ve aynı ortak test vektörü (araclar/alici_vektorleri.json; eklentide
# tests/alici_vektorleri.json kopyası). Girdi yalnız gönderenin kendi sözleri (not), belgenin içi değil. Model yok, ağ yok.
# Sıra: 4 ("ekip için" / --ekip → ekip, 1–3'ü ezer), 1 (yönetim kelimesi → yönetim), 2 (sözlerde adı geçen alıcılar:
# gönderen de alıcıların hepsi de yönetim kişisiyse → yönetim, yani yönetim kendi arasında; ekipten yöneticiye giden ya da
# karışık alıcılı belge → ekip; gönderen bilinmiyorsa → ekip), 3 (alıcı yoksa: gönderen yalnız yönetimdeyse → yönetim,
# değilse ekip). Ekipten biri belgeyi yönetimde tutmak isterse "yönetim" yazar (kural 1). Kişi listeleri Enes kararıdır
# (7 Kas 2026 gece), kisiler.json'dan türetilmez. Ortak vektör dosyasındaki `yonetimi_gorenler` artık kuralda kullanılmaz
# (eski kural 2; KB dosyasıyla aynı kalsın diye dosyada durur).
YONETIM_KISILERI = frozenset({"ilgim", "dilara", "enes", "ogi"})
YALNIZ_YONETIM = frozenset({"dilara", "ogi"})
# Yönetim kelimeleri: iki kökün izinli çekimleri (review tf-bilgi#11). İyelik/tamlama biçimleri ("hesap yöneticisi",
# "yöneticisine", "proje yöneticimiz", "kampanya yönetiminde") listede yok, sayılmaz.
YONETIM_EKLERI = (("yonetim", ("", "e", "i", "in", "de", "den", "le", "ce", "deki", "dekiler", "dekilere")),
                  ("yonetici", ("", "ye", "yi", "nin", "de", "den", "yle", "ler", "lere", "leri", "lerin", "lerle",
                                "lerden", "lerimiz", "lerimize")))
YONETIM_KELIMELERI = tuple(kok + ek for kok, ekler in YONETIM_EKLERI for ek in ekler)
YONETIM_TAMLAMA_BASI = ("panel", "sistem", "ekran", "sayfa", "arac", "modul", "konsol", "uygulama", "yazilim",
                        "platform")  # "yönetim paneli": teknik tamlama, yönetim sayılmaz
# Belirtme hâli de iyelik de olabilen biçimler: metnin ilk kelimesiyse, önceki kelime YONETIM_BELIRTME_ONCESI'nde
# ya da sonraki kelime YONETIM_BELIRTME_FIILLERI'yle başlıyorsa sayılır; aksi hâlde tamlama ("başvuru yönetimi").
YONETIM_IYELIK_BELIRSIZ = ("yonetimi", "yoneticileri")
YONETIM_BELIRTME_ONCESI = ("ust", "sirket", "tum", "genel", "lutfen", "ve")
YONETIM_BELIRTME_FIILLERI = ("bilgilendir", "haberdar", "ilgilendir", "toplantiya")
AD_EKLERI = ("e", "a", "ye", "ya", "i", "u", "yi", "yu", "in", "un", "nin", "nun", "de", "da", "te", "ta", "den", "dan",
             "ten", "tan", "le", "la", "yle", "yla", "ler", "lar", "lere", "lara")  # kesmesiz yazılan ada gelen ek
_YONETIM_GORUNUR = {k: "yön" + k[3:] for k in YONETIM_KELIMELERI}  # ekler ASCII: "yonetimle" → "yönetimle"
_KATLA_TR = str.maketrans({"ş": "s", "Ş": "s", "ı": "i", "İ": "i", "I": "i", "ğ": "g", "Ğ": "g", "ü": "u", "Ü": "u",
                           "ö": "o", "Ö": "o", "ç": "c", "Ç": "c"})
_KESMELER = "'’‘`´ʼ"
_URL_RE = re.compile(r"https?://\S+", re.I)
# TF Bilgi kimlikleri (katlanmış metinde): girdi B-20261105-enes-03 / BY-…, paket P-20261105-enes, konu K-0007 / KY-…,
# paylaşım kodu G-ab12cd. İçlerindeki kişi anahtarı ad sayılmaz ("Re: B-20261105-enes-03" Enes'e gönderim değildir).
_KIMLIK_RE = re.compile(r"(?<![a-z0-9])(?:[a-z]{1,3}-\d{8}-[a-z][a-z0-9]*(?:-\d{2,3})?|[a-z]{1,3}-\d{4}|g-[a-z0-9]{6})"
                        r"(?![a-z0-9])")
_KELIME_RE = re.compile(r"([a-z0-9]+)('[a-z0-9]*)?")
_YONETIM_BAYRAK_RE = re.compile(r"(?:^|\s)--yonetim(?![a-z0-9])")
_EKIP_BAYRAK_RE = re.compile(r"(?:^|\s)--ekip(?![a-z0-9])")
_EKIP_ICIN_RE = re.compile(r"(?<![a-z0-9])ekip\s+icin(?![a-z0-9])")
_CLEVEL_RE = re.compile(r"(?<![a-z0-9])c ?-? ?level(?![a-z0-9])")


def katla(metin):
    """Türkçe harfler ASCII'ye (ş→s, ı/İ/I→i, ğ→g, ü→u, ö→o, ç→c), aksanlar atılır, küçük harf."""
    t = unicodedata.normalize("NFKD", unicodedata.normalize("NFC", metin or "").translate(_KATLA_TR))
    return "".join(c for c in t if not unicodedata.combining(c)).lower()


def _soz_hazirla(metin):
    """Katlanmış sözler: bağlantılar ve TF Bilgi kimlikleri atılır (içlerindeki kelimeler ad sayılmasın), kesme
    işaretleri tek tip."""
    t = katla(_URL_RE.sub(" ", metin or ""))
    for k in _KESMELER:
        t = t.replace(k, "'")
    return _KIMLIK_RE.sub(" ", t)


def _soz_kelimeleri(t):
    """[(kelime, kesmeli_mi)]: "enes'e" → ("enes", True); "dilaraya" → ("dilaraya", False)."""
    return [(m.group(1), bool(m.group(2))) for m in _KELIME_RE.finditer(t)]


def _takma_adlar(kisiler):
    """(tek kelimelik takma ad → {kişiler}, çok kelimeli tam adlar [(kelimeler, kişi)] uzundan kısaya). Takma adlar:
    kişi anahtarı, adının ilk kelimesi ve (birden çok kelimeyse) tam adı."""
    tek, cok = {}, []
    for k, v in (kisiler or {}).items():
        if not isinstance(k, str) or k.startswith("_"):
            continue
        adlar = {katla(k)}
        parca = re.findall(r"[a-z0-9]+", katla(str((v if isinstance(v, dict) else {}).get("ad") or "")))
        if parca:
            adlar.add(parca[0])
            if len(parca) > 1:
                cok.append((tuple(parca), k))
        for a in adlar:
            if a:
                tek.setdefault(a, set()).add(k)
    cok.sort(key=lambda x: -len(x[0]))
    return tek, cok


def _ada_uyar(kelime, kesmeli, ad):
    """Kelime bu ada (ekiyle) uyuyor mu? Kesmeliyse ek zaten ayrıdır: birebir eşitlik."""
    return kelime == ad or (not kesmeli and kelime.startswith(ad) and kelime[len(ad):] in AD_EKLERI)


def alicilari_bul(metin, kisiler, gonderen=None):
    """Sözlerde adı geçen kişi anahtarları (alfabetik; gönderen hariç; birden çok kişiye uyan ad sayılmaz: "Oğuzhan"
    tek başına iki kişiye uyar, "Oğuzhan <soyad>" tek kişiye)."""
    tek, cok = _takma_adlar(kisiler)
    kel = _soz_kelimeleri(_soz_hazirla(metin))
    bulunan, i = set(), 0
    while i < len(kel):
        eslesti = False
        for parcalar, kisi in cok:
            n = len(parcalar)
            if i + n > len(kel):
                continue
            if all(w == p and not kes for (w, kes), p in zip(kel[i:i + n - 1], parcalar[:-1])) and \
                    _ada_uyar(kel[i + n - 1][0], kel[i + n - 1][1], parcalar[-1]):
                bulunan.add(kisi)
                i += n
                eslesti = True
                break
        if eslesti:
            continue
        kelime, kesmeli = kel[i]
        adaylar = set()
        for ad, sahipler in tek.items():
            if _ada_uyar(kelime, kesmeli, ad):
                adaylar |= sahipler
        if len(adaylar) == 1:
            bulunan |= adaylar
        i += 1
    bulunan.discard(gonderen)
    return sorted(bulunan)


def yonetim_kelimesi(metin):
    """Sözlerde yönetim kelimesi varsa görünür biçimi ("yönetim", "C-level", "--yonetim"), yoksa None."""
    t = _soz_hazirla(metin)
    if _YONETIM_BAYRAK_RE.search(t):
        return "--yonetim"
    if _CLEVEL_RE.search(t):
        return "C-level"
    kel = _soz_kelimeleri(t)
    for i, (w, _) in enumerate(kel):
        if w not in YONETIM_KELIMELERI:
            continue
        if w == "yonetim" and i + 1 < len(kel) and kel[i + 1][0].startswith(YONETIM_TAMLAMA_BASI):
            continue  # "yönetim paneli", "içerik yönetim sistemi"
        if w in YONETIM_IYELIK_BELIRSIZ and not (
                i == 0 or kel[i - 1][0] in YONETIM_BELIRTME_ONCESI
                or any(kel[j][0].startswith(YONETIM_BELIRTME_FIILLERI) for j in range(i + 1, min(i + 4, len(kel))))):
            continue  # "kampanya yönetimi", "başvuru yönetimi": tamlama (iyelik)
        return _YONETIM_GORUNUR[w]
    return None


def ekip_icin_mi(metin):
    t = _soz_hazirla(metin)
    if _EKIP_BAYRAK_RE.search(t):
        return "--ekip"
    if _EKIP_ICIN_RE.search(t):
        return "ekip için"
    return None


def alan_sec(metin, gonderen, kisiler):
    """Sözleşme §3: gönderenin sözleri + gönderen anahtarı (ya da None) + kisiler ({anahtar: {ad, …}}) →
    {alan, alicilar, neden}. `neden` kısa Türkçe gerekçedir (içerik yok: kural, kelime, kişi anahtarları)."""
    alicilar = alicilari_bul(metin, kisiler, gonderen)
    ekip = ekip_icin_mi(metin)
    if ekip:
        return {"alan": "ekip", "alicilar": alicilar, "neden": f"kural 4: “{ekip}” yazılmış"}
    kelime = yonetim_kelimesi(metin)
    if kelime:
        return {"alan": "yonetim", "alicilar": alicilar, "neden": f"kural 1: “{kelime}” geçiyor"}
    if alicilar:
        # Yalnız yönetim kendi arasında (alici.py ile aynı): ekipten yöneticiye giden belge ekipte kalır.
        if gonderen in YONETIM_KISILERI and set(alicilar) <= YONETIM_KISILERI:
            return {"alan": "yonetim", "alicilar": alicilar,
                    "neden": f"kural 2: yönetim kendi arasında ({', '.join(alicilar)})"}
        return {"alan": "ekip", "alicilar": alicilar, "neden": f"kural 2: alıcılar ekipte ({', '.join(alicilar)})"}
    if gonderen in YALNIZ_YONETIM:
        return {"alan": "yonetim", "alicilar": [], "neden": f"kural 3: gönderen yalnız yönetimde ({gonderen})"}
    return {"alan": "ekip", "alicilar": [], "neden": "kural 3: alıcı yok"}


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


def kisiler_coz(data):
    kisiler = data.get("kisiler") if isinstance(data, dict) else None
    # kb.py gibi: nesne olmayan kayıt (ör. null) kişi sayılmaz
    return {k: v for k, v in kisiler.items() if isinstance(v, dict)} if isinstance(kisiler, dict) else {}


def kisileri_oku(kok):
    try:
        data = json.loads((kok / "kisiler.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}
    return kisiler_coz(data)


def kisi_bul(kok, notlar):
    """Önbellek klonunun kisiler.json'una göre kişi (kisi_eslestir); git e-postası klonun ayarından."""
    kisiler = kisileri_oku(kok)
    if not kisiler:
        notlar.append("kisiler.json okunamadı; kim olduğunuz otomatik bulunamadı.")
    return kisi_eslestir(kisiler, gh_login(), notlar,
                         lambda: git(kok, "config", "user.email", check=False).stdout)


def kisi_eslestir(kisiler, login, notlar, eposta_oku):
    """gh login ↔ kisiler.json `github` > TF_BILGI_KISI > git user.email ↔ `eposta` > (None, None).

    TF_BILGI_KISI yalnız gh girişi bir kişiye eşlenemiyorsa geçerlidir; eşlenen kişiyle çelişirse durur
    (başkası adına paylaşmayı önler). Bu bir hata önleyicidir, kötü niyetli yazara karşı koruma değildir.
    `eposta_oku`: git e-postasını yalnız gerekince okuyan fonksiyon."""
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
    eposta = (eposta_oku() or "").strip().lower()
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
    """Yazma yetkisi olmayana (6 Kas kararı): depoya yalnız `yazanlar` ve Slack'teki TF Bilgi botu belge ekler; öbürleri
    belgeyi bota gönderir, alındıyı bota yazar. Kişi adı verilmez. Okuma ve yorum (okuma yetkisiyle) çalışır."""
    login = gh_login()
    hesap = f"GitHub hesabının ({login}) " if login else "GitHub hesabının "
    yazanlar = " (depoya yalnız `.kb.json` `yazanlar` listesindekiler yazar)" if ayar.get("yazanlar") else ""
    return f"{BOT_YOLU} {hesap}{uzak} deposunda yazma yetkisi yok{yazanlar}. {OKUMA_YOLU}"


def hazirla(argv):
    parser = argparse.ArgumentParser(prog="tf_bilgi.py hazirla")
    parser.add_argument("--yonetim", action="store_true")
    parser.add_argument("--yazma", action="store_true",
                        help="yazacak iş (/paylas, /toplu-paylas, /bilgi alindi): yazma yetkisi yoksa dur")
    args = parser.parse_args(argv)
    if yol_sec() == "kopru":
        return hazirla_kopru(args)
    alan = alan_bayrak(args.yonetim)
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
        notlar.append("Yazma yetkin denetlenemedi (gh api yanıt vermedi); kayıtta GitHub reddederse belgeyi Slack'teki "
                      "TF Bilgi botuna gönder.")
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
        "islem": islem, "notlar": notlar, "yol": "dogrudan",
        # /paylas geri-al köprü üzerinden gider: doğrudan yolda yalnız köprü anahtarı olan (TF_BILGI_YOL=dogrudan) geri alır
        "geri_al": anahtar_yolu().is_file(),
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
                   "yalnız deponun `yazanlar` listesindekiler kaydeder; alıcı aldığını köprü anahtarıyla `/bilgi alindi "
                   "<kod>`, Slack'teki TF Bilgi botuna 'aldım <kod>' yazarak ya da depoya yazabilen birine 'alındı "
                   "<kod>' diye ileterek bildirir.")
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
    if yol_sec() == "kopru":
        return kb_kopru(alan, argv, komut)
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

def kopru_girisi(ayar):
    """`.kb.json` `kopru_github`: köprünün GitHub anahtarının sahibinin girişi (küçük harf) ya da None."""
    deger = str((ayar or {}).get("kopru_github") or "").strip().lower()
    return deger or None


# Köprü yorumunun ilk satırı: `kisi=<anahtar>` ve ardından satır sonu, boşluk ya da "·" (köprü Code.gs ve KB bildir.py ile
# aynı kural; ortak vektörler KB kopruler/paylas/test_vektorleri.json).
KOPRU_KISI_RE = re.compile(r"^kisi=([a-z][a-z0-9]*)(?=$|[\s·])")


def _yorum_satirlari(govde):
    return str(govde or "").replace("\r\n", "\n").split("\n")


def kopru_yorum_kisisi(yorum_, kopru, kisiler):
    """Köprü yorumu (yazarı köprünün GitHub girişi, ilk satırı `kisi=<anahtar>`) → o kişi; değilse None. Kural KB
    bildir.py ve köprüyle aynı (sözleşme §7); başka bir hesabın `kisi=` satırı hiçbir şey ifade etmez."""
    login = str(((yorum_ or {}).get("user") or {}).get("login") or "").lower()
    if not kopru or login != str(kopru).lower():
        return None
    m = KOPRU_KISI_RE.match(_yorum_satirlari((yorum_ or {}).get("body"))[0].strip())
    return m.group(1) if m and m.group(1) in kisiler else None


def kopru_metni(govde):
    """Köprü yorumunun metni: ilk satır (`kisi=…`) ve ardındaki YALNIZ BİR boş satır atılır (köprüyle aynı)."""
    satirlar = _yorum_satirlari(govde)[1:]
    if satirlar and not satirlar[0].strip():
        satirlar = satirlar[1:]
    return "\n".join(satirlar)


def tercih_coz(yorumlar, kisiler, yoneticiler, kopru=None):
    """Issue yorumları → ({kisi: {kanallar, kaynak}}, uyarılar). bildir.py tercihleri_coz ile aynı kurallar: yazarı
    kisiler.json `github` hesabı olan, düzenlenmemiş yorum; en son kazanır; başkası adına yalnız yöneticiler ve köprü
    (`kopru`: `.kb.json` `kopru_github`; köprü kişi adına `tercih: kisi=<anahtar> kanal=…` yazar)."""
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
        kopru_mu = bool(kopru) and login.lower() == kopru
        if not yazar and not kopru_mu:
            uyarilar.append(f"{yer} kisiler.json'daki bir GitHub hesabından değil; sayılmaz")
            continue
        for satir in satirlar:
            m = TERCIH_RE.match(satir.lower())
            kanallar = list(dict.fromkeys(k.strip() for k in m.group(2).split(","))) if m else []
            if not m or any(k not in KANALLAR for k in kanallar):
                uyarilar.append(f"{yer} bozuk satır; sayılmaz")
                continue
            hedef = m.group(1) or yazar
            if not hedef:
                uyarilar.append(f"{yer} köprü satırında kisi= yok; sayılmaz")
                continue
            if hedef != yazar and yazar not in yoneticiler and not kopru_mu:
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


def issue_yorumlari(repo, no, ne="Bildirim tercihleri", ipucu=None):
    proc = sh(["gh", "api", "--paginate", f"repos/{repo}/issues/{no}/comments?per_page=100", "--jq", ".[]"],
              check=False, timeout=60)
    if proc.returncode != 0:
        raise Stop(f"{ne} okunamadı ({repo} issue #{no}). {ipucu or ERISIM_IPUCU}\nAyrıntı: {ayrinti(proc)}")
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
        sonuc, _ = tercih_coz(issue_yorumlari(repo, no), kisileri_oku(kok), set(ayar.get("tercih_yoneticileri") or []),
                              kopru_girisi(ayar))
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
    # 0.9.0: --haber ve --adet eski çağrılar bozulmasın diye kabul edilir, sonucu değiştirmez (7/24, anında, sınırsız).
    parser.add_argument("--haber", choices=("hemen", "simdi", "gunluk"), default="hemen", help=argparse.SUPPRESS)
    parser.add_argument("--adet", type=int, default=1, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    alan = alan_bayrak(args.yonetim)
    kok = mevcut_kok(alan)
    ayar = depo_ayari(kok, alan)
    kisiler = kisileri_oku(kok)
    alicilar = list(dict.fromkeys(k.strip() for k in args.kimden.split(",") if k.strip()))
    bilinmeyen = [k for k in alicilar + [args.yazar] if k not in kisiler]
    if not alicilar or bilinmeyen:
        raise Stop(f"Kişi anahtarı kisiler.json'da yok: {', '.join(bilinmeyen) or '(boş)'}")
    if args.son_tarih:
        datetime.date.fromisoformat(args.son_tarih)  # biçim denetimi (YYYY-MM-DD)
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
                durum = "simdi"
                gidecek.append(f"{ad} ({etiket})")
            else:
                durum = "kanal-yok"
                yok.append(ad)
        kisi_satirlari.append({"kisi": k, "ad": ad, "kanallar": kanallar, "tercih": "issue" if t else "varsayilan",
                               "etiket": etiket, "durum": durum})
    if gidecek:
        parcalar.insert(0, f"dosyalanınca hemen: {', '.join(gidecek)}")
    for ad in yok:
        parcalar.append(f"{ad}: kayıtlı kanal yok (Slack kimliği ve e-posta), gönderimde dizinde bulunamazsa "
                        "hiçbir şey gitmez")
    parcalar += ek_notlar
    return {"anlik": True, "alicilar": kisi_satirlari, "satir": " · ".join(parcalar), "notlar": notlar}


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
    if yol_sec() == "kopru":
        return tercih_kopru(args)
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
        sonuc, uyarilar = tercih_coz(issue_yorumlari(repo, no), kisiler, set(yoneticiler), kopru_girisi(ayar))
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
    alan = alan_bayrak(args.yonetim)
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


# --- entry discussion pages (yorum sayfaları: one GitHub issue per entry; read access is enough) ---

YORUM_ETIKETI = "yorum"
YORUM_ETIKET_AYARI = {"name": YORUM_ETIKETI, "color": "1d76db", "description": "TF Bilgi: bir girdinin yorum sayfası"}
YORUM_AZAMI = 10000   # karakter; daha uzunu belge olarak /paylas ile paylaşılır
YORUM_GOSTERIM = 20   # /bilgi yorumlar: son N yorum
ARAMA_TEKRAR_BEKLE = 3.0  # saniye: arama ile son issue listesi ayrışırsa bir kez daha bakmadan önce (testler 0 yapar)
YORUM_METIN_AZAMI = 2000  # /bilgi yorumlar: yorum başına gösterilen karakter
YORUM_KONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")  # sekme ve satır sonu kalır
AYLAR_KISA = ("Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara")
YORUM_IPUCU = ("GitHub hesabının bu depoya okuma yetkisi olmalı ve `gh auth status` geçerli olmalı (yorum için yazma "
               "yetkisi gerekmez). Sayfa kilitliyse yorum yazılamaz.")
# Yönetim girdisinin yorum sayfası yönetim deposundadır (eneskrblt/tf-bilgi-yonetim); yorum hiçbir zaman ekip deposuna
# yazılmaz (yönetim içeriği ekibe açılırdı). Depoyu okuyamayana ve köprüde (köprü yalnız ekip) bu kısa mesaj gider.
YONETIM_YORUM_YOK = "Yönetim yorumları yalnız yönetim deposuna erişimi olanlar içindir."
YONETIM_DENETLENEMEDI = ("Yönetim deposuna erişimin denetlenemedi (GitHub yanıt vermedi ya da bağlantı yok); biraz sonra "
                         "tekrar dene.")
GIZLI_YORUM_YOK = ("{id} gizli bir girdi: yorum yazılmaz. Yorum sayfası depoyu okuyan herkese açık olur ve yorum "
                   "belgenin içeriğini sızdırabilir. Görüşünü göndericiye ({ad}) doğrudan ilet.")
GIZLI_SAYFA_YOK = ("{id} gizli bir girdi: herkese açık yorum sayfası yok (yorum belgenin içeriğini sızdırabileceği için "
                   "yazılmaz). Görüşünü göndericiye ({ad}) doğrudan ilet.")
ARAMA_YOK = ("Bu girdinin yorum sayfası olup olmadığından emin olamadım (GitHub araması ya da son issue listesi yanıt "
             "vermedi ya da eksik döndü); ikinci bir sayfa açmamak için yazmadım. Biraz sonra tekrar dene.")


def kirp(metin, azami):
    metin = str(metin or "").strip()
    return metin if len(metin) <= azami else metin[:azami - 1].rstrip() + "…"


def tek_satir(metin, azami):
    metin = " ".join(KONTROL_KARAKTER_RE.sub(" ", str(metin or "")).split())
    return metin if len(metin) <= azami else metin[:azami - 1].rstrip() + "…"


def fm_degeri(deger):
    """Dar YAML skaleri: tırnaklı dizge, satır içi liste, null; tırnaksızda satır sonu yorumu atılır."""
    deger = deger.strip()
    if len(deger) >= 2 and deger[0] == deger[-1] and deger[0] in "\"'":
        ic = deger[1:-1]
        return ic.replace('\\"', '"').replace("\\\\", "\\") if deger[0] == '"' else ic
    if " #" in deger:
        deger = deger.split(" #", 1)[0].strip()
    if deger in ("", "~", "null", "Null", "NULL"):
        return None
    if deger.startswith("[") and deger.endswith("]"):
        return [x for x in (fm_degeri(p) for p in deger[1:-1].split(",")) if x]
    return deger


def girdi_alanlari(metin):
    """Girdi frontmatter'ı (üst düzey skaler, satır içi liste, bir düzey iç içe harita); gövde okunmaz."""
    satirlar = metin.lstrip("﻿").splitlines()
    if not satirlar or satirlar[0].strip() != "---":
        return {}
    sonuc, ust = {}, None
    for satir in satirlar[1:]:
        if satir.strip() in ("---", "..."):
            break
        if not satir.strip() or satir.lstrip().startswith("#"):
            continue
        anahtar, ayrac, deger = satir.strip().partition(":")
        if not ayrac:
            continue
        if satir[:1] in (" ", "\t"):
            if ust and isinstance(sonuc.get(ust), dict):
                sonuc[ust][anahtar.strip()] = fm_degeri(deger)
            continue
        ust = anahtar.strip()
        sonuc[ust] = {} if not deger.strip() else fm_degeri(deger)
    return sonuc


def girdi_oku(kok, ayar, girdi_id, repo=None):
    """Yayımlanmış (origin/main) girdinin yorum için gereken alanları (repo: bağlantının deposu; yoksa ekip)."""
    m = GIRDI_ID_RE.match(girdi_id)
    yol = f"girdiler/{m.group(2)}/{m.group(3)}/{girdi_id}.md"
    proc = git(kok, "show", f"origin/{DAL}:{yol}", check=False)
    if proc.returncode != 0:
        raise Stop(f"{girdi_id} bulunamadı: depoda yayımlanmış böyle bir girdi yok. Kimliği /bilgi ara ile bulabilirsin "
                   "(yeni paylaşıldıysa birkaç dakika sonra tekrar dene).")
    alanlar = girdi_alanlari(proc.stdout)
    ist = alanlar.get("istek") if isinstance(alanlar.get("istek"), dict) else {}
    kimden = ist.get("kimden")
    kimden = kimden if isinstance(kimden, list) else ([kimden] if kimden else [])
    return {"id": girdi_id, "yol": yol, "url": baglanti(repo or uzak_slug(ayar, "ekip"), yol),
            "baslik": tek_satir(alanlar.get("baslik") or girdi_id, 200), "tldr": tek_satir(alanlar.get("tldr"), 300),
            "yazar": alanlar.get("yazar") if isinstance(alanlar.get("yazar"), str) else None,
            "kimden": list(dict.fromkeys(str(k) for k in kimden)), "alan": alanlar.get("alan"),
            "gizli": gizli_girdi_mi(proc.stdout) or gizli_kimlik_mi(kok, girdi_id)}


def yorum_hedefi(girdi_id, yonetim):
    """(kok, ayar, girdi, alan, repo). Ekip girdisi ekip deposunda; yönetim girdisi (`--yonetim` ya da kimliği ekip
    önekiyle başlamayan) yönetim deposunda: önce okuma yetkisi denetlenir (yoksa kısa mesajla durur), sonra yönetim
    önbellek klonu kurulur ya da güncellenir. Yorum hiçbir zaman öbür alanın deposuna yazılmaz."""
    girdi_id = (girdi_id or "").strip()
    m = GIRDI_ID_RE.match(girdi_id)
    if not m:
        raise Stop(f"Girdi kimliği anlaşılmadı: {girdi_id!r} (örnek: B-20261105-ayse-01).")
    alan = "yonetim" if yonetim else "ekip"
    if alan == "ekip":
        kok = mevcut_kok("ekip")
        onek = depo_ayari(kok, "ekip").get("girdi_onek") or "B"
        if m.group(1) != onek:
            alan = "yonetim"  # ekip girdisi değil: yönetim deposunda aranır
    if alan == "yonetim":
        kok, repo = yonetim_klonu()
    else:
        repo = uzak_slug(depo_ayari(kok, "ekip"), "ekip")
    ayar = depo_ayari(kok, alan)
    onek = ayar.get("girdi_onek") or ("B" if alan == "ekip" else "BY")
    if m.group(1) != onek:
        raise Stop(f"{girdi_id} {'ekip' if alan == 'ekip' else 'yönetim'} deposunun girdisi değil (bu deponun girdileri "
                   f"{onek}- ile başlar).")
    girdi = girdi_oku(kok, ayar, girdi_id, repo)
    if girdi["alan"] not in (None, alan):
        raise Stop(f"{girdi_id} {alan} alanının girdisi değil; yorum yalnız kendi alanının deposuna yazılır.")
    return kok, ayar, girdi, alan, repo


def depo_erisimi(slug):
    """GitHub'da depo okunuyor mu: True; 403/404 (görünmüyor ya da erişim yok) False; başka hata (ağ, 5xx) None."""
    proc = sh(["gh", "api", f"repos/{slug}", "--jq", ".full_name"], check=False, timeout=30)
    if proc.returncode == 0:
        return True
    m = re.search(r"HTTP (\d{3})", f"{proc.stderr or ''}\n{proc.stdout or ''}")
    return False if m and m.group(1) in ("403", "404") else None


def yonetim_klonu():
    """Yönetim deposu: GitHub'da okuma yetkisi yoksa kısa mesajla durur; varsa önbellek klonu kurulur ya da güncellenir.
    → (klon, GitHub deposu). Depo, klonun uzağından (TF_BILGI_UZAK_YONETIM ya da varsayılan) alınır; yönetim .kb.json'unun
    `uzak` alanı eski org adını taşıyabilir."""
    deger, github = uzak_kaynagi("yonetim")
    if github:
        on_kontrol(github=True)
        erisim = depo_erisimi(deger)
        if erisim is False:  # 403/404: depo bu hesaba görünmüyor
            raise Stop(YONETIM_YORUM_YOK)
        if erisim is None:  # ağ ya da GitHub hatası: "erişimin yok" demek yanlış olur
            raise Stop(YONETIM_DENETLENEMEDI)
    kok = klon_yolu("yonetim")
    try:
        if kok.exists():
            guncelle(kok, deger, github, [])
        else:
            klonla(deger, github, kok)
    except Stop as e:
        raise Stop(f"{YONETIM_YORUM_YOK} ({tek_satir(str(e), 300)})")
    return kok, deger if github else uzak_slug(depo_ayari(kok, "yonetim"), "yonetim")


def sayfa_basligi_mi(baslik, girdi_id):
    """Başlık birebir "[<girdi-id>]" ile başlıyor ve ardından boşluk ya da hiçbir şey geliyor mu."""
    onek, baslik = f"[{girdi_id}]", str(baslik or "")
    return baslik == onek or (baslik.startswith(onek) and baslik[len(onek)].isspace())


def gh_api_al(*args):
    """(json, None) ya da (None, hata ayrıntısı); yalnız okur."""
    proc = sh(["gh", "api", *args], check=False, timeout=60)
    if proc.returncode != 0:
        return None, ayrinti(proc)
    try:
        return json.loads(proc.stdout or "null"), None
    except ValueError:
        return None, "yanıt JSON değil"


def gh_api_gonder(yol, govde, ne):
    """POST; gövde stdin'den JSON (`--input -`): metin hiçbir komut argümanına girmez."""
    proc = sh(["gh", "api", "-X", "POST", yol, "--input", "-"], check=False, timeout=60,
              girdi=json.dumps(govde, ensure_ascii=False))
    if proc.returncode != 0:
        raise Stop(f"{ne} yapılamadı. {YORUM_IPUCU}\nAyrıntı: {ayrinti(proc)}")
    try:
        veri = json.loads(proc.stdout or "{}")
    except ValueError:
        veri = {}
    return veri if isinstance(veri, dict) else {}


def yorum_sayfalari(repo, girdi_id):
    """Girdinin yorum sayfaları (numaraya göre) ve aramanın tam olup olmadığı. GitHub araması eski sayfaları, son açılan
    100 issue aramanın dizinleme gecikmesini kapatır; başlık birebir denetlenir, PR'lar elenir. `tam` yalnız ikisi de
    yanıt verdiyse ve arama eksik sonuç (`incomplete_results`) bildirmediyse True: değilse yeni sayfa açılmaz (biri
    yeni açılmış bir sayfayı göremeyebilir). İkisi de yanıt vermezse durur."""
    sorgu = f'repo:{repo} is:issue in:title "[{girdi_id}]"'
    arama, hata1 = gh_api_al("-X", "GET", "search/issues", "-f", f"q={sorgu}", "-f", "per_page=100")
    son, hata2 = gh_api_al("-X", "GET", f"repos/{repo}/issues", "-f", "state=all", "-f", "sort=created",
                           "-f", "direction=desc", "-f", "per_page=100")
    arama_var = hata1 is None and isinstance(arama, dict)
    liste_var = hata2 is None and isinstance(son, list)
    if not arama_var and not liste_var:
        raise Stop(f"Yorum sayfası aranamadı ({repo}). {YORUM_IPUCU}\nAyrıntı: {hata1 or hata2}")
    tam = arama_var and liste_var and not arama.get("incomplete_results")
    bulunan = {}
    for it in ((arama or {}).get("items") or [] if arama_var else []) + (son if liste_var else []):
        if (isinstance(it, dict) and isinstance(it.get("number"), int) and not it.get("pull_request")
                and sayfa_basligi_mi(it.get("title"), girdi_id)):
            bulunan[it["number"]] = {"numara": it["number"], "baslik": it.get("title"), "url": it.get("html_url"),
                                     "durum": it.get("state"), "yorum_sayisi": it.get("comments"),
                                     "acan": str((it.get("user") or {}).get("login") or "")}
    return [bulunan[n] for n in sorted(bulunan)], tam


def gh_bot_mu(kullanici):
    kullanici = kullanici if isinstance(kullanici, dict) else {}
    return kullanici.get("type") == "Bot" or str(kullanici.get("login") or "").lower().endswith("[bot]")


def github_kisileri(kisiler):
    return {str(v.get("github")).lower(): k for k, v in kisiler.items() if v.get("github")}


def yorum_kimligi(kok, notlar):
    """Yorum kişinin kendi `gh` hesabıyla yazılır. TF_BILGI_KISI ya da kisiler.json hesabı GitHub girişiyle
    çelişirse durur (yorum başka bir hesapla görünürdü)."""
    login = gh_login()
    if not login:
        raise Stop("GitHub girişin okunamadı; yorum senin GitHub hesabınla yazılır. Terminalde `gh auth login` yapıp "
                   "tekrar dene.")
    kisiler = kisileri_oku(kok)
    gh_kisi = github_kisileri(kisiler).get(login.lower())
    ben = kisi_bul(kok, [])[0]  # TF_BILGI_KISI GitHub girişiyle çelişirse durur
    hesap = str((kisiler.get(ben) or {}).get("github") or "") if ben else ""
    if gh_kisi is None and hesap:
        raise Stop(f"GitHub girişin ({login}) kisiler.json'daki hesabınla ({hesap}) aynı değil; yorum başka bir hesapla "
                   "görünürdü. `gh auth login` ile doğru hesaba geç.")
    if gh_kisi is None:
        notlar.append(f"GitHub hesabın ({login}) kisiler.json'da kayıtlı değil: bildirimlerde adın yerine '{login}' "
                      "görünür. kisiler.json'a `github` alanı eklenmeli.")
    return {"login": login, "kisi": gh_kisi, "ben": gh_kisi or ben}


def yorum_bildirimi(girdi, onceki_kisiler, kisiler, kimlik, alan="ekip"):
    """bildir.py yorum ile aynı kural: girdinin yazarı, istek alıcıları ve sayfaya daha önce yazanlar (kişi anahtarları:
    kisiler.json github hesabıyla ya da köprü yorumunun `kisi=` satırıyla çözülmüş), yorumu yazan hariç; girdinin
    alanının üyesi olmayana gitmez. ([alıcılar], tek satır)."""
    sirali = [(girdi["yazar"], "yazar")] + [(k, "alıcı") for k in girdi["kimden"]]
    sirali += [(k, "önceki yorumcu") for k in onceki_kisiler]
    alicilar, gorulen = [], set()
    for kisi, neden in sirali:
        if kisi and kisi != kimlik["kisi"] and kisi not in gorulen:
            gorulen.add(kisi)
            uye = alan in ((kisiler.get(kisi) or {}).get("alanlar") or [])
            alicilar.append({"kisi": kisi, "ad": ilk_ad(kisiler, kisi), "neden": neden, "alan_uyesi": uye})
    gidecek = [f"{a['ad']} ({a['neden']})" for a in alicilar if a["alan_uyesi"]]
    parcalar = []
    if gidecek:
        parcalar.append(f"şimdi: {', '.join(gidecek)} (kanal tercihine göre)")
    else:
        parcalar.append("kimseye bildirim gitmez")
    parcalar += [f"{yonelme(a['ad'])} bildirim gitmez ({alan} alanının üyesi değil)" for a in alicilar
                 if not a["alan_uyesi"]]
    if kimlik["kisi"] is None and kimlik["ben"] in gorulen:
        parcalar.append("kendi yorumunun bildirimi sana da gider (kisiler.json'da GitHub hesabın yok)")
    if gidecek:  # vaat abartılmasın: bildirimi KB'deki Action gönderir; kapalıysa gitmez
        parcalar.append("bildirim KB deposundaki bildirim iş akışı açıkken gider")
    return alicilar, " · ".join(parcalar)


def onceki_yorumcular(repo, sayfa, kisiler, kopru):
    """Sayfayı açan ve önceki yorumcular, kişi anahtarı olarak (botlar hariç). Köprü yorumu `kisi=` satırındaki kişiye
    sayılır; sayfayı köprü açtıysa açan sayılmaz (köprünün ilk yorumu gerçek kişiyi zaten taşır)."""
    if not sayfa:
        return []
    gh_kisi = github_kisileri(kisiler)
    acan = str(sayfa.get("acan") or "")
    sonuc = [gh_kisi.get(acan.lower())] if acan and acan.lower() != kopru else []
    for y in issue_yorumlari(repo, sayfa["numara"], "Yorum sayfası", YORUM_IPUCU):
        if gh_bot_mu(y.get("user")):
            continue
        login = str((y.get("user") or {}).get("login") or "")
        sonuc.append(kopru_yorum_kisisi(y, kopru, kisiler) or gh_kisi.get(login.lower()))
    return [k for k in sonuc if k]


def sayfa_govdesi(girdi):
    tldr = (girdi["tldr"] or "—").replace("@", "@​")  # TL;DR'deki @ad kimseyi etiketlemesin
    return (f"TF Bilgi girdisi **{girdi['id']}** için yorum sayfası.\n\n"
            f"Girdi: {girdi['url']}\nTL;DR: {tldr}\n\n"
            f"Yorum yazmak için Claude Code'da `/bilgi yorum {girdi['id']} <yorumun>` ya da bu sayfaya doğrudan yaz. "
            "Girdinin yazarı, alıcıları ve sayfaya yazanlar her yeni yorumda bildirim alır.")


def etiket_plani(repo):
    """(etiket eklenecek mi, açıklama): etiketi yalnız depoya yazma yetkisi olan ekler (ve yoksa oluşturur)."""
    yetki = yazma_yetkisi(repo, True)
    if yetki is True:
        return True, f"`{YORUM_ETIKETI}` etiketiyle (etiket yoksa oluşturulur)"
    neden = "depoya yazma yetkin yok" if yetki is False else "yazma yetkin denetlenemedi"
    return False, f"etiketsiz ({neden}; `{YORUM_ETIKETI}` etiketini yazma yetkisi olanlar ekler)"


def yorum_sayfasi_ac(repo, girdi):
    """Girdinin yorum sayfasını açar: başlık "[<id>] <başlık>", gövde girdi bağlantısı + TL;DR, yetki varsa etiket."""
    etiketli, aciklama = etiket_plani(repo)
    if etiketli and sh(["gh", "api", f"repos/{repo}/labels/{YORUM_ETIKETI}", "--jq", ".name"],
                       check=False, timeout=30).returncode != 0:
        proc = sh(["gh", "api", "-X", "POST", f"repos/{repo}/labels", "--input", "-"], check=False, timeout=30,
                  girdi=json.dumps(YORUM_ETIKET_AYARI, ensure_ascii=False))
        if proc.returncode != 0:
            etiketli, aciklama = False, f"etiketsiz (`{YORUM_ETIKETI}` etiketi oluşturulamadı)"
        else:
            aciklama = f"`{YORUM_ETIKETI}` etiketi oluşturuldu ve eklendi"
    veri = {"title": f"[{girdi['id']}] {girdi['baslik']}", "body": sayfa_govdesi(girdi)}
    if etiketli:
        veri["labels"] = [YORUM_ETIKETI]
    yanit = gh_api_gonder(f"repos/{repo}/issues", veri, "Yorum sayfası açma")
    if not isinstance(yanit.get("number"), int):
        raise Stop("Yorum sayfası açıldı mı anlaşılamadı (GitHub yanıtında numara yok); yorumu yazmadım. "
                   f"{repo} issue'larına bakıp tekrar dene.")
    if etiketli and YORUM_ETIKETI not in [str((e or {}).get("name")) for e in yanit.get("labels") or []]:
        aciklama = "etiketsiz (GitHub etiketi eklemedi)"
    return ({"numara": yanit["number"], "baslik": yanit.get("title"), "url": yanit.get("html_url"),
             "durum": yanit.get("state"), "yorum_sayisi": 0, "acan": ""}, aciklama)


def yorum_metni(dosya):
    yol = gecici_alti(dosya, "--dosya")
    if not yol.is_file():
        raise Stop(f"Yorum dosyası yok: {dosya}")
    metin = YORUM_KONTROL_RE.sub("", yol.read_text(encoding="utf-8").replace("\r\n", "\n")).strip()
    if not metin:
        raise Stop("Yorum boş; yazılacak metni ver.")
    if len(metin) > YORUM_AZAMI:
        raise Stop(f"Yorum çok uzun ({len(metin)} karakter; en çok {YORUM_AZAMI}). Kısalt ya da belge olarak /paylas "
                   "ile paylaş.")
    return yol, metin


def yorum_tara(kok, yol):
    """Yorum depoya girmez ama depoyu okuyan herkese açıktır: kb.py tara ile taranır, bulguda yazılmaz."""
    proc = sh(kb_komutu(kb_yolu(kok), "tara", str(yol), "--json"), cwd=kok, check=False, timeout=120,
              env=alt_ortam(kok))
    if proc.returncode == 0:
        return
    if proc.returncode == 3:
        try:
            bulgular = json.loads(proc.stdout).get("bulgular") or []
        except (ValueError, AttributeError):
            bulgular = []
        turler = sorted({"/".join(str(b[k]) for k in ("tur", "ad") if b.get(k)) for b in bulgular
                         if isinstance(b, dict)} - {""})
        raise Stop(f"Yorumda sır ya da kişisel veri olabilir ({', '.join(turler) or 'tarama bulgusu'}); yorumu yazmadım. "
                   "O kısmı çıkarıp tekrar dene (değeri burada da tekrar etme).")
    raise Stop(f"Yorum taranamadı (kb.py tara çıkış {proc.returncode}); yorumu yazmadım.\n{ayrinti(proc)}")


def yorum(argv):
    """/bilgi yorum: plan (salt okuma) ya da --gonder ile yaz. Gizli girdide durur; yönetim girdisi yönetim deposunda."""
    parser = argparse.ArgumentParser(prog="tf_bilgi.py yorum")
    parser.add_argument("girdi")
    parser.add_argument("--yonetim", action="store_true")
    parser.add_argument("--dosya", required=True, help="yorum metni: gecici/ altında, Write aracıyla yazılmış dosya")
    parser.add_argument("--gonder", action="store_true", help="yorumu yaz (yoksa yalnız plan; hiçbir şey yazılmaz)")
    args = parser.parse_args(argv)
    if yol_sec() == "kopru":
        return yorum_kopru(args)
    kok, ayar, girdi, alan, repo = yorum_hedefi(args.girdi, args.yonetim)
    kisiler = kisileri_oku(kok)
    if girdi["gizli"]:
        raise Stop(GIZLI_YORUM_YOK.format(id=girdi["id"], ad=ilk_ad(kisiler, girdi["yazar"] or "gönderen")))
    yol, metin = yorum_metni(args.dosya)
    on_kontrol(github=True)
    notlar = []
    kimlik = yorum_kimligi(kok, notlar)
    yorum_tara(kok, yol)
    sayfalar, tam = yorum_sayfalari(repo, girdi["id"])
    if not sayfalar and not tam:  # arama ile liste ayrıştı: bir kez daha bak, yine emin değilsen yeni sayfa açma
        time.sleep(ARAMA_TEKRAR_BEKLE)
        sayfalar, tam = yorum_sayfalari(repo, girdi["id"])
        if not sayfalar and not tam:
            raise Stop(ARAMA_YOK)
    sayfa = sayfalar[0] if sayfalar else None
    if len(sayfalar) > 1:
        notlar.append(f"Bu girdinin {len(sayfalar)} yorum sayfası var ("
                      + ", ".join(f"#{s['numara']}" for s in sayfalar) + f"); yorum en eskisine (#{sayfa['numara']}) yazılır.")
    alicilar, satir = yorum_bildirimi(girdi, onceki_yorumcular(repo, sayfa, kisiler, kopru_girisi(ayar)), kisiler, kimlik,
                                      alan)
    temel = {"girdi": girdi["id"], "baslik": girdi["baslik"], "girdi_url": girdi["url"], "ben": kimlik,
             "alicilar": alicilar, "bildirim": satir, "notlar": notlar, "alan": alan, "depo": repo}
    if not args.gonder:
        yeni = None if sayfa else {"baslik": f"[{girdi['id']}] {girdi['baslik']}", "etiket": etiket_plani(repo)[1]}
        return {**temel, "sayfa": sayfa, "yeni_sayfa": yeni, "karakter": len(metin), "yazildi": False}
    etiket = None
    if sayfa is None:
        sayfa, etiket = yorum_sayfasi_ac(repo, girdi)
    yanit = gh_api_gonder(f"repos/{repo}/issues/{sayfa['numara']}/comments", {"body": metin}, "Yorum yazma")
    return {**temel, "yazildi": True, "sayfa": {"numara": sayfa["numara"], "url": sayfa["url"]},
            "yeni_sayfa": etiket is not None, "etiket": etiket,
            "yorum_url": yanit.get("html_url") or sayfa["url"]}


def zaman_tr(deger):
    """GitHub zamanı → "6 Kas Per 14:05" (İstanbul)."""
    try:
        an = datetime.datetime.fromisoformat(str(deger or "").replace("Z", "+00:00"))
        try:
            from zoneinfo import ZoneInfo
            an = an.astimezone(ZoneInfo("Europe/Istanbul"))
        except Exception:
            an = an.astimezone(datetime.timezone(datetime.timedelta(hours=3)))
    except ValueError:
        return str(deger or "")
    return f"{an.day} {AYLAR_KISA[an.month - 1]} {GUN_KISA[an.weekday()]} {an:%H:%M}"


def yorumlar(argv):
    """/bilgi yorumlar: girdinin yorum sayfası (salt okuma), eskiden yeniye; adlar kisiler.json github hesabından."""
    parser = argparse.ArgumentParser(prog="tf_bilgi.py yorumlar")
    parser.add_argument("girdi")
    parser.add_argument("--yonetim", action="store_true")
    parser.add_argument("--son", type=int, default=YORUM_GOSTERIM, help="son N yorum (0: hepsi)")
    args = parser.parse_args(argv)
    if yol_sec() == "kopru":
        return yorumlar_kopru(args)
    kok, ayar, girdi, alan, repo = yorum_hedefi(args.girdi, args.yonetim)
    kisiler = kisileri_oku(kok)
    if girdi["gizli"]:
        raise Stop(GIZLI_SAYFA_YOK.format(id=girdi["id"], ad=ilk_ad(kisiler, girdi["yazar"] or "gönderen")))
    on_kontrol(github=True)
    sayfalar, tam = yorum_sayfalari(repo, girdi["id"])
    notlar = [] if tam else ["GitHub araması ya da son issue listesi yanıt vermedi: bazı yorum sayfaları görünmeyebilir."]
    gh_kisi = github_kisileri(kisiler)
    kopru = kopru_girisi(ayar)
    tum = []
    for s in sayfalar:
        for y in issue_yorumlari(repo, s["numara"], "Yorum sayfası", YORUM_IPUCU):
            kullanici = y.get("user") or {}
            login = str(kullanici.get("login") or "")
            kopru_kisi = kopru_yorum_kisisi(y, kopru, kisiler)
            kisi = kopru_kisi or gh_kisi.get(login.lower())
            metin = kopru_metni(y.get("body")) if kopru_kisi else y.get("body")
            tum.append({"sayfa": s["numara"], "kisi": kisi, "ad": ilk_ad(kisiler, kisi) if kisi else login,
                        "login": login, "bot": gh_bot_mu(kullanici), "kopru": bool(kopru_kisi),
                        "zaman": str(y.get("created_at") or ""), "tarih": zaman_tr(y.get("created_at")),
                        "duzenlendi": bool(y.get("updated_at")) and y.get("updated_at") != y.get("created_at"),
                        "metin": kirp(metin, YORUM_METIN_AZAMI), "url": y.get("html_url")})
    tum.sort(key=lambda y: (y["zaman"], y["sayfa"]))
    gosterilen = tum[-args.son:] if args.son > 0 else tum
    if len(sayfalar) > 1:
        notlar.append(f"Bu girdinin {len(sayfalar)} yorum sayfası var; hepsinin yorumları birlikte gösterildi, yeni "
                      f"yorum #{sayfalar[0]['numara']}'e yazılır.")
    return {"girdi": girdi["id"], "baslik": girdi["baslik"], "girdi_url": girdi["url"],
            "sayfa": sayfalar[0] if sayfalar else None, "sayfalar": [{"numara": s["numara"], "url": s["url"]}
                                                                      for s in sayfalar],
            "toplam": len(tum), "onceki": len(tum) - len(gosterilen), "yorumlar": gosterilen,
            "satir": "" if tum else f"Henüz yorum yok. Yazmak için: /bilgi yorum {girdi['id']} <yorumun>",
            "notlar": notlar}


# --- köprü (bridge): GitHub'sız paylaşım (0.6.0; 0.9.0 Cloudflare Worker; köprü sözleşmesi v1) ---
#
# 0.9.0: köprü bir Cloudflare Worker'dır (KB `kopruler/cf-kopru/`): paylaşımı ortak drive'daki gelen kutusuna
# (`00-Gelen/claude/<kayıt>/` ya da `01-Yonetim-Gelen/claude/<kayıt>/`, meta.json en son) yazar, kütüphaneci oradan
# dosyalar. Okuma köprüde yoktur (`desteklenmiyor`): belgeler kişilere Slack'ten bağlantıyla gelir. Türkiye'den
# *.workers.dev erişilemediği için anahtarın dağıtımı çoğunlukla bir Apps Script web uygulamasıdır
# (script.google.com/macros/s/<dağıtım>/exec): bu ince aktarıcı isteği Worker'a iletir. Hangi köprü olduğu `kim`
# yanıtından anlaşılır (köprü protokolü 2: yeni akış; `parca_json`: parçalar JSON/base64 `parca` işlemiyle). `cf1`
# dağıtımı (yurtdışı, VPN) doğrudan Worker'dır: parçalar ham gövdeyle (`/parca`, base64 yok) gider, Worker onları
# tamponlamadan Drive'a akıtır. Protokolsüz eski Apps Script köprüsü eski JSON akışıyla çalışmaya devam eder. Kişi anahtarı tek yapıştırmalık dizedir
# (`tfb1.<dağıtım>.<gizli>`; Slack botu `anahtar` komutuyla verir). Gizli kısım yalnız istek gövdesinde ya da
# Authorization başlığında gider (adreste değil) ve hiçbir mesaja, çıktıya ya da günlüğe yazılmaz.

KOPRU_SOZLESME = 1
ANAHTAR_RE = re.compile(r"^tfb1\.([A-Za-z0-9_-]{3,200})\.([0-9a-f]{64})$")
ANAHTAR_ARA_RE = re.compile(r"(?<![A-Za-z0-9_.-])tfb1\.[A-Za-z0-9_-]{3,200}\.[0-9a-f]{64}(?![0-9a-f])")
KOPRU_ADRES = "https://script.google.com/macros/s/{}/exec"   # Apps Script: aktarıcı (protokol 2) ya da eski köprü
KOPRU_CF_ADRES = "https://tf-bilgi-kopru.eneskarabulut.workers.dev"  # `cf1` anahtarları: Cloudflare Worker köprüsü
CF_DAGITIM_RE = re.compile(r"^cf\d+$")
AYNA = "kopru"             # ~/.tf-bilgi/kopru/: köprüden indirilen depo dosyalarının aynası (git klonu değil)
AYNA_KISI = ".kopru.json"  # hazirla'nın `kim` yanıtı (kişi, sınırlar); gonder/yorum/tercih buradan okur
TURLER = ("karar", "analiz", "durum", "devir", "nasil-yapilir", "pr-listesi", "toplanti", "arastirma")
BIRIMLER = ("dev", "cs", "satis", "ops", "yonetim", "urun", "genel")
KITLELER = ("c-level", "dev", "cs", "satis", "ops", "herkes")
URETIM_DEGERLERI = ("claude", "insan", "karma")
SABLONLAR = TURLER + ("devir-cs-degisiklik-brifi", "devir-hesap-devri")
AYNA_DOSYALARI = (".kb.json", "kisiler.json", "projeler.json", "KONULAR.md", "araclar/kb.py") + tuple(
    f"sablonlar/{s}.md" for s in SABLONLAR)
AYNA_ZORUNLU = (".kb.json", "kisiler.json", "araclar/kb.py")
KOPRU_KB_IZINLI = ("tara", "eslestir", "toplu-hazirla")  # ayna klonu yok: yalnız depoya yazmayan, git istemeyen komutlar
KOPRU_SINIRLAR = {"parca_bayt": 4 * 1024 * 1024, "dosya_azami_bayt": 20 * 1024 * 1024,
                  "kayit_azami_bayt": 25 * 1024 * 1024, "dosya_azami_sayi": 10}
KOPRU_ZAMAN_ASIMI, KOPRU_PARCA_ZAMAN_ASIMI = 60, 300
KIM_ZAMAN_ASIMI = 20  # saniye: `kim` kısa bir sorudur; köprü yanıt vermiyorsa kullanıcı uzun beklemesin
KOPRU_DENEME = 3          # bağlantı hatasında parça başına deneme (köprü aynı parçayı ikinci kez yazmaz)
KOPRU_BEKLE = 2.0         # saniye, denemeler arası (testler 0 yapar)
KOD_RE = re.compile(r"^G-[a-z0-9]{6}$")
GIZLI_LINK_RE = re.compile(r"^https://(?:drive|docs)\.google\.com/[A-Za-z0-9._~%/?#&=+-]+$")
KONU_RE = re.compile(r"^K-\d{4}$")
PROJE_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
BAGLANTI_DESEN = {"jira": re.compile(r"^(?:TA|TF|APP)-\d+$"), "pr": re.compile(r"^[a-z][\w.-]*#\d+$"),
                  "hatirlatma": re.compile(r"^H-\d{4}$"), "cl": re.compile(r"^CL-\d+$")}
KOPRU_ADI_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
AYRILMIS_ADLAR = {"meta.json", "taslak.md", "govde.md", "taslak.json"}
ANAHTAR_YOK = ("Köprü anahtarın yok. Slack'te TF Bilgi botuna `anahtar` yaz; gelen satırı terminale yapıştır (ya da "
               "`/bilgi kur <anahtar>`; anahtar tek satırdır, `tfb1.` ile başlar).")
KOPRU_OKUMA_YOK = "Okuma köprüde yok: belgeler sana Slack'ten bağlantıyla gelir."
KOPRU_YALNIZ_PAYLAS = ("Köprü anahtarıyla yalnız /paylas çalışır: dosyaları /paylas ile ya da Slack'te TF Bilgi botuna "
                       "gönder.")
KOPRU_YONETIM_YOK = ("Yönetim belgeleri köprüden okunmaz: belgeler sana Slack'ten bağlantıyla gelir. Yönetime "
                     "göndermek için /paylas yeter.")
KOPRU_YANIT_YOK = ("TF Bilgi köprüsünün yanıtı anlaşılamadı (JSON değil): köprü adresi yanlış, köprü kapalı ya da "
                   "herkese açık dağıtılmamış olabilir. TF Bilgi sorumlusuna haber ver.")
_TR_ASCII = str.maketrans({"ş": "s", "Ş": "S", "ı": "i", "İ": "I", "ğ": "g", "Ğ": "G", "ü": "u", "Ü": "U",
                           "ö": "o", "Ö": "O", "ç": "c", "Ç": "C"})


class KopruHatasi(Stop):
    """Köprünün kendi reddi (`tamam: false`): mesaj kullanıcıya aynen; `kod` makine içindir."""

    def __init__(self, mesaj, kod=None):
        super().__init__(mesaj)
        self.kod = kod


def anahtar_yolu():
    return onbellek_koku() / "anahtar"


def anahtar_coz(metin):
    m = ANAHTAR_RE.match(str(metin or "").strip())
    return (m.group(1), m.group(2)) if m else None


def anahtar_oku():
    yol = anahtar_yolu()
    try:
        metin = yol.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise Stop(ANAHTAR_YOK)
    except OSError as e:
        raise Stop(f"Köprü anahtarı okunamadı ({yol}): {e.strerror}")
    anahtar = anahtar_coz(metin)
    if not anahtar:
        raise Stop(f"Köprü anahtarı bozuk ({yol}). Slack'te TF Bilgi botuna `anahtar` yaz ve gelen satırı terminale "
                   "yapıştır (ya da `/bilgi kur <anahtar>`).")
    return anahtar


def cf_dagitim_mi(dagitim):
    """Anahtarın dağıtım kimliği Cloudflare Worker'ı mı gösteriyor (`cf1`, `cf2`, …)? Değilse eski Apps Script."""
    return bool(CF_DAGITIM_RE.match(str(dagitim or "")))


def kayitli_anahtar():
    """Kayıtlı anahtar (dağıtım, gizli) ya da None (dosya yok ya da bozuk); hata vermez."""
    try:
        return anahtar_coz(anahtar_yolu().read_text(encoding="utf-8"))
    except OSError:
        return None


def cf_anahtari_mi():
    """Kayıtlı anahtar doğrudan Worker (cf) anahtarı mı; dosya yoksa ya da bozuksa False. Ağa gitmez."""
    anahtar = kayitli_anahtar()
    return bool(anahtar) and cf_dagitim_mi(anahtar[0])


_KIM_ONBELLEK = {}  # bir çalıştırmada köprünün `kim` yanıtı (main her çalıştırmada boşaltır): ağ çağrısı artmasın


def kopru_kim(anahtar=None):
    """Köprünün `kim` yanıtı; bir çalıştırmada anahtar ve adres başına en çok bir kez sorulur (zaman aşımı
    KIM_ZAMAN_ASIMI). Hata da saklanır: aynı çalıştırmada yeniden sorulmaz, aynı hata (köprünün kendi mesajı ya da
    bağlantı hatası) yeniden yükselir; böylece bir anlık kesinti hem sessiz bir varsayıma hem de ikinci bir beklemeye
    dönüşmez (review #15)."""
    anahtar = anahtar or anahtar_oku()
    k = (anahtar[0], hashlib.sha256(anahtar[1].encode("ascii")).hexdigest(), kopru_adresi(anahtar[0]))
    if k not in _KIM_ONBELLEK:
        try:
            _KIM_ONBELLEK[k] = kopru_cagir("kim", zaman_asimi=KIM_ZAMAN_ASIMI, anahtar=anahtar)
        except Stop as e:
            _KIM_ONBELLEK[k] = e
    sonuc = _KIM_ONBELLEK[k]
    if isinstance(sonuc, Stop):
        raise sonuc
    return sonuc


def kopru_protokolu(kim):
    """`kim` yanıtındaki köprü protokolü: 2 = yeni köprü (Worker ya da onun Apps Script aktarıcısı), yoksa 1 (eski)."""
    p = (kim or {}).get("protokol")
    return p if isinstance(p, int) and not isinstance(p, bool) else 1


def yeni_kopru_mu():
    """Kayıtlı anahtar yeni köprüye mi gidiyor (okuma yok, yönetime gönderilir, alan/konu istemciden): `cf` dağıtımı
    ağsız evet; başka dağıtımda `kim.protokol >= 2` (Türkiye'den Apps Script aktarıcısı). `kim` yanıt vermezse onun
    hatası olduğu gibi yükselir (köprünün mesajı ya da bağlantı hatası): "anahtar eski" gibi bir tahmin söylenmez."""
    anahtar = kayitli_anahtar()
    if not anahtar:
        return False
    if cf_dagitim_mi(anahtar[0]):
        return True
    return kopru_protokolu(kopru_kim(anahtar)) >= 2


def yol_sec():
    """Sözleşme §1: TF_BILGI_YOL zorlar; yoksa anahtar dosyası varsa köprü, yoksa doğrudan (GitHub) yol. 0.9.0: yeni
    köprü (Worker ya da aktarıcısı) okuma yapmaz; depoya yazma yetkisi doğrulanan (gh push) anahtar sahibi doğrudan
    yoldan çalışır, diğerleri köprüde kalır ve sade cümleyi duyar."""
    zorla = os.environ.get("TF_BILGI_YOL", "").strip().lower()
    if zorla == "dogrudan":
        return "dogrudan"
    if zorla == "kopru":
        if not anahtar_yolu().is_file():
            raise Stop(ANAHTAR_YOK + " (TF_BILGI_YOL=kopru)")
        return "kopru"
    if zorla:
        raise Stop(f"TF_BILGI_YOL anlaşılmadı: {zorla!r} (kopru ya da dogrudan).")
    if not anahtar_yolu().is_file():
        return "dogrudan"
    if depoya_yazar() and yeni_kopru_mu():  # yeni köprü okumaz; depoya yazan (push doğrulandı) GitHub'dan çalışır
        return "dogrudan"
    return "kopru"


def depoya_yazar():
    """Bu makinedeki gh girişinin ekip deposuna push yetkisi doğrulandı mı (hizli_yetki: bir gün önbellekte). Yalnız
    `gh` girişi yetmez: depoyu okuyamayan ya da yazamayan anahtar sahibi doğrudan yola gönderilmez (review #15)."""
    slug = hizli_slug("ekip")
    if not slug or not which("gh"):
        return False
    login = gh_login()
    return bool(login) and hizli_yetki(login, slug)[0] is True


def eklenti_surumu():
    try:
        return json.loads((PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text())["version"]
    except Exception:
        return "?"


def kopru_adresi(dagitim):
    """Köprünün adresi: TF_BILGI_KOPRU_URL ezer; `cf` anahtarı Worker'a, eski anahtar Apps Script dağıtımına gider."""
    ortam = os.environ.get("TF_BILGI_KOPRU_URL", "").strip()
    if ortam:
        return ortam
    return KOPRU_CF_ADRES if cf_dagitim_mi(dagitim) else KOPRU_ADRES.format(dagitim)


def kopru_parca_adresi(dagitim):
    """Worker'ın ham parça adresi: <köprü adresi>/parca."""
    return kopru_adresi(dagitim).rstrip("/") + "/parca"


def kopru_tasi(adres, veri, zaman_asimi):
    """Tek HTTP POST (JSON gövde). Apps Script yanıtı 302 ile başka adresten verir; urllib POST'u o adrese GET olarak
    izler (gövdesiz). Testler bu fonksiyonu sahte köprüyle değiştirir."""
    istek = urllib.request.Request(adres, data=veri, method="POST",
                                   headers={"Content-Type": "application/json",
                                            "User-Agent": f"tf-bilgi/{eklenti_surumu()}"})
    with urllib.request.urlopen(istek, timeout=zaman_asimi) as yanit:
        return yanit.read()


def kopru_ham_tasi(adres, veri, basliklar, zaman_asimi):
    """Worker'a tek ham parça: POST <adres>/parca, gövde baytlar (base64 yok), anahtar Authorization başlığında. Testler
    bu fonksiyonu sahte Worker'la değiştirir."""
    istek = urllib.request.Request(adres, data=veri, method="POST",
                                   headers={**basliklar, "User-Agent": f"tf-bilgi/{eklenti_surumu()}"})
    with urllib.request.urlopen(istek, timeout=zaman_asimi) as yanit:
        return yanit.read()


def _kopru_yanit(gonder, gizli):
    """Taşıma çağrısı → yanıt sözlüğü. Bağlantı hatası Stop, köprünün reddi KopruHatasi (mesaj aynen); okuma
    desteklenmiyorsa (Worker) sade cümle. Gizli anahtar hiçbir hata metnine girmez."""
    try:
        ham = gonder()
    except urllib.error.HTTPError as e:
        raise Stop(f"TF Bilgi köprüsü yanıt vermedi (HTTP {e.code}). Biraz sonra tekrar dene; sürerse TF Bilgi "
                   "sorumlusuna haber ver.")
    except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError) as e:
        # http.client.HTTPException: ör. IncompleteRead (yanıt yarıda kesildi); bağlantı hatası gibi yeniden denenir
        neden = getattr(e, "reason", None) or e.__class__.__name__
        raise Stop(f"TF Bilgi köprüsüne ulaşılamadı ({tek_satir(str(neden).replace(gizli, '***'), 120)}). İnternet "
                   "bağlantını kontrol edip tekrar dene.")
    try:
        cevap = json.loads(ham.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise Stop(KOPRU_YANIT_YOK)
    if not isinstance(cevap, dict):
        raise Stop(KOPRU_YANIT_YOK)
    if cevap.get("tamam") is not True:
        if cevap.get("kod") == "desteklenmiyor":
            raise KopruHatasi(KOPRU_OKUMA_YOK, "desteklenmiyor")
        ham_mesaj = cevap.get("hata") or cevap.get("mesaj") or "TF Bilgi köprüsü isteği reddetti."
        mesaj = tek_satir(str(ham_mesaj).replace(gizli, "***"), 800)
        raise KopruHatasi(mesaj, cevap.get("kod"))
    return cevap


def kopru_cagir(islem, alanlar=None, zaman_asimi=KOPRU_ZAMAN_ASIMI, anahtar=None):
    """Köprü işlemi (JSON) → yanıt sözlüğü. Gizli anahtar yalnız gövdede gider; hiçbir hata metnine girmez."""
    dagitim, gizli = anahtar or anahtar_oku()
    govde = {"s": KOPRU_SOZLESME, "anahtar": gizli, "islem": islem, "istemci": f"tf-bilgi/{eklenti_surumu()}"}
    govde.update(alanlar or {})
    veri = json.dumps(govde, ensure_ascii=False).encode("utf-8")
    return _kopru_yanit(lambda: kopru_tasi(kopru_adresi(dagitim), veri, zaman_asimi), gizli)


def kopru_parca_gonder(yukleme, sira, veri, anahtar=None):
    """Worker'a tek ham parça (`/parca`): yükleme belirteci ve sıra başlıklarda, anahtar Authorization'da. → yanıt."""
    dagitim, gizli = anahtar or anahtar_oku()
    basliklar = {"Authorization": f"Bearer tfb1.{dagitim}.{gizli}", "X-Tfb-Yukleme": yukleme, "X-Tfb-Sira": str(sira),
                 "Content-Type": "application/octet-stream"}
    return _kopru_yanit(lambda: kopru_ham_tasi(kopru_parca_adresi(dagitim), veri, basliklar,
                                               KOPRU_PARCA_ZAMAN_ASIMI), gizli)


def kopru_cagir_tekrarla(islem, alanlar, zaman_asimi):
    return kopru_tekrarla(lambda: kopru_cagir(islem, alanlar, zaman_asimi))


def kopru_tekrarla(cagri):
    """Bağlantı hatasında ve köprünün geçici Drive hatasında (`kod: drive`) birkaç kez dener: köprü aynı parçayı ikinci
    kez yazmaz, Drive'a ne kadarını aldığını sorup kaldığı yerden sürer. Köprünün diğer retleri hemen durur."""
    for deneme in range(KOPRU_DENEME):
        try:
            return cagri()
        except KopruHatasi as e:
            if e.kod != "drive" or deneme == KOPRU_DENEME - 1:
                raise
            time.sleep(KOPRU_BEKLE)
        except Stop:
            if deneme == KOPRU_DENEME - 1:
                raise
            time.sleep(KOPRU_BEKLE)


def kopru_gerekli(ne, ipucu):
    if yol_sec() != "kopru":
        raise Stop(f"`{ne}` köprü yolunda çalışır; köprü anahtarın yok. {ipucu}")


def ayna_koku():
    return onbellek_koku() / AYNA


def ayna_yaz(kok, rel, icerik):
    """Atomik yazım; bayt olarak (satır sonu çevrilmez: kb.py'nin sha256'sı korunur)."""
    hedef = kok / rel
    hedef.parent.mkdir(parents=True, exist_ok=True)
    gecici_dosya = hedef.with_name(hedef.name + ".yeni")
    gecici_dosya.write_bytes(icerik.encode("utf-8"))
    os.replace(gecici_dosya, hedef)


def kopru_oku(yollar):
    cevap = kopru_cagir("oku", {"yollar": list(yollar)})
    dosyalar = cevap.get("dosyalar")
    if not isinstance(dosyalar, list) or not all(isinstance(d, dict) for d in dosyalar):
        raise Stop(KOPRU_YANIT_YOK)
    return dosyalar


def ayna_kur():
    """Köprüden ayna: .kb.json, kisiler.json, projeler.json, KONULAR.md, araclar/kb.py, sablonlar/. (kok, eksikler)."""
    kok = ayna_koku()
    eksik = []
    gelen = {d.get("yol"): d for d in kopru_oku(AYNA_DOSYALARI)}
    for rel in AYNA_DOSYALARI:
        icerik = (gelen.get(rel) or {}).get("icerik")
        if isinstance(icerik, str):
            ayna_yaz(kok, rel, icerik)
        else:
            eksik.append(rel)
    zorunlu = [r for r in AYNA_ZORUNLU if r in eksik]
    if zorunlu:
        raise Stop(f"TF Bilgi köprüsü {', '.join(zorunlu)} dosyasını vermedi; devam edemem. Biraz sonra tekrar dene; "
                   "sürerse TF Bilgi sorumlusuna haber ver.")
    return kok, eksik


def ayna_mevcut():
    """Eski köprünün aynası (hazirla_kopru kurar). Yeni köprü (Worker ya da aktarıcısı) okumaz, ayna kurmaz: `cf`
    anahtarı ağsız, aktarıcı anahtarı ayna yoksa `kim` ile anlaşılır (hatası olduğu gibi yükselir). Ayna varsa ağa
    gidilmez (kb.py aynada her çalıştığında köprü sorulmasın)."""
    if cf_anahtari_mi():
        raise Stop(KOPRU_OKUMA_YOK)
    kok = ayna_koku()
    if not (kok / ".kb.json").is_file() or not (kok / AYNA_KISI).is_file():
        if yeni_kopru_mu():
            raise Stop(KOPRU_OKUMA_YOK)
        raise Stop(f"TF Bilgi köprü önbelleği yok ({kok}); önce `tf_bilgi.py hazirla` çalışmalı.")
    depo_ayari(kok, "ekip")
    return kok


def kopru_kimligi():
    """hazirla'nın kaydettiği `kim` yanıtı: {kisi, ad, depo, kopru_github, sinirlar}."""
    try:
        veri = json.loads((ayna_mevcut() / AYNA_KISI).read_text(encoding="utf-8"))
    except ValueError:
        veri = {}
    if not isinstance(veri, dict) or not KISI_RE.match(str(veri.get("kisi") or "")):
        raise Stop("TF Bilgi köprü önbelleği bozuk; önce `tf_bilgi.py hazirla` çalışmalı.")
    sinirlar = dict(KOPRU_SINIRLAR)
    sinirlar.update({k: v for k, v in (veri.get("sinirlar") or {}).items()
                     if k in KOPRU_SINIRLAR and isinstance(v, int) and not isinstance(v, bool) and v > 0})
    veri["sinirlar"] = sinirlar
    return veri


KISI_RE = re.compile(r"^[a-z][a-z0-9]*$")


def hazirla_kopru(args):
    """Köprü yolunda hazırlık: kim + ayna; doğrudan yolla aynı JSON anahtarları (`yol: "kopru"`, `kok` = ayna). Yeni
    köprüde (Worker ya da aktarıcısı) okuma ve ayna yoktur: /bilgi okuması ve /toplu-paylas çalışmaz, yalnız /paylas."""
    if cf_anahtari_mi():
        raise Stop(KOPRU_YALNIZ_PAYLAS if args.yazma else KOPRU_OKUMA_YOK)
    if args.yonetim:
        raise Stop(KOPRU_YONETIM_YOK)
    if sys.version_info < (3, 9):
        raise Stop(f"Python 3.9 ya da üstü gerekli (şu an {sys.version.split()[0]}). Güncel bir python3 kurun.")
    notlar = [n for n in (surum_notu(True),) if n]
    kim = kopru_kim()
    if kim.get("okuma") is False or kopru_protokolu(kim) >= 2:  # okumayan köprü (Worker ya da aktarıcısı)
        raise Stop(KOPRU_YALNIZ_PAYLAS if args.yazma else KOPRU_OKUMA_YOK)
    kisi = str(kim.get("kisi") or "")
    if not KISI_RE.match(kisi):
        raise Stop(KOPRU_YANIT_YOK)
    ortam = os.environ.get("TF_BILGI_KISI", "").strip()
    if ortam and ortam != kisi:
        raise Stop(f"TF_BILGI_KISI='{ortam}' ama köprü anahtarın '{kisi}' kişisine ait. Başkası adına paylaşılmaz: "
                   "TF_BILGI_KISI'yi düzelt ya da kaldır.")
    kok, eksik = ayna_kur()
    ayar = depo_ayari(kok, "ekip")
    kb = kb_yolu(kok)
    sinirlar = dict(KOPRU_SINIRLAR)
    sinirlar.update({k: v for k, v in (kim.get("sinirlar") or {}).items()
                     if k in KOPRU_SINIRLAR and isinstance(v, int) and not isinstance(v, bool) and v > 0})
    kimlik = {"kisi": kisi, "ad": kim.get("ad"), "depo": kim.get("depo"), "kopru_github": kim.get("kopru_github"),
              "sinirlar": sinirlar}
    ayna_yaz(kok, AYNA_KISI, json.dumps(kimlik, ensure_ascii=False, indent=1) + "\n")
    kisiler = kisileri_oku(kok)
    if kisi not in kisiler:
        notlar.append(f"'{kisi}' köprüden gelen kisiler.json'da yok; köprü bir sonraki çağrıda reddedebilir.")
    sablon_eksik = [Path(r).stem for r in eksik if r.startswith("sablonlar/")]
    if sablon_eksik:
        notlar.append(f"Köprü şu şablonları vermedi: {', '.join(sablon_eksik)}; gövdeyi turler.md'ye göre yaz.")
    uzak = uzak_slug(ayar, "ekip")
    gun = bugun()
    return {
        "kok": str(kok), "alan": "ekip", "kisi": kisi, "kb": str(kb), "uzak": uzak, "yazabilir": None,
        "damga": damga(), "kisi_kaynagi": "kopru", "baglanti_koku": f"https://github.com/{uzak}/blob/{DAL}/",
        "bugun": gun.isoformat(), "bugun_gun": GUNLER[gun.weekday()],
        "takvim": [f"{(gun + datetime.timedelta(days=i)).isoformat()} "
                   f"{GUNLER[(gun + datetime.timedelta(days=i)).weekday()]}" for i in range(1, 15)],
        "gecici": str(gecici_dizin()), "islem": "kopru", "notlar": notlar, "yol": "kopru",
        "kopru": kimlik, "geri_al": True,
    }


def kb_kopru(alan, argv, komut):
    """Köprü yolunda kb.py: ayna klasöründeki pinli kb.py, yalnız depo klonu istemeyen komutlar."""
    if alan != "ekip":
        raise Stop(KOPRU_YONETIM_YOK)
    if komut not in KOPRU_KB_IZINLI:
        raise Stop(f"Köprü yolunda kb.py yalnız {', '.join(KOPRU_KB_IZINLI)} çalıştırır ('{komut}' depo klonu ister). "
                   "Okuma /bilgi komutlarıyla, paylaşım `tf_bilgi.py gonder` ile köprüden yapılır.")
    kok = ayna_mevcut()
    kb = kb_yolu(kok)
    if komut == "toplu-hazirla":
        toplu_hazirla_denetle(argv)
    sys.stdout.flush()
    return subprocess.run(kb_komutu(kb, *argv), cwd=kok, env=alt_ortam(kok)).returncode


# --- köprü: taslak (sözleşme §5) ---

TASLAK_ANAHTARLARI = ("tur", "baslik", "tldr", "konu_onerisi", "konu_kaynagi", "aday_konular", "istek", "haber",
                      "kisisel_veri", "birim", "proje", "hedef_kitle", "belge_tarihi", "uretim", "baglantilar",
                      "gecersiz_kildigi", "gizli", "gizli_link", "notlar")


def _duz_metin(v):
    return " ".join(KONTROL_KARAKTER_RE.sub(" ", v).split()) if isinstance(v, str) else v


def _tarih_mi(v):
    try:
        return isinstance(v, str) and len(v) == 10 and bool(datetime.date.fromisoformat(v))
    except ValueError:
        return False


def taslak_dogrula(ham, kisiler, ben):
    """Sözleşme §5 taslağı → (normalleştirilmiş taslak, notlar). Sorun varsa Stop (köprü de aynı kuralı uygular)."""
    if not isinstance(ham, dict):
        raise Stop("Taslak bir JSON nesnesi olmalı.")
    sorunlar, notlar, t = [], [], {}
    bilinmeyen = sorted(set(ham) - set(TASLAK_ANAHTARLARI) - {"hizli"})
    if bilinmeyen:
        notlar.append("taslakta bilinmeyen alan atıldı: " + ", ".join(bilinmeyen))
    # hizli (0.7.0, /paylas hizli): taslak boştur; türü, başlığı, özeti, konuyu ve alıcıları kütüphaneci govde.md ve
    # eklerden çıkarır. Yalnız bu taslakta tur boş olabilir ve haber istek olmadan gelir (alıcıyı notta kütüphaneci bulur).
    hizli_ = ham.get("hizli", False)
    if not isinstance(hizli_, bool):
        sorunlar.append("hizli true ya da false olmalı")
        hizli_ = False
    gizli = ham.get("gizli", False)
    if not isinstance(gizli, bool):
        sorunlar.append("gizli true ya da false olmalı")
        gizli = False
    if hizli_ and gizli:
        sorunlar.append("hizli taslak gizli olamaz")
    t["gizli"] = gizli
    tur = ham.get("tur")
    if hizli_ and tur in (None, ""):
        tur = ""
    elif tur is not None and tur not in TURLER:
        sorunlar.append(f"tur geçersiz: {tur!r}")
    t["tur"] = tur
    for alan, azami in (("baslik", 40 if gizli else 120), ("tldr", 400)):
        v = _duz_metin(ham.get(alan) or "")
        if not isinstance(v, str):
            sorunlar.append(f"{alan} metin olmalı")
            v = ""
        elif len(v) > azami:
            sorunlar.append(f"{alan} en çok {azami} karakter ({len(v)})")
        t[alan] = v
    if gizli and t["tldr"]:
        sorunlar.append("gizli taslakta tldr boş olmalı (belge okunmaz, özetlenmez)")
    konu = _duz_metin(ham.get("konu_onerisi"))
    if konu is not None and not (isinstance(konu, str) and (
            KONU_RE.match(konu) or konu == "AYIKLA" or (konu == "GIZLI" and gizli)
            or (konu.startswith("ONERI: ") and 0 < len(konu) - 7 <= 80 and not gizli))):
        sorunlar.append(f"konu_onerisi geçersiz: {konu!r} (K-####, \"ONERI: <başlık>\", AYIKLA ya da gizlide GIZLI)")
    if gizli and konu == "AYIKLA":
        sorunlar.append("gizli taslakta konu AYIKLA olamaz (kütüphaneci içeriği açmaz)")
    t["konu_onerisi"] = konu
    kaynak = ham.get("konu_kaynagi")
    if kaynak not in (None, "kullanici", "claude"):
        sorunlar.append(f"konu_kaynagi geçersiz: {kaynak!r}")
    t["konu_kaynagi"] = kaynak
    aday = ham.get("aday_konular") or []
    if not isinstance(aday, list) or len(aday) > 3 or not all(isinstance(x, str) and KONU_RE.match(x) for x in aday):
        sorunlar.append("aday_konular en çok 3 konu kimliği (K-####) olmalı")
        aday = []
    t["aday_konular"] = aday
    istek = ham.get("istek")
    if istek is not None:
        if not isinstance(istek, dict):
            sorunlar.append("istek null ya da {tip, kimden, son_tarih} olmalı")
            istek = None
        else:
            kimden = istek.get("kimden")
            kimden = [kimden] if isinstance(kimden, str) else kimden
            if not isinstance(kimden, list) or not kimden or not all(isinstance(k, str) for k in kimden):
                sorunlar.append("istek.kimden en az bir kişi anahtarı olmalı")
                kimden = []
            kimden = list(dict.fromkeys(kimden))
            if len(kimden) > 10:
                sorunlar.append("istek.kimden en çok 10 kişi")
            bilinmeyen_kisi = [k for k in kimden if k not in kisiler]
            if bilinmeyen_kisi:
                sorunlar.append(f"istek.kimden kisiler.json'da yok: {', '.join(bilinmeyen_kisi)}")
            if istek.get("tip") not in ISTEK_TIPLERI:
                sorunlar.append(f"istek.tip geçersiz: {istek.get('tip')!r} (EYLEM · KARAR · INCELE · BILGI)")
            son = istek.get("son_tarih")
            if son is not None and not _tarih_mi(son):
                sorunlar.append(f"istek.son_tarih YYYY-MM-DD ya da null olmalı: {son!r}")
            istek = {"tip": istek.get("tip"), "kimden": kimden, "son_tarih": son}
    t["istek"] = istek
    haber = ham.get("haber")
    if haber not in (None, "hemen", "simdi"):
        sorunlar.append(f"haber geçersiz: {haber!r} (null, hemen, simdi)")
    elif haber and istek is None and not hizli_:
        sorunlar.append("haber yalnız istek varken yazılır")
    t["haber"] = haber
    kv = ham.get("kisisel_veri", False)
    if not isinstance(kv, bool):
        sorunlar.append("kisisel_veri true ya da false olmalı")
        kv = False
    t["kisisel_veri"] = kv
    birim = ham.get("birim") or []
    if not isinstance(birim, list) or any(b not in BIRIMLER for b in birim):
        sorunlar.append(f"birim yalnız şunlardan: {' '.join(BIRIMLER)}")
        birim = []
    t["birim"] = list(dict.fromkeys(birim))
    proje = ham.get("proje")
    if proje is not None and not (isinstance(proje, str) and PROJE_RE.match(proje)):
        sorunlar.append(f"proje geçersiz: {proje!r}")
    t["proje"] = proje
    kitle = ham.get("hedef_kitle") or []
    if not isinstance(kitle, list) or any(not isinstance(k, str) or (k not in KITLELER and k not in kisiler)
                                          for k in kitle):
        sorunlar.append(f"hedef_kitle yalnız {' '.join(KITLELER)} ya da kişi anahtarları")
        kitle = []
    t["hedef_kitle"] = list(dict.fromkeys(kitle))
    bt = ham.get("belge_tarihi")
    if bt is not None and not _tarih_mi(bt):
        sorunlar.append(f"belge_tarihi YYYY-MM-DD ya da null olmalı: {bt!r}")
    t["belge_tarihi"] = bt
    uretim = ham.get("uretim") or "claude"
    if uretim not in URETIM_DEGERLERI:
        sorunlar.append(f"uretim geçersiz: {uretim!r}")
    t["uretim"] = uretim
    bag = ham.get("baglantilar") or {}
    t["baglantilar"] = {}
    if not isinstance(bag, dict):
        sorunlar.append("baglantilar {jira, pr, hatirlatma, cl} listeleri olmalı")
        bag = {}
    for k, desen in BAGLANTI_DESEN.items():
        v = bag.get(k) or []
        if not isinstance(v, list) or not all(isinstance(x, str) and desen.match(x) for x in v):
            sorunlar.append(f"baglantilar.{k} biçimi yanlış")
            v = []
        t["baglantilar"][k] = list(dict.fromkeys(v))
    gk = ham.get("gecersiz_kildigi") or []
    if not isinstance(gk, list) or len(gk) > 5 or not all(
            isinstance(x, str) and GIRDI_ID_RE.match(x) and GIRDI_ID_RE.match(x).group(4) == ben for x in gk):
        sorunlar.append("gecersiz_kildigi yalnız kendi girdilerinin kimlikleri (en çok 5)")
        gk = []
    t["gecersiz_kildigi"] = gk
    link = ham.get("gizli_link")
    if gizli:
        if not (isinstance(link, str) and len(link) <= 500 and GIZLI_LINK_RE.match(link)):
            sorunlar.append("gizli taslakta gizli_link tek bir https://drive.google.com/… ya da "
                            "https://docs.google.com/… bağlantısı olmalı")
        if not istek or not istek.get("kimden"):
            sorunlar.append("gizli taslakta en az bir alıcı (istek.kimden) olmalı")
    elif link is not None:
        sorunlar.append("gizli_link yalnız gizli taslakta olur")
        link = None
    t["gizli_link"] = link if gizli else None
    nt = ham.get("notlar") or []
    if not isinstance(nt, list) or len(nt) > 5 or not all(isinstance(x, str) and len(_duz_metin(x)) <= 200 for x in nt):
        sorunlar.append("notlar en çok 5 kısa metin (≤200)")
        nt = []
    t["notlar"] = [_duz_metin(x) for x in nt]
    if hizli_:
        t = {"hizli": True, **t}  # yalnız hızlı taslakta gider (köprü sözleşmesi: diğer taslaklarda anahtar yok)
    if sorunlar:
        raise Stop("Taslak geçersiz, hiçbir şey gönderilmedi: " + "; ".join(sorunlar))
    return t, notlar


# --- köprü: gönderim ---

def kopru_dosya_adi(ad, kullanilan):
    """Ek adı: ASCII, `^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$`, ayrılmış adlar ve tekrar yok. Türkçe harfler çevrilir
    (macOS'un ayrık NFD biçimi de), diğer aksanlı harfler aksansız hâline iner."""
    ad = unicodedata.normalize("NFC", Path(ad).name).translate(_TR_ASCII)
    ad = "".join(c for c in unicodedata.normalize("NFKD", ad) if not unicodedata.combining(c))
    nokta = ad.rfind(".")
    kok, uz = (ad[:nokta], ad[nokta + 1:]) if nokta > 0 else (ad, "")
    kok = re.sub(r"[^A-Za-z0-9._-]+", "-", kok).strip(".-_")[:80] or "ek"
    uz = re.sub(r"[^A-Za-z0-9]", "", uz).lower()[:10]
    aday, i = kok + (f".{uz}" if uz else ""), 2
    while aday.lower() in kullanilan or aday.lower() in AYRILMIS_ADLAR:
        aday, i = f"{kok}-{i}" + (f".{uz}" if uz else ""), i + 1
    if not KOPRU_ADI_RE.match(aday):
        aday = "ek-" + aday
    kullanilan.add(aday.lower())
    return aday


def anahtar_icerir(yol):
    """Dosyanın baytlarında bir köprü anahtarı (tfb1.…) var mı (metin olarak; ikili dosyada da düz geçen anahtar)."""
    try:
        return bool(ANAHTAR_ARA_RE.search(Path(yol).read_bytes().decode("utf-8", "replace")))
    except OSError:
        return False


def kopru_tara(kok, yol):
    """Ayna kb.py'siyle (pinli) tarama → (çıkış, bulgular, neden)."""
    proc = sh(kb_komutu(kb_yolu(kok), "tara", str(yol), "--json"), cwd=kok, check=False, timeout=180,
              env=alt_ortam(kok))
    try:
        veri = json.loads(proc.stdout) if proc.stdout.strip() else {}
    except ValueError:
        veri = {}
    veri = veri if isinstance(veri, dict) else {}
    bulgular = [b for b in (veri.get("bulgular") or []) if isinstance(b, dict)]
    if proc.returncode == 3 and not bulgular:  # çıktı okunamadıysa temkinli: sır say
        bulgular = [{"tur": "sir", "ad": "tarama bulgusu"}]
    return proc.returncode, bulgular, str(veri.get("neden") or "")


def kopru_makbuz(kod, taslak, dosyalama, kisiler, kisisel):
    baslik = taslak["baslik"] or ("Gizli belge" if taslak["gizli"] else "(başlıksız)")
    ist = taslak["istek"]
    hedef = (adlari_bagla([ilk_ad(kisiler, k) for k in ist["kimden"]]) + " (haber dosyalanınca gider)") if ist \
        else "bildirimsiz"
    parcalar = [f'Gönderildi: {kod} · "{baslik}" → {hedef}']
    if taslak["gizli"]:
        parcalar.append("gizli: içerik depoya girmez")
    if kisisel:
        parcalar.append("kişisel veri var (etiketlendi)")
    parcalar += [f"kütüphaneci {dosyalama_metni(dosyalama)} dosyalar", f"geri almak için: /paylas geri-al {kod}"]
    return " · ".join(parcalar)


def dosyalama_metni(dosyalama):
    """Makbuzda "kütüphaneci …"den sonra gelen zaman: Worker'ın `dosyalama`sı ("10 dk içinde") olduğu gibi, eski köprünün
    tur saati ("bugün 15:05") "… turunda", hiçbiri yoksa "bir sonraki turunda"."""
    d = tek_satir(str(dosyalama or ""), 60)
    if not d:
        return "bir sonraki turunda"
    return f"{d} turunda" if re.search(r"\d{1,2}:\d{2}$", d) else d


def gonder(argv):
    """Köprü paylaşımı: taslak + dosyalar → Drive gelen kutusu (sözleşme §4 baslat/parca/bitir). Soru sormaz."""
    parser = argparse.ArgumentParser(prog="tf_bilgi.py gonder")
    parser.add_argument("--taslak", required=True, help="taslak.json (gecici/ altında, Write aracıyla)")
    parser.add_argument("--metin", help="taslak.md: girdi gövdesi (gecici/ altında)")
    parser.add_argument("--govde", help="govde.md: kullanıcının kendi sözleri (gecici/ altında)")
    parser.add_argument("--ek", action="append", default=[], help="paylaşılan dosya (mutlak yol); birden çok kez")
    args = parser.parse_args(argv)
    kopru_gerekli("gonder", "Doğrudan yolda paylaşım `tf_bilgi.py yaz` ve `kaydet` ile yapılır.")
    if yeni_kopru_mu():  # yeni köprü yalnız hızlı kaydı alır (taslaklı, gizli ve toplu paylaşım yok)
        raise Stop(KOPRU_YALNIZ_PAYLAS)
    kok = ayna_mevcut()
    kimlik = kopru_kimligi()
    ben, sinir = kimlik["kisi"], kimlik["sinirlar"]
    kisiler = kisileri_oku(kok)
    taslak_yolu = gecici_alti(args.taslak, "--taslak")
    if not taslak_yolu.is_file():
        raise Stop(f"Taslak dosyası yok: {args.taslak}")
    try:
        ham = json.loads(taslak_yolu.read_text(encoding="utf-8"))
    except ValueError as e:
        raise Stop(f"Taslak JSON okunamadı ({e}); hiçbir şey gönderilmedi.")
    taslak, notlar = taslak_dogrula(ham, kisiler, ben)
    if taslak["gizli"] and (args.metin or args.govde or args.ek):
        raise Stop("Gizli paylaşımda belge, gövde ya da not gönderilmez (içerik depoya girmez, Drive'da kalır); "
                   "yalnız taslak gider. Hiçbir şey gönderilmedi.")
    if not taslak["gizli"] and not args.metin:
        raise Stop("Girdi gövdesi (taslak.md, --metin) gerekli; hiçbir şey gönderilmedi.")
    dosyalar, kullanilan = [], set()   # (köprüdeki ad, yerel yol, mesajlardaki ad)
    for secenek, ad, gorunen in ((args.metin, "taslak.md", "girdi metni"), (args.govde, "govde.md", "notun")):
        if secenek:
            yol = gecici_alti(secenek, f"--{'metin' if ad == 'taslak.md' else 'govde'}")
            if not yol.is_file():
                raise Stop(f"Dosya yok: {secenek}")
            if ad == "govde.md" and not yol.read_text(encoding="utf-8").strip():
                continue
            dosyalar.append((ad, yol, gorunen))
            kullanilan.add(ad)
    for ek in args.ek:
        yol, gercek = ek_denetle(ek)
        dosyalar.append((kopru_dosya_adi(yol.name, kullanilan), gercek, yol.name))
    boyut_denetle(dosyalar, sinir["dosya_azami_bayt"], sinir["kayit_azami_bayt"], sinir["dosya_azami_sayi"])
    anahtar_denetle([("taslak.json", taslak_yolu, "taslak")] + dosyalar)
    # 7 Kas kararı: sır ve kişisel veri paylaşımı engellemez (özel depo, iç kullanım). Pinli kb.py taraması yalnız
    # kişisel veri etiketi (kisisel_veri) için yapılır; bulgu, taranamayan dosya ya da kb.py'nin hata çıkışı hiçbir şeyi
    # durdurmaz.
    kisisel = False
    for ad, yol, gorunen in [("taslak.json", taslak_yolu, "taslak (başlık/özet)")] + dosyalar:
        cikis, bulgular, _ = kopru_tara(kok, yol)
        kisisel = kisisel or (cikis == 3 and any(b.get("tur") == "kisisel" for b in bulgular))
    taslak["kisisel_veri"] = taslak["kisisel_veri"] or kisisel
    kod, bas, bit, ozetler = kopru_gonder(taslak, dosyalar, sinir)
    dosyalama = bit.get("dosyalama") or bas.get("dosyalama")
    return {"kod": kod, "kayit": bit.get("kayit") or bas.get("kayit"), "dosyalama": dosyalama,
            "dosyalar": [{"ad": o["ad"], "boyut": o["boyut"]} for o in ozetler], "kisisel_veri": taslak["kisisel_veri"],
            "gizli": taslak["gizli"], "satir": kopru_makbuz(kod, taslak, dosyalama, kisiler, taslak["kisisel_veri"]),
            "notlar": notlar}


def ek_denetle(ek):
    """Paylaşılacak dosya: mutlak yol, var olan dosya; ~/.tf-bilgi (köprü anahtarı, depo klonları, köprü aynası,
    önbellek) paylaşılmaz. Tek istisna gecici/ (hazırlık kopyaları, /paylas'ın yazdığı not dosyaları); oraya ya da
    ~/.tf-bilgi'nin herhangi bir yerine giden bağlantı (symlink) da reddedilir. Anahtar kopyalanırsa içerik denetimi
    (anahtar_denetle) yakalar. → (verilen yol, gerçek yol)."""
    yol = Path(ek).expanduser()
    if not yol.is_absolute():
        raise Stop(f"Ek mutlak yol olmalı: {ek}")
    if yol.is_dir():
        raise Stop(f"{yol.name} bir klasör; klasörü /toplu-paylas ile paylaş. Hiçbir şey gönderilmedi.")
    if not yol.is_file():
        raise Stop(f"Ek bulunamadı: {ek}")
    onbellek = onbellek_koku().resolve()
    gecici_kok = (onbellek / "gecici").resolve()
    gercek = yol.resolve()
    if (gercek == onbellek or onbellek in gercek.parents) and (yol.is_symlink() or gecici_kok not in gercek.parents):
        raise Stop(f"{yol.name}: TF Bilgi'nin kendi klasöründeki ({onbellek}) dosyalar paylaşılmaz (köprü anahtarı, "
                   "depo klonları ve köprü aynası orada durur). Hiçbir şey gönderilmedi.")
    return yol, gercek


def boyut_denetle(dosyalar, dosya_azami, toplam_azami, sayi_azami=None):
    """dosyalar: [(ad, kaynak (yol ya da bayt), görünen ad)]. Sınır aşılırsa hiçbir şey gönderilmeden durur."""
    if sayi_azami and len(dosyalar) > sayi_azami:
        raise Stop(f"Bir paylaşımda en çok {sayi_azami} dosya gider ({len(dosyalar)} verildi); ikiye böl.")
    toplam = 0
    for _, kaynak, gorunen in dosyalar:
        boyut = len(kaynak) if isinstance(kaynak, bytes) else kaynak.stat().st_size
        toplam += boyut
        if boyut > dosya_azami:
            raise Stop(f"{gorunen} çok büyük ({boyut // 1048576} MB; en çok {dosya_azami // 1048576} MB). "
                       "Hiçbir şey gönderilmedi.")
    if toplam > toplam_azami:
        raise Stop(f"Dosyaların toplamı çok büyük (en çok {toplam_azami // 1048576} MB); ikiye böl. Hiçbir şey "
                   "gönderilmedi.")


def anahtar_denetle(dosyalar):
    """Köprü anahtarı hiçbir dosyayla gitmez (paylaşılırsa depoyu okuyan herkes o kişi adına köprüyü kullanabilirdi).
    Yalnız dosyanın adı söylenir, anahtar asla."""
    anahtarli = [gorunen for _, kaynak, gorunen in dosyalar
                 if (ANAHTAR_ARA_RE.search(kaynak.decode("utf-8", "replace")) if isinstance(kaynak, bytes)
                     else anahtar_icerir(kaynak))]
    if anahtarli:
        raise Stop(f"Köprü anahtarı paylaşılmaz: {', '.join(anahtarli)} içinde bir TF Bilgi köprü anahtarı (tfb1.…) var. "
                   "Çıkarıp tekrar dene; anahtar paroladır, kimseyle paylaşma. Hiçbir şey gönderilmedi.")


def dosya_ozeti_al(kaynak):
    """(boyut, sha256) — yerel dosya parça parça okunur (büyük dosya belleğe bir kerede alınmaz)."""
    if isinstance(kaynak, bytes):
        return len(kaynak), hashlib.sha256(kaynak).hexdigest()
    ozet, boyut = hashlib.sha256(), 0
    with open(kaynak, "rb") as f:
        for blok in iter(lambda: f.read(1 << 20), b""):
            ozet.update(blok)
            boyut += len(blok)
    return boyut, ozet.hexdigest()


def kopru_gonder(taslak, dosyalar, sinir, ek=None, parca_json=False):
    """Köprü kaydı (sözleşme §4): baslat → parca* → bitir. dosyalar: [(köprüdeki ad, kaynak, görünen ad)]; kaynak yerel
    yol ya da bayt. ek: baslat'a giden ek alanlar (Worker: alan, konu_satiri, aciklama). Worker baslat'ta dosya başına
    `yuklemeler` belirteci verirse parçalar ham gövdeyle `/parca`'ya gider (parca_json: Apps Script aktarıcısı ham gövde
    alamaz, belirteçli JSON/base64 `parca`) ve bitir `durum` belirtecini taşır; vermezse eski köprünün JSON/base64
    parçaları. Yarıda kalırsa kaydı geri-al ile durdurmayı dener. → (kod, baslat yanıtı,
    bitir yanıtı, özetler)."""
    ozetler = []
    for ad, kaynak, _ in dosyalar:
        boyut, sha = dosya_ozeti_al(kaynak)
        ozetler.append({"ad": ad, "boyut": boyut, "sha256": sha})
    bas = kopru_cagir("baslat", {"taslak": taslak, "dosyalar": ozetler, **(ek or {})})
    kod = str(bas.get("kod") or "")
    if not KOD_RE.match(kod):
        raise Stop(KOPRU_YANIT_YOK)
    parca_bayt = bas.get("parca_bayt") if isinstance(bas.get("parca_bayt"), int) and bas["parca_bayt"] > 0 \
        else sinir["parca_bayt"]
    yuklemeler = bas.get("yuklemeler")
    try:
        if yuklemeler is not None and not (isinstance(yuklemeler, dict) and isinstance(bas.get("durum"), str) and all(
                isinstance(yuklemeler.get(ad), str) and yuklemeler.get(ad) for ad, _, _ in dosyalar)):
            raise Stop(KOPRU_YANIT_YOK)
        for ad, kaynak, _ in dosyalar:
            if yuklemeler is None:
                kopru_yukle(kod, ad, kaynak, parca_bayt)
            else:
                kopru_yukle_belirtecli(yuklemeler[ad], kaynak, parca_bayt, parca_json)
        bit = kopru_bitir(kod, bas.get("durum") if yuklemeler is not None else None)
    except Stop as e:
        try:
            kopru_cagir("geri-al", {"hedef": kod})
            durum = f"kaydı durdurdum ({kod}), hiçbir şey dosyalanmayacak"
        except Stop:
            durum = f"kaydı durduramadım: gerekirse `/paylas geri-al {kod}` yaz"
        raise Stop(f"Gönderim yarıda kaldı: {e} — {durum}. Tekrar dene.")
    return kod, bas, bit, ozetler


def kopru_bitir(kod, durum=None):
    """bitir: köprüde idempotent (ikinci çağrı aynı yanıtı `tekrar: true` ile döner). Eski köprü ikinci çağrıda
    "zaten tamamlandı" der: yanıtı kaybolan ilk `bitir` başarılı olmuştur, başarı sayılır (geri-al yapılmaz). Bağlantı
    hatası ve geçici Drive hatası yeniden denenir; köprünün diğer retleri hemen durur. durum: Worker'ın baslat'ta verdiği
    belirteç (Worker durumsuzdur, kaydın bilgisini bu belirteçten okur)."""
    alanlar = {"kod": kod, **({"durum": durum} if durum else {})}
    for deneme in range(KOPRU_DENEME):
        try:
            return kopru_cagir("bitir", alanlar, KOPRU_PARCA_ZAMAN_ASIMI)
        except KopruHatasi as e:
            if e.kod == "durum" and "zaten tamamlandı" in str(e):
                return {"kod": kod, "tekrar": True}
            if e.kod != "drive" or deneme == KOPRU_DENEME - 1:
                raise
        except Stop:
            if deneme == KOPRU_DENEME - 1:
                raise
        time.sleep(KOPRU_BEKLE)


def kopru_yukle(kod, ad, kaynak, parca_bayt):
    """Dosyayı (yol ya da bayt) sırayla parça parça gönderir (son parça kısa; boş dosya tek boş parça)."""
    boyut = len(kaynak) if isinstance(kaynak, bytes) else kaynak.stat().st_size
    with (io.BytesIO(kaynak) if isinstance(kaynak, bytes) else open(kaynak, "rb")) as dosya:
        sira = 0
        while True:
            veri = dosya.read(parca_bayt)
            kopru_cagir_tekrarla("parca", {"kod": kod, "ad": ad, "sira": sira,
                                           "veri": base64.b64encode(veri).decode("ascii")}, KOPRU_PARCA_ZAMAN_ASIMI)
            sira += 1
            if dosya.tell() >= boyut:
                return


def kopru_yukle_belirtecli(yukleme, kaynak, parca_bayt, parca_json=False):
    """Yeni köprü: dosyayı sırayla parçalarla gönderir (son parça kısa; boş dosya tek boş parça). Worker'a ham gövdeyle
    (`/parca`), aktarıcıya JSON/base64 `parca` işlemiyle (`yukleme` belirteci, sıra). Aynı sıra yeniden gönderilebilir
    (Worker Drive'a ne kadarını aldığını sorar); bağlantı ve geçici Drive hatası (`kod: drive`) yeniden denenir."""
    boyut = len(kaynak) if isinstance(kaynak, bytes) else kaynak.stat().st_size
    with (io.BytesIO(kaynak) if isinstance(kaynak, bytes) else open(kaynak, "rb")) as dosya:
        sira = 0
        while True:
            veri = dosya.read(parca_bayt)
            if parca_json:
                alanlar = {"yukleme": yukleme, "sira": sira, "veri": base64.b64encode(veri).decode("ascii")}
                kopru_tekrarla(lambda: kopru_cagir("parca", alanlar, KOPRU_PARCA_ZAMAN_ASIMI))
            else:
                kopru_tekrarla(lambda: kopru_parca_gonder(yukleme, sira, veri))
            sira += 1
            if dosya.tell() >= boyut:
                return


def geri_al(argv):
    parser = argparse.ArgumentParser(prog="tf_bilgi.py geri-al")
    parser.add_argument("hedef", help="G-xxxxxx (makbuz kodu) ya da kendi girdi kimliğin")
    hedef = parser.parse_args(argv).hedef.strip()
    if not (KOD_RE.match(hedef) or GIRDI_ID_RE.match(hedef)):
        raise Stop(f"Geri alınacak kod anlaşılmadı: {hedef!r} (örnek: G-4k9x2m ya da B-20261106-ayse-01).")
    if KOD_RE.match(hedef):
        sonuc = geri_al_yazan(hedef)  # yazanın hızlı kaydı: GitHub'dan; yazan değilse None
        if sonuc is not None:
            return sonuc
    if not anahtar_yolu().is_file():
        raise Stop("Geri alma köprü üzerinden gider (kütüphaneci girdiyi iptal eder) ve köprü anahtarın yok. "
                   + ANAHTAR_YOK)
    return kopru_geri_al(hedef)


def kopru_geri_al(hedef):
    r = kopru_cagir("geri-al", {"hedef": hedef})
    if r.get("sonuc") == "durduruldu":
        satir = f"Geri alındı: {hedef} · yükleme durduruldu, hiçbir şey dosyalanmayacak."
    else:
        satir = (f"Geri alma isteği kaydedildi: {hedef} · kütüphaneci {dosyalama_metni(r.get('dosyalama'))} işler "
                 "(dosyalanmadıysa kayıt atlanır, dosyalandıysa girdi iptal olur).")
    return {"hedef": hedef, "sonuc": r.get("sonuc"), "kod": r.get("kod"), "kayit": r.get("kayit"),
            "dosyalama": r.get("dosyalama"), "yol": "kopru", "satir": satir}


# --- hızlı paylaşım (0.7.0; 0.9.0 herkes için): `/paylas` tek komut, sorusuz; sınıflamayı kütüphaneci yapar ---
#
# 7 Kas kararı (Enes): /paylas Slack'ten ya da WhatsApp'tan hızlı olmalı, 7/24. Claude belgeyi okumaz, özetlemez,
# taslak yazmaz, soru sormaz; `hizli` dosyaları ve kullanıcının kendi sözlerini (govde.md) gelen kutusuna bırakır.
# Bağlantılar (Claude artifact, Google) sözlerin parçasıdır, indirilmez. Alanı (ekip | yönetim) yardımcı sözleşme §3
# kuralıyla seçer (alan_sec). Türü, konuyu, başlığı, özeti ve alıcıları kütüphaneci çıkarır. Depoya yazabilen (push
# yetkisi) GitHub Git Data API'siyle tek commit atar (klon yok, kb.py yok): `00-gelen/<YYYYMMDD-HHMMSS>-<kisi>-<kimlik>/`
# (dosyalar, govde.md, meta.json) ve zili çalar (kütüphaneci hemen başlar). Yazamayan köprü anahtarıyla Worker
# köprüsünden gönderir (ekip ya da yönetim). Sır ve kişisel veri paylaşımı engellemez (özel depo, iç kullanım); yalnız
# sistemin kendi kimlik bilgileri (köprü anahtarı, ~/.tf-bilgi) paylaşılmaz.

GELEN = "00-gelen"
HIZLI_DOSYA_AZAMI = 50 * 1024 * 1024    # yazan (GitHub blob API): dosya başı
HIZLI_KAYIT_AZAMI = 100 * 1024 * 1024   # yazan: kayıt toplamı
YUKLEME_DOSYA_AZAMI = 90 * 1024 * 1024  # her yolun üst sınırı (Worker: dosya başı 90 MB), ağdan önce denetlenir
YUKLEME_KAYIT_AZAMI = 900 * 1024 * 1024
HIZLI_DENEME = 3          # ref ileri sarılamazsa (arada başkası push etti) baştan okuyup en çok bu kadar yeniden dener
HIZLI_BEKLE = 0.5         # saniye, denemeler arası (testler 0 yapar)
ONBELLEK_OMRU = 86400     # saniye: push yetkisi ve kisiler.json önbelleği bir gün
GECMIS_AZAMI = 200        # yerel gönderim geçmişi (geri-al kodun hangi depoda olduğunu bilsin)
TR_SAAT = datetime.timezone(datetime.timedelta(hours=3))     # İstanbul (2016'dan beri yaz saati yok)
KAYIT_ADI_RE = re.compile(r"^\d{8}-\d{6}-([a-z][a-z0-9]*)-([a-z0-9]{6})$")
# Zil (bitiş tasarımı §1): tf-bilgi issue #9 (ekip) / #10 (yönetim) üzerinde `zil` etiketini kaldırıp yeniden eklemek
# `issues.labeled` olayı doğurur, kütüphaneci saniyeler içinde başlar. Zil çalınamazsa paylaşım bozulmaz.
ZIL_ISSUE = {"ekip": 9, "yonetim": 10}
ZIL_ETIKETI = "zil"
ZIL_YOK = "Zil çalınamadı; kütüphaneci bir sonraki turda dosyalar."
YAZAN_DOSYALAMA = "birkaç dakika içinde"   # zil çaldı
HIZLI_YOL_YOK = ("Slack'te TF Bilgi botuna `anahtar` yaz; gelen satırı terminale yapıştır, sonra /paylas'ı tekrar "
                 "dene.")
KOPRU_ESKI_YONETIM = ("Bu köprü anahtarı eski: yönetime gönderemez. Slack'te TF Bilgi botuna `anahtar` yaz; gelen "
                      "satırı terminale yapıştır, sonra /paylas'ı tekrar dene.")
GH_OTURUM_YOK = "GitHub oturumun kapalı ya da bağlantı yok: `gh auth login` yap, sonra tekrar /paylas."
BASKASININ_KODU = "Bu kod senin paylaşımın değil."
# --otomatik (skill dosyayı kendisi seçtiyse): yalnız belge benzeri dosyalar; kod, ayar, anahtar, uzantısız ve nokta ile
# başlayan dosyalar (ör. .env) reddedilir. Kullanıcının açıkça verdiği yol her türde çalışır.
OTOMATIK_UZANTILAR = frozenset({".html", ".htm", ".pdf", ".md", ".txt", ".docx", ".pptx", ".xlsx", ".csv", ".png",
                                ".jpg", ".jpeg", ".gif", ".webp"})
OTOMATIK_RET = "Hangi dosyayı paylaşacağımı bilemedim; dosya yolunu yaz: /paylas <dosya> …"
MAKBUZ_AD_SAYISI, MAKBUZ_AD_UZUNLUGU = 3, 40
_KIMLIK_HARFLERI = "abcdefghijklmnopqrstuvwxyz0123456789"


class GhHatasi(Stop):
    """GitHub REST hatası; `http` durum kodu (bilinmiyorsa None)."""

    def __init__(self, mesaj, http=None):
        super().__init__(mesaj)
        self.http = http


def gh_api(yontem, yol, govde=None, zaman_asimi=60):
    """Tek GitHub REST çağrısı (`gh api`) → JSON. Gövde stdin'den JSON (`--input -`, ASCII kaçışlı): belge ve not içeriği
    hiçbir komut argümanına girmez. Hata GhHatasi; HTTP kodu `gh`'nin hata satırından ("… (HTTP 422)")."""
    komut = ["gh", "api", yol, "-X", yontem]
    if govde is not None:
        komut += ["--input", "-"]
    proc = sh(komut, check=False, timeout=zaman_asimi, girdi=None if govde is None else json.dumps(govde))
    if proc.returncode != 0:
        m = re.search(r"\(HTTP (\d{3})\)", f"{proc.stderr or ''}\n{proc.stdout or ''}")
        raise GhHatasi(f"GitHub isteği başarısız ({yontem} {yol.split('?', 1)[0]}): "
                       f"{tek_satir(ayrinti(proc), 300) or 'yanıt yok'}", int(m.group(1)) if m else None)
    try:
        return json.loads(proc.stdout) if proc.stdout.strip() else None
    except ValueError:
        raise GhHatasi(f"GitHub yanıtı anlaşılamadı ({yontem} {yol.split('?', 1)[0]}).")


def _sha_al(veri):
    sha = veri.get("sha") if isinstance(veri, dict) else None
    if not isinstance(sha, str) or not sha:
        raise GhHatasi("GitHub yanıtı anlaşılamadı (sha yok).")
    return sha


# --- hızlı yol: yerel önbellek (~/.tf-bilgi/hizli.json: push yetkisi, kisiler.json, gönderim geçmişi) ---

def hizli_onbellek_yolu():
    return onbellek_koku() / "hizli.json"


def hizli_onbellek():
    try:
        veri = json.loads(hizli_onbellek_yolu().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return veri if isinstance(veri, dict) else {}


def hizli_onbellek_yaz(veri):
    """Atomik, yalnız kullanıcıya açık (0600): kisiler.json kopyası iş e-postaları taşır. Yazılamazsa sessiz geçer
    (önbellek yalnız hız içindir)."""
    yol = hizli_onbellek_yolu()
    try:
        yol.parent.mkdir(parents=True, exist_ok=True)
        yeni = yol.with_name(yol.name + ".yeni")
        fd = os.open(str(yeni), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(veri, f, ensure_ascii=False)
        os.replace(yeni, yol)
    except OSError:
        pass


def _bolum(ob, ad):
    if not isinstance(ob.get(ad), dict):
        ob[ad] = {}
    return ob[ad]


def _taze(kayit):
    zaman = kayit.get("zaman") if isinstance(kayit, dict) else None
    return isinstance(zaman, (int, float)) and 0 <= time.time() - zaman < ONBELLEK_OMRU


def hizli_push(slug):
    """yazma_yetkisi gibi; ama depo bu hesaba hiç görünmüyorsa (HTTP 404: private, erişim yok) False: yazamaz (review
    #14: yönetim deposunu göremeyen ekip üyesi "depo bulunamadı" değil, Slack botu yolunu duymalı). Ağ ya da başka
    hata None (denetlenemedi)."""
    if not which("gh"):
        return None
    proc = sh(["gh", "api", f"repos/{slug}", "--jq", ".permissions.push"], check=False, timeout=30)
    if proc.returncode == 0:
        return {"true": True, "false": False}.get(proc.stdout.strip().lower())
    return False if "(HTTP 404)" in f"{proc.stderr or ''}\n{proc.stdout or ''}" else None


def hizli_yetki(login, slug, yenile=False):
    """(push yetkisi True/False/None, önbellekten mi). `gh api repos/<slug> --jq .permissions.push` (hizli_push);
    kesin yanıt bir gün önbellekte durur: depo görünmüyorsa (HTTP 404) False da. Denetlenemeyen (None: ağ, başka hata)
    yazılmaz. Önbellekteki False, başka yol yoksa bir kez taze denetlenir (hizli_yol)."""
    anahtar = f"{login.lower()}|{slug.lower()}"
    kayit = _bolum(hizli_onbellek(), "yetki").get(anahtar)
    if not yenile and _taze(kayit) and isinstance(kayit.get("push"), bool):
        return kayit["push"], True
    push = hizli_push(slug)
    if push is not None:
        ob = hizli_onbellek()
        _bolum(ob, "yetki")[anahtar] = {"push": push, "zaman": time.time()}
        hizli_onbellek_yaz(ob)
    return push, False


def hizli_yetki_unut(login, slug):
    ob = hizli_onbellek()
    if _bolum(ob, "yetki").pop(f"{login.lower()}|{slug.lower()}", None) is not None:
        hizli_onbellek_yaz(ob)


def hizli_kisiler(slug, yenile=False):
    """Deponun kisiler.json'u (GitHub contents API, klon yok; bir gün önbellekte). İçerik bozuksa {}; GitHub hatası
    (depo yok, erişim yok, ağ) GhHatasi olarak yükselir: "kim olduğun bulunamadı" diye yanlış söylenmesin."""
    kayit = _bolum(hizli_onbellek(), "kisiler").get(slug.lower())
    if not yenile and _taze(kayit) and isinstance(kayit.get("kisiler"), dict):
        return kayit["kisiler"]
    veri = gh_api("GET", f"repos/{slug}/contents/kisiler.json?ref={DAL}")
    try:
        kisiler = kisiler_coz(json.loads(base64.b64decode(veri["content"]).decode("utf-8")))
    except (KeyError, TypeError, ValueError):
        return {}
    ob = hizli_onbellek()
    _bolum(ob, "kisiler")[slug.lower()] = {"kisiler": kisiler, "zaman": time.time()}
    hizli_onbellek_yaz(ob)
    return kisiler


def git_eposta():
    if not which("git"):
        return ""
    return sh(["git", "config", "--global", "--get", "user.email"], check=False, timeout=20).stdout


def hizli_kisi(slug, login, notlar):
    """Kişi, deponun kisiler.json'uyla (kisi_eslestir: gh girişi > TF_BILGI_KISI > git e-postası). Önbellekteki kopyada
    bulunamazsa bir kez taze okunur; yine yoksa durur (depoya yalnız kendi adına yazılır)."""
    for yenile in (False, True):
        kisi, _ = kisi_eslestir(hizli_kisiler(slug, yenile), login, notlar if yenile else [], git_eposta)
        if kisi and not KISI_RE.match(kisi):  # kayıt klasörünün adına girer: yalnız düz kişi anahtarı
            raise Stop(f"kisiler.json'daki kişi anahtarı geçersiz: {kisi!r}. TF Bilgi sorumlusuna haber ver.")
        if kisi:
            return kisi
    raise Stop(KIM_BILINMIYOR)


def gecmise_yaz(kod, alan, yol, slug, klasor):
    ob = hizli_onbellek()
    gecmis = _bolum(ob, "gonderilen")
    gecmis[kod] = {"alan": alan, "yol": yol, "depo": slug, "klasor": klasor, "zaman": time.time()}
    if len(gecmis) > GECMIS_AZAMI:
        for eski in sorted(gecmis, key=lambda k: (gecmis[k] or {}).get("zaman") or 0)[:len(gecmis) - GECMIS_AZAMI]:
            del gecmis[eski]
    hizli_onbellek_yaz(ob)


def gecmisten(kod):
    kayit = _bolum(hizli_onbellek(), "gonderilen").get(kod)
    return kayit if isinstance(kayit, dict) else {}


# --- hızlı yol: zaman, kimlik, meta.json ---

def an_tr():
    return simdi().astimezone(TR_SAAT)


def yeni_kimlik():
    return "".join(secrets.choice(_KIMLIK_HARFLERI) for _ in range(6))


def gelen_meta(kisi, login, an, alan, kod, dosyalar, not_metni, haber, tur="girdi", konu=None, ek=None):
    """00-gelen kaydının meta.json'u (anahtarlar ve sıra sözleşmedir; kütüphaneci okur). konu_satiri: notun ilk dolu
    satırı (≤120), yoksa ilk dosyanın adı; aciklama: notun ilk 5 dolu satırı."""
    ilk_konu, aciklama = not_ozeti(not_metni, dosyalar[0] if dosyalar else "")
    meta = {"kaynak_kanal": "claude-code", "gonderen": kisi, "gonderen_ham": f"github:{login}",
            "alinma": an.isoformat(timespec="seconds"), "dosyalar": list(dosyalar), "alan": alan, "tur": tur}
    meta.update(ek or {})
    meta.update({"mesaj_kimligi": kod, "konu_satiri": ilk_konu if konu is None else konu, "aciklama": aciklama,
                 "haber": haber, "atlanan_dosyalar": []})
    return meta


def not_ozeti(not_metni, yedek_ad=""):
    """meta.json'un konu_satiri'si (notun ilk dolu satırı, ≤120; not yoksa yedek_ad) ve aciklama'sı (notun ilk 5 dolu
    satırı, satır başı ≤400). Yazan yolu ve Worker köprüsü aynı kuralı kullanır."""
    dolu = [s for s in (tek_satir(x, 400) for x in not_metni.replace("\r\n", "\n").split("\n")) if s]
    return (tek_satir(dolu[0], 120) if dolu else tek_satir(yedek_ad, 120)), "\n".join(dolu[:5])


def _metin_girdisi(yol, icerik):
    return {"path": yol, "mode": "100644", "type": "blob", "content": icerik}


# --- hızlı yol: GitHub Git Data API (klon yok) ---

def dal_basi(slug):
    veri = gh_api("GET", f"repos/{slug}/branches/{DAL}")
    try:
        return veri["commit"]["sha"], veri["commit"]["commit"]["tree"]["sha"]
    except (KeyError, TypeError):
        raise GhHatasi(f"GitHub yanıtı anlaşılamadı ({slug} {DAL} dalı).")


def api_commit(slug, hazirla):
    """`main`'e tek commit, klon olmadan: dal başını oku → ağaç (base_tree) → commit → ref'i force olmadan ileri sar.
    Arada başkası push ettiyse ref ileri sarılamaz (HTTP 422): dal başı yeniden okunur, en çok HIZLI_DENEME kez yeniden
    denenir (bloblar yeniden yüklenmez). hazirla(bas, agac) → (ağaç girdileri, commit mesajı) ya da None (yapılacak bir
    şey kalmadı: commit yok). → commit sha ya da None."""
    for deneme in range(HIZLI_DENEME + 1):
        bas, agac = dal_basi(slug)
        is_ = hazirla(bas, agac)
        if is_ is None:
            return None
        girdiler, mesaj = is_
        yeni_agac = _sha_al(gh_api("POST", f"repos/{slug}/git/trees", {"base_tree": agac, "tree": girdiler}, 300))
        commit = _sha_al(gh_api("POST", f"repos/{slug}/git/commits",
                                {"message": mesaj, "tree": yeni_agac, "parents": [bas]}))
        try:
            gh_api("PATCH", f"repos/{slug}/git/refs/heads/{DAL}", {"sha": commit, "force": False})
            return commit
        except GhHatasi as e:
            if e.http != 422 or deneme == HIZLI_DENEME:
                raise
        time.sleep(HIZLI_BEKLE)


def agac_ogeleri(slug, agac, ozyineli=False):
    """Bir git ağacının öğeleri (git trees API: contents API'nin klasör başı 1000 öğe sınırı yok)."""
    veri = gh_api("GET", f"repos/{slug}/git/trees/{agac}" + ("?recursive=1" if ozyineli else ""))
    return [o for o in ((veri or {}).get("tree") or []) if isinstance(o, dict)]


def _alt_agac(slug, ogeler, ad):
    oge = next((o for o in ogeler if o.get("path") == ad and o.get("type") == "tree" and o.get("sha")), None)
    return agac_ogeleri(slug, oge["sha"]) if oge else []


def kod_klasorleri(slug, agac, kimlik, yerler=(GELEN, f"arsiv/{GELEN}")):
    """Bu kimlikli kayıt klasörleri (kimin olursa olsun): [{yer, ad, sha, kisi}]. 00-gelen/ dosyalanmamış, arsiv/00-gelen/
    dosyalanmış kayıtlardır (kütüphaneci işlediği kaydı oraya taşır)."""
    kok = agac_ogeleri(slug, agac)
    sonuc = []
    for yer in yerler:
        ogeler = kok
        for ad in yer.split("/"):
            ogeler = _alt_agac(slug, ogeler, ad)
        for o in ogeler:
            m = KAYIT_ADI_RE.match(str(o.get("path") or ""))
            if m and o.get("type") == "tree" and m.group(2) == kimlik:
                sonuc.append({"yer": yer, "ad": o["path"], "sha": o.get("sha"), "kisi": m.group(1)})
    return sonuc


def gelen_sil(slug, kisi, kimlik, kod):
    """Kişinin dosyalanmamış kaydını (00-gelen/<…>-<kisi>-<kimlik>/) tek commit'le siler. Bulunamazsa False (arada
    dosyalanmış olabilir). Dal başı her denemede yeniden okunduğu için klasör de her denemede yeniden aranır."""
    def hazirla(bas, agac):
        klasor = next((k for k in kod_klasorleri(slug, agac, kimlik, (GELEN,)) if k["kisi"] == kisi), None)
        if not klasor:
            return None
        girdiler = [{"path": f"{GELEN}/{klasor['ad']}/{o['path']}", "mode": o.get("mode") or "100644",
                     "type": "blob", "sha": None}
                    for o in agac_ogeleri(slug, klasor["sha"], ozyineli=True) if o.get("type") == "blob"]
        return (girdiler, f"gelen: {kod} geri alındı") if girdiler else None
    return api_commit(slug, hazirla) is not None


def geri_al_kaydi(slug, alan, kisi, login, kod):
    """Dosyalanmış kayıt için geri-al kaydı (yalnız meta.json): kütüphaneci sonraki turda girdiyi iptal eder (GOREV
    2.G.0: hedef klasör `-<gonderen>-<kimlik>` olmalı)."""
    an, kimlik = an_tr(), yeni_kimlik()
    yeni = f"G-{kimlik}"
    klasor = f"{GELEN}/{an:%Y%m%d-%H%M%S}-{kisi}-{kimlik}"
    meta = gelen_meta(kisi, login, an, alan, yeni, [], "", "hemen", tur="geri-al", konu=f"geri al: {kod}",
                      ek={"geri_alinan": kod})
    girdiler = [_metin_girdisi(f"{klasor}/meta.json", json.dumps(meta, ensure_ascii=False, indent=1) + "\n")]
    api_commit(slug, lambda bas, agac: (girdiler, f"gelen: {yeni} · {kisi} · geri-al {kod}"))
    return yeni


def geri_al_yazan(kod):
    """Yazanın kendi hızlı kaydı (G-…): 00-gelen'de duruyorsa (dosyalanmadı) klasörü tek commit'le kaldırır; dosyalandıysa
    (arsiv/00-gelen) geri-al kaydı yazar. Kod başkasının kaydıysa durur: yalnız kendi paylaşımın geri alınır. Yazan
    değilse ya da kod köprüden gittiyse None (köprü akışı sürer)."""
    zorla = os.environ.get("TF_BILGI_YOL", "").strip().lower()
    if zorla == "kopru" or not which("gh"):
        return None
    gecmis = gecmisten(kod)
    if gecmis.get("yol") == "kopru":
        return None
    login = gh_login()
    if not login:  # gh kurulu ama oturum kapalı ya da bağlantı yok
        if zorla == "dogrudan" or not anahtar_yolu().is_file() or gecmis.get("yol") == "writer":
            raise Stop(GH_OTURUM_YOK)
        return None
    adaylar = [(alan, slug) for alan, slug in ((a, hizli_slug(a)) for a in ("ekip", "yonetim"))
               if slug and hizli_yetki(login, slug)[0]]
    if not adaylar:
        return None
    adaylar.sort(key=lambda a: a[0] != gecmis.get("alan"))
    kimlik, notlar, dosyalanmis = kod[2:], [], None
    try:
        for alan, slug in adaylar:
            kisi = hizli_kisi(slug, login, notlar)
            bulunan = kod_klasorleri(slug, dal_basi(slug)[1], kimlik)
            kendi = [k for k in bulunan if k["kisi"] == kisi]
            if bulunan and not kendi:
                raise Stop(BASKASININ_KODU)
            if any(k["yer"] == GELEN for k in kendi) and gelen_sil(slug, kisi, kimlik, kod):
                return {"hedef": kod, "sonuc": "silindi", "kod": None, "alan": alan, "yol": "writer",
                        "satir": f"Geri alındı: {kod} dosyalanmadan önce kaldırıldı (içerik git geçmişinde durur; "
                                 "gerekiyorsa Enes'e haber ver).", "notlar": notlar}
            if kendi and dosyalanmis is None:  # dosyalandı (ya da tam şimdi dosyalanıp arşive taşındı)
                dosyalanmis = (alan, slug, kisi)
        if dosyalanmis is None:  # hiçbir yazan deposunda yok
            hedef = next((a for a in adaylar if a[0] == gecmis.get("alan")), None)
            if hedef is None and zorla != "dogrudan" and anahtar_yolu().is_file():
                try:  # bu makinede gönderilmemiş kod: köprü kaydı olabilir, köprüye sor
                    return kopru_geri_al(kod)
                except KopruHatasi as e:
                    if e.kod != "yok":
                        raise
            alan, slug = hedef or adaylar[0]
            dosyalanmis = (alan, slug, hizli_kisi(slug, login, notlar))
        alan, slug, kisi = dosyalanmis
        yeni = geri_al_kaydi(slug, alan, kisi, login, kod)
    except GhHatasi as e:
        raise Stop(f"Geri alınamadı: {e} Tekrar dene.")
    return {"hedef": kod, "sonuc": "kaydedildi", "kod": yeni, "alan": alan, "yol": "writer",
            "satir": "Geri alma isteği kaydedildi; kütüphaneci sonraki turda girdiyi iptal eder.", "notlar": notlar}


# --- hızlı yol: hizli alt komutu ---

def belge_mi(ad):
    """--otomatik: belge benzeri dosya mı (OTOMATIK_UZANTILAR; nokta ile başlayan ad hiçbir zaman)."""
    return not ad.startswith(".") and Path(ad).suffix.lower() in OTOMATIK_UZANTILAR


def hizli_slug(alan):
    """GitHub `sahip/ad` (TF_BILGI_UZAK_* ile ezilebilir; GitHub adresi de olur) ya da None (yerel yol: hızlı yazım yok)."""
    deger, github = uzak_kaynagi(alan)
    if github:
        return deger
    m = GITHUB_URL_RE.search(deger)
    return m.group(1) if m and not os.path.exists(deger) else None


_HESAPLA = object()  # hizli_yol: gh girişi henüz sorulmadı


def hizli_yol(alan, login=_HESAPLA, kopru_once=False):
    """('writer', login, slug, önbellekten) ya da ('kopru', None, None, False); hiçbiri yoksa tek satırla durur. Sıra:
    kopru_once ise yeni köprü anahtarı (0.9.2: alıcıya bağlantıyı Worker o anda yazar, depo yolunda ~40 sn sürer) → depoya
    yazan → köprü anahtarı (Worker anahtarı ekip de yönetim de; eski Apps Script anahtarı yalnız ekip).
    TF_BILGI_YOL=kopru|dogrudan zorlar. login: alan seçimi için zaten sorulduysa gh girişi (None: giriş yok)."""
    zorla = os.environ.get("TF_BILGI_YOL", "").strip().lower()
    if zorla not in ("", "kopru", "dogrudan"):
        raise Stop(f"TF_BILGI_YOL anlaşılmadı: {zorla!r} (kopru ya da dogrudan).")
    anahtar_var = zorla != "dogrudan" and anahtar_yolu().is_file()
    if kopru_once and anahtar_var:
        try:
            if yeni_kopru_mu():
                return "kopru", None, None, False
        except Exception:  # yalnız yol seçimi yoklaması: köprüye ulaşılamadıysa depoya yazan GitHub yolundan devam eder
            pass
    slug = hizli_slug(alan)
    if zorla != "kopru" and slug and which("gh"):
        if login is _HESAPLA:
            login = gh_login()
        if not login and yazan_bilinen() and (not anahtar_var or alan == "yonetim"):
            raise Stop(GH_OTURUM_YOK)  # bu makine yazan: "anahtar al" demek yanıltır, oturum açılmalı
        if login:
            push, onbellekten = hizli_yetki(login, slug)
            if push or (push is None and not anahtar_var):  # denetlenemedi ve başka yol yok: yazmayı dene
                return "writer", login, slug, onbellekten
            if push is False and onbellekten and not anahtar_var:  # yetki bugün verilmiş olabilir: bir kez taze bak
                push, onbellekten = hizli_yetki(login, slug, yenile=True)
                if push:
                    return "writer", login, slug, onbellekten
    if anahtar_var:
        if alan == "yonetim" and not yeni_kopru_mu():
            raise Stop(KOPRU_ESKI_YONETIM)  # eski Apps Script köprüsü yalnız ekip gelen kutusuna yazar
        return "kopru", None, None, False
    if zorla == "kopru":
        raise Stop(ANAHTAR_YOK + " (TF_BILGI_YOL=kopru)")
    raise Stop(HIZLI_YOL_YOK)


def hizli_yedek_yol(alan, hata):
    """Köprü gönderimi olmadı: depoya yazabilen GitHub yolundan gönderir (alıcıya ~1 dakikada), yazamayan köprünün hatasını
    görür. TF_BILGI_YOL=kopru yedeği kapatır."""
    if os.environ.get("TF_BILGI_YOL", "").strip().lower() == "kopru":
        raise hata
    try:
        yol = hizli_yol(alan)
    except Stop:
        raise hata from None
    if yol[0] != "writer":
        raise hata
    return yol


def hizli_kopru(alan, kim, kaynaklar, dosyalar, not_metni, haber):
    """Köprüden gönderir → (kod, kayıt klasörü, dosya adları, dosyalama metni)."""
    kim = kim or kopru_kim()  # cf dışındaki dağıtımda önce kim (protokol); çalıştırmada bir kez
    yeni = cf_anahtari_mi() or kopru_protokolu(kim) >= 2
    sinir = kopru_sinirlari(kim)
    boyut_denetle(kaynaklar, sinir["dosya_azami_bayt"], sinir["kayit_azami_bayt"], sinir["dosya_azami_sayi"])
    taslak, _ = taslak_dogrula(hizli_taslagi(haber), {}, None)
    ek = None
    if yeni:  # Worker / aktarıcı: alan ve meta.json'un konu/açıklaması istemciden (Worker notu okumaz, akıtır)
        konu, aciklama = not_ozeti(not_metni, dosyalar[0][2] if dosyalar else "")
        ek = {"alan": alan, "konu_satiri": konu, "aciklama": aciklama[:2000]}
        if "parca_bayt" in (kim.get("sinirlar") or {}):  # aktarıcının parça boyu Worker'ın yükleme belirtecine girer
            ek["parca_bayt"] = sinir["parca_bayt"]
    kod, bas, bit, ozetler = kopru_gonder(taslak, kaynaklar, sinir, ek, parca_json=yeni and kim.get("parca_json") is True)
    return (kod, bit.get("kayit") or bas.get("kayit"), [o["ad"] for o in ozetler],
            dosyalama_metni(bit.get("dosyalama") or bas.get("dosyalama")))


def yazan_bilinen():
    """Bu makinede bir TF Bilgi deposuna daha önce push yetkisi görüldü mü (hizli.json; gh oturumu kapalıyken
    yazanı köprü mesajına değil `gh auth login`'e yönlendirmek için)."""
    return any(isinstance(v, dict) and v.get("push") is True for v in _bolum(hizli_onbellek(), "yetki").values())


def stdin_metni():
    """--not-dosya verilmediyse yedek: stdin'den not (ör. elle `<<'X'` ya da boru). Terminalse ya da yarım saniyede
    hiçbir şey gelmezse boş (açık kalmış bir stdin komutu asmasın). Geçersiz UTF-8 bayt değiştirilir."""
    try:
        if sys.stdin is None or sys.stdin.isatty():
            return ""
        try:
            hazir = select.select([sys.stdin], [], [], 0.5)[0]
        except (OSError, ValueError, TypeError):  # dosya tanıtıcısı yok (testlerdeki StringIO) ya da desteklenmiyor
            hazir = [sys.stdin]
        if not hazir:
            return ""
        tampon = getattr(sys.stdin, "buffer", None)
        return tampon.read().decode("utf-8", "replace") if tampon is not None else sys.stdin.read()
    except (OSError, ValueError):
        return ""


def kopru_sinirlari(kim=None):
    """Köprü sınırları: Worker'ın `kim` yanıtından (verildiyse), yoksa hazirla'nın kaydettiği kimlikten, o da yoksa
    varsayılan. Yalnız bilinen anahtarlar ve pozitif tam sayılar alınır."""
    if kim is not None:
        sinirlar = dict(KOPRU_SINIRLAR)
        sinirlar.update({k: v for k, v in (kim.get("sinirlar") or {}).items()
                         if k in KOPRU_SINIRLAR and isinstance(v, int) and not isinstance(v, bool) and v > 0})
        return sinirlar
    try:
        return kopru_kimligi()["sinirlar"]
    except Stop:
        return dict(KOPRU_SINIRLAR)


def zil_cal(alan, notlar):
    """Kütüphaneciyi hemen çalıştırır: tf-bilgi issue #9 (ekip) / #10 (yönetim) üzerinde `zil` etiketini kaldırır (yoksa
    404 yutulur) ve yeniden ekler. Hiçbir hata paylaşımı bozmaz: çalınamazsa notlara tek satır düşer. → True/False."""
    slug, no = hizli_slug("ekip"), ZIL_ISSUE.get(alan)
    try:
        if not slug or not no:
            raise Stop("zil deposu yok")
        try:
            gh_api("DELETE", f"repos/{slug}/issues/{no}/labels/{ZIL_ETIKETI}", zaman_asimi=30)
        except GhHatasi:
            pass  # etiket takılı değildi (404) ya da kaldırılamadı: eklemeyi yine dene
        gh_api("POST", f"repos/{slug}/issues/{no}/labels", {"labels": [ZIL_ETIKETI]}, zaman_asimi=30)
        return True
    except Exception:  # noqa: BLE001 — zil yardımcıdır; paylaşım zaten kaydedildi
        notlar.append(ZIL_YOK)
        return False


def alan_karari(args, not_metni):
    """Alan seçimi → ({alan, alicilar, neden}, gh girişi | _HESAPLA, köprünün `kim` yanıtı | None). --yonetim / --ekip
    açıkça verildiyse o; değilse sözleşme §3 (alan_sec). Kural 4 ya da 1'in kelimesi yoksa gönderen ve kişi listesi
    gerekir: GitHub'dan okuyabilenin kisiler.json'u (bir gün önbellekte), değilse köprü anahtarlının `kim` yanıtı (ad
    ve alanlar). Liste yüklenemezse (GitHub o an yanıt vermedi, köprü hata döndü) hiçbir şey gönderilmez: belirsizlikte
    ekip seçilmez (review #15). Hiçbir yol yoksa (gh girişi de anahtar da yok) karar ekip kalır; gönderim yolu zaten
    tek satırla durur."""
    if args.yonetim or args.ekip:
        alan = "yonetim" if args.yonetim else "ekip"
        return {"alan": alan, "alicilar": None, "neden": f"--{alan} verildi"}, _HESAPLA, None
    if ekip_icin_mi(not_metni) or yonetim_kelimesi(not_metni):  # kural 4 / 1: kişi listesi gerekmez, alıcı aranmaz
        return {**alan_sec(not_metni, None, {}), "alicilar": None}, _HESAPLA, None
    zorla = os.environ.get("TF_BILGI_YOL", "").strip().lower()
    login, kisiler, ben, kim, hata = _HESAPLA, {}, None, None, None
    slug = hizli_slug("ekip")
    if zorla != "kopru" and slug and which("gh"):
        login = gh_login()
        if login:
            try:
                kisiler = hizli_kisiler(slug)
            except GhHatasi as e:
                kisiler = {}
                if e.http != 404:  # depo görünmüyor değil: GitHub o an yanıt vermedi
                    hata = Stop(f"Kişi listesi GitHub'dan okunamadı ({tek_satir(str(e), 200)}); ekip mi yönetim mi "
                                "seçilemedi, hiçbir şey gönderilmedi. Biraz sonra tekrar dene.")
            if kisiler:
                try:
                    ben = kisi_eslestir(kisiler, login, [], git_eposta)[0]
                except Stop:  # kimlik çelişkisi: yazan yolu ayrıca durdurur
                    ben = None
    if not kisiler and zorla != "dogrudan" and anahtar_yolu().is_file():
        kim = kopru_kim()  # hata olduğu gibi yükselir (köprünün mesajı ya da bağlantı hatası); çalıştırmada bir kez
        kisiler = kim.get("kisiler") if isinstance(kim.get("kisiler"), dict) else {}
        ben = kim.get("kisi") if isinstance(kim.get("kisi"), str) else None
        hata = None
    if not kisiler and hata:
        raise hata
    return alan_sec(not_metni, ben, kisiler), login, kim


def hizli_alan(args, not_metni):
    """(alan, alıcılar | None, gh girişi | _HESAPLA, `kim` | None): alan_karari'nın hızlı yol biçimi."""
    karar, login, kim = alan_karari(args, not_metni)
    return karar["alan"], karar["alicilar"], login, kim


def alan_komutu(argv):
    """`alan` alt komutu, salt okuma: gönderenin sözlerinden (--not-dosya) alan kararı (sözleşme §3) → {alan, alicilar, neden}. Gizli
    paylaşım bunu `hazirla`'dan önce çağırır (anahtar kelime listesi değil, /paylas'la aynı kural). Yazmaz, göndermez."""
    parser = argparse.ArgumentParser(prog="tf_bilgi.py alan")
    alan_grubu = parser.add_mutually_exclusive_group()
    alan_grubu.add_argument("--yonetim", action="store_true", help="yönetim alanı (§3 kuralını ezer)")
    alan_grubu.add_argument("--ekip", action="store_true", help="ekip alanı (§3 kuralını ezer)")
    parser.add_argument("--not-dosya", dest="not_dosya",
                        help="kullanıcının kendi sözleri: gecici/ altında, Write aracıyla yazılmış dosya")
    args = parser.parse_args(argv)
    not_metni = ""
    if args.not_dosya:
        yol = gecici_alti(args.not_dosya, "--not-dosya")
        if not yol.is_file():
            raise Stop(f"Not dosyası yok: {args.not_dosya}")
        not_metni = yol.read_bytes().decode("utf-8", "replace")
    karar, _, _ = alan_karari(args, not_metni)
    return {"alan": karar["alan"], "alicilar": karar["alicilar"], "neden": karar["neden"]}


def hizli_taslagi(haber):
    """Köprüye giden en küçük taslak (köprü sözleşmesi, hızlı kayıt): her alanı kütüphaneci doldurur."""
    return {"hizli": True, "tur": "", "baslik": "", "tldr": "", "konu_onerisi": "AYIKLA", "konu_kaynagi": "claude",
            "aday_konular": [], "istek": None, "haber": haber, "kisisel_veri": False, "birim": [], "proje": None,
            "hedef_kitle": [], "belge_tarihi": None, "uretim": "insan",
            "baglantilar": {"jira": [], "pr": [], "hatirlatma": [], "cl": []}, "gecersiz_kildigi": [], "gizli": False,
            "gizli_link": None, "notlar": []}


def hizli_yazan(alan, slug, login, onbellekten, dosyalar, not_metni, haber, notlar):
    """Yazan: tek API commit'i → (kod, klasör, kayıttaki adlar)."""
    notlu = bool(not_metni.strip())
    adlar = (["govde.md"] if notlu else []) + [ad for ad, _, _ in dosyalar]
    try:
        kisi = hizli_kisi(slug, login, notlar)
        an, kimlik = an_tr(), yeni_kimlik()
        kod = f"G-{kimlik}"
        klasor = f"{GELEN}/{an:%Y%m%d-%H%M%S}-{kisi}-{kimlik}"
        girdiler = [_metin_girdisi(f"{klasor}/govde.md", not_metni)] if notlu else []
        for ad, yol, _ in dosyalar:
            blob = gh_api("POST", f"repos/{slug}/git/blobs",
                          {"content": base64.b64encode(yol.read_bytes()).decode("ascii"), "encoding": "base64"}, 600)
            girdiler.append({"path": f"{klasor}/{ad}", "mode": "100644", "type": "blob", "sha": _sha_al(blob)})
        meta = gelen_meta(kisi, login, an, alan, kod, adlar, not_metni, haber,
                          konu=None if notlu or not dosyalar else tek_satir(dosyalar[0][2], 120))
        girdiler.append(_metin_girdisi(f"{klasor}/meta.json", json.dumps(meta, ensure_ascii=False, indent=1) + "\n"))
        api_commit(slug, lambda bas, agac: (girdiler, f"gelen: {kod} · {kisi} · {len(adlar)} dosya"))
    except GhHatasi as e:
        if onbellekten and e.http in (401, 403, 404):
            hizli_yetki_unut(login, slug)  # yetki değişmiş olabilir: bir sonraki çalıştırma yeniden denetler
        neden = (f"{slug} deposu bulunamadı ya da erişimin yok (depo henüz açılmamış olabilir). " if e.http == 404
                 else "")
        raise Stop(f"Gönderilemedi: {neden}{e} Hiçbir şey kaydedilmedi. Tekrar dene; sürerse dosyayı Slack'te TF Bilgi "
                   "botuna DM at.")
    return kod, klasor, adlar


def kisalt_ad(ad, azami=MAKBUZ_AD_UZUNLUGU):
    """Makbuz için dosya adı: tek satır, uzunsa ortası "…" (uzantı kalır)."""
    ad = tek_satir(ad, 300)
    if len(ad) <= azami:
        return ad
    nokta = ad.rfind(".")
    uz = ad[nokta:] if 0 < nokta and len(ad) - nokta <= 10 else ""
    return ad[:azami - len(uz) - 1].rstrip() + "…" + uz


def dosya_ozeti(adlar):
    """Gönderilen dosyaların adları (yanlış dosya fark edilsin): en çok 3 ad, kalanı "+N dosya"."""
    kisa = [kisalt_ad(a) for a in adlar]
    metin = ", ".join(kisa[:MAKBUZ_AD_SAYISI])
    return metin + (f" +{len(kisa) - MAKBUZ_AD_SAYISI} dosya" if len(kisa) > MAKBUZ_AD_SAYISI else "")


def hizli_satir(kod, adlar, notlu, alan, dosyalama):
    """Tek satır makbuz; gönderilen dosyaların adlarını söyler (yol verilmeden seçilen dosya da görünür). dosyalama:
    "kütüphaneci …"den sonra gelen zaman ("birkaç dakika içinde", Worker'ın "10 dk içinde", "bir sonraki turunda")."""
    icerik = " + ".join(([dosya_ozeti(adlar)] if adlar else []) + (["not"] if notlu else []))
    return (f"Gönderildi ✓ {kod} · {icerik} · {'yönetim' if alan == 'yonetim' else 'ekip'} · kütüphaneci "
            f"{dosyalama} dosyalar, alıcılara o an haber gider · geri al: /paylas geri-al {kod}")


def hizli(argv):
    """/paylas: kullanıcının sözleri (--not-dosya, yoksa stdin) + ekler → gelen kutusu, tek satır makbuz. Belge okunmaz,
    taslak yoktur, soru sorulmaz, 7/24. Alan §3 kuralıyla (ya da --yonetim / --ekip). Yazan: bilgi deposuna tek commit
    + zil; köprü anahtarı olan: Worker köprüsü (ekip ya da yönetim); hiçbiri yoksa tek satırla durur."""
    parser = argparse.ArgumentParser(prog="tf_bilgi.py hizli")
    alan_grubu = parser.add_mutually_exclusive_group()
    alan_grubu.add_argument("--yonetim", action="store_true", help="yönetim alanı (§3 kuralını ezer)")
    alan_grubu.add_argument("--ekip", action="store_true", help="ekip alanı (§3 kuralını ezer)")
    # 0.9.0: sessiz saat yok, alıcılara her zaman anında haber gider; --haber eski çağrılar için kabul edilir.
    parser.add_argument("--haber", choices=("simdi", "hemen"), help=argparse.SUPPRESS)
    parser.add_argument("--ek", action="append", default=[], help="paylaşılan dosya (mutlak yol); birden çok kez")
    parser.add_argument("--otomatik", action="store_true",
                        help="dosyayı skill kendisi seçti (kullanıcı yol vermedi): yalnız belge benzeri dosyalar gider")
    parser.add_argument("--not-dosya", dest="not_dosya",
                        help="kullanıcının kendi sözleri: gecici/ altında, Write aracıyla yazılmış dosya (yoksa stdin)")
    args = parser.parse_args(argv)
    haber = "simdi" if args.haber == "simdi" else "hemen"
    not_yolu = None
    if args.not_dosya:
        not_yolu = gecici_alti(args.not_dosya, "--not-dosya")
        if not not_yolu.is_file():
            raise Stop(f"Not dosyası yok: {args.not_dosya}")
        not_metni = not_yolu.read_bytes().decode("utf-8", "replace")
    else:
        not_metni = stdin_metni()
    notlu = bool(not_metni.strip())
    dosyalar, kullanilan, gorulen = [], set(), set()
    for ek in args.ek:
        yol, gercek = ek_denetle(ek)
        if args.otomatik and not all(belge_mi(ad) for ad in (yol.name, gercek.name)):
            raise Stop(OTOMATIK_RET)  # kullanıcı yol vermedi ve seçilen dosya belge değil: yanlış dosya gitmesin
        if gercek not in gorulen:  # aynı dosya iki kez verildiyse bir kez gider
            gorulen.add(gercek)
            dosyalar.append((kopru_dosya_adi(yol.name, kullanilan), gercek, yol.name))
    if not dosyalar and not notlu:
        raise Stop("Paylaşılacak bir şey yok: dosya yolu ya da bir not ver. Hiçbir şey gönderilmedi.")
    kaynaklar = ([("govde.md", not_metni.encode("utf-8"), "notun")] if notlu else []) + dosyalar
    anahtar_denetle(kaynaklar)
    boyut_denetle(kaynaklar, YUKLEME_DOSYA_AZAMI, YUKLEME_KAYIT_AZAMI)  # her yolun üst sınırı; ağdan önce
    # Bağlantılar (Claude artifact, Google Docs) sözlerin parçasıdır: indirilmez, kütüphaneci nottan sınıflar.
    alan, alicilar, login, kim = hizli_alan(args, not_metni)
    yol, login, slug, onbellekten = hizli_yol(alan, login, kopru_once=True)
    notlar = []
    kopru_sonuc = None
    if yol == "kopru":
        try:
            kopru_sonuc = hizli_kopru(alan, kim, kaynaklar, dosyalar, not_metni, haber)
        except Stop as hata:
            yol, login, slug, onbellekten = hizli_yedek_yol(alan, hata)
            notlar.append("Köprüye ulaşılamadı; GitHub yolundan gitti (alıcıya ~1 dakikada ulaşır).")
    if yol == "writer":
        boyut_denetle(kaynaklar, HIZLI_DOSYA_AZAMI, HIZLI_KAYIT_AZAMI)  # GitHub blob API
        kod, klasor, adlar = hizli_yazan(alan, slug, login, onbellekten, dosyalar, not_metni, haber, notlar)
        dosyalama = YAZAN_DOSYALAMA if zil_cal(alan, notlar) else "bir sonraki turunda"
    else:
        kod, klasor, adlar, dosyalama = kopru_sonuc
    gecmise_yaz(kod, alan, yol, slug, klasor)
    gecici_kok = (onbellek_koku() / "gecici").resolve()
    silinecek = [gercek for _, gercek, _ in dosyalar] + ([not_yolu] if not_yolu else [])
    for gercek in silinecek:  # /paylas'ın gecici/'ye yazdığı not ve metin kopyaları gönderildi: bekletilmez
        if gecici_kok in gercek.parents:
            try:
                gercek.unlink()
            except OSError:
                pass
    return {"kod": kod, "alan": alan, "alicilar": alicilar, "yol": yol, "dosyalar": adlar,
            "satir": hizli_satir(kod, [gorunen for _, _, gorunen in dosyalar], notlu, alan, dosyalama),
            "notlar": notlar}


# --- köprü: okuma, alındı, anahtar kurulumu ---

def oku(argv):
    parser = argparse.ArgumentParser(prog="tf_bilgi.py oku")
    parser.add_argument("yollar", nargs="+")
    yollar = parser.parse_args(argv).yollar
    kopru_gerekli("oku", "Doğrudan yolda dosyalar önbellek klonundadır (`hazirla` çıktısındaki `kok`).")
    if len(yollar) > 25:
        raise Stop("Tek seferde en çok 25 dosya okunur.")
    for y in yollar:
        if y.startswith("/") or ".." in y.split("/") or KONTROL_KARAKTER_RE.search(y):
            raise Stop(f"Geçersiz yol: {y!r} (depo içi göreli yol bekleniyor, ör. SON.md)")
    return {"dosyalar": kopru_oku(yollar)}


def ara(argv):
    parser = argparse.ArgumentParser(prog="tf_bilgi.py ara")
    parser.add_argument("sorgu", nargs="+")
    sorgu = _duz_metin(" ".join(parser.parse_args(argv).sorgu))
    kopru_gerekli("ara", "Doğrudan yolda arama `tf_bilgi.py kb ara '<sorgu>' --json` ile yapılır.")
    if not 2 <= len(sorgu) <= 100:
        raise Stop("Arama 2–100 karakter olmalı.")
    r = kopru_cagir("ara", {"sorgu": sorgu})
    return {"sorgu": sorgu, "kaynak": r.get("kaynak"), "toplam": r.get("toplam"), "sonuclar": r.get("sonuclar") or []}


def girdi(argv):
    """Tek girdi: köprüde köprüden (alıcısı olmadığın gizli girdi içeriksiz), doğrudan yolda önbellek klonundan."""
    parser = argparse.ArgumentParser(prog="tf_bilgi.py girdi")
    parser.add_argument("id")
    parser.add_argument("--yonetim", action="store_true")
    args = parser.parse_args(argv)
    gid = args.id.strip()
    m = GIRDI_ID_RE.match(gid)
    if not m:
        raise Stop(f"Girdi kimliği anlaşılmadı: {gid!r} (örnek: B-20261105-ayse-01).")
    yol = f"girdiler/{m.group(2)}/{m.group(3)}/{gid}.md"
    if yol_sec() == "kopru":
        if args.yonetim:
            raise Stop(KOPRU_YONETIM_YOK)
        d = kopru_oku([yol])[0]
        if d.get("hata") == "gizli" or d.get("gizli") and d.get("icerik") is None:
            return {"id": gid, "yol": yol, "gizli": True, "icerik": None,
                    "mesaj": d.get("mesaj") or f"{gid} gizli bir belge; yalnız alıcıları görür."}
        if not isinstance(d.get("icerik"), str):
            raise Stop(d.get("mesaj") or f"{gid} bulunamadı: depoda yayımlanmış böyle bir girdi yok.")
        icerik, uzak = d["icerik"], uzak_slug(depo_ayari(ayna_mevcut(), "ekip"), "ekip")
    else:
        alan = alan_bayrak(args.yonetim)
        kok = mevcut_kok(alan)
        proc = git(kok, "show", f"origin/{DAL}:{yol}", check=False)
        if proc.returncode != 0:
            raise Stop(f"{gid} bulunamadı: depoda yayımlanmış böyle bir girdi yok (yeni paylaşıldıysa birkaç dakika "
                       "sonra tekrar dene).")
        icerik, uzak = proc.stdout, uzak_slug(depo_ayari(kok, alan), alan)
    return {"id": gid, "yol": yol, "url": baglanti(uzak, yol), "gizli": gizli_girdi_mi(icerik), "icerik": icerik}


def alindi(argv):
    parser = argparse.ArgumentParser(prog="tf_bilgi.py alindi")
    parser.add_argument("id")
    gid = parser.parse_args(argv).id.strip()
    if not GIRDI_ID_RE.match(gid):
        raise Stop(f"Girdi kimliği anlaşılmadı: {gid!r} (örnek: B-20261105-ayse-01).")
    kopru_gerekli("alindi", "Doğrudan yolda alındı `tf_bilgi.py kb alindi <id> --kisi <sen>` ve `kaydet` ile yazılır.")
    r = kopru_cagir("alindi", {"girdi": gid})
    return {"girdi": gid, "kod": r.get("kod"), "kayit": r.get("kayit"), "dosyalama": r.get("dosyalama"),
            "satir": f"Alındın gönderildi: {gid} · kütüphaneci {dosyalama_metni(r.get('dosyalama'))} kaydeder."}


def kur(argv):
    """/bilgi kur: anahtar dosyadan (Write aracıyla gecici/ altına yazılmış) okunur, köprüyle doğrulanır, 0600 kaydedilir;
    geçici dosya her durumda silinir. Anahtar hiçbir çıktıya yazılmaz."""
    parser = argparse.ArgumentParser(prog="tf_bilgi.py kur")
    grup = parser.add_mutually_exclusive_group()
    grup.add_argument("--dosya", help="anahtarın yazıldığı dosya (gecici/ altında)")
    grup.add_argument("--sil", action="store_true", help="köprü anahtarını kaldır")
    args = parser.parse_args(argv)
    yol = anahtar_yolu()
    dosya_yeri = str(gecici_dizin() / "anahtar.txt")
    if args.sil:
        vardi = yol.is_file()
        if vardi:
            yol.unlink()
        return {"silindi": vardi, "anahtar": False, "satir": "Köprü anahtarı kaldırıldı." if vardi else
                "Köprü anahtarı zaten yoktu."}
    if args.dosya is None:
        # Durum hiçbir zaman kurulumu kilitlemez: eski anahtar silinmiş (anahtarUret yeniledi), dosya bozuk ya da köprü
        # yanıt vermiyor olsa da çıkış 0; yeni anahtar `--dosya` ile eskiden bağımsız doğrulanıp üzerine yazılır.
        if not yol.is_file():
            return {"anahtar": False, "gecerli": None, "dosya_yeri": dosya_yeri, "yol": "dogrudan"}
        try:
            yol_simdi = yol_sec()
        except Stop:
            yol_simdi = "kopru"
        try:
            kim = kopru_kim(anahtar_oku())
        except KopruHatasi as e:
            return {"anahtar": True, "gecerli": False, "dosya_yeri": dosya_yeri, "yol": yol_simdi,
                    "uyari": f"Kayıtlı köprü anahtarı geçerli değil: {e}"}
        except Stop as e:
            bozuk = not anahtar_coz(yol.read_text(encoding="utf-8", errors="replace")) if yol.is_file() else False
            return {"anahtar": True, "gecerli": False if bozuk else None, "dosya_yeri": dosya_yeri, "yol": yol_simdi,
                    "uyari": (f"Kayıtlı köprü anahtarı bozuk ({yol}); yenisini kur." if bozuk else
                              f"Köprü şu an doğrulanamadı: {e}")}
        return {"anahtar": True, "gecerli": True, "kisi": kim.get("kisi"), "ad": kim.get("ad"), "depo": kim.get("depo"),
                "dosya_yeri": dosya_yeri, "yol": yol_simdi}
    kaynak = gecici_alti(args.dosya, "--dosya")
    try:
        if not kaynak.is_file():
            raise Stop(f"Anahtar dosyası yok: {args.dosya}")
        bulunan = ANAHTAR_ARA_RE.findall(kaynak.read_text(encoding="utf-8", errors="replace"))
        if len(set(bulunan)) != 1:
            raise Stop("Bu bir TF Bilgi köprü anahtarı değil (`tfb1.` ile başlayan tek satır bekleniyor). Anahtarı Slack'te "
                       "TF Bilgi botunun verdiği haliyle yapıştır (bota `anahtar` yaz)." if not bulunan else
                       "Metinde birden çok köprü anahtarı var; yalnız kendi anahtarını yapıştır.")
        anahtar = anahtar_coz(bulunan[0])
        kim = kopru_kim(anahtar)
        kisi = str(kim.get("kisi") or "")
        if not KISI_RE.match(kisi):
            raise Stop(KOPRU_YANIT_YOK)
        yol.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(yol), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(bulunan[0] + "\n")
        os.chmod(yol, 0o600)
    finally:
        if kaynak.is_file() or kaynak.is_symlink():
            kaynak.unlink()
    ad = kim.get("ad") or kisi
    satir = (f"Köprü anahtarı kuruldu: {ad} ({kisi}). /paylas artık GitHub'sız çalışır; belgeler sana Slack'ten "
             "bağlantıyla gelir." if cf_dagitim_mi(anahtar[0]) or kopru_protokolu(kim) >= 2 else
             f"Köprü anahtarı kuruldu: {ad} ({kisi}). /paylas ve /bilgi artık köprüden, GitHub'sız çalışır.")
    return {"kuruldu": True, "kisi": kisi, "ad": ad, "depo": kim.get("depo"), "yol": yol_sec(), "satir": satir}


# --- köprü: yorum, yorumlar, tercih ---

def kopru_yorum_hedefi(girdi_id, yonetim):
    girdi_id = (girdi_id or "").strip()
    m = GIRDI_ID_RE.match(girdi_id)
    if not m:
        raise Stop(f"Girdi kimliği anlaşılmadı: {girdi_id!r} (örnek: B-20261105-ayse-01).")
    if yonetim:
        raise Stop(YONETIM_YORUM_YOK)
    kok = ayna_mevcut()
    onek = depo_ayari(kok, "ekip").get("girdi_onek") or "B"
    if m.group(1) != onek:
        raise Stop(f"{girdi_id} ekip deposunun girdisi değil (ekip girdileri {onek}- ile başlar; yönetim girdileri ayrı "
                   f"depodadır). {YONETIM_YORUM_YOK}")
    return girdi_id, kok


def yorum_kopru(args):
    """/bilgi yorum köprüden: metin önce yerelde taranır, köprü sayfayı bulur/açar ve yorumu köprü adına (ilk satır
    `kisi=<sen>`) yazar. Bildirim satırı doğrudan yoldaki kuralla hesaplanır."""
    girdi_id, kok = kopru_yorum_hedefi(args.girdi, args.yonetim)
    kisiler = kisileri_oku(kok)
    ben = kopru_kimligi()["kisi"]
    yol, metin = yorum_metni(args.dosya)
    yorum_tara(kok, yol)  # metin makineden çıkmadan önce
    plan = kopru_cagir("yorum", {"girdi": girdi_id, "metin": metin, "gonder": False})
    g = plan.get("girdi") if isinstance(plan.get("girdi"), dict) else {}
    kimden = g.get("kimden") if isinstance(g.get("kimden"), list) else []
    girdi_ = {"id": girdi_id, "baslik": tek_satir(g.get("baslik") or girdi_id, 200), "url": g.get("url"),
              "yazar": g.get("yazar") if isinstance(g.get("yazar"), str) else None,
              "kimden": list(dict.fromkeys(str(k) for k in kimden))}
    kimlik = {"login": None, "kisi": ben, "ben": ben, "kopru": True}
    onceki = [k for k in (plan.get("onceki") or []) if isinstance(k, str) and k in kisiler]
    alicilar, satir = yorum_bildirimi(girdi_, onceki, kisiler, kimlik)
    sayfa = plan.get("sayfa") if isinstance(plan.get("sayfa"), dict) else None
    notlar = []
    if isinstance(plan.get("sayfa_sayisi"), int) and plan["sayfa_sayisi"] > 1 and sayfa:
        notlar.append(f"Bu girdinin {plan['sayfa_sayisi']} yorum sayfası var; yorum en eskisine (#{sayfa.get('numara')}) "
                      "yazılır.")
    temel = {"girdi": girdi_id, "baslik": girdi_["baslik"], "girdi_url": girdi_["url"], "ben": kimlik,
             "alicilar": alicilar, "bildirim": satir, "notlar": notlar, "yol": "kopru"}
    if not args.gonder:
        yeni = None if sayfa else {"baslik": f"[{girdi_id}] {girdi_['baslik']}",
                                   "etiket": f"`{YORUM_ETIKETI}` etiketiyle (sayfayı köprü açar)"}
        return {**temel, "sayfa": sayfa, "yeni_sayfa": yeni, "karakter": len(metin), "yazildi": False}
    r = kopru_cagir("yorum", {"girdi": girdi_id, "metin": metin, "gonder": True})
    sayfa = r.get("sayfa") if isinstance(r.get("sayfa"), dict) else sayfa
    yeni = bool(r.get("yeni_sayfa"))
    return {**temel, "yazildi": True, "sayfa": sayfa, "yeni_sayfa": yeni,
            "etiket": f"`{YORUM_ETIKETI}` etiketiyle (köprü açtı)" if yeni else None,
            "yorum_url": r.get("yorum_url") or (sayfa or {}).get("url")}


def yorumlar_kopru(args):
    girdi_id, kok = kopru_yorum_hedefi(args.girdi, args.yonetim)
    kisiler = kisileri_oku(kok)
    r = kopru_cagir("yorumlar", {"girdi": girdi_id, "son": args.son})
    liste = []
    for y in r.get("yorumlar") or []:
        if not isinstance(y, dict):
            continue
        kisi = y.get("kisi") if y.get("kisi") in kisiler else None
        liste.append({**y, "kisi": kisi, "ad": ilk_ad(kisiler, kisi) if kisi else (y.get("ad") or y.get("login")),
                      "tarih": zaman_tr(y.get("zaman")), "metin": kirp(y.get("metin"), YORUM_METIN_AZAMI)})
    toplam = r.get("toplam") if isinstance(r.get("toplam"), int) else len(liste)
    return {"girdi": girdi_id, "baslik": r.get("baslik"), "girdi_url": r.get("girdi_url"), "sayfa": r.get("sayfa"),
            "sayfalar": r.get("sayfalar") or [], "toplam": toplam,
            "onceki": r.get("onceki") if isinstance(r.get("onceki"), int) else 0, "yorumlar": liste,
            "satir": "" if toplam else f"Henüz yorum yok. Yazmak için: /bilgi yorum {girdi_id} <yorumun>",
            "notlar": r.get("notlar") or [], "yol": "kopru"}


def tercih_kopru(args):
    if args.kisi:
        raise Stop("Köprü yolunda tercih yalnız kendi adına yazılır. Başkası adına tercihi tercih yöneticileri "
                   "doğrudan yolda yazar.")
    kok = ayna_mevcut()
    kisiler = kisileri_oku(kok)
    ben = kopru_kimligi()["kisi"]
    cozum = kanal_cozumu(kisiler.get(ben) or {})
    if args.kanal is None:
        r = kopru_cagir("tercih")
        varsayilan = bool(r.get("varsayilan"))
        return {"kisi": r.get("kisi") or ben, "kanallar": r.get("kanallar") or ["slack"], "varsayilan": varsayilan,
                "kaynak": r.get("kaynak") or ("tercih yok: varsayılan Slack, Slack kimliği çözülemezse mail"
                                              if varsayilan else "köprü"),
                "cozum": cozum, "issue": r.get("issue"), "uyarilar": [], "yol": "kopru"}
    kanallar = list(dict.fromkeys(k.strip().lower() for k in args.kanal.split(",") if k.strip()))
    if not kanallar or any(k not in KANALLAR for k in kanallar):
        raise Stop(f"Kanal anlaşılmadı: {args.kanal!r}. Seçenekler: slack, mail, whatsapp (virgülle birden çok).")
    r = kopru_cagir("tercih", {"kanal": ",".join(kanallar)})
    return {"yazildi": True, "kisi": r.get("kisi") or ben, "kanallar": r.get("kanallar") or kanallar,
            "satir": r.get("satir") or f"tercih: kisi={ben} kanal={','.join(kanallar)}", "url": r.get("url"),
            "cozum": cozum, "yol": "kopru"}


KOMUTLAR = {"hazirla": hazirla, "gecici": gecici, "maskele": maskele, "temizle": temizle, "yaz": yaz,
            "kaydet": kaydet, "prler": prler, "bildirim-plani": bildirim_plani, "tercih": tercih,
            "gizli-alicilar": gizli_alicilar, "yorum": yorum, "yorumlar": yorumlar, "kur": kur, "gonder": gonder,
            "geri-al": geri_al, "oku": oku, "ara": ara, "girdi": girdi, "alindi": alindi, "hizli": hizli,
            "alan": alan_komutu}
KULLANIM = ("kullanım: tf_bilgi.py hizli [--yonetim | --ekip] [--otomatik] [--not-dosya F] [--ek YOL]... | "
            "alan [--yonetim | --ekip] [--not-dosya F] | "
            "hazirla [--yonetim] [--yazma] | kb [--yonetim] <komut> ... | gecici AD | "
            "maskele [--yonetim] DOSYA [--dizin D] | temizle YOL... | yaz [--yonetim] [--dosya F] [--uzerine] | "
            "kaydet [--yonetim] (--mesaj M | --mesaj-dosya F) YOL... | prler [REF...] [--repo R] | "
            "bildirim-plani [--yonetim] --tip T --kimden a,b --yazar K [--son-tarih D] [--haber hemen|simdi|gunluk] "
            "[--adet N] | tercih [--kanal slack,mail,whatsapp] [--kisi K] | gizli-alicilar [--yonetim] --kimden a,b | "
            "yorum GIRDI_ID --dosya F [--gonder] [--yonetim] | yorumlar GIRDI_ID [--son N] [--yonetim] | "
            "kur [--dosya F | --sil] | gonder --taslak F [--metin F] [--govde F] [--ek YOL]... | geri-al HEDEF | "
            "oku YOL... | ara SORGU... | girdi GIRDI_ID [--yonetim] | alindi GIRDI_ID")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    _KIM_ONBELLEK.clear()
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
