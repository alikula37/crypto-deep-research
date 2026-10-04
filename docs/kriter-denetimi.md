# 66 Kriter Denetimi ve Skorlama Gerekçesi

Bu doküman, 66 kriterin bağımsız denetimler sonucunda nasıl yeniden değerlendirildiğini ve
skorlama modelinin neden değiştiğini özetler.

Bu bir denetim geçmişidir; aşağıdaki eski test sayısı o denetim turuna aittir.
Güncel kurulum ve kontroller için [README](../README.md) ve
[katkı rehberine](../CONTRIBUTING.md), sonraki kalite ölçümleri için
[deney dizinine](experiments/README.md) bakın.

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

## Tam Madde Tablosu (66/66)

Kararlar: **KEEP** (korundu), **REWEIGHT** (ağırlık değişti), **REPLACE** (yöntem/kaynak
değişti), **REMOVE** (skordan çıkarıldı), **+not** (açıklama/anahtar kelime düzeltmesi).
`Grup` sütunu, skorlamada tek sinyal sayılan `score_group` üyeliğini gösterir.

| No | Kriter | Ağırlık | Karar | Grup | Gerekçe |
| --- | --- | --- | --- | --- | --- |
| 1 | Teknik Analiz | 1.0 → 1.0 | KEEP | teknik | Grup lideri; grup artık tek kez sayılıyor (faktör 0.465) |
| 2 | Temel Analiz | 1.0 → 0.9 | KEEP | — | FDV/mcap ve kilit açılım sinyali sağlam; hafif indirim |
| 3 | Piyasa Duyarlılığı | 0.8 → 0.4 | REWEIGHT | — | F&G + likidasyon + haber skorlarını yeniden tartıyor (çift kullanım) |
| 4 | Sosyal Medya ve Haberler | 0.9 → 0.8 | KEEP | — | Ana haber sentiment kaynağı; güven tavanı 0.7 |
| 5 | Türev Piyasalar | 0.9 → 0.7 | KEEP+not | — | Likidasyon geçmişi yoksa OI/funding ile çalışıyor |
| 6 | Yatırımcı Davranışları | 0.8 → 0.4 | REWEIGHT | — | F&G momentumu 3/22/30 ile korelasyonlu; "borsa giriş-çıkış" iddiası kaldırıldı |
| 7 | İndikatörler | 0.9 → 0.3 | REWEIGHT | teknik | Teknik skorun kopyası; grupta tek sayılıyor |
| 8 | Sektörel Analiz | 0.6 → 0.3 | REWEIGHT | — | Ölü 7g terimi kaldırıldı; coin vs sektör 24s göreli getiri |
| 9 | Regülasyon ve Yasal Durum | 0.7 → 0.5 | KEEP+not | — | Kelime sınırı: "sec" artık security'yi yakalamıyor |
| 10 | Global Jeopolitik Olaylar | 0.6 → 0.3 | REWEIGHT | — | "war"→warning hatası bitti; coine özel örneklem zayıf |
| 11 | Teknolojik İlerlemeler | 0.7 → 0.3 | REWEIGHT | — | `developer_data` açıldı; commit metrikleri artık gerçekten geliyor |
| 12 | Şirket Haberleri | 0.6 → 0.4 | KEEP+not | — | "company" genel kelimesi çıkarıldı; 60 ile örtüşme azaltıldı |
| 13 | Makroekonomik Faktörler | 0.9 → 0.6 | REWEIGHT | — | Sabit güven yerine veri kapsamı; yeni olasılık eğrisiyle dengeli |
| 14 | Mum Formasyonları | 0.6 → 0.15 | REWEIGHT | teknik | Bağımsız skoru yok; teknik grubunda tek sayılıyor |
| 15 | Grafik Formasyonları | 0.7 → 0.2 | REWEIGHT | teknik | Aynı: teknik skorun kopyası |
| 16 | Fibonacci | 0.6 → 0.1 | REWEIGHT | teknik | Seviyeler yalnız özet; skora bağımsız katkı yok |
| 17 | TradingView | 0.5 → 0.2 | REWEIGHT | teknik | Teknik skorun birebir kopyası; gruba alındı |
| 18 | Hacim | 0.9 → 0.7 | KEEP | — | Borsa bazlı likidite derinliği gerçek veri |
| 19 | Destek/Direnç | 0.8 → 0.2 | REWEIGHT | teknik | Teknik grubunda tek sayılıyor |
| 20 | AI Tahmini | 0.3 → 0.0 | REMOVE | — | Anahtarsız doğrulanabilir tahmin yok; raporda şeffaf kalıyor |
| 21 | Fraktal Modeller | 0.5 → 0.4 | KEEP+not | — | Hurst rejimi tutarlı ama tek pencere; küçük indirim |
| 22 | Sosyal Duygu (Twitter/Reddit) | 0.8 → 0.4 | REWEIGHT | — | Twitter iddiası düzeltildi; haber+F&G tekrarı azaltıldı |
| 23 | Python (pipeline meta) | 0.1 → 0.0 | REMOVE | — | Yapısal sıfır; yalnız 10 analizi ölçüyor; rapor metası kaldı |
| 24 | Tarihsel Benzerlikler | 0.7 → 0.2 | REPLACE | — | Hedef sızıntısı giderildi; yöntem doğrulanana dek düşük ağırlık |
| 25 | Astroloji | 0.05 → 0.0 | REMOVE | — | Bilimsel geçerlilik yok; ağırlık 0 (skora katılmıyor) |
| 26 | Google Trends | 0.5 → 0.25 | REWEIGHT | — | Yön tartışmalı (zirve ilgisi tepe işareti olabilir); servis kırılgan |
| 27 | Bitcoin ATM | 0.2 → 0.1 | REWEIGHT | — | "atm"→atmosphere hatası bitti; sinyal zayıf |
| 28 | Madencilik Elektrik Tüketimi | 0.5 → 0.35 | KEEP+not | — | ETH'te BTC hashrate kullanma hatası giderildi |
| 29 | Sektör Liderlerinin Tweet'leri | 0.4 → 0.3 | KEEP+not | — | Tweet değil başlık tonu; "ceo" genel kelimesi çıkarıldı |
| 30 | Kitle Psikolojisi | 0.8 → 0.5 | REWEIGHT | — | F&G ve long/short tekrarı; sinyal tek maddede toplandı |
| 31 | Balinaların Kararları | 0.8 → 0.8 | KEEP+not | whales | Stablecoin tekrarı skordan çıkarıldı; yön yoksa skora girmiyor |
| 32 | Balina İzleme | 0.8 → 0.5 | REMOVE (birleştir) | whales | 31 ile aynı kaynak; grupta tek sayılıyor |
| 33 | Kültürel Etkinlikler | 0.2 → 0.15 | KEEP+not | — | "event/adoption" genel kelimeleri çıkarıldı |
| 34 | Haberlerin Yazılma Hızı | 0.5 → 0.25 | REWEIGHT | — | Yön değil yoğunluk sinyali; yarıya indirildi |
| 35 | Bilimsel Deneysel Modeller | 0.6 → 0.3 | REWEIGHT | — | GARCH yok (EWMA+ATR); çoğu koşuda 0 |
| 36 | Mevsimsel Etkiler | 0.4 → 0.2 | REWEIGHT | — | 1 yılda ay başına tek gözlem; zayıf istatistik |
| 37 | Ekonometrik Modeller | 0.6 → 0.4 | KEEP+not | — | Fiyat seviyesi regresyonu → getiri t-istatistiği |
| 38 | Zincir Dışı Veriler | 0.7 → 0.15 | REWEIGHT | — | 18 + 5'in türevi; çift sayım azaltıldı |
| 39 | Korelasyon Analizi | 0.6 → 0.4 | KEEP+not | — | 90g kısa, p-değeri yok; DXY/VIX tekrarı sınırlandı |
| 40 | Hedge Fon ve Kurumsal | 0.6 → 0.4 | KEEP+not | — | ETF/flow anahtar kelimeleri sıkılaştırıldı; 58 ile örtüşme azaldı |
| 41 | Yerel Ekonomik Faktörler | 0.3 → 0.15 | REPLACE | — | "try/local" genel kelimeleri çıkarıldı; TR'ye özgü terimler |
| 42 | AML Verileri | 0.3 → 0.15 | REPLACE | — | "fine" sıfat eşleşmesi bitti; kelimeler sıkılaştırıldı |
| 43 | Alternatif Varlıklar | 0.5 → 0.25 | REPLACE | — | "Kripto ile karşılaştırma" iddiası kaldırıldı; risk iştahı göstergesi |
| 44 | Volatilite Endeksleri | 0.7 → 0.5 | KEEP+not | — | DVOL artık skora giriyor; veri yoksa `no_data` döner |
| 45 | Çapraz Zincir Verileri | 0.4 → 0.3 | REPLACE | — | Ücretli bridge API → ücretsiz DefiLlama zincir TVL serisi |
| 46 | Medya Manipülasyonu | 0.4 → 0.05 | KEEP+not | — | Yön skoru üretmiyor; yalnızca uyarı raporlar |
| 47 | Sentetik Kıyaslama | 0.7 → 0.2 | REWEIGHT | — | 10 modülü yeniden tartıyor; çift sayım nedeniyle düşürüldü |
| 48 | Psikolojik Seviyeler | 0.5 → 0.25 | KEEP+not | — | Tutarsız eşik mantığı sadeleştirildi; 19 ile örtüşme |
| 49 | Enerji Maliyetleri | 0.4 → 0.2 | REWEIGHT | — | Petrol hem doğrudan hem mining içinde; 28/64 ile çift |
| 50 | Makro Risk Faktörleri | 0.8 → 0.3 | REWEIGHT | — | FRED anahtarsız boş; 13/44 ile çift sayım giderildi; guard eklendi |
| 51 | Topluluk Yönetim Kararları | 0.4 → 0.4 | KEEP | — | Spesifik kelimeler; anahtarsız iyi çalışıyor |
| 52 | Ülkelerin Bitcoin Kararları | 0.5 → 0.2 | REPLACE | — | Alakasız haberle −0.99 skor üretiyordu; sıkı kelimeler |
| 53 | Halk Olayları ve Güvenlik | 0.4 → 0.4 | KEEP+not | — | "risk/security" genel kelimeleri çıkarıldı; hack/breach odaklı |
| 54 | Vergi Mevzuatı | 0.4 → 0.2 | REPLACE | — | "irs"→"first" 25 yanlış eşleşme bitti (kelime sınırı) |
| 55 | Fiziksel Dünya Etkileşimi | 0.3 → 0.15 | REWEIGHT | — | Eşleşmeler "etf"e kayıyordu; 40/27 ile örtüşme azaldı |
| 56 | Blockchain Anomalileri | 0.6 → 0.2 | REPLACE | — | ETH etherscan çökmesi giderildi; yalnız eşik cezası veriyor |
| 57 | Satış Baskısı Tespiti | 0.8 → 0.4 | REWEIGHT | — | Tek borsa anlık order book; Coinalyze bacağı anahtarsız yok |
| 58 | Sermaye Akışları | 0.7 → 0.3 | REWEIGHT | — | Stablecoin/DXY/ETF dört maddede tekrar; guard eklendi |
| 59 | Cüzdan Büyüme Oranı | 0.5 → 0.5 | KEEP+not | — | BTC gerçek; ETH artık `partial` (büyüme serisi ücretsiz yok) |
| 60 | Şirket Blockchain Projeleri | 0.4 → 0.2 | REWEIGHT | — | 12 ile örtüşme; kelimeler kurumsal projeye özelleştirildi |
| 61 | Akıllı Kontrat Analizleri | 0.5 → 0.3 | REWEIGHT | — | TVL skora girmiyor; exploit sentiment ağırlıklı |
| 62 | Stablecoin Rezerv Hareketleri | 0.7 → 0.7 | KEEP | — | Stablecoin sinyalinin tek taşıyıcısı (31/32/58'den çıkarıldı) |
| 63 | Merkez Bankalarının Bakışı | 0.5 → 0.25 | REWEIGHT | — | "fed"→federation hatası bitti; 13/50 ile örtüşme azaldı |
| 64 | Madencilik Taşınmaları | 0.4 → 0.1 | REWEIGHT | — | Bölge verisi ücretsiz yok; 28/49 ile aynı girdi; ağırlık 0.1'e indirildi |
| 65 | Borsa Listeleme Duyuruları | 0.2 → 0.2 | REPLACE | — | Patent akışı ölü → listeleme/vadeli işlem duyuruları |
| 66 | Bitcoin Dominance | 0.7 → 0.4 | REWEIGHT | — | Açıklama fiilî kodla hizalandı; global, coin-bağımsız sinyal |

Özet: 6 madde KEEP, 16 madde KEEP+not, 31 madde REWEIGHT, 9 madde REPLACE, 3 madde skordan
REMOVE (20, 23, 25) ve 1 birleştirme (32). Veri sinyali taşıyan maddeler skorda kalırken, çift
sayım, gürültü ve ölü kaynaklar kalibre edildi; 46 ve 64 bilgi amaçlı çok düşük ağırlıkla kaldı.

## Doğrulama

- `uv run pytest` (65 test) + `ruff` + web Vitest/build temiz.
- Gerçek BTC ve ETH koşularında: motor skoru bağımsız yeniden hesapla birebir eşleşti;
  teknik grup tek kez sayıldı; `no_data` kriterler ortalamaya girmedi; ETH'e özgü dallar
  (anomali, cüzdan büyümesi, madencilik) hata üretmeden `partial`/`ok` döndü.
