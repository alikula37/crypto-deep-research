# 66 Kriter Denetimi ve Skorlama Gerekçesi

Bu doküman, 66 kriterin bağımsız denetimler sonucunda nasıl yeniden değerlendirildiğini ve
skorlama modelinin neden değiştiğini özetler.

## Neden yeniden değerlendirildi?

Dört bağımsız denetimde şu yapısal sorunlar bulundu:

1. **Çift sayım:** `analysis:technical` skoru 6 maddede birebir kopyalanıyordu (1, 7, 14, 15,
   16, 19) ve `analysis:whales` 2 maddede (31, 32). Aynı sinyal efektif ağırlığın ~%24'ünü
   işgal ediyordu.
2. **Alt-dize eşleşme hataları:** `"sec"` → *security*, `"try"` → *country*, `"irs"` → *first*,
   `"fed"` → *federation*, `"war"` → *warning* haberlerini yakalıyordu; 54. madde 25 yanlış
   eşleşmeyle skorlanıyordu.
3. **Ölü/yapısal sıfır maddeler:** cross-chain bridge API'si ücretli (HTTP 402), medya
   manipülasyonu ve pipeline meta skoru her koşuda 0'dı; paydayı şişirip sinyalleri 50'ye
   seyreltiyordu.
4. **Haber gürültüsü:** eşleşmeyen haberler nötr (skor 0) sayılıp ortalamaya giriyordu; tek
   habere dayanan ±1 skorlar üretilebiliyordu; pencere iddiası (7 gün) ile gerçek pencere
   (72 saat) uyuşmuyordu.
5. **Kalibre edilmemiş ağırlıklar:** veri kalitesi düşük maddeler yüksek ağırlıklıydı
   (ör. FRED anahtarsız macro_risk 0.8, tek borsalık sell_pressure 0.8).

## Yapısal değişiklikler

- **Grup skorlaması (`score_group`):** aynı ham sinyali paylaşan kriterler skorda tek sinyal
  gibi ve grubun en yüksek ağırlığıyla sayılır. Teknik grubu: 1, 7, 14, 15, 16, 17, 19.
- **Kısmi veri cezası:** `partial` durumdaki kriterler yarım ağırlıkla katkı verir.
- **Dürüstlük:** veri bulunamayan/ölçülemeyen kriter `no_data` olur ve ortalamaya girmez.
- **Kelime sınırlı eşleştirme:** anahtar kelimeler `\b` sınırıyla aranır; çekim ekleri
  (`-s`, `-es`) desteklenir.
- **7 günlük haber penceresi:** motor haberleri gerçekten 7 gün çeker; örneklem küçükse
  (`< 3 haber`) skor orantılı sönümlenir.
- **Olasılık eğrisi:** `%50 + 35 × skor` (eski 45, gözlenen skor aralığında aşırı iddialıydı).
- **Teknik güven tavanı:** %100'den 0.8'e çekildi.

## Madde değişiklikleri

| Madde | Değişiklik |
| --- | --- |
| 17 TradingView | Teknik modülün kopyası olduğu için teknik grubuna alındı |
| 23 Python (meta) | Skora katılmıyor (ağırlık 0); rapor metası olarak kalıyor |
| 20 AI Tahmini, 25 Astroloji | Ağırlık 0; veri yoksa raporda şeffaf listelenir |
| 32 Balina İzleme | 31 ile aynı kaynak; grupta tek sayılır |
| 38 Off-chain | 18 + 5 bileşkesi; ağırlığı 0.15'e indirildi |
| 45 Cross-chain | Ücretli bridge API'si yerine DefiLlama zincir TVL serisi (ücretsiz) |
| 46 Medya Manipülasyonu | Yön skoru üretmiyor; yalnızca uyarı raporluyor |
| 65 Patentler | Ücretsiz akış yok → "Borsa Listeleme ve Vadeli İşlem Duyuruları" |
| 9, 10, 12, 27, 29, 33, 40, 41, 42, 51, 52, 53, 54, 55, 60, 63 | Anahtar kelimeler sıkılaştırıldı, genel kelimeler çıkarıldı |
| 24 Tarihsel Benzerlik | Hedef sızıntısı giderildi (aday pencereler cari dönemle örtüşmez) |
| 37 Ekonometrik Model | Fiyat seviyesi regresyonu yerine getiri t-istatistiği |
| 45-66 arası diğerleri | Ağırlıklar kanıt gücüne göre yeniden kalibre edildi |

Toplam nominal ağırlık 38.15 → **21.75**; en yüksek ağırlık 1.0, haber toplamı sınırlandı.

## Doğrulama

- `uv run pytest` (65 test) + `ruff` + web Vitest/build temiz.
- Gerçek BTC ve ETH koşularında: motor skoru bağımsız yeniden hesapla birebir eşleşti;
  teknik grup tek kez sayıldı; `no_data` kriterler ortalamaya girmedi; ETH'e özgü dallar
  (anomali, cüzdan büyümesi, madencilik) hata üretmeden `partial`/`ok` döndü.
