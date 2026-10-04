# Deney dizini

Bu dizin **kaydedilmiş tarihsel ölçümleri** içerir; çalışan ürünün güncel korpusu veya
anlık başarı panosu değildir. Korpuslar farklı olduğu için deneyler arasında doğrudan
skor karşılaştırması yapılmaz. Tam kaynak snapshot'ları/DB'ler yerelde kalır ve klona dahil değildir.

| Tarih | Deney | Soru / veri | Sonuç ve yorum |
| --- | --- | --- | --- |
| 2 Ekim 2026 | [Retrieval pilotu](2026-10-rag-retrieval-pilot.md) | 107 kaynak; 5 dev + 5 test sorusu | Hybrid test HitRate@5 4/5; asistan taslağı etiketler |
| 2 Ekim 2026 | [Cümle chunking ablasyonu](2026-10-sentence-chunking.md) | 170 kaynak; 5 dev sorusu | Sabit token / cümle metrikleri eşit; kalite kazancı gösterilmedi |
| 3 Ekim 2026 | [Bütçe/overlap seçimi](2026-10-chunk-tuning.md) | 252 kaynak; 24 dev sorusu; 7 ayar | 240/80 geçici öneri; 240/40 ürün varsayılanı korunuyor |
| 2 Ekim 2026 | [Finansal backfill baseline](2026-10-backfill-baseline.md) | 7.400 satır; ayrı kalibrasyon ve holdout | Üç ufuk da baseline Brier'ı geçemedi; model aktifleştirilmedi |

## Dosyalar ve yeniden üretim

- Retrieval pilotunun [taslak dev/test etiketleri](datasets/2026-10-rag-pilot.jsonl).
- Cümle yönteminin [ham ablation raporu](datasets/2026-10-sentence-chunking-ablation.json).
- Chunk seçiminin [son taslak dev etiketleri](datasets/2026-10-chunk-tuning-dev.jsonl)
  ve [yeniden puanlanmış sonucu](datasets/2026-10-chunk-tuning-results.json).
- Etiket düzeltmesinin izi: [ilk tek-kaynak etiketleri](datasets/2026-10-chunk-tuning-dev-single-source.jsonl)
  ve [ilk rapor/sıralamalar](datasets/2026-10-chunk-tuning-rankings-single-source.json).

Chunk seçiminde aynı tam kanıtı aynı coin altında taşıyan alternatif kaynaklar deterministik
olarak eklendi; bunlar insan anotasyonu değildir. Önceki 160/27 önerisinin 240/80'e
değişmesi etiket kapsamının etkisini gösterir. Sorular ve retrieval sıraları değişmedi.
240/0 da bütün kanıtları buldu; nDCG aşaması 240/80'i öne çıkardı. Farkın bootstrap
aralığı sıfırı içerir; kesin üstünlük veya optimum iddiası yoktur.

Sonuçları aynı kaynak sürümü olmadan yeniden üretmek beklenmez. Protokol, korpus SHA'sı,
etiket durumu, kullanılan yöntem ve ilk prototipin eksik provenance alanları ilgili
notlarda açıklanır. Yeni kaynaklarla çalışırken kanıt pasajları ve kaynak kimlikleri yeniden
etiketlenmelidir; eski `test` soruları ayar seçimine taşınmamalıdır.

## Kalan kalite çalışmaları

İnsan etiket incelemesi ve alternatif destek kaynaklarının tamamlanması; temsil gücü daha
yüksek dev soruları; ürünün `k=8` bağlamında bütçe ölçümü; ayarlar dondurulduktan sonra
yeni bağımsız test; gerçek yanıtlar üzerinde faithfulness/atıf etiketleri gerekiyor.
Reranker ve E5 giriş önekleri için ayrı ablation henüz yok. Finansal özellik/algoritma
değişiklikleri için yeni dokunulmamış final dönem gerekir.

[RAG etiketleme ve komut protokolü](../rag-benchmark.md) · [Mimari](../architecture.md).
