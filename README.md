# Crypto Deep Research

Kripto varlıklar için **tamamen yerel** derin araştırma sistemi. Ücretsiz veri kaynaklarından
66 kriteri değerlendirir; kaynaklı Türkçe rapor ve yapay zekâlara yapıştırmaya hazır prompt üretir.

> Yatırım tavsiyesi değildir. Skor ve olasılıklar araştırma amaçlıdır, kesinlik iddiası taşımaz.
> Örnek çıktı: [`examples/ornek-rapor-BTC.md`](examples/ornek-rapor-BTC.md)

## Ne yapar?

- **10 analiz modülü + 66 kriter** paralel çalışır; her kriter ne araştırdığını, bulgusunu,
  skorunu, güvenini ve kaynağını raporlar.
- Sonuçları tek bir **ağırlıklı skora** ve **yükseliş/düşüş olasılığına** indirger.
- **Yerel RAG** ile haber, analiz ve geçmiş raporlarda anlamsal arama yapar.
- **Web arayüzü, CLI, REST API ve MCP** olarak kullanılabilir.

## Öne çıkanlar

- **Şeffaf kriterler:** her kartta "Ne araştırılır?", bulgu, durum (Tam / Kısmi / Veri Yok),
  skor, güven ve kaynak bilgisi.
- **Çift sayım koruması:** aynı sinyali paylaşan kriterler skorda bir kez sayılır; kısmi veri
  yarım ağırlıkla katkı verir. Böylece aynı teknik skor 7 kez tartılmaz.
- **Dürüst veri:** veri bulunamayan kriter "veri yok" işaretlenir ve ortalamaya katılmaz.
- **Uzun işler arka planda:** canlı ilerleme çubuğu, aşama mesajları ve süre göstergesi.
- **Dayanıklı iş yönetimi:** araştırma işleri SQLite'ta saklanır; sunucu yeniden başlarsa yarım
  kalan iş "hata" olarak raporlanır (404 yerine), aynı anda tek araştırma çalışır.
- **Modern arayüz:** otomatik tamamlamalı varlık arama, interaktif mum grafiği, olasılık
  çubuğu, modül durum paneli, arama/sıralama, Markdown indirme ve yazdırma/PDF.
- **tr-TR sayı biçimi:** 1.234,56; mikro fiyatlar (ör. $0,00000338) kaybolmaz.
- **Skorlama profilleri:** Dengeli / Muhafazakâr / Agresif; kategori ağırlıkları profile göre ölçeklenir.
- **İsabet panosu:** geçmiş koşuların skorları sonraki 1/7/30 günlük gerçek getirilerle karşılaştırılır.
- **Öğrenme döngüsü:** her koşu 66 madde izi + ileri getiri etiketleriyle saklanır; kalibrasyon
  kovaları, model katmanı ve "heuristik/kalibre" etiketiyle şeffaf olasılık sunumu yapılır.
- **Veri hızlandırma:** ilk açılışta 10 major coin otomatik takibe alınır (günlük araştırma) ve
  drift/önbellek/arşiv işleri kendiliğinden çalışır.
- **Karşılaştırma modu:** 2–4 varlık fiyat, momentum ve son skorla yan yana.
- **Takip listesi ve alarmlar:** coinleri takibe alın (günlük otomatik araştırma), fiyat/skor/olasılık
  eşikleri için tarayıcı bildirimi kurun.
- **Portföy:** manuel pozisyonlar canlı fiyatlarla değerlenir; kâr/zarar ve dağılım görünür.
- **İngilizce destek:** prompt dilini seçin; OpenRouter anahtarı varsa raporu tek tıkla İngilizce'ye çevirin.
- **Telegram botu:** `/fiyat`, `/skor`, `/rapor`, `/arastir` komutlarıyla uzaktan kullanım.
- **API anahtarı gerekmez:** tüm temel kaynaklar anahtarsız çalışır; anahtar girilirse oto devreye girer.
- **MCP desteği:** Claude Code, Codex ve Cursor için 12 hazır araç; prompt'u araç içinden çekme (`get_prompt`) ve pipe örnekleri arayüzde.

## Hızlı başlangıç (Docker)

```bash
git clone https://github.com/alikula37/crypto-deep-research.git
cd crypto-deep-research
docker compose build && docker compose up -d
```

- Arayüz: http://127.0.0.1:8000 · API dokümantasyonu: http://127.0.0.1:8000/docs
- Docker yoksa: `brew install colima docker && colima start`
- Veriler `./data` altında kalıcıdır; ilk RAG kullanımında embedding modeli (~2 GB) bir kez indirilir.

### Yerel kurulum (Docker'sız)

```bash
uv sync
cp .env.example .env     # tüm anahtarlar opsiyonel
uv run cdr serve         # web UI + API → http://127.0.0.1:8000
```

Gereksinimler: Python 3.10+ ve [uv](https://docs.astral.sh/uv/). Web geliştirme:
`cd web && npm install && npm run dev`.

## Kullanım

### Web arayüzü

| Sekme | İçerik |
| --- | --- |
| Genel Bakış | Anlık fiyat/mcap, mum grafiği, skor geçmişi, olasılık dağılımı, modül durumları |
| Araştırma Bulguları | 66 kriter: açıklama, bulgu, skor, güven (koşu öncesi tüm kriterler listelenir) |
| İsabet | Geçmiş koşuların 1/7/30 günlük getirilerle isabet oranı, ort. getiri tablosu ve kalibrasyon şeridi |
| Karşılaştır | 2–4 varlık: fiyat, 24s/7g/30g, son skor, olasılık ve beklenen aralık |
| Takip | Takip listesi (günlük otomatik araştırma) + fiyat/skor/olasılık alarmları |
| Portföy | Manuel pozisyonlar: canlı değer, kâr/zarar, portföy payı |
| Rapor | Kaynaklı Markdown raporu (kopyala / indir / PDF; OpenRouter ile EN çeviri) |
| Prompt Çıktısı | Hazır prompt + MCP entegrasyon panosu + OpenRouter ile çalıştırma |
| Kaynak Arama | Yerel RAG araması ve (anahtar varsa) AI yanıtı |
| Rapor Arşivi | Geçmiş koşular, rapor arama filtresi ve Markdown görüntüleme |

Klavye kısayolları: `/` arama alanına git · `?` yardım · `⌘/Ctrl + Enter` derin araştırmayı başlat · `Esc` kapat.

### CLI

```bash
uv run cdr snapshot bitcoin                                      # anlık piyasa özeti
uv run cdr analyze bitcoin --types technical,news,liquidations   # seçili modüller
uv run cdr deep-research bitcoin --platform claude --json        # 66 kriter + rapor + prompt
uv run cdr deep-research bitcoin --profile conservative --lang en  # profil ve prompt dili
uv run cdr search "ETF akışları" --coin bitcoin                  # yerel RAG araması
uv run cdr ask "BTC likidasyon riski nedir?" --coin bitcoin      # RAG + isteğe bağlı LLM
uv run cdr items                                                 # 66 kriter ve açıklamaları
uv run cdr prompt bitcoin --raw                                  # son promptu yazdır (pipe için)
uv run cdr learning-backfill                                     # geçmiş koşulardan özellik çıkar
uv run cdr learning-fill                                         # vadesi gelen getiri etiketlerini doldur
uv run cdr ml-train                                              # model eğit (shadow/aktif kapılı)
uv run cdr ml-backfill-history --coin bitcoin --days 730         # geçmişten eğitim seti üret (extended)
uv run cdr ml-eval --horizon 7                                   # model durumu ve metrikleri
uv run cdr ml-activate <model_id>                                # modeli aktifleştir (kapılı)
uv run cdr ml-cross-section                                      # kesitsel özellikleri hesapla
uv run cdr ml-portfolio --horizon 30 --top-k 3                   # kesitsel portföy backtest'i
uv run cdr learning-drift                                        # drift metrikleri (PSI/ECE)
uv run cdr archive --days 540 [--delete]                         # eski koşuları arşivle
uv run cdr telegram                                              # Telegram botu (token gerekir)
uv run cdr mcp                                                   # MCP server (stdio)
```

Docker içinde çalıştırmak için: `docker compose run --rm app cdr snapshot bitcoin`

### MCP (Claude Desktop / Code, Codex, Cursor)

`claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "crypto-deep-research": {
      "command": "uv",
      "args": ["--directory", "/TAM/YOL/crypto-deep-research", "run", "cdr", "mcp"]
    }
  }
}
```

Araçlar: `list_analyses, list_research_items, resolve_coin, get_market_snapshot, run_analysis,
get_price_chart, deep_research, search_context, list_reports, get_report, get_run`

## Telegram Botu

Opsiyoneldir; BotFather'dan alınan token ile çalışır. Web arayüzündeki **Takip** sekmesinden
tek tıkla başlatılıp durdurulabilir; kalıcı kullanım için:

```bash
export CDR_TELEGRAM_TOKEN="123:ABC..."
uv run cdr telegram              # veya CDR_TELEGRAM_AUTOSTART=true ile sunucuyla birlikte
```

| Komut | Açıklama |
| --- | --- |
| `/fiyat <coin>` | Anlık fiyat, piyasa değeri, 24s/7g değişim |
| `/skor <coin>` | Son derin araştırma skoru ve olasılıklar |
| `/rapor <coin>` | Son raporun metni |
| `/arastir <coin> [dengeli\|muhafazakar\|agresif]` | Yeni derin araştırma başlatır |
| `/yardim` | Komut listesi |

## Öğrenme Döngüsü ve Kalibrasyon

Sistem "tahmin edip unutmaz": her koşu, sonraki getirilerle karşılaştırılabilecek şekilde saklanır.

- **Özellik kaydı:** her derin araştırma koşusunda 66 maddenin skor/güven/durum izleri, kategori
  kompozitleri, kapsam oranı ve **sinyal gücü** (nötr kütle dışlanmış normalize skor) SQLite'a yazılır.
- **İleri getiri etiketleri:** 1/7/30 günlük vade satırları koşu anında açılır; saatlik iş
  Binance kapanışlarıyla (yedek: CoinGecko) doldurur. Vadesi gelmemişler `pending` kalır.
- **Kalibrasyon:** doldurulmuş etiketlerden olasılık kovaları, Beta-binom düzeltmesi ve Wilson
  güven aralıkları üretilir (Brier, ECE, AUC). **n < 100 iken çıktılar açıkça "heuristik" etiketlenir**;
  kalibre olasılık iddiası için Brier'in temel orandan iyi olması şartı aranır.
- **Dürüst sınır:** 1 günlük kripto yönünde gerçekçi bant %48–55'tir; %50'ye yakın değerler düşük
  bilgi içeriğinin yansımasıdır. Amaç sayıyı şişirmek değil, ölçülebilir ve kalibre edilmiş hale getirmektir.
- **Model katmanı (shadow):** yeterli etiket birikince (≥30) L2 lojistik + Platt kalibrasyonu
  purged walk-forward ile eğitilir; **n<200 veya OOS metrikleri geçene kadar asla "aktif" olmaz**.
  Aktif model Brier'in temel orandan iyi ve AUC≥0,55 olması şartına bağlıdır.
- **Tarihsel replay (backfill_v1):** 13 fiyat-türevli kriter her gün için nokta-zamanında yeniden
  hesaplanır (sızıntısız); BTC+ETH 2 yılda ~1.480 örnek dakikalar içinde üretilir. Haber/sosyal
  kriterler geçmişte dürüstçe kurulamadığı için kapsam dışıdır ve `source=backfill` etiketiyle ayrılır.
- **Genişletilmiş replay (backfill_v2):** funding + perp/spot basis + makro (DXY/altın/SPX/10Y/VIX)
  + Fear&Greed + stablecoin arzı da nokta-zamanında eklenir (25 özellik); 10 major coin × 2 yıl =
  **7.400 örnek** ~2 dakikada üretilir.
- **Ablasyon (7g, 7.400 örnek):** taban özellikler (10) AUC 0,5495 · +makro/funding/F&G 0,5289 ·
  +kesitsel (35 özellik) 0,5345. Bu örneklemde ek özellikler sıralama kalitesini düşürdüğü için
  **varsayılan eğitim taban özelliklerle** yapılır (`--features base|base+extended|all`).
- **Algoritma seçimi:** L2 lojistik ve gradyan artırma purged walk-forward OOS'ta yarışır; önce
  sağlık kontrolü (Brier≤temel, ECE≤0,10, net Sharpe>0), sonra AUC üstünlüğü. Kalibrasyon
  n_oos≥300 ise izotonik, değilse Platt. Sağlığı geçmeyen model `rejected` olur ve tahminlerde
  kullanılmaz.
- **Nihai tarihsel tablo (10 coin, 7.400 örnek, OOS):**
  | Ufuk | Durum | AUC | Brier (temel) | ECE | Net Sharpe | Aktif oran |
  | --- | --- | --- | --- | --- | --- | --- |
  | 1g | **rejected** | 0,490 | 0,2493 (0,2492) | 0,004 | 0,26 | %0,5 |
  | 7g | shadow | 0,5495 | 0,2445 (0,2467) | 0,006 | 0,69 | %17 |
  | **30g** | shadow | **0,5777** | 0,2378 (0,2439) | 0,011 | 0,64 | %27 |

  30g modeli ilk kez AUC≥0,55 kapısını geçti; backfill modelleri manuel inceleme gerektirdiği
  için **shadow** kaldı (`cdr ml-activate <model_id>` ile yayına alınabilir). 1g modeli kenar
  bulamadığı için otomatik reddedildi — sistem işlem yapmadığında bunu açıkça söylüyor.
- **Kesitsel portföy backtest'i (`cdr ml-portfolio`):** yalnızca walk-forward OOS tahminleri
  kullanılarak 10 coin arasından modelin en iyi k'sı seçilir; eşit ağırlık ve BTC al-tut ile
  karşılaştırılır (maliyet düşülür). Örnek sonuç (30g, üst-3, aylık, 13 dönem, 10 bps):
  **long-short 1,29x · net Sharpe 1,66 · isabet %77**; üst-3 0,98x; eşit ağırlık 0,61x;
  BTC 0,93x. 7g/haftalıkta fark zayıf (0,32%/dönem). Dönem sayısı az olduğu için sonuç
  **ihtiyatla** yorumlanmalı; asıl kenar 30 günlük sıralamada görünüyor.
- **Kullanım önerisi:** model sıralaması tek başına yatırım kararı değildir; canlı koşular
  biriktikçe (30g etiketi ~1 ay sonra) doğrulama yenilenmelidir.
- **Uyarı:** Backfill örnekleri aynı piyasa günlerini paylaştığı için etkin örneklem daha küçüktür
  ve Sharpe iyimser olabilir; doğrulama canlı koşu birikimiyle yapılır.
- **Drift izleme:** kapsam sapması, skor dağılımı (PSI) ve kalibrasyon hatası (ECE) günlük ölçülür;
  eşik aşımları `drift_metrics` tablosunda alarm olarak işaretlenir ve İsabet sekmesinde görünür.
- **Bakım işleri:** HTTP önbelleği günlük temizlenir, raporlar `cdr archive` ile ayrı SQLite
  dosyasına taşınabilir (türev/öğrenme verisi asla silinmez). Model `ml-activate`/`ml-retire`
  ile geri alınabilir.
- **Yol haritası:** n≈100 L2 lojistik → n≈300 hiyerarşik (coin bazlı shrinkage) → n≈1000 gradyan
  artırma + izotonik kalibrasyon; her geçiş önceden tanımlı kapılarla.

---

## Fonlama Carry (delta-nötr, paper takip)

Piyasa-nötr strateji: long spot + short perp ile fonlama toplanır; fiyat yönü riski yoktur.
Her 3 günde bir, 7 günlük ortalama fonlaması en yüksek 8 coin seçilir (pozitif ve günlük %0,5
tavanın altındakiler), eşit ağırlıkla tutulur. **Hysteresis** (2 bps/gün) mevcut pozisyonları
küçük farklarda korur: turnover ve maliyet duyarlılığı belirgin şekilde azalır.

- 5,5 yıllık test (2001 gün, 2021 boğası + 2022 ayısı dahil, 40 likit kripto perp, 10 bps/bacak):
  **%12,0/yıl getiri, Sharpe 8,5, maksimum düşüş %-2,7**, BTC korelasyonu ~0. Aynı dönemde BTC
  al-tut: %-9,2/yıl, %-76,6 düşüş.
- Maliyet dayanıklılığı: hysteresis olmadan 15 bps/bacakta Sharpe 1,0'a çöker; hysteresis ile
  15 bps'te bile **Sharpe 6,5 / %10,1** ve 10 bps'te Sharpe 8,5 kalır.
- Aşırı fonlama tavanı (günlük %0,5) kuyruk rejimlerini dışlar; tavan olmadan Sharpe 4,4'te kalır.
- Yıllık: 2021 +%18,8 · 2022 −%0,9 · 2023 +%9,1 · 2024 +%17,2 · 2025 +%6,6 · 2026 (kısmi) +%16,4.
  Not: 2025'te fonlama rejimi sıkıştı; edge sağlığı panelde izlenir.
- **Seçim yanlılığı kontrolü (nokta-zamanında evren):** yukarıdaki sayılar bugünün top-40 listesini
  geçmişe uygular. Her gün trailing 30g hacme göre yeniden seçilen PIT evrende sonuç
  **%9,1/yıl, Sharpe 7,3, DD %-1,1**; yalnız köklü coinlerde (≥1300 gün) %5,9/yıl, Sharpe 5,7.
  Canlı paper takip PIT davranışına yakındır; gerçekçi beklenti bu banttır.
  `cdr carry-lab --pit` ile tekrarlanabilir.
- **Edge alarmı:** 30 günlük net carry < %3 (uyarı) / < %1 (kritik) olduğunda arayüzde banner
  gösterilir ve `CDR_TELEGRAM_CHAT_ID` tanımlıysa Telegram bildirimi gider (rejim sıkışması koruması).
- İsteğe bağlı vol hedefleme (hedef %10, max 3x): %36,1/yıl, Sharpe 8,9, DD %-8,0 (örneklem içi;
  kaldıraç öncesi canlı doğrulama önerilir).
- `cdr strategy-scan`: TSMOM/XSMOM/CARRY/BREAK ailelerini aynı maliyetle tarar.
  `cdr carry-lab`: carry varyantlarını uzun vadede karşılaştırır.
- `cdr carry-paper --step`: günlük paper adımı (fonlama geliri, rebalance, PnL; SQLite'ta saklanır).
  `--ranking` canlı fonlama sıralaması, `--reset` sıfırlama.
- Arayüzde **Takip → Fonlama Carry**: equity eğrisi, pozisyonlar, fonlama sıralaması, günlük adım;
  scheduler günde birkaç kez otomatik çalıştırır (aynı gün idempotent).
- Paper takiptir; gerçek emir gönderilmez. Kaldıraçlı kullanım öncesi birkaç haftalık canlı
  doğrulama önerilir.

## REST API

`uv run cdr serve` ile birlikte gelir; Swagger: `http://127.0.0.1:8000/docs`
| Metot | Yol | Açıklama |
| --- | --- | --- |
| GET | `/api/health` | Durum ve tanımlı API anahtarları |
| GET | `/api/analyses` | Analiz modülleri (açıklamalarıyla) |
| GET | `/api/items` | 66 kriter kayıt defteri |
| GET | `/api/coins/search?q=link` | Varlık arama (otomatik tamamlama) |
| GET | `/api/snapshot/{coin}` | Fiyat, mcap, ATH/ATL, global veriler |
| GET | `/api/ohlcv/{coin}?timeframe=1d` | Grafik için mum verisi |
| POST | `/api/analyze` | Seçili analizleri çalıştırır |
| POST | `/api/deep-research/jobs` | Derin araştırmayı arka planda başlatır |
| GET | `/api/deep-research/jobs/{id}` | Görev durumu, ilerleme ve sonuç |
| POST | `/api/rag/search` · `/api/rag/ask` | Yerel RAG araması / AI yanıtı |
| GET | `/api/reports` · `/api/reports/{name}` | Rapor listesi / içeriği |

## Yapılandırma

Tüm ayarlar `.env` üzerinden yönetilir; hiçbiri zorunlu değildir:

| Değişken | Ne sağlar |
| --- | --- |
| `CDR_COINGECKO_API_KEY` | Daha yüksek istek limiti (opsiyonel önerilir) |
| `CDR_COINALYZE_API_KEY` | Gerçek likidasyon geçmişi |
| `CDR_CRYPTOPANIC_API_KEY` | Ek haber kaynağı + sentiment |
| `CDR_ETHERSCAN_API_KEY` | ETH büyük transfer taraması |
| `CDR_FRED_API_KEY` | Faiz, enflasyon, getiri eğrisi |
| `CDR_OPENROUTER_API_KEY` | RAG yanıtı ve rapor üretimini LLM'e devreder |
| `CDR_EMBEDDING_MODEL` | Daha küçük embedding modeli (hız/disk kazancı) |
| `CDR_WATCHLIST_ENABLED` | Takip listesi otomatik koşuları (varsayılan: açık) |
| `CDR_WATCHLIST_INTERVAL_MINUTES` | Zamanlayıcı kontrol aralığı (varsayılan: 60) |
| `CDR_WATCHLIST_AUTO_RUN_HOURS` | Aynı coin için otomatik koşu sıklığı (varsayılan: 24 saat) |
| `CDR_LEARNING_ENABLED` | Özellik kaydı ve ileri getiri etiketleme (varsayılan: açık) |
| `CDR_OUTCOME_INTERVAL_MINUTES` | Etiket doldurma kontrol aralığı (varsayılan: 60 dk) |
| `CDR_WATCHLIST_SEED` | İlk açılışta önerilen coinleri takibe ekler (varsayılan: açık) |
| `CDR_DRIFT_WINDOW_DAYS` / `CDR_DRIFT_BASELINE_DAYS` | Drift penceresi / taban penceresi (30/90 gün) |
| `CDR_CACHE_PRUNE_DAYS` | HTTP önbelleğinde saklama süresi (varsayılan: 7 gün) |
| `CDR_ARCHIVE_RUNS_DAYS` | Arşivleme kesim yaşı (varsayılan: 540 gün) |
| `CDR_TELEGRAM_TOKEN` | Telegram botu tokeni (`cdr telegram` komutu için) |

Anahtarsız çalışan kaynaklar: CoinGecko, Binance/OKX/Bybit, DefiLlama, RSS, GDELT,
alternative.me, Reddit, Google Trends, Blockchain.com, mempool.space, Blockscout, yfinance,
Deribit, GitHub.

## Skorlama

- Her kriter `-1` (güçlü negatif) ile `+1` (güçlü pozitif) arasında skor ve `0–1` güven üretir.
- Formül: `Σ(skor × ağırlık × güven × grup faktörü) / Σ(ağırlık × güven × grup faktörü)`
- Aynı modülü paylaşan kriterler tek sinyal sayılır; `partial` durumdaki kriterler yarım
  ağırlıkla katkı verir; `no_data` kriterler ortalamaya girmez.
- Yükseliş olasılığı: `%50 + 35 × ağırlıklı skor` (5–95 aralığına kırpılır).
- Beklenen fiyat aralığı ATR bazlı oynaklık ve skor yönüyle hesaplanır.

Detaylı gerekçe ve kriter denetim notları: [`docs/kriter-denetimi.md`](docs/kriter-denetimi.md)

## Sınırlamalar

- Bazı kriterler için ücretsiz ve doğrulanabilir veri yoktur (astroloji, patent akışı, X/Twitter
  API'si); bunlar "veri yok" işaretlenir ve skora katılmaz.
- Coinalyze anahtarı yoksa likidasyon geçmişi yaklaşık tahmin edilir.
- TradingView'ün ücretsiz API'si yoktur; yerel teknik derecelendirme vekili kullanılır.
- Ücretsiz API'ler zaman zaman limit uygular (429); önbellek ve yedek kaynaklar devrededir.

## Geliştirme

Tüm testler yerelde çalıştırılır:

```bash
make check        # ruff + pytest + web testleri + derleme (hepsi)
make test         # yalnız Python testleri (pytest)
make web-test     # yalnız web birim testleri (Vitest)
make build        # web derleme
```

GitHub Actions, private repo faturalandırma limiti nedeniyle devre dışıdır; bu yüzden
değişiklikleri push etmeden önce `make check` çalıştırın. Dependabot güncellemeleri haftalık
açılmaya devam eder, birleştirme öncesi testleri yerelde doğrulayın.

Docker diski dolarsa (`no space left on device`): `docker image prune -f` ve
`docker builder prune -af` eski katmanları temizler; veriler (`cdr-state` birimi ve `./data`)
korunur.

## Lisans

MIT

## Haber Arka Uçları

- Coin haber havuzu: RSS (CoinDesk, Cointelegraph TR, Decrypt, The Block...) + opsiyonel CryptoPanic.
- **Konu bazlı kriterler** (jeopolitik, vergi, yerel ekonomi, listeleme, kurumsal...) için
  hedefli **Google News RSS** araması yapılır; sonuç yoksa GDELT yedeği denenir.
- GDELT yoğun 429 verdiği için havuz sorgusundan çıkarılmıştır; yalnızca yedek olarak kullanılır.
- İlk (soğuk) koşu ücretsiz API limitleri nedeniyle daha uzun sürebilir; aynı coin için sonraki
  koşular önbellekle ~2 dakikada tamamlanır.
