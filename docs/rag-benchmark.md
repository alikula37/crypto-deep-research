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
uv run cdr rag-eval data/rag-evaluation.jsonl --split dev --json
uv run cdr rag-eval data/rag-evaluation.jsonl --split test --json
```

`data/` yerel ve git tarafından yok sayılan uygulama verisidir; etiket dosyanızı orada tutabilir ya da
başka bir yolla sağlayabilirsiniz. Benchmark sonuçlarını paylaşırken sorgu kümesinin sürümünü, git
commit'ini, chunk token/overlap ayarlarını, reranker modelini ve `k` kesimlerini kaydedin. Metrikler
retrieval sıralamasını ölçer; üretilen yanıtın doğruluğunu veya kaynak iddialarını desteklediğini tek
başına göstermez.
