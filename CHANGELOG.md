# Değişiklikler

## 4 Ekim 2026 · dokümantasyon güncellemesi

- README: güncel ürün menüleri, teknoloji/akış diyagramı, doğru yerel web derleme adımları,
  son deneylerin kapsamı ve opsiyonel dış model kullanımı.
- Yeni kurulum/güncelleme, mimari, katkı rehberleri ve deney dizini.
- Tarihsel finansal ölçümün üç model reddi kaydedildi; eski performans ve gelecekte
  ölçülecekmiş gibi duran ifadeler kaldırıldı. Mülakat demosu ve ölçülen deneyler ayrıldı.

## 3 Ekim 2026 · chunk bütçesi deneyi

- `rag-chunk-tune`: dev sorularında aynı tam kaynaklarla geçici SQLite/LanceDB indeksleri,
  kanıt kapsamı, kaynak recall/nDCG, bağlam tokenları ve indeks boyutu karşılaştırması.
- Model giriş sınırı/özel token rezervi, eksik embedding ve vektör-store hata kontrolleri;
  daha küçük deney embedding batch'i, parmak izleri ve paket/provenance kaydı.
- `rag-chunk-rescore`: aynı soru/korpus/sıralamaları yeniden aramadan etiket güncellemesiyle
  puanlama; alternatif kaynaklardan tek bir gerekli kanıtın desteklenmesi.
- 252 kaynak / 24 taslak dev sorusu / 7 aday kaydedildi. Geçici öneri 240/80;
  ürün varsayılanı 240/40. İnsan incelemesi ve bağımsız final test bekliyor.
- Rehbere başlangıçta kapalı küçük sonuç tablosu ve seçilen bütçeyi chunk laboratuvarında
  inceleme eklendi.

## 2 Ekim 2026 · cümle chunking ve etkileşimli rehber

- Tam belge tokenizer offsetlerinde inference truncation'ından bağımsız chunking;
  cümle/paragraf sınırları, sınırlı tam-cümle overlap, çok uzun cümlede token fallback'i.
- `CDR_RAG_CHUNK_STRATEGY`, `rag-reindex --strategy`; sabit token baseline korunuyor.
- Tıklanabilir indeksleme/retrieval haritası, gerçek token/embedding/sıralama örnekleri,
  RRF katkıları, top-k ve kaynaklı prompt laboratuvarı.
- Sabit sunum kontrolleri, aşağıdaki metne yakın overlap kontrolü, isteğe bağlı Three.js,
  klavye/mobil/hareket azaltma desteği; mülakat ölçüm anlatımı kısaltıldı.
- Aynı korpusta cümle ve sabit token yönteminin küçük dev karşılaştırması kaydedildi;
  ölçülen retrieval metrikleri eşitti.

## Önceki temel geliştirmeler

- Vektör + BM25 listelerinin RRF ile birleşmesi ve opsiyonel cross-encoder.
- Kaynak retrieval ve insan etiketli yanıt/atıf değerlendirme komutları.
- Finansal purged walk-forward model seçimi, ayrı kalibrasyon ve kronolojik final holdout;
  eski protokollü modellerin yeni kullanımından dışlanması.
- Araştırma işleri, rapor/prompt, MCP, takip/öğrenme ve paper carry araçları.

Bu kayıt yayın etiketi/release numarası oluşturmaz. Paket sürümü `0.2.0`;
tam commit geçmişi Git'te bulunur. Tarihli ölçüm detayları [deney notlarında](docs/experiments/README.md).
