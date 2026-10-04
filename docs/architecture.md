# Mimari ve veri akışı

## Üç ayrı hat

**Araştırma:** dış veri → 10 analiz modülü → 66 kriter → ağırlıklı skor → yerel rapor/prompt.
**RAG:** haber/analiz/rapor indeksleme → soru için kaynak retrieval → opsiyonel LLM yanıtı.
**Finansal öğrenme:** koşu özellikleri → ileri getiriler → model seçimi → kalibrasyon → holdout.

Araştırma raporu oluşturmak için LLM çağrısı gerekmez. RAG, üretilen raporu daha sonra
sorularda kullanılacak bir kaynak olarak indeksler. RAG retrieval başarısı finansal
yön tahmininin doğruluğunu göstermez.

## Belge geldiğinde

1. Tam kaynak metni ve kimliği SQLite `rag_source_documents` arşivinde tutulur.
2. FastEmbed modelinin tokenizer'ından tam belge offsetleri çıkarılır. Ayrı tokenizer
   kopyasında truncation/padding kapatılır; modelin inference giriş sınırı değiştirilmez.
3. `split_text`, varsayılan 240 token bütçesinde tam cümle/paragrafları sığdırır.
   Sondaki tam cümlelerden en çok 40 token hedefiyle tekrar oluşturulur; sonraki yeni
   cümleye yer açmak için tekrar azaltılabilir. Tek cümle bütçeyi aşarsa token fallback'i kullanılır.
4. Chunk metni ve metadata SQLite'a, metnin embedding'i aynı chunk kimliğiyle LanceDB'ye yazılır.
   Eski aynı-belge chunk'ları yenilenir; tam kaynak reindex için korunur.

Tam kaynak arşivi eski kurulumdan önce kaydedilmemiş metinleri geriye dönük geri getiremez.
Model/tokenizer bulunamazsa ürün kelime offsetleriyle parçalayabilir ve sözcüksel aramayla
devam edebilir. Bu fallback gerçek E5 token bütçesiyle aynı ölçüm değildir.

## Soru geldiğinde

1. İsteğe bağlı coin filtresiyle soru aynı embedding sarmalayıcısına verilir.
2. LanceDB'de vektör yakınlığı ve SQLite FTS5'te BM25 terim sıralaması ayrı alınır.
   Her dal `max(4 × k, 32)` aday ister; ürünün varsayılan `k` değeri 8'dir.
3. RRF, aynı chunk kimliği için sıra katkılarını toplar:
   `RRF(chunk) = Σ 1 / (60 + rank)`; sıralar 1'den başlar.
   Ham BM25 ve vektör uzaklıkları aynı ölçeğe zorlanmaz.
4. `CDR_RAG_RERANKER_MODEL` tanımlıysa yerel cross-encoder birleşik adayları yeniden sıralar.
   Kapalıysa RRF sırası korunur; hata durumunda ürün mevcut retrieval sırasına döner.
5. İlk k chunk, kaynak numarası/tarih/URL ile prompt'a eklenir. OpenRouter anahtarı varsa
   LLM yanıtı oluşturulur; yoksa arama ve prompt kullanılabilir.

RRF chunk düzeyindedir; aynı kaynak birden fazla chunk ile bağlama girebilir. Embedding
veya LanceDB kullanılamazsa hybrid mod yalnız mevcut sözcüksel sonuçlarla ilerleyebilir.
Deney komutu bu durumu başarılı hybrid ölçümü olarak kabul etmez; hata vererek durur.

## Teknoloji sınırları

| Bileşen | Mevcut uygulama |
| --- | --- |
| Model | `intfloat/multilingual-e5-large`; FastEmbed/ONNX, varsayılan 1024 boyut |
| Token sınırı | Kaydedilmiş E5 deneyinde 512 inference tokenı; özel tokenlar dahildir |
| Bütçe | Tam metindeki kaynak offsetleri; bağımsız chunk yeniden token sayımı farklı olabilir |
| LanceDB | Yerel vektör tablosu ve varsayılan arama uzaklığı; kod özel ANN/HNSW indeksi kurmaz |
| SQLite FTS5 | Kalıcı metin indeksi, BM25; tam kaynak arşivi chunk tablosundan ayrıdır |
| LLM | Opsiyonel OpenRouter; kaynaklı prompt hazırlanır, atıf doğruluğu otomatik garanti edilmez |

Chunk boyutunu LanceDB değil, embedding giriş limiti ve retrieval kalite/maliyet dengesi
sınırlar. `rag-chunk-tune` aday bütçesine özel token rezervi ekler ve gerçek bağımsız
chunk girişlerini ayrıca sayar; sessiz model kırpmasıyla deney yapmaz. Bu kontrollerin
tüm ürün ingestion yollarına uygulandığı iddia edilmez.

Mevcut sarmalayıcı metni `model.embed(texts)` ile verir; uygulama katmanında E5
`query:` / `passage:` önekleri eklenmez. Bu seçim için ayrı bir ablation yapılmadı.
Model değişiklikleri veya önek deneyi, yeni indeks ve ayrı dev değerlendirmesi gerektirir.

## Finansal skor ve öğrenme

Heuristik yön yüzdesi `50 + 35 × ağırlıklı skor` formülünden gelir; 5–95 aralığına
kırpılır. Bu sayı tek başına kalibre edilmiş olasılık ya da beklenen isabet değildir.
Kriterler güven/ağırlık/grup faktörüyle toplanır; `partial` yarım ağırlık, `no_data`
sıfır katkıdır. Ayrıntılar [kriter denetiminde](kriter-denetimi.md).

Koşu özellikleri ve 1/7/30 günlük ileri getiri etiketleri SQLite'a kaydedilir.
`separate_calibration_final_holdout_v1` protokolü benzersiz tarihlerde yaklaşık %65/%80
sınırları kullanır; aynı tarihteki coin satırları birlikte kalır. Sınıra değen/aşan
gelecek etiketi purge edilir. Erken dönemde purged walk-forward algoritma seçer,
seçilen model erken dönemde fit edilir; sonraki dönem kalibratörü fit eder. En son
holdout yalnız AUC/Brier/ECE ve ekonomik değerlendirme içindir.

En az 30 kalibrasyon ve 30 holdout satırı gerekir. Kalibrasyon satırı sayısı en az
300 ise izotonik, daha azsa Platt kullanılır. Aktivasyon için holdout'ta en az 200 satır,
AUC en az 0,55 ve baseline'dan düşük Brier gerekir; düşük ekonomik metrikler shadow
durumuna yol açabilir. Son kaydedilmiş [backfill deneyi](experiments/2026-10-backfill-baseline.md)
üç modeli de reddetti. Bu kayıt, her kullanıcı kurulumunun güncel model durumu değildir.

## Rehber ve deneylerin ayrımı

“Nasıl Çalışır?” gerçek backend çağrısı yapmadan kaydedilmiş kurgu örneği açıklar:
910 tokenizer tokenı, yöntem başına gerçek embedding ve dense/BM25 sıraları, browser'da
hesaplanan RRF, değişen top-k ve kaynak numaraları. Retrieval snapshot'ları 240/40'a
aittir; bütçe/overlap kontrolleri chunk laboratuvarını değiştirir. Reranker sırası ve
örnek yanıt öğretim amaçlıdır; LLM çıktısı olarak sunulmaz.

Örneği üretmek için `uv run python scripts/generate_rag_walkthrough.py` kullanılır.
Önbellekteki model gerekir; geçici indeks kurar ve fixture'ı günceller, ürün DB'sine yazmaz.
Chunk deneyinin kısa özeti `scripts/export_chunk_tuning_summary.py` ile ham rapordan
üretilir. Canlı arama veya canlı benchmark yerine kaydedilmiş dev ölçümü gösterilir.

## Kod haritası

| Dizin / dosya | Sorumluluk |
| --- | --- |
| `src/crypto_deep_research/providers/` | Dış veri ve önbellek entegrasyonları |
| `src/crypto_deep_research/analysis/`, `deep_research/` | Modüller, kriterler, skor ve rapor/prompt |
| `src/crypto_deep_research/rag/` | Chunking, embedding, vektör arama, fusion ve değerlendirme |
| `src/crypto_deep_research/storage/` | SQLite kayıtları ve arşivleme |
| `src/crypto_deep_research/learning/` | Özellikler, getiri etiketleri, model/kalibrasyon ve paper deneyleri |
| `src/crypto_deep_research/api/`, `cli.py`, `mcp_server.py` | API, CLI ve MCP girişleri |
| `web/src/ArchitectureExplorer.jsx`, `RagWalkthrough.jsx` | Mimari harita ve laboratuvar |
| `docs/experiments/` | Tarihli yöntem, sonuç, etiket ve sınırlamalar |
