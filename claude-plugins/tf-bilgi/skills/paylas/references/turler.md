# Türler ve gövde kuralları (/paylas)

`kb taslak` çıktısındaki gövde (deponun `sablonlar/<tur>.md` dosyası) esastır. Bu
dosya yalnız tür seçimini, uzunlukları ve devir alt şablonlarının ne zaman
seçileceğini anlatır. Şablon ile bu dosya çelişirse şablon kazanır.

## Tür seçimi (8 değer)

| Kullanıcı ne diyor / içerik ne | `tur` | Not |
|---|---|---|
| "geldiğim nokta", durum, ilerleme, haftalık güncelleme | `durum` | `saglik` zorunlu (yesil/sari/kirmizi) |
| PR listesi, merge sırası, "PR'ları devrediyorum" | `pr-listesi` | SKILL.md "PR list mode" |
| devir, "X'e devrediyorum", izin öncesi devir, CS'e değişiklik brifi, hesap devri | `devir` | `istek` zorunlu; alt şablon aşağıda |
| "karar lazım", seçenekler, alınmış karar | `karar` | `istek` zorunlu (alınmış kararda `tip: BILGI`) |
| analiz, rapor, metrik, kök neden, olay raporu | `analiz` | |
| araştırma, rakip, benchmark, pazar taraması | `arastirma` | |
| toplantı notu, görüşme özeti | `toplanti` | |
| nasıl yapılır, adım adım, SOP | `nasil-yapilir` | `birimler/` SOP'larını kütüphaneci türetir; /paylas `birimler/`'e yazmaz |

Kararsız kalırsan: istek bir karar ise `karar`, bir el değiştirme ise `devir`,
ilerleme bildirimi ise `durum`, kalıcı bilgi ise `analiz`/`arastirma`.

## Her türde ilk blok (BLUF)

```
**Sonuç:** <1–2 cümle>
**Senden istenen:** <TIP — kişi ya da kişiler> ya da "Yok, bilgi için"
**Son tarih:** <YYYY-MM-DD> ya da "—"
```

Bu üç satır WhatsApp ya da Slack önizlemesinde tek başına anlaşılmalı: anlık bildirim
(Slack DM / mail) bu satırları alıcıya aynen gösterir. Birden çok alıcıda "Senden
istenen" herkes için doğru olmalı ("Ayşe ve Mert: merge sırasını onaylayın").

## Uzunluk

| Tür | Sınır |
|---|---|
| `durum` | ≤150 kelime, telefon ekranı |
| `devir`, `pr-listesi` | ~150–250 kelime, tek ekran |
| `karar` | Tek ekran + ham bağlantısı |
| `analiz`, `arastirma` | En çok 10 satır özet + "Ayrıntı: ham dosya" bağlantısı |
| `toplanti`, `nasil-yapilir` | Kısa; uzun metin ham dosyada kalır |

Her rakamın yanında kaynağı ve tarihi olur. Belgede olmayan rakam, kişi, tarih yazılmaz.

## `durum`

Sağlık rengi + tek cümle → **Bitti** / **Sırada** / **Senden lazım** → son tarih.

## `karar`

Soru · en az 2 seçenek (maliyet/risk) · öneri · geri dönülebilirlik · karar tarihi ·
karar çıkmazsa ne olur. C-level'a gidiyorsa `dogrulayan` sorulur.

## `devir` — ortak iskelet

1. Sonuç (BLUF).
2. Senden istenen: eylem, sahip, tarih.
3. Şu anki durum ve son girdiden beri ne değişti.
4. Dikkat ve "olursa ne yap".
5. Bağlantılar: Jira, PR, ham dosya (ek yok).
6. Alındı: "Aldığını `/bilgi alindi <id>` ile ya da tek satırla bildir." Birden çok
   alıcıda alındı kişi başınadır: istek, her alıcı alındı deyince kapanır. Depoya yazma
   yetkisi olmayan alıcı aldığını köprü anahtarıyla yine `/bilgi alindi <id>` diyerek
   bildirir (kütüphaneci kaydeder); anahtarı yoksa Slack'teki TF Bilgi botuna "aldım <id>"
   yazar ya da “alındı <id>”yi deponun `yazanlar` listesindekilerden birine yazar, o
   `/bilgi alindi <id> --kisi <alıcı>` ile onun adına kaydeder (onay dosyasında `kaydeden`).

Alt şablonu kitleye göre seç: depoda `sablonlar/devir-cs-degisiklik-brifi.md` ve
`sablonlar/devir-hesap-devri.md` olarak durur; `kb taslak --tur devir --sablon
devir-cs-degisiklik-brifi` (ya da `devir-hesap-devri`) onu basar. Aşağıdaki
listeler o şablonların özetidir; iskeletin 3–4. maddelerinin yerine geçer:

### `cs-degisiklik-brifi` (ürün → CS/ops)

- Müşteri için ne değişiyor (müşteri diliyle)
- Ne zamandan beri / ne zaman
- Kim etkileniyor (paket, segment)
- Yapıştırmaya hazır müşteri mesajı (TR; gerekiyorsa EN)
- Söylenmeyecekler
- 3 olası soru ve cevabı
- Yükseltme yolu (CS talebi teknik ekibe kimin üzerinden gider)

Adım adım SOP gerekiyorsa ayrı bir `nasil-yapilir` girdisi olur (numaralı adım + ekran görüntüsü yolu).

### `hesap-devri` (satış → CS)

- Müşteri ve paket
- Söz verilenler (tarihli)
- Beklentiler ve hassasiyetler
- Kişiler: tercihen rolle; ad, telefon ya da e-posta gerekiyorsa yazılır ve girdi
  `kisisel_veri: var` olur (kişisel veri engellenmez, maskelenmez)
- Kırmızı bayraklar
- İlk CS temas tarihi
- CRM kaydı bağlantısı

## `pr-listesi`

Tablo (SKILL.md "PR list mode") + **Nasıl doğrulanır** + **Bilinen tuzaklar**. Tek ekran.

## Gizli (`gizli: true`, SKILL.md "Gizli mode")

Belge okunmaz, depoya girmez; Drive'da yalnız alıcılarla paylaşılır. Gövde, `tldr`,
`ham` ve `ham_notu` `kb taslak --gizli`'nin bastığı sabit metindir ve elle değişmez
(`kb dogrula` birebir denetler; köprü yolunda bu sabit girdiyi kütüphaneci yazar). Burada yalnız tür seçimi geçerlidir ve yalnız
kullanıcının kendi sözlerinden yapılır, belgeden değil:

| Kullanıcı ne diyor | `tur` | `--istek-tip` |
|---|---|---|
| "karar lazım", "onayla" | `karar` | `KARAR` (varsayılan) |
| "devrediyorum", "sende" | `devir` | `EYLEM` (varsayılan) |
| "bak / incele / yorumla" | `analiz` | `INCELE` |
| yalnız "gönderiyorum", "bilgin olsun" ya da belirsiz | `analiz` | `BILGI` (varsayılan) |

Başlık varsayılan "Gizli belge"dir; kullanıcı açıkça "başlık görünsün" demedikçe
belgenin adı ya da konusu başlığa yazılmaz. Konu yalnız kullanıcı bir konu
kimliği verirse değişir, yoksa `GIZLI` kalır.
