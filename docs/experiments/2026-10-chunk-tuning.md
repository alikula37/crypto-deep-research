# Chunk boyutu ve overlap: kanıt kapsamı ile dev seçimi

## Deney tasarımı

3 Ekim 2026 tarihinde yerel arşivin **252 tam kaynağı** tek seferde donduruldu.
Arşiv 100 analiz, 140 haber, 12 rapor ve toplam 163.822 E5 offset tokenı içerir.
[24 dev sorusu](datasets/2026-10-chunk-tuning-dev.jsonl), aday sıralamaları görülmeden
hazırlandı: 8 kısa analiz, 8 haber, 8 uzun rapor. Her soruda ilgili kaynak kimliği yanında
cevabı taşıyan tam kanıt pasajı vardır. Rapor soruları rapor tarihini açıkça belirtir;
analiz/haber/rapor etiketi belli bir arşiv sürümüne aittir.

Etiketler **asistan taslağıdır ve insan incelemesi bekler**. Diğer kaynakların da aynı soruyu
yanıtlayabilmesi insan incelemesinde kontrol edilmelidir. Bu kaynak güdümlü küçük pilot,
gerçek kullanıcı sorularını temsil eden bağımsız başarı ölçümü değildir. Korpus bir kez
okundu; çalışan araştırmaların sonraki değişiklikleri deneye girmedi.

İlk etiket şeması her soru için tek bir kaynağı hedefliyordu. Aynı tam kanıtı aynı coin
filtresi altında taşıyan raporlar da sekiz genel analiz sorusunu yanıtlayabilir. Bu sekiz
kanıt birimine deterministik tam-metin taramasıyla alternatif kaynaklar eklendi; tarihli
rapor sorularının hedefi değişmedi. Eklemeler insan etiketi sayılmaz. İlk
[tek kaynak taslağı](datasets/2026-10-chunk-tuning-dev-single-source.jsonl) saklanır.
Son tablo genişletilmiş taslak etiketlerle, aynı kaydedilmiş sıralamalar yeniden puanlanarak
elde edilir. Soru, korpus, retrieval sırası ve aday ayarları değişmez. İnsan incelemesi
farklı ifadelerle aynı kanıtı taşıyan diğer kaynakları da kontrol etmelidir.

Önceden belirlenen adaylar: `96/16`, `160/27`, `240/40`, `320/53`, `448/75`, `240/0`,
`240/80`. İlk beşte bütçe değişir ve yaklaşık 1/6 overlap hedefi korunur; son iki adayda
240 bütçesi sabitken tekrar hedefi değişir. Cümle sınırlarını koruyan yöntem, gerçek yerel
`intfloat/multilingual-e5-large`, LanceDB, SQLite FTS5 ve RRF hybrid kullanıldı. Reranker ve
LLM kapalıydı. Her aday geçici bir indekse yazıldı; vektör sayısı chunk sayısıyla doğrulandı.

Bağımsız yeniden token sayımı özel tokenlarla birlikte modelin 512 token sınırıyla
kontrol edildi. Tam belgedeki offset bütçesi ile bağımsız inference girişi aynı sayı
olmak zorunda değildir. Büyük adayların gövdesi en çok 448 offset tokenıdır; gerçek giriş
sayısının sınırı aşmadığı ayrıca kontrol edildi.

## Ölçüm ve seçim kuralı

- **Kanıt kapsamı@5:** Sorunun etiketli kanıt pasajlarından kaçının ilk beş chunk içinde
  tek parçada tam olarak bulunduğu. Boşluk farklılıkları normalize edilir. İki eksik chunk
  birleştirilip tam kanıt sayılmaz. Anlamsal yanıt doğruluğu ölçümü değildir.
- **Kaynak Recall / MRR / nDCG:** Gerçek ilk beş chunk içindeki kaynak kimlikleri
  tekilleştirilerek hesaplanır. Aynı kaynağın çok chunk'ı başka kaynaklara ayrılan alanı
  tüketebilir. Kaynak sıralaması için over-fetch kullanan eski pilotla doğrudan kıyaslanmaz.
- **Bağlam tokenları:** Gerçek ilk beş chunk'ın bağımsız E5 token sayımlarının toplamı.
  LLM prompt talimatları, soru ve metadata bu toplama dahil değildir. LLM tokenizer'ı
  farklı olabileceğinden bu sayı ücret değil, aynı deneyde metin miktarı vekilidir.
- **İndeks / süre:** Chunk-vektör sayısı, indeksleme süresi, query embedding dahil sıcak
  arama gecikmesi. Tek geçiş ve tek makine nedeniyle gecikme seçimde kullanılmadı.

Sonuçlar görülmeden seçim kuralı sabitlendi: kanıt kapsamının en iyisinden en çok 0,02
uzak olan adaylar; sonra aynı toleransla kaynak recall, sonra nDCG. Son kalanlar arasında
bağlam tokenı, ardından chunk sayısı en düşük olan seçilir. 2 yüzde puan tolerans bir
maliyet/kalite tercihidir; istatistiksel eşdeğerlik testi değildir. Tek etiketli 24 soruda
bir sorunun değişmesi yaklaşık 4,17 yüzde puandır.

Baseline'a karşı eşleştirilmiş grup bootstrap (2.000 tekrar, seed=37) uygulanır. Aynı
varlığın analiz ve rapor soruları birlikte, haber olayları ayrı gruplanır (16 grup).
Aynı dev verisinde seçim yapıldığı için aralık betimseldir; seçilmiş adayın bağımsız
başarısını veya çoklu deneme düzeltmeli anlamlılığını kanıtlamaz.

## Kaydedilmiş dev sonuçları

[Son rapor](datasets/2026-10-chunk-tuning-results.json), alternatif kaynakları içeren
taslak etiketlerle yeniden puanlandı. Yüzdeler 24 sorunun ortalamasıdır; burada her
soruda bir gerekli kanıt birimi vardır. Overlap bir üst hedeftir: yalnız sığan tam
cümleler tekrar edildiği için gerçek tekrar miktarı daha az olabilir.

| Bütçe / overlap | Kanıt kapsamı@5 | Kaynak recall@5 | nDCG@5 | Ortalama bağlam tokenı | Chunk / vektör |
| --- | ---: | ---: | ---: | ---: | ---: |
| 96 / 16 | %87,50 | %93,75 | 0,9180 | 366,4 | 2.281 |
| 160 / 27 | %95,83 | %95,83 | 0,9180 | 632,0 | 1.398 |
| **240 / 40 · varsayılan** | **%95,83** | **%95,83** | **0,9214** | **857,3** | **990** |
| 320 / 53 | %91,67 | %95,83 | 0,9214 | 1.221,2 | 816 |
| 448 / 75 | %95,83 | %95,83 | 0,9275 | 1.658,7 | 642 |
| 240 / 0 | %100,00 | %95,83 | 0,9215 | 864,0 | 959 |
| **240 / 80 · dev önerisi** | **%100,00** | **%95,83** | **0,9436** | **870,6** | **1.139** |

Donmuş kurala göre **240/80** seçildi. 240/0 da bütün kanıtları buldu; kaynak recall
eşitken nDCG farkı 0,0221 ile 0,02 toleransını geçtiği için ikinci aday elendi.
240/40'a göre kanıt kapsamı **bir soru / 4,17 yüzde puan** arttı; ortalama bağlam
yaklaşık %1,55, vektör sayısı %15,05 arttı. Eşleştirilmiş grup bootstrap'ın %95 aralığı
**0–12,5 yüzde puan**: bu küçük dev ölçümü üstünlük kanıtı değildir. Daha büyük
chunk'ın otomatik olarak daha iyi olmadığı ve bu örneklerde tekrarın zorunlu olmadığı
görülüyor; bunlar genel kullanıcı davranışı sonuçları değildir.

[İlk tek kaynak raporu](datasets/2026-10-chunk-tuning-rankings-single-source.json)
160/27 öneriyordu. Alternatif kaynak etiketleri düzeltilince önerinin değişmesi,
etiket kapsamının karar üzerindeki etkisini gösterir. Bu düzeltme sıralamalara bakıp
aday seçmek için yapılmadı: aynı coin altında aynı tam pasajı taşıyan kaynaklara
deterministik olarak uygulandı. Yine de insan incelemesi gereklidir.

## Tekrar çalıştırma

Ek sınır denetiminde her etiketli pasajın ilgili kaynağın bütün chunk'ları arasında en az
bir parçada tam olarak bulunup bulunmadığı kontrol edildi. 96/16'da Chainlink dominance
pasajı hiçbir chunk içinde tam bulunmuyor; diğer 23 pasaj indekslenebilir. Diğer altı
ayarda 24 pasajın tamamı en az bir chunk içinde var. Bu, sınır nedeniyle kaybı sıralama
nedeniyle kayıptan ayırır; bir kanıtın indekste bulunması ilk beşte getirileceğini garanti etmez.

Tam kaynak snapshot'ı yerel ve git tarafından yok sayılan
`data/experiments/chunk-tuning/sources.json` dosyasındadır. Başka bir kurulumun güncel
arşivi farklıysa aynı skorlar beklenmez; etiketli kanıtın kaynakta bulunması doğrulanır.

```bash
uv run cdr rag-chunk-tune docs/experiments/datasets/2026-10-chunk-tuning-dev.jsonl --sources data/experiments/chunk-tuning/sources.json --output data/experiments/chunk-tuning/new-results.json --embedding-batch-size 32
uv run cdr rag-chunk-rescore docs/experiments/datasets/2026-10-chunk-tuning-dev.jsonl --report docs/experiments/datasets/2026-10-chunk-tuning-rankings-single-source.json --sources data/experiments/chunk-tuning/sources.json --output docs/experiments/datasets/2026-10-chunk-tuning-results.json
uv run python scripts/export_chunk_tuning_summary.py docs/experiments/datasets/2026-10-chunk-tuning-results.json
cd web
npm run build
```

Alternatifleri taslak olarak çıkarmak için `scripts/expand_chunk_evidence_labels.py` kullanılır.
Etiket incelemesinden sonra aynı sorular, kaynak snapshot'ı ve kaydedilmiş sıralamalar
`cdr rag-chunk-rescore` ile pahalı embedding üretimi tekrarlanmadan yeniden puanlanabilir.

İlk ölçüm komutun prototipiyle, FastEmbed'in varsayılan **256 embedding batch** boyutuyla
çalıştı; chunk bütçesi ile batch boyutu farklı ayarlardır. 448/75 indeksleme süresi
39,4 dakika sürdü ve bellek baskısı gözlendi. Bu yüzden komutun yeni varsayılan batch'i
32 oldu; gecikme ya da indeksleme süreleri farklı batch'lerle doğrudan kıyaslanmamalı.
Kaydedilmiş arama gecikmeleri tek sıcak geçiştir; seçimde kullanılmadı.

İlk prototip kaynak SHA'sı, chunk sayıları ve sıralamaları kaydetti; chunk sınırı SHA'sı
ve ilk yürütmenin paket/uygulama SHA'sı yoktur. Yeniden puanlama kaynak SHA'sını ve
chunk sayılarını doğruladı, ancak eski sınır hash'i olmadığından raporda
`all_chunk_layouts_verified=false` yazılır. Bu turda chunker değişmedi. Yeni sweep'ler
chunk sınırı, kod, paket ve batch bilgilerini de kaydeder; rescore kendi kod/paket
bilgilerini kaydeder ve arama/sürelerin tekrar üretilmediğini belirtir.

Varsayılan `k=5` bu araştırma kesimidir; ürünün varsayılan soru-cevap bağlamı `k=8`.
Ürün için nihai seçimde `--k 8` ile de aynı protokol uygulanmalı ve bu seçim bağımsız
sorularda doğrulanmalıdır. Seçim komutu final test sorularını kullanmaz. Eski pilotun
beş final sorusu yeniden ölçülmedi. Üretim varsayılanı **240/40 korunur**; dev adayını
kesin optimum kabul edip otomatik dağıtım yapılmaz.

İnsanlar etiketleri ve alternatif kaynakları kontrol ettikten sonra daha geniş,
kullanıcı sorularını temsil eden dev kümesiyle yeniden seçim yapılmalı. Ayarlar
dondurulduktan sonra yeni ve bağımsız testte retrieval ile yanıt/atıf kalitesi ölçülmeli.
