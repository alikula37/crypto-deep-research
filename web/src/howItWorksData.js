export const STAGES = [
  {
    label: "Kaynaklar", short: "Veri toplama", color: "#3fb0c4", noun: "GİRDİ",
    title: "Farklı kaynaklar, tek araştırma.",
    description: "Fiyat, hacim, türev piyasa, zincir üstü veriler ve haberler bir araya gelir. Her bulgunun nereden geldiği ve ne kadar veriye dayandığı izlenebilir.",
    technical: "Sağlayıcı katmanı, farklı API’leri ortak veri modellerine dönüştürür. Ağ istekleri asenkron çalışır; SQLite önbelleği tekrar eden istekleri azaltır.",
    tags: ["CoinGecko", "Borsalar", "DefiLlama", "Haber akışları"],
    takeaway: "İlk adım: üstte bir varlık seç, ardından Derin Araştırma’yı başlat.",
    question: "Bir kaynaktan veri gelmezse?", answer: "Eksik bilgiyi uydurmak yerine veri durumunu açıkça gösteriyorum. Veri yok olarak işaretlenen kriter genel skora katkı vermiyor.",
    action: "Genel bakışı aç", tab: "overview",
  },
  {
    label: "Araştırma", short: "10 modül · 66 kriter", color: "#e0bb55", noun: "KANIT",
    title: "Her skorun arkasında bir bulgu.",
    description: "10 analiz modülü ve 66 kriter; bulgu, skor, güven ve veri durumu üretir. Rapor ve hazır prompt bu yapılandırılmış araştırmadan yerel olarak hazırlanır.",
    technical: "Ortak sinyalleri kullanan kriterlere grup düzeltmesi uygulanır. Kısmi veri daha düşük ağırlık alır. Bu adımın rapor üretmek için bir LLM’e veya RAG aramasına ihtiyacı yoktur.",
    tags: ["Skor −1…+1", "Güven 0…1", "Tam / Kısmi / Veri yok"],
    takeaway: "Bulgular’da önce veri durumuna, sonra skora ve kaynağa bak.",
    question: "66 kriter, 66 bağımsız sinyal mi?", answer: "Hayır. Aynı analizden gelen bilgiyi tekrar tekrar saymamak için katkıları grupluyorum. Kriter sayısını bağımsız gözlem sayısı olarak sunmuyorum.",
    action: "Bulguları keşfet", tab: "findings",
  },
  {
    label: "Bilgi tabanı", short: "Parçala · indeksle", color: "#3fb0c4", noun: "HAFIZA",
    title: "Bir rapor, sonraki sorunun kaynağı.",
    description: "Haberler, analiz özetleri ve tamamlanan raporlar bilgi tabanına kaydedilir. Uzun metinler, sınırda bağlam kaybolmasın diye örtüşen parçalara ayrılır.",
    technical: "Embedding modelinin tokenizer’ıyla 240 token üst bütçesi kullanılır; chunk sınırları mümkün olduğunca cümle sonunda seçilir. Tam cümle overlap’i en fazla 40 token hedefler; gerçekleşen tekrar daha az olabilir. Çok uzun cümle token pencerelerine bölünür. Tam metinler ve kaynak kimlikleri SQLite’ta, vektörler LanceDB’de saklanır; yeniden indeksleme tam metinden yapılır.",
    tags: ["240 token bütçe", "Cümle sınırları", "≤40 overlap", "SQLite + LanceDB"],
    takeaway: "Bilgi tabanı, tamamladığın araştırmalarla büyür; yeni sorularda geçmiş kanıtları kullanırsın.",
    question: "Neden chunking ve overlap?", answer: "Uzun raporu kırpmak yerine tüm içeriği aranabilir yapıyorum. Cümle sınırlarını dikkate alarak parçanın anlamını korumaya çalışıyorum; overlap tam cümleleri tekrar eder. Sabit token penceresi baseline olarak durur. Hangisinin retrieval ve yanıt desteğinde daha iyi olduğunu dev sorgularında ölçmek gerekir.",
    action: "Kaynak aramayı aç", tab: "rag",
  },
  {
    label: "Soru-cevap", short: "Hybrid RAG", color: "#8fa9d6", noun: "ERİŞİM",
    title: "Anlamı da arar, kelimeyi de.",
    description: "Soru, kayıtlı kaynaklarda iki yoldan aranır. Anlamsal arama ve BM25 sonuçları birleşir; ilgili pasajlar kaynak numaralarıyla sunulur.",
    technical: "Dense ve BM25 adayları RRF ile birleştirilir (rank constant: 60). İsteğe bağlı cross-encoder yeniden sıralar. OpenRouter açıkken kaynaklı bağlamdan yanıt üretilir; anahtar yoksa hazır prompt sunulur.",
    tags: ["Dense", "BM25", "RRF", "Opsiyonel reranker / LLM"],
    takeaway: "Kaynak Arama’da belirli bir soru sor; yanıttaki atıfın ilgili pasajı gerçekten desteklediğini kontrol et.",
    question: "Neden iki arama yöntemi?", answer: "Dense benzer anlamları; BM25 ticker, özel isim ve birebir terimleri yakalayabilir. Skorları farklı ölçeklerde olduğu için RRF ile sıraları birleştiriyorum. Hangisinin daha iyi olduğunu benchmark belirler.",
    action: "Bir soru sor", tab: "rag",
  },
  {
    label: "Değerlendirme", short: "Ölç · doğrula", color: "#5cd08d", noun: "DOĞRULAMA",
    title: "Çıktı üretmek başlangıçtır.",
    description: "Doğru kaynağı bulmak, kaynaklı bir yanıt üretmek ve fiyat yönünü tahmin etmek farklı problemlerdir. Her biri kendi veri seti ve metriğiyle değerlendirilir.",
    technical: "Retrieval ayarları dev sorgularında seçilir, test ayrı tutulur. Finansal ML’de purged walk-forward model seçimini ayrı kalibrasyon dönemi ve final kronolojik holdout izler. Kalite kapısını geçmeyen model aktifleştirilmez.",
    tags: ["Recall / MRR / nDCG", "İddia + atıf etiketi", "AUC / Brier / ECE"],
    takeaway: "Bir yüzdeyi yorumlamadan önce örneklem boyutunu, veri dönemini ve kalibrasyon durumunu kontrol et.",
    question: "AUC iyiyse neden Brier ve ECE?", answer: "AUC sıralamayı ölçer. Brier ve ECE olasılıkların ne kadar doğru ve kalibre olduğunu sorgular. Modeli baseline ve ayrı final dönemle kıyaslarım; başarısız sonucu da raporlarım.",
    action: "İsabet ekranını aç", tab: "accuracy",
  },
];

// Deliberately fictional teaching examples. These are never live search results.
export const FUSION_EXAMPLES = [
  {
    id: "liquidation", query: "Bitcoin’de likidasyon riski nasıl değerlendirilir?",
    documents: [
      { id: "risk", title: "Kaldıraç ve likidasyon seviyeleri", kind: "Analiz" },
      { id: "perps", title: "BTC türev piyasası araştırması", kind: "Rapor" },
      { id: "volatility", title: "Piyasa oynaklığı ve risk göstergeleri", kind: "Analiz" },
      { id: "technical", title: "BTC haftalık teknik görünümü", kind: "Rapor" },
      { id: "volume", title: "BTC spot işlem hacimleri", kind: "Analiz" },
    ],
    dense: ["risk", "perps", "volatility", "technical"],
    bm25: ["perps", "technical", "risk", "volume"],
  },
  {
    id: "parity", query: "ETH/BTC paritesindeki değişim ne anlatıyor?",
    documents: [
      { id: "rotation", title: "Bitcoin ile Ethereum arasında sermaye rotasyonu", kind: "Analiz" },
      { id: "parity", title: "ETH/BTC parite ve direnç analizi", kind: "Analiz" },
      { id: "dominance", title: "Piyasa payı ve dominance görünümü", kind: "Rapor" },
      { id: "eth", title: "ETH piyasa özeti", kind: "Rapor" },
      { id: "btc", title: "BTC günlük hacim raporu", kind: "Rapor" },
    ],
    dense: ["rotation", "parity", "dominance", "eth"],
    bm25: ["parity", "eth", "rotation", "btc"],
  },
];

export function fusionRanking(example, mode, constant = 60) {
  if (!Number.isFinite(constant) || constant < 0) throw new Error("Rank constant must be non-negative");
  if (!["dense", "bm25", "hybrid"].includes(mode)) throw new Error("Unknown retrieval mode");
  const ranks = (ids) => new Map([...new Set(ids)].map((id, index) => [id, index + 1]));
  const dense = ranks(example.dense);
  const bm25 = ranks(example.bm25);
  return example.documents.map((doc) => {
    const denseRank = dense.get(doc.id);
    const bm25Rank = bm25.get(doc.id);
    const score = (mode !== "bm25" && denseRank ? 1 / (constant + denseRank) : 0)
      + (mode !== "dense" && bm25Rank ? 1 / (constant + bm25Rank) : 0);
    return { ...doc, denseRank, bm25Rank, score };
  }).filter((doc) => doc.score > 0).sort((a, b) => b.score - a.score || a.id.localeCompare(b.id));
}

export const INTERVIEW_SCRIPT = "Bu projede kripto araştırmasını veri toplama, analiz, bilgi erişimi ve değerlendirme olarak ayırdım. Farklı kaynaklardan gelen veriyi 10 analiz modülü ve 66 kriterde birleştiriyorum. Her sonucun skoru, güveni ve veri durumu tutuluyor; rapor bu yapılandırılmış sonuçlardan yerel olarak oluşturuluyor. RAG ayrı bir soru-cevap hattı: haber, analiz ve raporları 240 token bütçesine uyan, mümkün olduğunca cümle sınırlarını koruyan parçalara ayırıyorum. Overlap için 40 tokena kadar tam cümleler tekrar edilir; çok uzun cümlede token tabanlı bölmeye dönülür. Sabit token penceresini karşılaştırma için tutuyorum; bu değişikliğin kaliteyi artırdığını ölçmeden iddia etmiyorum. Dense ve BM25 sıralamalarını RRF ile birleştiriyorum; isteğe bağlı cross-encoder adayları yeniden sıralıyor. LLM açıkken kaynak numaralı bağlamdan yanıt üretiliyor. Retrieval, yanıt kalitesi ve finansal tahminler ayrı ölçülüyor. İlk RAG pilotu küçük ve etiketleri asistan taslağı; bunu genel başarı iddiası olarak sunmuyorum. Finansal tahminlerde purged walk-forward model seçimi, ayrı kalibrasyon ve son kronolojik holdout var. Güncel deneyde modeller baseline’ı geçemediği için hiçbirini aktifleştirmedim. Projenin değeri yalnız çıktı üretmesi değil, hangi çıktıya ne kadar güvenebileceğimizi ölçmesidir.";
