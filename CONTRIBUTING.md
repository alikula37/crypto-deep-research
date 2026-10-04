# Katkı ve doğrulama

## Kurulum

```bash
uv sync --frozen --extra dev
npm --prefix web ci
make check
```

`make check`, Ruff, pytest, Vitest ve production web derlemesini çalıştırır.
CI ve Dependabot auto-merge GitHub'da manuel kapalıdır; mevcut workflow dosyalarını
otomatik test geçmişi varmış gibi değerlendirmeyin. Dependabot PR'ları da yerelde
doğrulanmalıdır. Bu doküman iş akışlarını etkinleştirmez.

## Değişiklik hazırlama

- Sorunu, son davranışı ve çalıştırdığınız kontrolleri PR açıklamasına yazın.
- Python değişikliklerinde ilgili hata/kontrat testini; UI değişikliklerinde gerçek
  tarayıcı davranışını, klavye erişimini ve mobil görünümü kontrol edin.
- Bağımlılık değişikliklerinde `uv.lock` / `web/package-lock.json` dosyalarını birlikte güncelleyin.
- `.env`, anahtarlar, DB, tam haber/kaynak snapshot'ları, model önbellekleri ve kullanıcı
  portföy kayıtlarını commit etmeyin. Örnekler sentetik veya açıkça tarihli/etiketli olsun.

## Deney raporlama

Dev ve final test sorularını ayırın; aynı final kümesinde ayar seçmeyin. Korpus sürümü,
model, chunking, retrieval kesimi, etiket durumu ve sınırlamaları sonuçla birlikte yazın.
Kaynak retrieval, yanıt desteği ve finansal tahmin metriklerini birbirinin başarısı olarak
sunmayın. Asistan taslağı etiketleri `human-reviewed` olarak işaretlemeyin.

Kaydedilmiş gerçek deney ile rehberdeki kurgu öğretim örneğini ayırın. Yeni backend
fixture'ını üretip arayüzü değiştirdiğinizde fixture/data kontrat testleri ve build'i
çalıştırın. Protokol için [RAG benchmark rehberi](docs/rag-benchmark.md), kayıtlar için
[deney dizini](docs/experiments/README.md).
