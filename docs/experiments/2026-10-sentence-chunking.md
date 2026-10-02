# Cümle sınırlarını koruyan chunking: dev karşılaştırması

2 Ekim 2026 tarihinde aynı yerel kaynak arşivinden iki ayrı geçici indeks
oluşturuldu. Sabit token penceresi ile cümle sınırlarını koruyan yöntem, aynı
240 token bütçesi ve 40 token overlap hedefiyle karşılaştırıldı.

| Yöntem | Kaynak | Chunk | Dense HitRate@5 | BM25 HitRate@5 | Hybrid HitRate@5 | Hybrid MRR@5 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Sabit token | 170 | 473 | 0.60 | 0.60 | 0.60 | 0.50 |
| Cümle sınırları | 170 | 483 | 0.60 | 0.60 | 0.60 | 0.50 |

Bu beş dev sorusunda ölçülen retrieval metrikleri aynı çıktı. Yeni yöntemin
arama veya yanıt kalitesini artırdığı sonucuna varılmadı. Varsayılanı
değiştirme gerekçesi, bütçeye sığan cümlelerin birlikte tutulmasıdır.

## Protokol

- Tam kaynak arşivi bir kez okundu; iki yöntem aynı metinlerden beslendi.
  Kaynak kimlikleri ve metinlerinin sıralanmış JSON gösteriminin SHA-256 değeri
  sonuç dosyasında bulunur. Kaynak metinleri bu nota eklenmedi.
- SQLite ve vektör depoları geçici dizinlerde oluşturuldu; bu karşılaştırma
  ürünün indeksini değiştirmedi. Her yöntem için vektör sayısının chunk sayısına
  eşit olduğu doğrulandı.
- Aynı `intfloat/multilingual-e5-large` modeli, gerçek yerel embedding'ler,
  dense / BM25 / RRF hybrid arama kullanıldı. Reranker kapalıydı.
- [Pilot veri setinin](datasets/2026-10-rag-pilot.jsonl) yalnızca beş `dev`
  sorusu kullanıldı; final `test` soruları açılmadı. Etiketler mevcut asistan
  taslağıdır, insan kalite etiketi değildir.
- Mevcut `evaluate_retrieval` ile k=1, 5, 10 ölçüldü. İlgililik kaynak belge
  kimliğine göre değerlendirilir; tek tek pasajların tamlığı ölçülmez.
- [Ham sonuç](datasets/2026-10-sentence-chunking-ablation.json) bütün metrikleri,
  belge sayısını, model adını, bütçeyi ve korpus parmak izini içerir.

## Yorum ve sınırlar

170 kaynaklı bu korpus, önceki 107 kaynaklı pilotla aynı değildir. Önceki
pilotun final skoruyla burada verilen dev skorunu doğrudan kıyaslamayın.
Beş soru ve taslak etiketler, küçük farkları ayırt etmeye yetmez. Faithfulness,
atıf doğruluğu, gecikme ve maliyet için bu çalışmada sonuç üretilmedi.

Yeni yöntemde 40 overlap bir üst hedeftir: tekrar, yalnız bütçeye sığan tam
cümlelerden oluşur ve sıfır olabilir. Bütçeyi aşan cümle token parçalarına
bölünür. Cümle sınırları noktalama ve paragraf sezgiseliyle belirlenir; semantik
chunking modeli kullanılmaz. Token sayısı tam belgenin offsetlerine aittir;
çok küçük fallback parçalarının bağımsız yeniden token sayımı farklı olabilir.

Öğretim sayfasındaki 910 tokenlık kurgu belge bu gerçek korpustan ayrıdır.
Sayfada her iki yöntem için arama sonuçları ayrıca hesaplanmıştır; yeniden
sıralama ve örnek yanıt öğretim için yazılmıştır. Kurgu sahnenin sonucu genel
başarı ölçümü olarak sunulmaz.
