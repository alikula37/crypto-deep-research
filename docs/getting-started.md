# Kurulum, kullanım ve güncelleme

## Yerel kurulum

Python 3.10+, uv ve Node.js 22.12+ kullanın. Frontend bağımlılığı Vite 8'in
Node sınırı `^20.19.0 || >=22.12.0`; aşağıdaki kurulum 22.12+ varsayar.

```bash
git clone https://github.com/alikula37/crypto-deep-research.git
cd crypto-deep-research
uv sync --frozen
cp .env.example .env
npm --prefix web ci
npm --prefix web run build
uv run cdr serve --host 127.0.0.1 --port 8000
```

Sunucu terminalde çalışır; `Ctrl+C` durdurur. Arayüz [8000 portunda](http://127.0.0.1:8000),
Swagger [docs adresinde](http://127.0.0.1:8000/docs),
rehber [mülakat modunda](http://127.0.0.1:8000/?tab=how&mode=interview) açılır.
Sağlık kontrolü:

```bash
curl --fail http://127.0.0.1:8000/api/health
```

Sağlık yanıtı sunucunun yanıt verdiğini gösterir; bütün dış sağlayıcıların, embedding
modelinin veya RAG kalite ölçümünün başarılı olduğunu kanıtlamaz. Anahtar alanları
değerleri değil, tanımlı olup olmadıklarını bildirir.

### Eski yerel sürümü çalıştırmayı önleme

Bu kurulum GitHub `main` kaynak kodunu ve checkout'un `uv.lock` dosyasını kullanır.
Global `pip`/`pipx` ortamındaki çıplak `cdr` komutu farklı bir kurulum olabilir;
depo kökünde `uv run cdr` kullanın. Repo dışından başlatırken proje yolunu açıkça seçin:

```bash
uv run --project /TAM/YOL/crypto-deep-research cdr serve
```

Python paketi sürüm numarası tek başına güncel commit'i göstermez. Yüklenen modül yolunu,
son commit'i ve üretilmiş arayüzü kontrol edin:

```bash
git log -1 --format='%h %s'
uv run python -c 'import crypto_deep_research; print(crypto_deep_research.__version__); print(crypto_deep_research.__file__)'
```

Modül yolu bu checkout'un `src/crypto_deep_research` dizinine işaret etmelidir. Eski
terminalde çalışan sunucu yeni dosyalardan bağımsız olarak eski kodu bellekte tutabilir;
güncelleme sonrası sunucuyu yeniden başlatın. Eski `web/dist` de eski ekranı sunar;
`npm --prefix web run build` adımını atlamayın. Güncellenmiş rehberde tıklanabilir mimari
ve “Boyutu nasıl seçiyoruz?” paneli bulunur.

İlk açılışta 10 coin takibe alınabilir ve otomatik araştırmalar başlayabilir.
Yalnız elle kullanım için `.env` içinde `CDR_WATCHLIST_ENABLED=false` ve
`CDR_WATCHLIST_SEED=false` seçin. OpenRouter anahtarı olmadan araştırma, rapor,
prompt ve arama kullanılabilir; LLM yanıtı yerine prompt gösterilir.

## İlk araştırma ve RAG kullanımı

1. Arayüzde bir coin seçip **Derin Araştırma** başlatın. İş ilerlemesi ekranda görünür.
2. **Araştırma → Bulgular** içinde skor, güven ve veri durumunu; **Üretim → Rapor**
   içinde yerel olarak oluşturulan Markdown çıktısını inceleyin.
3. **Arşiv → Kaynak Arama** üzerinden arşivlenen haber, analiz ve raporlarda soru sorun.
   Boş arşivden kaynak getirilemez; yeni kurulum geçmişte ölçülen deney korpusunu içermez.
4. **Rehber → Nasıl Çalışır?** ürün akışını gösterir. Laboratuvar ayarları gerçek ürün
   konfigürasyonunu veya indeksini değiştirmez.

CLI karşılığı:

```bash
uv run cdr deep-research bitcoin --platform claude
uv run cdr search "ETF akışları" --coin bitcoin --json
uv run cdr ask "Bitcoin türev piyasasındaki risk nedir?" --coin bitcoin --json
```

İlk model yüklemesi/indirmesi ve API kotaları araştırmayı uzatabilir. Model indirilemiyorsa
ürün BM25 ile devam edebilir; bunun dense/hybrid kalitesiyle aynı olduğu varsayılmaz.

## Docker

Depo kökünde:

```bash
docker compose up -d --build
docker compose logs --tail 50 app
docker compose run --rm app cdr snapshot bitcoin
docker compose stop app
```

Docker web derlemesini de yapar. `.env` opsiyoneldir. Compose kalıcı veriyi iki yerde tutar:

| Konum | İçerik |
| --- | --- |
| `./data/reports`, `./data/prompts` → `/data/...` | Host ile paylaşılan çıktı dosyaları |
| `cdr-state` adlı Docker volume → `/state` | SQLite, LanceDB ve model önbellekleri |

Dolayısıyla Docker verisinin tamamı host `./data` dizininde değildir. Yerel kurulumda
varsayılan SQLite `data/crypto.db`, vektörler `data/vectors` altındadır.
`CDR_STATE_DIR` belirtilirse bu iki depo oraya taşınır; rapor/promptlar `CDR_DATA_DIR` kullanır.
Yedekleme için sunucuyu durdurup state dizinini/volume'u ve çıktı dizinlerini birlikte koruyun.

## Mevcut kurulumu güncelleme

Sunucuyu durdurun; yerel değişikliklerinizi önce kontrol edin. `.env` ve `data/` dosyalarınızı
koruyun. `--ff-only`, farklılaşmış yerel geçmişi sessizce yeniden yazmaz:

```bash
git status --short
git switch main
git pull --ff-only origin main
uv sync --frozen
npm --prefix web ci
npm --prefix web run build
uv run cdr serve
```

`git status` yerel değişiklik gösterirse önce bunları koruyun; `reset --hard` kullanarak
silmek gerekmez. Başka bir geliştirme dalındaki işiniz varsa `main` güncellemesiyle
karıştırmayın. Güncel commit kontrolü için `git rev-parse HEAD` ve
`git rev-parse origin/main` aynı olmalıdır (yukarıdaki fetch/pull sonrasında).

Docker kurulumu için güncel checkout üzerinde `docker compose up -d --build` yeterlidir.
Tarayıcıyı yenileyin. Chunking veya embedding modeli değişmişse yeni ortam ayarlarını
eşleştirip araştırma ingestion'ı duruyorken tam kaynaklardan yeniden indeksleyin:

```bash
uv run cdr rag-reindex --strategy sentence --chunk-tokens 240 --overlap-tokens 40
```

CLI ayarı yalnız bu reindex için geçerlidir; kalıcı ingestion ayarı `.env` içindedir.
Dev önerisi 240/80 henüz üretim varsayılanı değildir.

## Geliştirme ve sorun giderme

Backend ve geliştirme UI'ı ayrı terminallerde:

```bash
uv sync --frozen --extra dev
uv run cdr serve --reload
```

```bash
npm --prefix web ci
npm --prefix web run dev
```

Vite `http://localhost:5173` üzerinde çalışır ve `/api` isteklerini backend'in 8000 portuna
iletir. `make check` tüm yerel kontrolleri çalıştırır.

| Belirti | Kontrol |
| --- | --- |
| 8000 bağlantısı reddediliyor | `uv run cdr serve` terminalinin açık ve Uvicorn'un dinliyor olduğundan emin olun; Docker'da `docker compose ps` |
| API açık, ana sayfa yok | `npm --prefix web run build` ile `web/dist` oluşturun, backend'i yeniden başlatın |
| Değişiklik ekranda görünmüyor | Production build'i yenileyin ve tarayıcıyı yeniden yükleyin |
| Arama boş | Önce bir araştırma oluşturun; coin filtresini ve `/api/rag/stats` çıktısını kontrol edin |
| Embedding indirilemiyor | Ağ/model erişimini ve logları kontrol edin; gerekirse `CDR_EMBEDDINGS_ENABLED=false` ile yalnız BM25 kullanın |
| API 429 veya kısmi veri | Sağlayıcı kotası/erişimi; veri durumu ve kaynak bilgilerini inceleyin |
| Port kullanımda | Çalışan servisi kullanın veya `cdr serve --port 8001`; Vite proxy'si varsayılan olarak 8000'i kullanır |

Tam CLI listesi `uv run cdr --help`; komut seçenekleri `uv run cdr <komut> --help`.
