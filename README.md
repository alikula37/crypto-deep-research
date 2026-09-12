# Crypto Deep Research

Kripto paralar için **yerel RAG + 66 maddelik deep research** sistemi. NotebookLM benzeri bir
yapı: seçili coinler için ücretsiz veri kaynaklarından veri toplar, analiz eder, kaynaklı rapor
üretir ve hariçi AI'lara (Claude, Codex, ChatGPT...) yapıştırılabilecek detaylı Türkçe prompt
oluşturur.

> Bu sistem yatırım tavsiyesi değildir. Üretilen skor ve olasılıklar araştırma amaçlıdır ve
> kesinlik iddiası taşımaz.

---

## Özellikler

- **10 ana analiz modülü** (çoklu seçilebilir):
  1. Likidasyon haritası ve türev piyasalar (funding, open interest, long/short)
  2. Balina alım-satım / toplam arz (zincir-üstü büyük transferler + stablecoin likiditesi)
  3. Tüm borsalardaki hacimler (CoinGecko ticker dağılımı + Binance/OKX/Bybit doğrulaması)
  4. Gelirler, fee'ler ve fee/mcap oranı (DefiLlama)
  5. Son haberler + sentiment skorları (CryptoPanic, RSS, GDELT, VADER)
  6. Geçmiş mcap / güncel mcap oranı ve kendi tarihine göre konum
  7. BTC/ETH paritesi, ATH ve direnç mesafesi
  8. USD bazlı ATH/ATL mesafesi
  9. Coinler arası mcap sıralaması ve geçmiş max/min rank uzaklığı
  10. Timeframe teknik analiz (RSI, MACD, EMA, Bollinger, ATR, Fibonacci, formasyonlar)

- **66 maddelik deep research motoru**: Kullanıcının verdiği 66 maddelik liste birebir
  `items.yaml` içinde tanımlıdır. Her madde veri + kaynak + güven + skor üretir; veri
  bulunamayan maddeler açıkça "veri yok" işaretlenir ve ortalamaya katılmaz.
- **Context Control Plane**: Her context objesinin kimliği, scope'u, provenance'ı, TTL'i ve
  versiyonu vardır. Politika kararları: `KEEP / COMPRESS / CACHE / OFFLOAD / DROP / PIN /
  PREFETCH`. Offload geri alınabilir (offload → compress → retrieve → rehydrate).
- **Tamamen yerel RAG**: SQLite (metadata + FTS5) + LanceDB (vektör) + `fastembed`
  (`intfloat/multilingual-e5-large`). İnternet gerekmez, ek maliyet yok.
- **MCP server**: Claude Desktop, Claude Code, Codex, Cursor gibi araçlara doğrudan veri ve
  analiz sunar.
- **Web UI**: NotebookLM benzeri koyu tema; coin/timeframe/analiz seçimi, **timeframe bazlı
  interaktif SVG fiyat grafiği**, yükseliş/düşüş olasılık çubuğu, 66 madde tablosu (arama +
  sıralama), rapor ve prompt görüntüleme, RAG arama, rapor geçmişi.
- **tr-TR sayı biçimi**: Tüm çıktılarda binlik ayracı nokta, ondalık virgül; mikro fiyatlar
  (ör. PEPE $0,00000338) bilimsel gösterime düşmeden ve sıfıra yuvarlanmadan gösterilir.
- **Opsiyonel OpenRouter**: API anahtarı girilirse RAG soruları ve rapor üretimi LLM'e
  devredilebilir. Anahtar yoksa sistem yalnızca prompt üretir (varsayılan davranış).

---

## Kurulum

```bash
git clone https://github.com/alikula37/crypto-deep-research.git
cd crypto-deep-research
uv sync
cp .env.example .env        # opsiyonel API anahtarları
```

Gereksinimler: Python 3.10+, [uv](https://docs.astral.sh/uv/). Web UI için Node 18+.

> İlk RAG kullanımında embedding modeli indirilir (~2GB). Daha küçük model için `.env` içinde
> `CDR_EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` kullanın.

---

## Kullanım

```bash
# Anlık piyasa özeti
uv run cdr snapshot bitcoin

# Seçili analizler
uv run cdr analyze bitcoin --types technical,news,liquidations

# Tüm analizler + 66 madde + rapor + prompt
uv run cdr deep-research bitcoin --platform claude --json

# RAG arama (haber + analiz + rapor deposu)
uv run cdr search "ETF akışları" --coin bitcoin

# RAG + OpenRouter (anahtar varsa)
uv run cdr ask "BTC için likidasyon riski nedir?" --coin bitcoin

# MCP server (stdio)
uv run cdr mcp

# Web UI + REST API
uv run cdr serve            # http://127.0.0.1:8000

# Diğer
uv run cdr items            # 66 madde listesi
uv run cdr analyses         # analiz anahtarları
uv run cdr cache --stats    # önbellek durumu
uv run cdr rag-stats        # RAG deposu durumu
```

Web UI geliştirme modu:

```bash
cd web && npm install && npm run dev    # http://localhost:5173
```

---

## Docker ile Çalıştırma

Docker Desktop veya Colima ile çalışır. Veriler `./data` altında kalıcıdır
(SQLite, raporlar, promptlar, vektör deposu, embedding önbelleği).

```bash
# İmajı derle ve web UI + API'yi başlat
docker compose build
docker compose up -d          # http://127.0.0.1:8000
docker compose logs -f
docker compose down
```

CLI komutları konteynerde:

```bash
docker compose run --rm app cdr snapshot bitcoin
docker compose run --rm app cdr analyze bitcoin -t technical,news
docker compose run --rm app cdr deep-research bitcoin --platform claude
docker compose exec app cdr search "ETF akışları" --coin bitcoin
```

MCP server (stdio) konteynerde:

```bash
docker run -i --rm -v "$PWD/data:/data" crypto-deep-research:latest /app/.venv/bin/cdr mcp
```

Colima kurulumu (Docker Desktop alternatifi, hesap gerektirmez):

```bash
brew install colima docker docker-compose
colima start --cpu 4 --memory 6 --disk 40
brew services start colima     # açılışta otomatik başlat (opsiyonel)
```

Not: Embedding modeli ilk RAG kullanımında indirilir ve `./data/fastembed` altında
saklanır (~2GB); sonraki çalıştırmalarda yeniden indirilmez.

---

## MCP Entegrasyonu

MCP server `uv run cdr mcp` komutuyla stdio üzerinden çalışır. Claude Desktop için
`claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "crypto-deep-research": {
      "command": "uv",
      "args": [
        "--directory",
        "/TAM/YOL/crypto-deep-research",
        "run",
        "cdr",
        "mcp"
      ]
    }
  }
}
```

Sunulan araçlar:

| Araç | Açıklama |
| --- | --- |
| `list_analyses` | Kullanılabilir analiz anahtarları |
| `list_research_items` | 66 maddelik liste |
| `resolve_coin` | Sembol → CoinGecko id çözümleme |
| `get_market_snapshot` | Fiyat, mcap, ATH/ATL, global veriler |
| `run_analysis` | Tek analiz çalıştırma |
| `deep_research` | 66 madde + skor + rapor + prompt |
| `search_context` | Yerel RAG araması |
| `list_reports`, `get_report` | Rapor listeleme/okuma |
| `get_run` | Koşu detayları (66 madde dahil) |

---

## Ücretsiz Veri Kaynakları

| Kaynak | Kullanım | Anahtar |
| --- | --- | --- |
| CoinGecko Demo | fiyat, mcap, rank, ATH/ATL, geçmiş mcap, kategori, dominance | opsiyonel (`CDR_COINGECKO_API_KEY`) |
| Binance / OKX / Bybit public | OHLCV, hacim, order book, funding, OI, long/short | gerekmez |
| Coinalyze | gerçek likidasyon geçmişi, OI/funding serisi | ücretsiz key önerilir |
| DefiLlama | fee/gelir, stablecoin, TVL, bridge (cross-chain) | gerekmez |
| CryptoPanic | haber + topluluk sentiment | ücretsiz key |
| RSS (CoinDesk, Cointelegraph TR, Decrypt, The Block...) | haber akışı | gerekmez |
| GDELT | haber hacmi, jeopolitik tarama | gerekmez |
| alternative.me | Fear & Greed endeksi | gerekmez |
| Reddit | topluluk sentimenti | gerekmez |
| Google Trends (pytrends) | arama ilgisi | gerekmez |
| Blockchain.com / mempool.space | hashrate, adres, ücret, büyük BTC transferleri | gerekmez |
| Blockscout / Etherscan | ETH ağı, gas, büyük transferler | Etherscan için opsiyonel key |
| yfinance | DXY, S&P, altın, VIX, petrol, 10Y | gerekmez |
| FRED | faiz, enflasyon, getiri eğrisi | ücretsiz key |
| Deribit | DVOL volatilite endeksi | gerekmez |
| GitHub API | geliştirici aktivitesi | gerekmez |

Kimlik gerektirmeyen kaynaklar anahtarsız çalışır; anahtar verilen kaynaklar otomatik devreye
girer. Tüm istekler SQLite önbelleğindedir (TTL + stale fallback), sayaçlar rate limit
korunacak şekilde ayarlanmıştır.

---

## Skorlama Metodolojisi

- Her madde `-1` (güçlü negatif) ile `+1` (güçlü pozitif) arasında skor ve `0..1` güven üretir.
- Ağırlıklı skor: `Σ(skor × ağırlık × güven) / Σ(ağırlık × güven)`; yalnızca `ok`/`partial`
  durumdaki ve güveni > 0 olan maddeler katılır.
- Yükseliş olasılığı: `%50 + 45 × ağırlıklı skor` (5–95 aralığına kırpılır); düşüş bunun
  tümleyenidir.
- Beklenen fiyat aralığı: ATR yüzdesinden türetilen günlük hareket ve skora göre asimetrik
  kaydırma ile hesaplanır.
- Veri bulunmayan maddeler (ör. astroloji, ücretli API gerektiren alanlar) ortalamaya
  katılmaz; raporda şeffaf şekilde listelenir.

---

## Bilinen Sınırlamalar

- Bazı 66 madde için ücretsiz ve doğrulanabilir veri yoktur (astroloji, patent veritabanları,
  Bitcoin ATM hacmi, X/Twitter API'si). Bu maddeler "veri yok" olarak işaretlenir.
- Likidasyon haritası, Coinalyze anahtarı yoksa open interest ve kaldıraç kademelerinden
  yaklaşık olarak tahmin edilir.
- Balina yön tespiti yalnızca kamuya açık bilinen borsa adresleriyle sınırlıdır; etiketler
  doğrulama gerektirebilir.
- TradingView'ün ücretsiz API'si yoktur; yerel teknik derecelendirme vekili kullanılır.
- Ücretsiz API'ler zaman zaman limit uygular (429); stale cache + FTS yedekleri devrededir.

---

## Geliştirme

```bash
uv run pytest -q            # testler
uv run ruff check src tests # lint
cd web && npm run build     # web derleme
```

CI: GitHub Actions (`ruff` + `pytest` + web build).

## Lisans

MIT
