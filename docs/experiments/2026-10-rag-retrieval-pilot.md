# RAG retrieval pilot (2026-10-02)

## Amaç ve kurulum

Dense, BM25 ve RRF hibrit aramayı; ayrıca 240/40 ile 160/32 token/overlap chunk ayarlarını küçük bir
BTC korpusunda karşılaştırdım. Korpus, `uv run cdr deep-research bitcoin --json` komutuyla üretildi
(run ID `9da57e42332c`). İndekste 10 analiz, 96 haber ve 1 rapor olmak üzere 107 kaynak belge;
varsayılan 240/40 ayarında 109 chunk vardı. Embedding modeli `intfloat/multilingual-e5-large` idi.

Sorgular ve beklenen kaynak kimlikleri
[`datasets/2026-10-rag-pilot.jsonl`](datasets/2026-10-rag-pilot.jsonl) içindedir. Küme beş `dev` ve
beş `test` sorgusundan oluşur; her sorgunun bir ilgili kaynak etiketi vardır. Etiketler bu deneyde
asistan tarafından kaynak metinleri incelenerek taslaklandı; bağımsız insan anotasyonu veya etiketleyiciler
arası uyum ölçümü yoktur. Bu yüzden skorlar yalnızca boru hattı ve retrieval davranışı için pilot
sinyalidir; ürün kalitesi, genellenebilir performans veya insan değerlendirmesi iddiası değildir.

Korpusun kendisi kullanıcı verisi olarak `data/` altında kalır ve depoya eklenmez. Bu nedenle başka
bir checkout, aynı kaynakları içeren indeksi kurmadan bu sonuçları birebir yeniden üretemez.

## Dev ablation'ı

Reranker kapalıyken beş `dev` sorgusunda `k=1` ve `k=5` sonuçları:

| Retrieval | HitRate@1 | HitRate@5 | Recall@5 | MRR@5 | nDCG@5 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Dense | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| BM25 | 0.60 | 0.80 | 0.80 | 0.67 | 0.70 |
| Hybrid (RRF) | 0.80 | 1.00 | 1.00 | 0.87 | 0.90 |

160/32 ile yeniden indeksleme 110 chunk üretti. Aynı `dev` sorgularında dense ve hibrit sıralamaları
raporlanan kesimlerde değişmedi; BM25'in MRR@5 değeri 0.67'den 0.65'e, nDCG@5 değeri 0.70'ten
0.69'a indi. Küçük örneklemde yeni chunk ayarı kazanç göstermediği için varsayılan 240/40 korundu.

## Ayrılmış test pilotu

Chunk ayarı tekrar 240/40'a alındı; yalnız hibrit, reranker kapalı olarak beş `test` sorgusu ölçüldü:

| k | HitRate@k | Recall@k | MRR@k | nDCG@k |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 0.60 | 0.60 | 0.60 | 0.60 |
| 5 | 0.80 | 0.80 | 0.70 | 0.73 |
| 10 | 1.00 | 1.00 | 0.73 | 0.79 |

Beş ilgili kaynağın dördü ilk beşte, tamamı ilk onda yer aldı. Test sonuçlarına göre ayar seçilmedi.
Ancak etiketlerin insan incelemesinden geçmemesi, test kümesinin çok küçük olması ve korpusun tek bir
varlık/run'a dayanması, bu sayıları kesin performans sonucu olarak kullanmayı engeller.

## Sınırlar ve sıradaki ölçüm

- Reranker bu deneyde kapalıydı; `CDR_RAG_RERANKER_MODEL` yapılandırılmamıştı. Uygun dil/lisans
  kapsamına sahip bir reranker seçilip insan etiketli `dev` kümesinde ayrıca karşılaştırılmalı.
- OpenRouter anahtarı yapılandırılmadığından model cevabı üretilmedi. `rag-answer-eval` için gerçek
  `cdr ask --json` cevapları ve insan tarafından iddia/atıf etiketleri henüz yok.
- Daha güçlü bir benchmark için farklı coin ve soru türlerini kapsayan daha büyük bir korpus; en az
  iki bağımsız insan anotatörü; anlaşmazlık çözümü; sonra dondurulmuş ayarlarla bir kez ölçülen yeni
  bir test kümesi gerekir.

Komutlar:

```bash
uv run cdr rag-eval docs/experiments/datasets/2026-10-rag-pilot.jsonl --split dev --retrieval dense --json
uv run cdr rag-eval docs/experiments/datasets/2026-10-rag-pilot.jsonl --split dev --retrieval bm25 --json
uv run cdr rag-eval docs/experiments/datasets/2026-10-rag-pilot.jsonl --split dev --retrieval hybrid --json
uv run cdr rag-reindex --chunk-tokens 240 --overlap-tokens 40
uv run cdr rag-eval docs/experiments/datasets/2026-10-rag-pilot.jsonl --split test --retrieval hybrid --json
```
