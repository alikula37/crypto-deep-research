# RAG retrieval benchmark'ı

`rag-eval`, insan tarafından etiketlenmiş sorguları kaynak-belge düzeyinde değerlendirir. Güvenilir
bir skor için önce arama yapacağınız yerel korpusu oluşturun (`cdr deep-research bitcoin` veya kendi
belgeleriniz), ardından her sorguya ilgili kaynakların `parent_id` değerlerini verin. Etiketleri
yalnızca benzer kelimelere göre değil, belgenin soruyu yanıtlamak için yeterli kanıt taşıyıp
taşımadığına göre koyun.

Kaydedilmiş pilotlar, chunk ablasyonu ve bütçe çalışması [deney dizinindedir](experiments/README.md).
Bu notlardaki asistan taslağı etiketler insan anotasyonu yerine geçmez. Yeni kurulum,
yerel korpus/DB snapshot'ını otomatik indirmez; kendi kaynaklarınıza uygun etiket gerekir.

## Veri biçimi ve etiketleme

Her JSONL satırında benzersiz bir `id`, sorgu, isteğe bağlı coin filtresi, `dev` ya da `test` ayrımı
ve en az bir ilgili kaynak bulunur:

```jsonl
{"id":"dev-btc-etf-01","split":"dev","query":"Bitcoin ETF akışlarında ne değişti?","coin":"bitcoin","relevant_parent_ids":["news-kaynak-kimligi"]}
{"id":"test-btc-funding-01","split":"test","query":"BTC fonlama oranı piyasa yönü hakkında ne söylüyor?","coin":"bitcoin","relevant_parent_ids":["report-kaynak-kimligi"]}
```

`cdr search "..." --coin bitcoin --json` çıktısındaki `parent_id`, kaynak kimliğidir. Aynı sorunun
parafrazlarını veya aynı haber olayını soran örnekleri farklı kümelere bölmeyin; benzer örnekler
ayar seçimi sırasında final kümeye bilgi sızdırabilir. Mümkünse iki kişi etiketlesin ve anlaşmazlıkları
çözsün. Etiketlenemeyen soruyu benchmark'a eklemeyin.

## Ayar seçimi ve final ölçüm

Varsayılan `sentence` stratejisi cümle/paragraf birimlerini 240 token bütçesinde paketler.
40 token overlap bir üst hedeftir: bütçeye sığan tam son cümleler tekrar kullanılır. Son cümle
hedefi aşıyorsa tekrar sıfır olabilir; yeni cümle sığmıyorsa eski overlap çıkarılır. Tek cümle
chunk bütçesini aşıyorsa token pencerelerine bölünür. Sınır bulma noktalama, paragraf ve yaygın
Türkçe/İngilizce kısaltma kurallarına dayanır; dilbilimsel ya da semantik bütünlük garantisi değildir.

Bütçe ve `token_start`/`token_count`, tam belgenin tokenizer offsetlerine göre hesaplanır.
Kelime içinden bölünen kısa fallback parçalarının bağımsız yeniden tokenizasyonu farklı sayılabilir;
embedding modelinin giriş limiti ayrıca korunur. Sabit `token` stratejisi aynı offsetlerle eşit
pencereler ve kesin token overlap üretir. Cümle yönteminin kaliteyi artırdığı varsayılmaz.

Kalıcı yöntem `CDR_RAG_CHUNK_STRATEGY` ile seçilir. `rag-reindex --strategy ...` yalnız o yeniden
indekslemeyi etkiler; gelecekteki ingestion ortam ayarını kullanır. Karşılaştırmada her yöntem
için hem yeniden indekslemeyi hem evaluation'ı aynı ortam ayarıyla çalıştırın. JSON çıktısındaki
`configured_chunking`, çalışan ayarı gösterir; indeksin gerçekten o ayarla kurulduğunun kanıtı değildir.

```bash
CDR_RAG_CHUNK_STRATEGY=token uv run cdr rag-reindex
CDR_RAG_CHUNK_STRATEGY=token uv run cdr rag-eval data/rag-evaluation.jsonl --split dev --retrieval hybrid --json
CDR_RAG_CHUNK_STRATEGY=sentence uv run cdr rag-reindex
CDR_RAG_CHUNK_STRATEGY=sentence uv run cdr rag-eval data/rag-evaluation.jsonl --split dev --retrieval hybrid --json
```

Sorguları konu ve sorgu türüne göre dengeli biçimde `dev` ve `test` kümelerine ayırın. `dev`, retrieval
ve chunk ayarı seçmek içindir. Ayarları dondurduktan sonra final sayıları `test` ile bir kez raporlayın.
Test sonuçlarına bakıp ayar değiştirilirse o test kümesi artık bağımsız final ölçümü sayılmaz.

```bash
uv run cdr rag-eval data/rag-evaluation.jsonl --split dev --retrieval dense --json
uv run cdr rag-eval data/rag-evaluation.jsonl --split dev --retrieval bm25 --json
uv run cdr rag-eval data/rag-evaluation.jsonl --split dev --retrieval hybrid --json
uv run cdr rag-reindex --strategy sentence --chunk-tokens 160 --overlap-tokens 32
uv run cdr rag-eval data/rag-evaluation.jsonl --split dev --retrieval hybrid --json
uv run cdr rag-eval data/rag-evaluation.jsonl --split test --retrieval hybrid --json
```

`data/` yerel ve git tarafından yok sayılan uygulama verisidir; etiket dosyanızı orada tutabilir ya da
başka bir yolla sağlayabilirsiniz. Benchmark sonuçlarını paylaşırken sorgu kümesinin sürümünü, git
commit'ini, chunk token/overlap ayarlarını, reranker modelini ve `k` kesimlerini kaydedin. Metrikler
retrieval sıralamasını ölçer; üretilen yanıtın doğruluğunu veya kaynak iddialarını desteklediğini tek
başına göstermez.

`--retrieval` üç kontrollü karşılaştırma sunar: `dense` yalnız vektör aramasını, `bm25` yalnız sözcüksel
aramayı, `hybrid` ise iki sıralamanın RRF birleşimini çalıştırır. Reranker ortam değişkeni açıksa her
moddaki adaylara uygulanır; baseline kıyaslamasında kapalı tutun veya sonucu ayrıca raporlayın.
`rag-reindex`, saklanan tam metinlerden indeksin tamamını yeniden kurar. Eski veritabanındaki tam
metin arşivlenmemiş parçaları bir kez birleştirerek kurtarır; sonraki yeniden indekslemelerde tam
kaydedilmiş metni kullanır. Her chunk denemesinde aynı korpusu baştan indeksleyin ve yalnız `dev`
sonuçlarına bakarak ayar seçin.

Chunk sınırları tam metnin tokenizer offsetlerinden çıkarılır. Offset tokenizer'ı embedding
modelinin giriş kırpmasından bağımsızdır; örneğin 512 token inference sınırı, uzun belgenin
sonunu indeksleme öncesinde kesmez. Önceki sürümde indekslenen uzun belgeleri düzeltmek için
`uv run cdr rag-reindex` çalıştırın. Değişen indeksle eski pilot skorlarını yeni ölçüm saymayın;
korpus/indeks sürümüyle birlikte benchmark'ı yeniden çalıştırın.

## Yanıt ve atıf değerlendirmesi

Retrieval doğru belgeyi getirse bile yanıt belgeyi yanlış yorumlayabilir veya desteksiz bir iddia
ekleyebilir. Yanıt örneği üretmek için modeli etkinleştirip `cdr ask "..." --json` çalıştırın. Çıktıdaki
`retrieved_parent_ids` ve `retrieved_sources` alanlarını koruyun; `citation_index`, yanıttaki `[1]`,
`[2]` atıflarının hangi kaynak belgesine karşılık geldiğini gösterir.

Her cevaba 1–5 arasında insan tarafından `answer_relevance` puanı verin (1: ilgisiz, 3: kısmen yanıtlıyor,
5: doğrudan ve yeterli). Cevabı atomik, doğrulanabilir iddialara bölün. Her iddia için `supported`,
getirilen kaynakların iddiayı gerçekten destekleyip desteklemediğini belirtir. Her atıf için ayrıca
`supports_claim` alanı o belirli kaynağın bu iddiayı destekleyip desteklemediğini söyler:

```jsonl
{"id":"answer-btc-01","split":"dev","query":"BTC fonlama oranı ne söylüyor?","answer":"Fonlama pozitifti [1].","answer_relevance":5,"retrieved_parent_ids":["report-abc"],"claims":[{"text":"Fonlama pozitifti.","supported":true,"citations":[{"parent_id":"report-abc","supports_claim":true}]}]}
```

```bash
uv run cdr rag-answer-eval data/rag-answers.jsonl --split dev --json
uv run cdr rag-answer-eval data/rag-answers.jsonl --split test --json
```

`faithfulness`, desteklenen iddia oranıdır. `citation_coverage`, en az bir doğru ve retrieval'da bulunan
atıfı olan iddia oranıdır. `citation_precision`, doğru iddiayı destekleyen ve retrieval sonucunda yer
alan kaynak atıflarının tüm atıflara oranıdır. `answer_relevance` insan puanlarının ortalamasıdır.
Rapor hem cevap başına macro ortalamayı hem tüm iddia/atıfları bir arada değerlendiren micro oranı
verir. Model yargıçları yerine insan etiketleri kullanılır; bu yüzden benchmark boyutu ve etiketleyenler
arası tutarlılık sonuçla birlikte raporlanmalıdır.

## Chunk boyutu seçimi (izole dev deneyi)

`rag-chunk-tune`, çalışan indeksleri değiştirmeden aynı tam metin arşiviyle her ayar için
geçici SQLite + LanceDB kurar. Model/tokenizer bulunamazsa, embedding eksikse veya bağımsız
olarak sayılan bir chunk modelin giriş sınırını aşıyorsa deneyi durdurur; BM25 fallback'i
başarılı bir hybrid deneyi gibi raporlamaz. Model girişi sayımında özel tokenlar da vardır.
Aday bütçesi özel token rezerviyle birlikte sınırı aşamaz; gerçek chunk metinleri ayrıca
yeniden sayılır. Deneyin `--embedding-batch-size` varsayılanı 32'dir: tek model çağrısındaki
metin sayısını sınırlar, chunk token bütçesini değiştirmez.

Boyut seçmek için yalnız belge etiketi yeterli değildir. Her dev sorusuna, cevabı taşıyan
kaynak pasajını da ekleyin. `evidence` öğeleri gerekli ayrı kanıtlardır; hepsinin bulunması
`evidence_complete`, bulunanların oranı `evidence_coverage` olur. Aynı kanıt için alternatif
kaynakları ayrı zorunlu öğeler olarak eklemeyin; tek öğede `alternatives` listesi kullanın.
Bu ölçüm tam metin eşleşmesidir; anlamsal
cevap doğruluğu veya insan faithfulness değerlendirmesi değildir.

```jsonl
{"id":"dev-risk-1","split":"dev","group":"btc-risk","query":"Kaldıraç riski neye bağlı?","coin":"bitcoin","relevant_parent_ids":["report-abc"],"evidence":[{"parent_id":"report-abc","text":"Risk kaldıraç oranına bağlıdır."}],"label_status":"human-reviewed"}
```

Örneğin aynı gerekli iddia iki kaynaktan desteklenebiliyorsa:
`{"alternatives":[{"parent_id":"a","text":"Risk yükseldi."},{"parent_id":"b","text":"Risk arttı."}]}`.
İki kaynak da `relevant_parent_ids` içinde olmalı; tek alternatifin bulunması o iddia için yeterlidir.

`group`, aynı olayın/sorunun parafrazlarını veya ilişkili örnekleri aynı bootstrap grubunda
tutar. Eksik grup, soru kimliğiyle doldurulur. Tüm dev etiketleri indeks denemelerinden önce
hazırlanır. Etiketli pasajın mevcut kaynak sürümünde olmaması bir hatadır; eksik kaynağı
sessizce atlayıp kolaylaşmış bir benchmark üretmez.

```bash
uv run cdr rag-chunk-tune data/rag-chunk-dev.jsonl --output data/chunk-selection.json
# Dondurulmuş tam kaynak JSON'u varsa tüm adaylar aynı snapshot ile yeniden çalışır:
uv run cdr rag-chunk-tune data/rag-chunk-dev.jsonl --sources data/sources.json --output data/chunk-selection.json --candidates 96/16,160/27,240/40,320/53,448/75,240/0,240/80
```

Varsayılan seçim kuralı sonuçlar görülmeden belirlenmiştir: en iyi kanıt kapsamının 0,02
altına kadar adayları tut; sonra kalanlarda kaynak recall ve nDCG için aynı toleransı uygula;
son kalanlarda ortalama bağlam tokenı, sonra indeks chunk sayısı en düşük olanı seç.
Bu eşik işletim tercihidir, istatistiksel eşdeğerlik testi değildir. `--quality-tolerance 0`
ile tam eşitlik istenebilir. Çalışan ayar grid'de yoksa baseline olarak eklenir.

Metrikler **gerçekte prompt'a girecek ilk k chunk** üzerinde hesaplanır. Kaynak kimlikleri
bu liste içinde tekilleştirilir; `rag-eval` komutundaki kaynak sıralaması için over-fetch
burada kullanılmaz. Bu iki raporun skorlarını doğrudan karşılaştırmayın. Bağlam miktarı E5
standalone token sayımıdır; seçilecek LLM tokenizer'ı farklı olabilir, ücret hesabı değildir.
Gecikme sıcak modelle, query embedding dahil tek geçişte ölçülür; gürültülü gecikme ayar
seçiminde kullanılmaz. Ayrı bir yük testi ve LLM yanıt değerlendirmesi yapılmış sayılmaz.

JSON raporu korpus/dev etiketi parmak izlerini, modeli, paket sürümlerini, kod parmak izini,
tüm ayarları, soru başına sonuçları ve baseline'a karşı eşleştirilmiş grup bootstrap aralığını
saklar. Bootstrap aralığı betimseldir: aynı dev verisiyle aday seçilmiş olduğu için bağımsız
başarı veya çoklu denemelere karşı düzeltilmiş anlamlılık kanıtı değildir.

Komut yalnız `dev` sorularını kullanır, final test çalıştırmaz ve üretim ayarını otomatik
uygulamaz. Taslak etiketlerle çıkan seçim bir adaydır. İnsan incelemesi, daha geniş sorgular
ve ayarları dondurduktan sonra yeni bağımsız test gerekir. Onaylanan ayar kalıcı ortam
ayarlarıyla uygulanıp tam metinden yeniden indekslenir:

```bash
CDR_RAG_CHUNK_TOKENS=240 CDR_RAG_CHUNK_OVERLAP_TOKENS=40 CDR_RAG_CHUNK_STRATEGY=sentence uv run cdr rag-reindex
```

Bu ortam değerleri sadece komutun süresince geçerlidir; gelecekteki ingestion için aynı
ayarları uygulamanın `.env` dosyasına yazıp sunucuyu yeniden başlatın. Yeniden indeksleme
sırasında sunucunun araştırma ingestion'ını durdurun. Daha önce ayar seçiminde görülen
sorulara final test adı vermeyin.

Varsayılan tuning kesimi `k=5`'tir; ürünün varsayılan soru-cevap bağlamı `k=8`.
Ürüne uygulanacak seçim için aynı deneyi `--k 8` ile de yapın ve bağımsız sorularda doğrulayın.

İnsan etiket incelemesi arama sırasını değiştirmez. Aynı sorular ve aynı kaynak snapshot'ı ile
`rag-chunk-rescore` kaydedilmiş ilk k sıralamaları yeniden puanlar; embedding/index üretimini
tekrarlamaz. Soru, coin veya kaynak metni değişirse hata verir. Yeni raporlarda tüm chunk
metin/sınırlarının parmak izi de doğrulanır; eski prototip raporunda bu alan yoksa yalnız
chunk sayısı doğrulanabilir ve `all_chunk_layouts_verified=false` açıkça yazılır.

```bash
uv run cdr rag-chunk-rescore data/reviewed-dev.jsonl --report data/chunk-selection.json --sources data/sources.json --output data/reviewed-selection.json
```
