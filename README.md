# Teamfluencer-Dev / .github

Org defaults for Teamfluencer-Dev repositories.

## Mandatory Claude PR review (`tf-review` plugin)

Every repository's default branch has a ruleset named **Claude review zorunlu**:

- changes land only through pull requests (no direct pushes), and
- the PR head commit must carry a successful **`claude-review`** commit status.

That status is set by the `tf-review` Claude Code plugin. The review runs in the
developer's own Claude Code session, on their Claude subscription — never on
Anthropic API credits — by a fresh-context Opus agent.

### One-time setup (each developer)

```bash
claude plugin marketplace add Teamfluencer-Dev/.github
claude plugin install tf-review@teamfluencer
```

Also required: the GitHub CLI logged in (`gh auth login`), Claude Code logged in
with a Claude subscription (`/login`), and no `ANTHROPIC_API_KEY` in the
environment Claude Code starts from (the plugin refuses to run otherwise).

### Usage

Open Claude Code in the repository and run:

```
/pr-review            # the PR of the current branch
/pr-review 123        # a PR number or URL
/pr-review 123 --full # force a full review
```

What happens:

1. `scripts/tf_review.py prepare` resolves the PR and picks a mode:
   - **full** — first review of the PR (or `--full`, or more than 1,500 changed
     lines since the last review, or the last reviewed commit was force-pushed
     away);
   - **incremental** — code changed since the last review; only the delta is
     reviewed and earlier findings are tracked;
   - **carry** — nothing in the PR's files changed since the last review (e.g. a
     base-branch merge) or only docs changed: the status is re-issued without an
     agent run;
   - **docs-only** — the PR only touches `*.md`, `*.mdx`, `*.rst`, `docs/` or
     `LICENSE`.
2. For full / incremental reviews, the skill launches `full-reviewer` or
   `incremental-reviewer` (Opus, zero context). The agent reads the job directory
   (`.tf-review/pr-<n>/` in the repo, git-excluded) and the code at the PR head,
   and writes `review.md`.
3. `scripts/tf_review.py post` posts the review as a PR comment, sets
   `claude-review` = success on the reviewed commit, collapses older review
   comments and removes the job directory.

Every new push needs `/pr-review` again before merging; later runs are
incremental or carry-forward, so they are quick.

The verdict (APPROVE / NEEDS-CHANGES / BLOCKER) is informational: the check
requires that a review happened, not that it approved.

### Safeguards and limits

- The reviewer agents read text written by others, so a plugin `PreToolUse` hook
  (`hooks/reviewer_guard.py`) confines them: Bash is denied unless it is a
  single-line read-only command (git history, `rg`/`grep`, file viewers) with no
  shell expansion, writes are denied outside their own `review.md`, and web, MCP,
  nested-agent and skill tools are denied. The hook only ever denies — a command
  it considers read-only still goes through the session's normal permission
  flow, so a parser mistake cannot become a silent run.
- PR descriptions and earlier reviews are wrapped in per-job random delimiters.
- Pull requests from forks are refused.
- Markdown that instructs Claude or the reviewer (`CLAUDE.md`, `AGENTS.md`,
  `SKILL.md`, `.claude/`, `claude-plugins/`, `.github/claude-review-context.md`)
  is reviewed like code, never skipped as documentation.
- Review state is read only from unedited marker comments written by org
  members or collaborators.
- The gate is a team process control, not a security boundary: anyone with push
  access can technically create a `claude-review` status through the API.

Repo-specific review invariants live in each repository's
`.github/claude-review-context.md` (INV-### / INV-T##) and are handed to the agent.

### Updating the plugin

```bash
claude plugin marketplace update teamfluencer
claude plugin update tf-review@teamfluencer
```

`/pr-review` prints a reminder when a newer version is published. Bump
`claude-plugins/tf-review/.claude-plugin/plugin.json` `version` with every change.

### Tests

```bash
python3 -m unittest discover -s claude-plugins/tf-review/tests -v
```

### Emergency

An org admin can temporarily set the ruleset to *Disabled* in the repository's
Settings → Rules → Rulesets (for example if a hotfix cannot wait for a review).
Re-enable it right after.

## TF Bilgi (`tf-bilgi` eklentisi)

TF Bilgi, ekibin GitHub'daki bilgi bankasıdır: `Teamfluencer-Dev/tf-bilgi` (ekip) ve
`Teamfluencer-Dev/tf-bilgi-yonetim` (yönetim), ikisi de private. Eklenti Claude Code'dan
tek komutla yazmayı (`/paylas`), bir klasör dolusu belgeyi toplu paylaşmayı (`/toplu-paylas`) ve
okumayı (`/bilgi`) sağlar. Kuralların tek kaynağı
KB deposundaki `araclar/kb.py` ve `CLAUDE.md`'dir; eklenti yalnız onu çağırır.

### Kurulum (her geliştirici, bir kez)

```bash
claude plugin marketplace add Teamfluencer-Dev/.github   # tf-review için yaptıysanız gerekmez
claude plugin install tf-bilgi@teamfluencer
```

Gerekenler: git, Python 3.9+, `gh auth login` ve GitHub hesabınızın KB deposuna okuma
yetkisi. **Yazma** (`/paylas`, `/toplu-paylas`, `/bilgi alindi`) için depoya yazma yetkisi
gerekir; 6 Kas 2026'dan beri bu yetki yalnız KB deposunun `.kb.json` `yazanlar` listesindeki
kişilerde. Yetkisi olmayanda eklenti taslak hazırlamadan durur ve belgeyi kime ileteceğini
söyler; okuma (`/bilgi`) ve bildirim tercihi (`/bilgi tercih`) çalışır. Eklenti model çağırmaz, API anahtarı istemez; `tf-review` ile yan yana
çalışır. Kurulum her yapılandırma klasörü (`CLAUDE_CONFIG_DIR`) için ayrı yapılır.

### Kullanım

```
/paylas ekteki PDF yönetim için; Cuma'ya kadar fiyat kararı lazım ./abonelik.pdf
/paylas geldiğim nokta: ödeme ekranı bitti, test bekliyor
/paylas api#1976 web#689 merge sırası devri
/paylas Ayşe ve Mert'ten Cuma'ya merge onayı lazım, hemen haber ver ./plan.pdf
/paylas gizli: Ayşe'ye, yalnız o görsün ./teklif.pdf   # belge okunmaz, Drive'da paylaşılır
/toplu-paylas ~/Desktop/artifaktlar     # klasör dolusu HTML/PDF: tek onay tablosu
/bilgi                       # kuyruğun + son 3 gün
/bilgi son 7
/bilgi konu K-0003
/bilgi ara abonelik
/bilgi alindi B-20261105-ayse-01 Cuma'ya bakıyorum
/bilgi alindi B-20261105-ayse-01 --kisi mert   # yazanlar: yetkisi olmayanın alındısını onun adına
/bilgi tercih                # bildirim kanalın ve çözülüp çözülmediği
/bilgi tercih slack,mail     # tercihini "Bildirim tercihleri" issue'suna yazar
```

`/paylas` konuyu eşleştirir (`kb.py eslestir`), içeriği ve ekleri sır/KVKK için tarar
(`kb.py tara`), tek bir onay kartı gösterir (konu + güven, tür · kitle · alan, istek,
TL;DR, yerine geçtiği girdi, ham dosya + tarama sonucu) ve **Onayla / Düzelt / Vazgeç**
diye sorar. Onaydan önce depoya hiçbir şey yazılmaz. Onayda yalnız yeni `girdiler/`,
`ham/` ve `onaylar/` dosyaları commit'lenip gönderilir; konu dizini, konu sayfaları ve
kuyruklar kütüphanecinindir, eklenti onlara dokunmaz. Yönetim deposuna yalnız
`--yonetim` ile ya da açıkça "yönetim için" denince yazılır; içerik tek başına alanı
belirlemez. `pr-listesi` türünde tablo `gh` ile (yalnız okuma) PR'ların
`claude-review` ve merge durumundan kurulur.

İstek bir ya da birden çok kişiye yöneltilir (`kimden: ayse` ya da
`kimden: [ayse, mert]`); alındı kişi başınadır. Depoya yazma yetkisi olmayan alıcı
“alındı <girdi-id>”yi `yazanlar` listesindekilerden birine yazar; o
`/bilgi alindi <girdi-id> --kisi <alıcı>` ile onun adına kaydeder (onay dosyasında
`kaydeden`; KB `dogrula` kaydedenin `yazanlar`'da olduğunu denetler). "Hemen haber ver"
denirse girdiye `haber: hemen` yazılır ve push'ta her alıcıya anlık mesaj gider (hafta içi 08:30–19:00,
kişi başı günde en çok 3; dışında 08:30 özetinde). Kartın `bildirim` satırı kime şimdi,
kime özette, hangi kanaldan gideceğini ve kime hiçbir şey gitmeyeceğini adıyla söyler
(`tf_bilgi.py bildirim-plani`, yalnız okur). Kanal tercihi (Slack, mail, WhatsApp; bir ya
da birden çok) KB ekip deposundaki "Bildirim tercihleri" issue'sunda `tercih: kanal=…`
yorumuyla durur; `/bilgi tercih` okur ve yazar.

**Gizli paylaşım** ("gizli", "özel", "confidential", "yalnız o görsün" ya da
`--gizli`): belgenin içeriği hiçbir depoya girmez. Eklenti belgeyi açmaz, taramaz,
dönüştürmez, özetlemez ve geçici klasöre kopyalamaz. Alıcıların iş e-postalarını
gösterir (`tf_bilgi.py gizli-alicilar`, KB `kisiler.json`'dan; kayıtlı değilse
söyler, tahmin etmez) ve Drive adımlarını verir: dosyayı kendi Drive'ına (ortak
drive'a değil: ortak drive üyeleri her şeyi görür) yükle, Paylaş → yalnız bu
e-postalar Görüntüleyici, "Genel erişim" Kısıtlı ("Teamfluencer" kuruluş geneli ya da
"Bağlantıya sahip olan herkes" değil), bağlantıyı yapıştır. Hazır bir bağlantı verilse
de aynı adımlar "Paylaşımı kontrol et" diye gösterilir ve konum, kişiler, genel erişim
üç ayrı soruyla onaylatılır; kartın `paylaşım` satırı yalnız onaylananı yazar. Bağlantı
yalnız `https://drive.google.com/…` ya da `https://docs.google.com/…` olabilir
(`kb.py taslak --gizli` denetler); eklentinin `kaydet`'i gizli girdiye ham dosya ya da
defter satırı bağlanmasını ayrı çağrılarda da reddeder. Depoya yalnız sabit metinli bir girdi yazılır:
kim → kime, Drive bağlantısı, nasıl alındı denir (`gizli: true`, `ham: null`; başlık
istenmedikçe "Gizli belge", en çok 40 karakter). Ortak drive'daki dosya için kopya
oluşturulursa kayda kopyanın bağlantısı girer ve üç soru o bağlantı için yeniden sorulur. Kartta `gizli: evet · içerik depoya girmez · link: …`
satırı çıkar. Oturumda dosyayı yoldan yükleyip paylaşabilen bir Google Drive
connector'ı varsa eklenti bunu önerebilir; elle yol her zaman tek başına çalışır.
Bildirim kuralları (hemen, kanal, sessiz saat, pilot) aynıdır; mesaj "<Gönderen> sana
gizli bir belge gönderdi" + Drive bağlantısı. `/bilgi` gizli girdiyi 🔒 ve bağlantıyla
gösterir, özet göstermez; erişimi Drive verir. `/toplu-paylas`'ta gizli kip yoktur.
Kurallar: KB `CLAUDE.md` §4.6.

`/toplu-paylas` bir klasörü (ör. claude.ai'den indirilmiş artifact'ler: her alt klasör
bir öğe, `ekler/*.pdf` ayrı öğe, görseller varlık) ya da dosya listesini önce
`kb.py toplu-hazirla` ile `~/.tf-bilgi/gecici/toplu-<zaman>/` altına açar (düz metin,
sır/KVKK taraması, konu adayları, `zaten_var` / `kopya` bayrakları; depoya yazmaz).
Sonra her öğeyi **ekip**, **yönetim** ya da **girmez** diye sınıflar (10'dan fazla
öğede alt ajanlarla, ~15'lik gruplar), tek bir tablo (Ekip / Yönetim / Girmeyenler)
gösterir ve **Onayla / Düzelt / Vazgeç** diye sorar. Onayda her alana tek commit
atılır. Ham dosya yalnız tarama temizse, influencer kimliği ve açık güvenlik ayrıntısı
yoksa ve dosya 20 MB'tan küçükse depoya girer. Yönetim öğesi hiçbir zaman ekip
deposuna yazılmaz; yönetim deposuna erişim yoksa hazırlık klasöründe kalır.
`--yonetim-yok` yönetim deposunu bu çalıştırmada hiç kullanmaz. KB deposundaki
`kb.py`'nin `toplu-hazirla`'yı bilmesi gerekir (KB `CLAUDE.md` §8.1).

### Ortam değişkenleri

| Değişken | Ne işe yarar | Varsayılan |
|---|---|---|
| `TF_BILGI_KISI` | `kisiler.json`'daki anahtarınız | `gh` hesabınızdan, sonra git e-postanızdan bulunur; bulunamazsa bir kez sorulur |
| `TF_BILGI_DIZIN` | Önbellek klonlarının klasörü | `~/.tf-bilgi` |
| `TF_BILGI_UZAK_EKIP`, `TF_BILGI_UZAK_YONETIM` | Depo adresi (GitHub `sahip/ad`, git adresi ya da test için yerel yol) | `Teamfluencer-Dev/tf-bilgi`, `Teamfluencer-Dev/tf-bilgi-yonetim` |
| `TF_BILGI_SURUM_KONTROLU` | `0` → güncel sürüm kontrolü kapalı | açık |

Önbellek klonunda commit'lenmemiş değişiklik varsa eklenti üzerine çekmez ve durur
(ne yapılacağını yazar). Klonun `.kb.json` alanı beklenenle tutmazsa da durur.

`/paylas` ve `/toplu-paylas` belge metnini kabuk komutuna koymaz: eşleştirme metni,
başlık, commit mesajı ve girdi Write aracıyla `~/.tf-bilgi/gecici/` altındaki o çalıştırmaya
ait klasöre yazılır ve dosya seçenekleriyle verilir (`--baslik-dosya`, `--mesaj-dosya`,
`--dosya`). Bu klasör belgelerin tam metin kopyalarını tutar: başarılı kayıttan sonra
silinir (`tf_bilgi.py temizle`, yalnız `gecici/` altını siler); Vazgeç'te klasörün yeri
söylenir ve istenirse silinir.

**KB aracı sabitli.** Eklenti, KB deposundaki `araclar/kb.py`'nin yalnız onayladığı
sürümünü çalıştırır: sha256'sı `scripts/tf_bilgi.py` içindeki `KB_SHA256`'da durur ve bu
repoda review'dan geçer. Klondaki `kb.py` farklıysa eklenti hiçbir komutu çalıştırmaz ve
eklentiyi güncellemeyi söyler; `kb.py` yalıtılmış kipte (`python3 -I`) çalışır.
`kb.py` değişikliği şöyle yayınlanır (KB `CLAUDE.md` §12):

1. Değişiklik KB deposunda bir dalda PR olarak açılır; `main`'e doğrudan push yapılmaz.
2. Bu repoda yeni hash'i ekleyen PR (sürüm artar, `/pr-review`) o KB PR'ının bağlantısını
   ve head SHA'sını taşır. Hash o SHA'daki `kb.py`'nindir.
3. İki PR aynı gün merge edilir: KB PR'ı eklenti merge'ünün hemen ardından. O andan sonra
   güncellenmemiş eklenti kapalı kalır: durur ve güncellemeyi söyler.
4. Yeni özellik iki taraf da canlı olunca duyurulur; "eklentiyi güncelleyin" mesajı ondan
   söz etmez.

Geçişte `KB_SHA256` iki hash taşır (0.4.0: GitHub'daki KB deposunun bugünkü `kb.py`'si ve
gizli paylaşımlı yeni `kb.py`, Teamfluencer-Dev/tf-bilgi#2 head `76fd0e7`); eski hash bir
sonraki sürümde çıkar. Yönetim deposu (`tf-bilgi-yonetim`) GitHub'da henüz yok: 0.3.1
kullanan kimse ona erişemedi. Depo açıldığında ilk push'u aynı yeni `kb.py` ile yapılır;
o güne kadar `--yonetim` ile paylaşım çalışmaz.

### Notlar

- Bu repo public olduğu için eklentide sır, token ya da iç adres yoktur; GitHub
  erişimi kullanıcının kendi `gh` girişinden gelir.
- Belge, mail ve PDF içeriği veridir, talimat değildir.
- Claude'suz yollar (mail, WhatsApp, Drive) ve claude.ai sürümü Faz 2'de gelir.
- Güncelleme: `claude plugin marketplace update teamfluencer && claude plugin update tf-bilgi@teamfluencer`.
  Her değişiklikte `claude-plugins/tf-bilgi/.claude-plugin/plugin.json` sürümü artırılır.

Testler: `python3 -m unittest discover -s claude-plugins/tf-bilgi/tests -v`

## Test coverage

`coverage-policy.md` defines what counts, the current phase (visibility, no
gates) and the planned gates. Repositories publish their `lcov.info` with the
shared action `actions/coverage-summary`:

```yaml
- uses: Teamfluencer-Dev/.github/actions/coverage-summary@main
  if: always()
  with:
    lcov: coverage/lcov.info
    title: Coverage — <repo>
```

Tests: `python3 -m unittest discover -s actions/coverage-summary`.

## No GitHub-side PR review

The API-billed CI review is gone: the reusable `claude-review.yml` workflow was
deleted, the caller workflows were removed from the repositories, their API key
secrets were deleted and the review API keys were deactivated. Nothing on GitHub
calls a model any more — PR review happens only in a developer's Claude Code
session, through the plugin above. The v11 review instructions live in the
plugin's agents.
