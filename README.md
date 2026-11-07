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
`eneskrblt/tf-bilgi-yonetim` (yönetim; org dışında), ikisi de private. Eklenti Claude Code'dan
tek komutla yazmayı (`/paylas`), bir klasör dolusu belgeyi toplu paylaşmayı (`/toplu-paylas`) ve
okumayı ve belgeler üzerine yorumlaşmayı (`/bilgi`, `/bilgi yorum`) sağlar. Kuralların tek kaynağı
KB deposundaki `araclar/kb.py` ve `CLAUDE.md`'dir; eklenti yalnız onu çağırır.

**0.8.0: Claude Code'u olan herkes** (Enes, 7 Kas). Bilgi deposuna yazma yetkisi yalnız Enes ve
Ilgım'da kalır; diğer ekip üyelerinin `/paylas`'ı aynı tek commit'i ayrı **gelen kutusu deposuna**
(`Teamfluencer-Dev/tf-bilgi-gelen`; yalnız bu depoya yazma yetkisi, sır ve iş akışı yok) atar.
tf-bilgi'nin `gelen-depo` iş akışı (hafta içi 15 dakikada bir) kaydı olduğu gibi `00-gelen/`'e
aktarır, kütüphaneci her hızlı kayıt gibi dosyalar. Kişi ekip deposunun `kisiler.json`'undan
(`gh` girişi) bulunur. Yönetime Claude Code'dan yalnız yönetim deposuna yazanlar gönderir; diğerleri
Slack botuna "yönetim için" yazar. Claude artifact bağlantısı (`claude.ai/…artifact…`) verilirse
`/paylas` artifact'ı Artifact aracıyla indirip ek olarak gönderir (kütüphaneci artifact'ı açamaz;
eksiz artifact bağlantısında yardımcı durur); Google Docs/Drive bağlantıları notta kalır,
kütüphaneci açar.

**0.7.0: `/paylas` anında** (7 Kas kararı). Slack'ten göndermekten hızlı olmalı: Claude belgeyi
açmaz, okumaz, özetlemez, taslak yazmaz ve hiçbir şey sormaz. Tek komut
(`tf_bilgi.py hizli`) dosyaları ve kullanıcının kendi sözlerini (`govde.md`) gelen kutusuna
bırakır, tek satır makbuz verir:

```
Gönderildi ✓ G-ab12cd · rapor.html, ozet.md + not · ekip · kütüphaneci bugün 13:05 turunda dosyalar, alıcılara o zaman haber gider · geri al: /paylas geri-al G-ab12cd
```

Türü, konuyu, başlığı, özeti ve alıcıları kütüphaneci bir sonraki turunda (hafta içi 09:05,
11:05, 13:05, 15:05, 17:05) çıkarır. Makbuz gönderilen dosyaların adlarını söyler (uzunsa
kısaltılır, 3'ten fazlası "+N dosya"). Yol verilmezse bu konuşmanın kendi çıktısı (artifact
HTML, PDF, rapor) `--otomatik` ile gider: yardımcı o zaman yalnız belge benzeri dosyaları
(html/htm, pdf, md, txt, docx, pptx, xlsx, csv, png/jpg/jpeg/gif/webp) kabul eder; kod,
ayar, anahtar, uzantısız ya da `.` ile başlayan dosyada "Hangi dosyayı paylaşacağımı
bilemedim; dosya yolunu yaz: /paylas <dosya> …" der. Açıkça verilen yol her türde çalışır.
"Bu özeti paylaş" denirse o metin Write ile `~/.tf-bilgi/gecici/`'ye yazılıp paylaşılır.
Yol yardımcıda seçilir:

| Kim | Ne olur |
|---|---|
| Depoya yazabilen (push yetkisi; `gh` ile denetlenir, bir gün önbellekte) | GitHub Git Data API ile `main`'e tek commit, klon ve `kb.py` yok: `00-gelen/<YYYYMMDD-HHMMSS>-<kisi>-<kod>/` (dosyalar, `govde.md`, `meta.json`). Arada başka push olursa dal başını yeniden okuyup 3 kez daha dener. Dosya başı 50 MB, toplam 100 MB |
| Yazamayan, gelen kutusu deposuna yazabilen (0.8.0; yalnız ekip) | Aynı tek commit `Teamfluencer-Dev/tf-bilgi-gelen` `00-gelen/`'e; makbuzdaki tur aktarım payıyla (+15 dk) hesaplanır. Geri alma: aktarılmadıysa kayıt kaldırılır, aktarıldıysa (`tasindi/`) geri-al kaydı yazılır |
| Yazamayan, köprü anahtarı olan | Köprüden (en küçük taslak `hizli: true`, `govde.md` ve dosyalar); yalnız ekip alanı |
| Hiçbiri yok | Durur: "GitHub hesabının TF Bilgi gelen kutusuna yazma yetkisi olmalı: Enes'e yaz; o zamana kadar dosyayı Slack'te TF Bilgi botuna DM at" (`gh` kurulu değilse `brew install gh` ve `gh auth login`) |
| `gh` kurulu ama oturum kapalı ya da bağlantı yok (anahtar yoksa; yönetimde bu makinede yazan görülmüşse anahtar olsa da) | "GitHub oturumun kapalı ya da bağlantı yok: `gh auth login` yap, sonra tekrar /paylas." |

Sözlerde tam kelime olarak yönetim, yönetime, "yönetim için", yönetici, yöneticiler,
yöneticilere, C-level ya da `--yonetim` geçerse paylaşım yönetim alanına gider ("hesap
yöneticisi", "proje yöneticisi", "yöneticisine", "yönetim paneli" gibi tamlamalar değil;
köprüde yönetim yok: Slack botuna "yönetim" yazarak gönderilir); "acil", "hemen haber ver"
→ `haber: simdi`. `/paylas geri-al <kod>` yalnız kendi paylaşımını geri alır: yazanın
kaydı henüz `00-gelen/`'deyse tek commit'le kaldırılır ("içerik git geçmişinde durur;
gerekiyorsa Enes'e haber ver"), dosyalandıysa (`arsiv/00-gelen/`) kütüphaneciye geri-al
kaydı yazılır; kod başkasının kaydıysa "Bu kod senin paylaşımın değil." der ve hiçbir şey
yazmaz (kütüphaneci de GOREV 2.G.0'da hedef klasörün `-<gonderen>-<kimlik>` olmasını
şart koşar). Köprü kodları bugünkü gibi köprüden geri alınır. Gizli kip ve PR listesi ayrı başvuru
dosyalarındadır (`skills/paylas/references/`), yalnız açıkça istenince okunur.

0.6.0'dan beri iki yol var (gizli paylaşım, `/toplu-paylas`, `/bilgi`):

| Yol | Kim | Nasıl |
|---|---|---|
| **Köprü** | Köprü anahtarı olan herkes (GitHub hesabı gerekmez) | Taslağı ve dosyaları (gizli `/paylas`, `/toplu-paylas`) TF Bilgi köprüsüne (Google Apps Script web uygulaması) gönderir; köprü onları ortak drive'daki gelen kutusuna yazar, kütüphaneci bir sonraki turunda (hafta içi 09:05–17:05) yeniden tarayıp dosyalar. Okuma, arama, yorum ve tercih de köprüden |
| **Doğrudan** | Anahtarı olmayan, depoya yazma yetkisi olanlar (KB `.kb.json` `yazanlar`) | Bugünkü akış: önbellek klonu, `kb.py`, commit ve push |

Yol `TF_BILGI_YOL` (`kopru` · `dogrudan`) ile zorlanır; yoksa `~/.tf-bilgi/anahtar` varsa
köprü, yoksa doğrudan. Anahtarı olan yazan doğrudan yolu `TF_BILGI_YOL=dogrudan` ile seçer.

### Kurulum (her geliştirici, bir kez)

```bash
claude plugin marketplace add Teamfluencer-Dev/.github && claude plugin install tf-bilgi@teamfluencer
```

Tek satırdır (marketplace zaten ekliyse ilk yarısı "already on disk" deyip geçer). Gerekenler: `gh auth login`
yapılmış olmalı ve GitHub hesabın gelen kutusu deposuna yazabilmeli (Enes ekler).

Köprü yolu için: Python 3.9+ ve TF Bilgi sorumlusunun özel olarak gönderdiği **köprü anahtarı**
(tek satır, `tfb1.` ile başlar). Claude Code'da bir kez `/bilgi kur <anahtar>` yazılır: anahtar
Write aracıyla geçici dosyaya yazılır (kabuk argümanına girmez), köprüyle doğrulanır,
`~/.tf-bilgi/anahtar`'a yalnız sizin okuyabileceğiniz biçimde (0600) kaydedilir ve geçici dosya
silinir. Anahtar kişiye özeldir; köprü yalnız SHA-256'sını tutar, sorumlu geri alabilir.

Doğrudan yol için: git, Python 3.9+, `gh auth login` ve GitHub hesabınızın KB deposuna okuma
yetkisi. **Yazma** (`/paylas`, `/toplu-paylas`, `/bilgi alindi`) için depoya yazma yetkisi
gerekir; 6 Kas 2026'dan beri bu yetki yalnız KB deposunun `.kb.json` `yazanlar` listesindeki
kişilerde. Anahtarı ve yetkisi olmayanda eklenti taslak hazırlamadan durur ve köprü anahtarı
istemesini söyler; anahtar gelene kadar yedek yollar: Slack'teki TF Bilgi botu ya da depoya
yazabilen biri. Okuma (`/bilgi`), bildirim tercihi (`/bilgi tercih`) ve yorum (`/bilgi yorum`,
`/bilgi yorumlar`) okuma yetkisiyle çalışır. Eklenti model çağırmaz, API anahtarı istemez;
`tf-review` ile yan yana çalışır. Kurulum her yapılandırma klasörü (`CLAUDE_CONFIG_DIR`) için
ayrı yapılır.

### Kullanım

```
/paylas ./abonelik.pdf yönetim için; Cuma'ya kadar fiyat kararı lazım
/paylas Ayşe'ye                  # yol yoksa konuşmanın ürettiği son belge (html, pdf, md…; kod/ayar asla)
/paylas bu özeti Mert'e paylaş   # konuşmadaki metin dosyaya yazılıp paylaşılır
/paylas Ayşe ve Mert'ten Cuma'ya merge onayı lazım, hemen haber ver ./plan.pdf
/paylas api#1976 web#689 merge sırası devri   # PR tablosu gh ile kurulur, dosya olarak gider
/paylas gizli: Ayşe'ye, yalnız o görsün ./teklif.pdf   # belge okunmaz, Drive'da paylaşılır
/paylas geri-al G-4k9x2m     # makbuzdaki kod (yazan: GitHub'dan; diğerleri köprüden) ya da kendi girdi kimliğin
/toplu-paylas ~/Desktop/artifaktlar     # klasör dolusu HTML/PDF: tek onay tablosu
/bilgi                       # kuyruğun + son 3 gün
/bilgi son 7
/bilgi konu K-0003
/bilgi ara abonelik
/bilgi oku B-20261105-ayse-01            # tek girdi (köprüde gizli girdi yalnız alıcısına)
/bilgi kur tfb1.…                        # köprü anahtarını bir kez kur
/bilgi alindi B-20261105-ayse-01 Cuma'ya bakıyorum
/bilgi alindi B-20261105-ayse-01 --kisi mert   # yazanlar: yetkisi olmayanın alındısını onun adına
/bilgi tercih                # bildirim kanalın ve çözülüp çözülmediği
/bilgi tercih slack,mail     # tercihini "Bildirim tercihleri" issue'suna yazar
/bilgi yorum B-20261105-ayse-01 Growth için 14.990 bence erken   # belgenin yorum sayfasına (okuma yetkisi yeter)
/bilgi yorumlar B-20261105-ayse-01
```

**Yazma yetkisi olmayanlar: köprü.** 6 Kas 2026'dan beri depoya yalnız `.kb.json`
`yazanlar` listesindekiler ve kütüphaneci yazar. Diğer herkes köprü anahtarıyla Claude
Code'dan `/paylas` der; köprü kaydı Drive gelen kutusuna bırakır, kütüphaneci dosyalar,
girdiyi yazar ve konuya bağlar. Alındı da köprüden: `/bilgi alindi <girdi-id>`. Anahtar gelene kadar yedek
yollar: Slack'teki TF Bilgi botu (`aldım <girdi-id>`) ya da depoya yazabilen biri
(“alındı <girdi-id>”). Eklenti kişi adı vermez, "TF Bilgi sorumlusu" der.

**`/paylas` soru sormaz.** Tek istisna gizli paylaşımdır (Drive adımları, üç onay sorusu ve
kart kalır); `/toplu-paylas` da tek onay tablosunu korur.

**Sır ve kişisel veri paylaşımı engellemez** (7 Kas kararı: özel depo, iç kullanım). Şifre,
token, bağlantı dizesi ya da kişisel veri içeren belge de paylaşılır; `/paylas` belgeyi
taramaz bile. Reddedilen yalnız sistemin kendi kimlik bilgileridir: TF Bilgi köprü anahtarı
(`tfb1.…`; dosyada ya da notta) ve `~/.tf-bilgi` altındaki dosyalar (`gecici/` hariç; oraya
giden bağlantı da). Ret mesajı yalnız dosyanın adını söyler. `gonder` (köprü) pinli
`kb.py` taramasını yalnız `kisisel_veri` etiketi için kullanır. `/toplu-paylas`'ta sırlı
öğe de paylaşılır; yalnız ham dosyası, deponun pinli `kb.py dogrula`'sı `ham/` altındaki
sırrı hâlâ reddettiği için girmez. Ham banka hareketi, kâr tablosu ve maaş listesi kuralı
kütüphanecidedir.

`/paylas` (hızlı) depoya yalnız `00-gelen/` altına yeni bir kayıt klasörü yazar; doğrudan
yolun eski akışı (gizli paylaşım, `/toplu-paylas`, `/bilgi alindi`) yalnız yeni `girdiler/`,
`ham/` ve `onaylar/` dosyalarını commit'ler. Konu dizini, konu sayfaları ve kuyruklar
kütüphanecinindir, eklenti onlara dokunmaz. Köprü yalnız ekip alanını taşır. `pr-listesi`
tablosu `gh` ile (yalnız okuma) PR'ların `claude-review` ve merge durumundan kurulur.

İstek bir ya da birden çok kişiye yöneltilir (`kimden: ayse` ya da
`kimden: [ayse, mert]`); alındı kişi başınadır. Depoya yazma yetkisi olmayan alıcı
aldığını TF Bilgi botuna `aldım <girdi-id>` yazarak (bot yanıt vermezse yazabilen birine
“alındı <girdi-id>” ileterek) bildirir; `yazanlar`'daki biri gerekirse
`/bilgi alindi <girdi-id> --kisi <alıcı>` ile onun adına kaydeder (onay dosyasında
`kaydeden`; KB `dogrula` kaydedenin `yazanlar`'da olduğunu denetler). `haber: hemen`
push'ta her alıcıya anlık mesaj gönderir (hafta içi 08:30–19:00, kişi başı günde en çok 3;
dışında 08:30 özetinde); `haber: simdi` sessiz saati de deler. `tf_bilgi.py bildirim-plani`
(yalnız okur) kime şimdi, kime özette, hangi kanaldan gideceğini ve kime hiçbir şey
gitmeyeceğini adıyla söyler. Kanal tercihi (Slack, mail, WhatsApp; bir ya
da birden çok) KB ekip deposundaki "Bildirim tercihleri" issue'sunda `tercih: kanal=…`
yorumuyla durur; `/bilgi tercih` okur ve yazar.

**Gizli paylaşım** (yalnız açıkça istenince: "gizli", "confidential", "yalnız o görsün",
"kimse görmesin" ya da `--gizli`; yordamı `skills/paylas/references/gizli.md`):
belgenin içeriği hiçbir depoya girmez. Köprü yolunda yalnız taslak (Drive bağlantısı,
alıcılar, istek) gider; sabit girdiyi kütüphaneci yazar ve bağlantıyı açmaz. Eklenti belgeyi açmaz, taramaz,
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

**Yorum sayfaları** (KB `CLAUDE.md` §10.3): her girdinin tartışması KB deposunda bir
GitHub issue'sunda durur (`[<girdi-id>] <başlık>`, etiket `yorum`, gövde girdi bağlantısı ve
TL;DR); sayfa ilk yorumda açılır. `/bilgi yorum <girdi-id> <yorum>` yorumu Write aracıyla
geçici klasöre yazar (kabuğa girmez), `tf_bilgi.py yorum` önce yalnız okuyup kartı kurar
(sayfa var mı, yeni açılacaksa başlığı ve etiketi, kime bildirim gider), onayda yorumu
`kb.py tara` ile tarar (sır ya da kişisel veri bulgusunda yazmaz), sayfa yoksa açar ve
yorumu kişinin kendi `gh` hesabıyla yazar; okuma yetkisi yeter. Etiketi yalnız depoya yazma
yetkisi olan ekler (etiket yoksa oluşturur), öbürleri sayfayı etiketsiz açar. Sayfa başlık
önekiyle bulunur: GitHub araması ve son açılan 100 issue, sonra başlık birebir denetlenir.
Sayfa bulunamadığında ikisinden biri yanıt vermediyse ya da arama eksik döndüyse bir kez daha
bakar; yine emin değilse ikinci bir sayfa açmamak için durur. GitHub girişi `kisiler.json`'daki
hesapla çelişirse durur. Gizli girdiye yorum yazılmaz (sayfa her okuyana açık; `/bilgi
yorumlar` gizli girdide herkese açık sayfa olmadığını söyler); yönetim girdilerinin sayfası
yalnız yönetim deposunda (`eneskrblt/tf-bilgi-yonetim`) olur: `--yonetim` ya da ekip dışı kimlik
(`BY-…`) o deponun sayfalarına gider, yalnız o depoyu okuyabilenler için (doğrudan yol);
diğerlerine ve köprüde "Yönetim yorumları yalnız yönetim deposuna erişimi olanlar içindir."
denir. Yorum hiçbir zaman öbür alanın deposuna yazılmaz. KB'deki
`bildirim.yml` yeni yorumda girdinin yazarına, alıcılarına ve önceki yorumculara bildirir
(kanal, sessiz saat ve pilot aynı; günlük sınır ayrı: kişi başı günde 5 yorum bildirimi, acil
istek bildirimlerinin hakkını yemez); sessiz saatte yazılan yorum ertesi iş günü 08:30 günlük
mesajında çıkar. Kart bildirim için söz vermez: bildirimleri KB'deki Action gönderir, kapalıyken
ya da pilotta gitmeyebilir.

`/toplu-paylas` bir klasörü (ör. claude.ai'den indirilmiş artifact'ler: her alt klasör
bir öğe, `ekler/*.pdf` ayrı öğe, görseller varlık) ya da dosya listesini önce
`kb.py toplu-hazirla` ile `~/.tf-bilgi/gecici/toplu-<zaman>/` altına açar (düz metin,
sır/KVKK taraması, konu adayları, `zaten_var` / `kopya` bayrakları; depoya yazmaz).
Sonra her öğeyi **ekip**, **yönetim** ya da **girmez** diye sınıflar (10'dan fazla
öğede alt ajanlarla, ~15'lik gruplar), tek bir tablo (Ekip / Yönetim / Girmeyenler)
gösterir ve **Onayla / Düzelt / Vazgeç** diye sorar. Onayda her alana tek commit
atılır (köprü yolunda her ekip öğesi ayrı bir köprü kaydı olur). Sır ve kişisel veri öğeyi
engellemez; ham dosya yalnız taranabildiyse, sır bulgusu yoksa (pinli `kb.py dogrula` onu
`ham/`'da hâlâ reddeder) ve dosya 20 MB'tan küçükse depoya girer; kişisel veride öğe
`kisisel_veri: var` olur. Yönetim öğesi hiçbir zaman ekip
deposuna yazılmaz; yönetim deposuna erişim yoksa hazırlık klasöründe kalır.
`--yonetim-yok` yönetim deposunu bu çalıştırmada hiç kullanmaz. KB deposundaki
`kb.py`'nin `toplu-hazirla`'yı bilmesi gerekir (KB `CLAUDE.md` §8.1).

### Ortam değişkenleri

| Değişken | Ne işe yarar | Varsayılan |
|---|---|---|
| `TF_BILGI_KISI` | `kisiler.json`'daki anahtarınız | `gh` hesabınızdan, sonra git e-postanızdan bulunur; `/paylas` bulamazsa durur |
| `TF_BILGI_DIZIN` | Önbellek klonlarının ve `hizli.json`'un (yetki, `kisiler.json`, gönderim geçmişi) klasörü | `~/.tf-bilgi` |
| `TF_BILGI_UZAK_EKIP`, `TF_BILGI_UZAK_YONETIM` | Depo adresi (GitHub `sahip/ad`, git adresi ya da test için yerel yol) | `Teamfluencer-Dev/tf-bilgi`, `eneskrblt/tf-bilgi-yonetim` |
| `TF_BILGI_SURUM_KONTROLU` | `0` → güncel sürüm kontrolü kapalı | açık |
| `TF_BILGI_YOL` | `kopru` ya da `dogrudan`: yolu zorlar | `/paylas`: yazan önce, sonra köprü; diğer komutlar: anahtar varsa köprü, yoksa doğrudan |
| `TF_BILGI_KOPRU_URL` | Köprü adresini ezer (yalnız test; normalde adres anahtarın içindedir) | — |

Önbellek klonunda commit'lenmemiş değişiklik varsa eklenti üzerine çekmez ve durur
(ne yapılacağını yazar). Klonun `.kb.json` alanı beklenenle tutmazsa da durur.

`/paylas` kullanıcının kendi sözlerini Write aracıyla `~/.tf-bilgi/gecici/not-<zaman>.txt`'ye
yazar ve tek satırlık komuta `--not-dosya` ile verir (heredoc yok; stdin yalnız yedek);
gönderimden sonra yardımcı dosyayı siler. Belge ya da not metni hiçbir zaman komuta girmez.
Gizli paylaşım ve `/toplu-paylas` belge metnini kabuk komutuna koymaz: eşleştirme metni,
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

Geçişte `KB_SHA256` eski ve yeni hash'i birlikte taşır; eski hash bir sonraki sürümde çıkar.
0.6.0 geçişi: `kb.py` `haber: simdi` ve `kisisel_veri` alanını öğrendi
(Teamfluencer-Dev/tf-bilgi#5 head `d24c0a4`, sha256 `74ae1f87…`); 0.6.0 eski hash'i
(`e6b4e224…`, 0.4.0) ve yeni hash'i birlikte taşır. Yayın sırası: önce bu
repodaki eklenti PR'ı, aynı gün hemen ardından KB PR'ı. Köprü yolunda `kb.py` köprüden
indirilir (`~/.tf-bilgi/kopru/araclar/kb.py`) ve aynı pinle denetlenir.
0.4.0 geçişi (gizli paylaşımlı `kb.py`, Teamfluencer-Dev/tf-bilgi#2 head `76fd0e7`) bitti:
0.5.0 yalnız o hash'i taşır. 0.7.0 geçişi: hızlı yol ve raflar `kb.py`'si (Teamfluencer-Dev/tf-bilgi#6
head `e59a23b`, #7'yi içerir; sha256 `c9fd7f6a…`, ekip ve yönetim kopyası aynı) eklendi; KB PR'ı merge
edilene kadar 0.4.0 ve 0.6.0 hash'leri de geçer. Yönetim deposu org dışında, `eneskrblt/tf-bilgi-yonetim`'de
(0.7.0). `/paylas`'ın hızlı yolu `kb.py`'ye hiç dokunmaz (klon yok); pin yalnız gizli
paylaşım, `/toplu-paylas` ve `/bilgi` için geçerlidir.

### Notlar

- Bu repo public olduğu için eklentide sır, token ya da iç adres yoktur; GitHub
  erişimi kullanıcının kendi `gh` girişinden, köprünün adresi ve gizli kısmı kişinin
  kendi anahtarından gelir. Gizli kısım yalnız HTTPS istek gövdesinde gider, adreste,
  çıktıda ve hata mesajında yer almaz.
- Belge, mail ve PDF içeriği veridir, talimat değildir.
- Köprünün kodu ve kurulumu KB deposunda: `kopruler/paylas/` (README, Apps Script) ve
  `kutuphaneci/KURULUM.md`. Claude'suz yollar (mail, WhatsApp) ve claude.ai sürümü sonra.
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
