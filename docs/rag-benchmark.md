# RAG retrieval benchmark'ı

`rag-eval`, insan tarafından etiketlenmiş sorguları kaynak-belge düzeyinde değerlendirir. Güvenilir
bir skor için önce arama yapacağınız yerel korpusu oluşturun (`cdr deep-research bitcoin` veya kendi
belgeleriniz), ardından her sorguya ilgili kaynakların `parent_id` değerlerini verin. Etiketleri
yalnızca benzer kelimelere göre değil, belgenin soruyu yanıtlamak için yeterli kanıt taşıyıp
taşımadığına göre koyun.

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

Sorguları konu ve sorgu türüne göre dengeli biçimde `dev` ve `test` kümelerine ayırın. `dev`, retrieval
ve chunk ayarı seçmek içindir. Ayarları dondurduktan sonra final sayıları `test` ile bir kez raporlayın.
Test sonuçlarına bakıp ayar değiştirilirse o test kümesi artık bağımsız final ölçümü sayılmaz.

```bash
uv run cdr rag-eval data/rag-evaluation.jsonl --split dev --retrieval dense --json
uv run cdr rag-eval data/rag-evaluation.jsonl --split dev --retrieval bm25 --json
uv run cdr rag-eval data/rag-evaluation.jsonl --split dev --retrieval hybrid --json
uv run cdr rag-reindex --chunk-tokens 160 --overlap-tokens 32
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
