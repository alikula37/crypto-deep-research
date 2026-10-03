import { DEMO_SOURCE, DEMO_QUERY, CHUNK_STRATEGIES, claimsForChunks } from "./ragWalkthroughData.js";

// The map explains the implementation. Its examples share the walkthrough's
// state; live chunk controls and recorded 240/40 retrieval are kept separate.
export const ARCHITECTURE_NODES = [
  { id: "source", title: "Haber / analiz / rapor", kicker: "TAM KAYNAK", subtitle: "Metin + kaynak kimliği", lane: "index", phase: 0 },
  { id: "chunk", title: "Token bütçesi + chunking", kicker: "PARÇALA", subtitle: "Cümle sınırları · overlap", lane: "index", phase: 1 },
  { id: "chunkEmbedding", title: "E5: chunk embedding", displayTitle: "E5 · chunk vektörü", kicker: "ANLAMI KODLA", subtitle: "E5 · 1024 boyut", lane: "index", phase: 2 },
  { id: "sqlite", title: "SQLite: metin + FTS5", displayTitle: "SQLite + FTS5", kicker: "SÖZCÜKSEL İNDEKS", subtitle: "Metin + ortak kimlik", lane: "index", phase: 2 },
  { id: "lance", title: "LanceDB: vektörler", kicker: "VEKTÖR DEPOSU", subtitle: "Vektör + ortak kimlik", lane: "index", phase: 2 },
  { id: "question", title: "Kullanıcının sorusu", kicker: "SORGULA", subtitle: "Arşivi yeniden indekslemez", lane: "query", phase: 3 },
  { id: "queryEmbedding", title: "E5: soru embedding", kicker: "SORUYU KODLA", subtitle: "E5 · 1024 boyut", lane: "query", phase: 2 },
  { id: "dense", title: "Vektör arama", kicker: "ANLAMSAL ERİŞİM", subtitle: "LanceDB · yakınlık", lane: "query", phase: 3 },
  { id: "bm25", title: "BM25 arama", kicker: "TERİM EŞLEŞMESİ", subtitle: "SQLite FTS5 · terimler", lane: "query", phase: 3 },
  { id: "rrf", title: "RRF ile birleşim", kicker: "HYBRID FUSION", subtitle: "Ham skorları değil, sıraları birleştir", lane: "query", phase: 4 },
  { id: "rerank", title: "Opsiyonel reranker", kicker: "YENİDEN SIRALA", subtitle: "Soru + pasaj birlikte", lane: "query", phase: 4, optional: true },
  { id: "context", title: "Top-k + kaynaklı prompt", kicker: "KANITI SEÇ", subtitle: "[1], [2]… · metin + kaynak", lane: "query", phase: 5 },
  { id: "answer", title: "Opsiyonel LLM yanıtı", kicker: "KAYNAKTAN YANITA", subtitle: "OpenRouter · iddia + atıf", lane: "query", phase: 6, optional: true },
];

export const ARCHITECTURE_EDGES = [
  { id: "source-chunk", from: "source", to: "chunk", label: "Tam metin", phase: 1 },
  { id: "chunk-chunkEmbedding", from: "chunk", to: "chunkEmbedding", label: "Chunk metni", phase: 2 },
  { id: "chunk-sqlite", from: "chunk", to: "sqlite", label: "Metin + metadata", phase: 2 },
  { id: "chunkEmbedding-lance", from: "chunkEmbedding", to: "lance", label: "Vektör + kimlik", phase: 2 },
  { id: "lance-dense", from: "lance", to: "dense", label: "Kayıtlı vektörler", phase: 3 },
  { id: "sqlite-bm25", from: "sqlite", to: "bm25", label: "Kayıtlı metinler", phase: 3 },
  { id: "question-queryEmbedding", from: "question", to: "queryEmbedding", label: "Soru metni", phase: 2 },
  { id: "question-bm25", from: "question", to: "bm25", label: "Soru terimleri", phase: 3 },
  { id: "queryEmbedding-dense", from: "queryEmbedding", to: "dense", label: "Soru vektörü", phase: 3 },
  { id: "dense-rrf", from: "dense", to: "rrf", label: "Dense sırası", phase: 4 },
  { id: "bm25-rrf", from: "bm25", to: "rrf", label: "BM25 sırası", phase: 4 },
  { id: "rrf-rerank", from: "rrf", to: "rerank", label: "Birleşik adaylar", phase: 4 },
  { id: "rerank-context", from: "rerank", to: "context", label: "Son sıra → top-k", phase: 5 },
  { id: "context-answer", from: "context", to: "answer", label: "Kaynaklı prompt", phase: 6 },
];

const RAG_PATH = "src/crypto_deep_research/rag/";
const range = (chunk) => `${chunk.id} [${chunk.start}, ${chunk.end}) · ${chunk.tokenCount} token`;
const order = (ids) => ids.join(" → ");
const vector = (values) => `[${values.map((value) => value.toFixed(3)).join(", ")}, …]`;
const sourceId = (chunk) => `${DEMO_SOURCE.id}#chunk-${String(Number(chunk.id.slice(1)) - 1).padStart(6, "0")}`;
const record = (chunk) => JSON.stringify({
  id: sourceId(chunk), parent_id: DEMO_SOURCE.id,
  token_start: chunk.start, token_count: chunk.tokenCount,
  source: DEMO_SOURCE.source,
}, null, 2);
const snippet = (text, limit = 180) => text.length > limit ? `${text.slice(0, limit)}…` : text;

export function architectureDetail(selection, state) {
  const { strategy, chunkSize, overlap, chunks, candidates, demo, rows, contexts, rerank } = state;
  const first = chunks[0];
  const next = chunks[1];
  const candidate = candidates[0];
  const embedded = demo.documents.find((item) => item.id === candidate.id);
  const shared = next ? Math.max(0, first.end - next.start) : 0;
  const method = CHUNK_STRATEGIES[strategy].label;
  const measured = `${method} · 240 token / ≤40 overlap · kurgu korpusta hesaplanan sonuç`;
  const finalIds = rerank ? demo.reranked : rows.map((row) => row.id);
  const selectedIds = contexts.map((chunk) => chunk.id);
  const missingBm25 = candidates.filter((chunk) => !demo.bm25.includes(chunk.id)).map((chunk) => chunk.id);
  const firstRow = rows[0];
  const rankConstant = demo.provenance.rankConstant;
  const contribution = (rank) => rank ? `1/(${rankConstant}+${rank})` : "0";
  const claim = claimsForChunks(candidates)[0];
  const evidence = contexts.findIndex((chunk) => claim.sourceIDs.includes(chunk.id));
  const metadata = selection.kind === "edge"
    ? ARCHITECTURE_EDGES.find((item) => item.id === selection.id)
    : ARCHITECTURE_NODES.find((item) => item.id === selection.id);
  if (!metadata) throw new Error(`Unknown architecture selection: ${selection.id}`);

  const nodeDetails = {
    source: {
      description: "Haberler, analiz özetleri ve tamamlanan araştırma raporları bilgi tabanının kaynaklarıdır. Tam metin, parçalardan ayrı saklanır.",
      input: "Kaynak metni + kaynak bilgisi", output: "SQLite tam kaynak arşivi",
      example: [{ label: "Bu belgenin kimliği", value: DEMO_SOURCE.id }, { label: "Öğretim kaynağı", value: DEMO_SOURCE.title }, { label: "Tam belge", value: `${DEMO_SOURCE.tokens.length} token · kurgu araştırma notu` }],
      note: "Bu örnek piyasa verisi değildir. Tam kaynak korunur; chunk yöntemi değiştiğinde yeniden indeksleme bu metinden yapılır.",
      codePath: "src/crypto_deep_research/storage/db.py", codeLabel: "save_rag_source_document",
    },
    chunk: {
      description: strategy === "sentence" ? "Tam cümleleri token bütçesine sığdırır. Son cümlelerden bir bölümü overlap olarak taşınır; bir sonraki yeni cümleye yer açmak için tekrar azaltılabilir." : "Sabit token pencereleri oluşturur. Sonraki pencere overlap kadar geri başlar; cümle veya kelime ortasında bitebilir.",
      input: "Tam metin + tokenizer offsetleri", output: "Metin parçaları + token aralıkları",
      example: [{ label: "Laboratuvar ayarı", value: `${method} · bütçe ${chunkSize} · overlap ≤${overlap}` }, { label: "İlk iki parça", value: [first, next].filter(Boolean).map(range).join("\n") }, { label: "Bu sınırda gerçekleşen tekrar", value: `${shared} token` }],
      note: "Bu değerler kaydırıcıyla güncellenir. Aşağıdaki retrieval örnekleri seçili yöntemin 240/40 indeksinden gelir. Cümle bütçeyi aşarsa token parçalarına bölünür.",
      codePath: `${RAG_PATH}chunking.py`, codeLabel: "split_text",
    },
    chunkEmbedding: {
      description: "Her chunk metni, yerel FastEmbed / ONNX modeliyle sayısal vektöre dönüştürülür. Arşivdeki pasajlar ile soru aynı modelin vektör uzayında karşılaştırılır.",
      input: "Chunk metni", output: `${demo.vectorDimension} boyutlu vektör`,
      example: [{ label: "Model", value: demo.provenance.model }, { label: "Ölçülen indeksin parçası", value: range(candidate) }, { label: "İlk 8 gerçek koordinat", value: vector(embedded.vectorPreview) }],
      note: `${measured}. İlk 8 değer vektörün tamamı veya bir 2D izdüşüm değildir. Mevcut kod metni doğrudan embed eder; query:/passage: önekleri eklemez.`,
      codePath: `${RAG_PATH}embeddings.py`, codeLabel: "Embedder.embed",
    },
    sqlite: {
      description: "SQLite tam kaynağı ve chunk kayıtlarını saklar. FTS5 aynı chunk metinleri üzerinde sözcüksel arama sağlar; kaynak bilgisi sonuçla birlikte geri gelir.",
      input: "Chunk metni + kaynak metadata", output: "documents + documents_fts kayıtları",
      example: [{ label: "240/40 indeksinden örnek kayıt", value: record(candidate) }, { label: "Metin", value: snippet(candidate.text) }],
      note: "FTS5 ve vektör deposu aynı chunk kimliğini paylaşır; iki arama listesindeki aynı pasaj bu kimlikle birleştirilir.",
      codePath: "src/crypto_deep_research/storage/db.py", codeLabel: "save_document",
    },
    lance: {
      description: "Yerel LanceDB, chunk vektörlerini kimlik ve metinle birlikte kalıcı tutar. Yeni soruda kayıtlı belge vektörleri kullanılır.",
      input: "Chunk kimliği + vektör + metin", output: "Aranabilir vektör kayıtları",
      example: [{ label: "Ortak chunk kimliği", value: sourceId(candidate) }, { label: "Vektör boyutu", value: `${demo.vectorDimension} float` }, { label: "Örnek ilk koordinatlar", value: vector(embedded.vectorPreview) }],
      note: "Mevcut kod ayrıca bir ANN/HNSW indeksi kurmaz; depo ve arama yeteneğini ANN yapılandırmasıyla karıştırmamak gerekir.",
      codePath: `${RAG_PATH}store.py`, codeLabel: "VectorStore.add / search",
    },
    question: {
      description: "Kullanıcının sorusu hem anlamsal aramaya hem sözcüksel aramaya girdi olur. Belge chunk ve embedding işlemleri bu aşamada tekrarlanmaz.",
      input: "Soru metni + isteğe bağlı varlık filtresi", output: "Soru embedding'i ve BM25 sorgusu",
      example: [{ label: "Aynı soru iki yolu besler", value: DEMO_QUERY }],
      note: "Harita iki ayrı erişim yolunu gösterir. Mevcut search kodu bu yolları sırayla çağırır.",
      codePath: `${RAG_PATH}engine.py`, codeLabel: "RAGEngine.search",
    },
    queryEmbedding: {
      description: "Soru metni, chunk embedding'lerinde kullanılan modelle vektöre çevrilir. Soru vektörü yalnız bu sorgu için gerekir.",
      input: "Soru metni", output: `${demo.vectorDimension} boyutlu soru vektörü`,
      example: [{ label: "Soru", value: DEMO_QUERY }, { label: "İlk 8 gerçek koordinat", value: vector(demo.queryVectorPreview) }],
      note: "Vektör modelin sayısal temsilidir; tek bir koordinata 'risk' veya 'fonlama' gibi bir anlam etiketi atanmaz.",
      codePath: `${RAG_PATH}embeddings.py`, codeLabel: "Embedder.embed_one",
    },
    dense: {
      description: "Soru vektörü kayıtlı chunk vektörleriyle karşılaştırılır. Küçük mesafeli pasajlar anlamsal aday sıralamasına girer.",
      input: "Soru vektörü + kayıtlı vektörler", output: "Dense aday sırası",
      example: [{ label: "Ölçülen dense sırası", value: order(demo.dense) }, { label: `${candidate.id} sunum skoru`, value: `${embedded.denseScore.toFixed(6)} = 1 / (1 + mesafe)` }],
      note: `${measured}. Bu skor güven olasılığı değildir; kod cosine benzerliği olarak etiketlemez.`,
      codePath: `${RAG_PATH}store.py`, codeLabel: "VectorStore.search",
    },
    bm25: {
      description: "SQLite FTS5, sorudaki terimler ile chunk metnindeki terimleri eşleştirir. Özel isimler ve birebir sözcükler için farklı adaylar öne çıkabilir.",
      input: "Soru metni + FTS5 metin indeksi", output: "BM25 aday sırası",
      example: [{ label: "Ölçülen BM25 sırası", value: order(demo.bm25) }, { label: "Bu sorguda eşleşmeyen", value: missingBm25.length ? missingBm25.join(", ") : "Bütün adaylar eşleşti" }],
      note: `${measured}. SQLite BM25 rank'inde küçük değer önce gelir; dense skoruyla doğrudan toplanmaz.`,
      codePath: "src/crypto_deep_research/storage/db.py", codeLabel: "search_documents",
    },
    rrf: {
      description: "İki sıralı listedeki katkılar ortak chunk kimliğiyle toplanır. Bir pasaj iki listede de varsa iki katkı alır; eşleşmeyen dal sıfır katkı verir.",
      input: "Aday kimlikleri + her listedeki sıra", output: "Birleşik RRF sırası",
      example: [{ label: "Hesaplanan birleşik sıra", value: order(rows.map((row) => row.id)) }, { label: `${firstRow.id} katkı hesabı`, value: `${contribution(firstRow.denseRank)} + ${contribution(firstRow.bm25Rank)} = ${firstRow.score.toFixed(6)}` }],
      note: `Rank sabiti ${rankConstant}. Ham dense ve BM25 skorları farklı ölçeklerde olduğu için sıralar kullanılır; üstünlük dev sorularında ölçülür.`,
      codePath: `${RAG_PATH}engine.py`, codeLabel: "reciprocal_rank_fusion",
    },
    rerank: {
      description: "Yapılandırılmış cross-encoder varsa soru ve her aday pasaj birlikte değerlendirilir. Kapalıysa birleşik RRF sırası korunur.",
      input: "Soru + RRF aday pasajları", output: "Son aday sırası",
      example: [{ label: "Bu laboratuvarda durum", value: rerank ? "Temsili yeniden sıralama açık" : "Kapalı · RRF sırası korunuyor" }, { label: "Gösterilen son sıra", value: order(finalIds) }],
      note: "Buradaki reranker sırası öğretim için yazılmıştır; cross-encoder çalıştırılmadı. Üründe ayrıca model yapılandırılır; hata olursa önceki sıra kullanılır.",
      codePath: `${RAG_PATH}engine.py`, codeLabel: "RAGEngine.search / rerank",
    },
    context: {
      description: "Son sıradan top-k pasaj seçilir. Soru, kaynak numaraları, pasaj metinleri ve kaynak bilgisi prompt'a girer; bütün arşiv gönderilmez.",
      input: "Son sıralı pasaj listesi + soru", output: "Numaralı kaynaklı prompt",
      example: [{ label: "Seçili bağlam", value: contexts.map((chunk, index) => `[${index + 1}] ${range(chunk)}`).join("\n") }, { label: "Talimat", value: "Kaynaklara dayanarak Türkçe yanıtla, kaynak numaralarına atıf yap; bilgi yoksa belirt, uydurma." }],
      note: `Demo top-${selectedIds.length}; ürünün arama varsayılanı k=8. [n] bu prompt'taki sıradır; kalıcı kaynak kimliği değildir.`,
      codePath: `${RAG_PATH}engine.py`, codeLabel: "answer_prompt / _format_context",
    },
    answer: {
      description: "OpenRouter yapılandırıldığında seçilen kaynaklı prompt'tan yanıt istenebilir. Atıf, iddiayı destekleyen pasajı incelemeye açar.",
      input: "Kaynaklı prompt", output: "İddialar + kaynak atıfları",
      example: [{ label: "Öğretim iddiası", value: claim.text }, { label: "Seçili bağlamdaki desteği", value: evidence < 0 ? "Destekleyen pasaj bağlama alınmadı; bu iddia bu bağlamla sunulmamalı." : `[${evidence + 1}] ${contexts[evidence].id}: “${claim.quote}”` }],
      note: "Bu laboratuvarın yanıtı yazılmış öğretim örneğidir; LLM çağrısı değildir. Atıf bulunması doğruluk garantisi sağlamaz; iddia desteği ayrıca değerlendirilir.",
      codePath: "src/crypto_deep_research/llm/openrouter.py", codeLabel: "OpenRouterClient",
    },
  };

  if (selection.kind === "node") {
    return { title: metadata.title, kicker: metadata.kicker, phase: metadata.phase, ...nodeDetails[metadata.id] };
  }

  const edgeDetails = {
    "source-chunk": {
      description: "Parçalama, tam kaynağın tokenizer offsetleri ve metin sınırları üzerinde çalışır. Kaynak metni kırpılmadan işlenir.",
      input: "Tam kaynak metni", output: "Token offsetleri → chunk sınırları",
      example: [{ label: "Kaynak", value: `${DEMO_SOURCE.id} · ${DEMO_SOURCE.tokens.length} token` }, { label: "Seçili laboratuvar ayarı", value: `${method} · ${chunkSize} / ≤${overlap}` }],
      note: "Overlap, sonraki parçanın başlangıcını etkiler. Cümle sınırını koruma kararı ayrıca chunk yöntemine bağlıdır.", codePath: `${RAG_PATH}chunking.py`, codeLabel: "split_text",
    },
    "chunk-chunkEmbedding": {
      description: "Embedding modeline sayısal token kimlikleri veya kaynak metadata yerine chunk'ın özgün metni verilir.",
      input: "240/40 indeksinden chunk metni", output: "Embedding modelinin metin girdisi",
      example: [{ label: "Ölçülen parça", value: range(candidate) }, { label: "Gönderilen metinden önizleme", value: snippet(candidate.text) }],
      note: "Önizleme ekranda kısaltılmıştır; embedding hesaplamasında parçanın metni kullanıldı.", codePath: `${RAG_PATH}engine.py`, codeLabel: "_embed_and_store",
    },
    "chunk-sqlite": {
      description: "Chunk'ın metni ve kaynakla bağlantısı SQLite'a yazılır. Aynı kimlik FTS5 tablosunda da aranabilir hale gelir.",
      input: "Chunk + metadata", output: "Kimlikli metin kaydı",
      example: [{ label: "Taşınan kayıt alanlarından örnek", value: record(candidate) }],
      note: "Metin, varlık, tür, URL ve tarih de saklanır. parent_id bütün parçaları tam kaynak belgeye bağlar.", codePath: "src/crypto_deep_research/storage/db.py", codeLabel: "save_document",
    },
    "chunkEmbedding-lance": {
      description: "Üretilen vektör, metin kaydıyla aynı chunk kimliğini taşıyarak LanceDB'ye yazılır.",
      input: "Chunk kimliği + embedding", output: "Kalıcı vektör kaydı",
      example: [{ label: "Kimlik", value: sourceId(candidate) }, { label: "Taşınan vektör", value: `${demo.vectorDimension} float · ${vector(embedded.vectorPreview)}` }],
      note: "İki depodaki ortak kimlik, aynı pasajın fusion aşamasında tek aday olarak birleşmesini sağlar.", codePath: `${RAG_PATH}engine.py`, codeLabel: "_embed_and_store",
    },
    "lance-dense": {
      description: "Arama kayıtlı chunk vektörlerini kullanır; sorgu sırasında belgeler yeniden embed edilmez.",
      input: "Kalıcı belge vektörleri", output: "Soru vektörüyle karşılaştırılacak adaylar",
      example: [{ label: "Öğretim indeksindeki adaylar", value: `${candidates.length} chunk × ${demo.vectorDimension} boyut` }],
      note: `${measured}. Bu sayı gerçek ürün arşivinin büyüklüğü değildir.`, codePath: `${RAG_PATH}store.py`, codeLabel: "VectorStore.search",
    },
    "sqlite-bm25": {
      description: "FTS5, daha önce kaydedilen chunk metinlerini sorgular. Sonuçlar kaynak metadata ile birleştirilerek geri döner.",
      input: "Metin indeksi", output: "Eşleşen kimlikler + BM25 sırası",
      example: [{ label: "Bu örnekte eşleşen kimlikler", value: order(demo.bm25) }],
      note: "FTS5 metin aramasıdır; burada embedding vektörü kullanılmaz.", codePath: "src/crypto_deep_research/storage/db.py", codeLabel: "search_documents",
    },
    "question-queryEmbedding": {
      description: "Sorunun özgün metni aynı embedding modeline gider. Elde edilen vektör dense arama girdisidir.",
      input: "Soru metni", output: "E5 model girdisi",
      example: [{ label: "Taşınan metin", value: DEMO_QUERY }],
      note: "Yalnız soru yeniden embed edilir; kalıcı belge vektörleri tekrar üretilmez.", codePath: `${RAG_PATH}embeddings.py`, codeLabel: "Embedder.embed_one",
    },
    "question-bm25": {
      description: "Aynı soru, vektöre dönüştürülmeden sözcüksel sorgu yoluna girer. Veritabanı sorgu terimlerini FTS5 için hazırlar.",
      input: "Soru metni", output: "FTS5 terim sorgusu",
      example: [{ label: "Taşınan soru", value: DEMO_QUERY }],
      note: "İki yolun girdisi aynı soru; eşleştirme biçimleri farklıdır.", codePath: "src/crypto_deep_research/storage/db.py", codeLabel: "search_documents",
    },
    "queryEmbedding-dense": {
      description: "Soru vektörü LanceDB aramasına verilir. Kayıtlı pasaj vektörleriyle mesafe hesabı yapılır.",
      input: "Soru embedding'i", output: "Vektör arama girdisi",
      example: [{ label: `${demo.vectorDimension} koordinattan ilk 8`, value: vector(demo.queryVectorPreview) }],
      note: "Soru ve chunk vektörlerinin boyutu ve modeli aynı olmalıdır.", codePath: `${RAG_PATH}store.py`, codeLabel: "VectorStore.search",
    },
    "dense-rrf": {
      description: "RRF dense skorun büyüklüğünü kullanmaz; her adayın bu listedeki sıra numarasını kullanır.",
      input: "Dense aday listesi", output: "Aday kimliği + dense rank",
      example: [{ label: "Taşınan sıra", value: demo.dense.map((id, index) => `${id}: #${index + 1}`).join(" · ") }],
      note: `Her katkı 1/(${rankConstant}+rank). Diğer arama dalının katkısı ayrıca eklenir.`, codePath: `${RAG_PATH}engine.py`, codeLabel: "reciprocal_rank_fusion",
    },
    "bm25-rrf": {
      description: "Sözcüksel adayların sıra numaraları fusion'a girer. Listede bulunmayan aday bu daldan katkı almaz.",
      input: "BM25 aday listesi", output: "Aday kimliği + BM25 rank",
      example: [{ label: "Taşınan sıra", value: demo.bm25.map((id, index) => `${id}: #${index + 1}`).join(" · ") }, { label: "Sırası olmayan", value: missingBm25.join(", ") || "Yok" }],
      note: "BM25 ham skorunu dense skora eklemek yerine sıralar birleştirilir.", codePath: `${RAG_PATH}engine.py`, codeLabel: "reciprocal_rank_fusion",
    },
    "rrf-rerank": {
      description: "Birleşik adaylar, model yapılandırılmışsa soru ile birlikte cross-encoder'a verilir. Kapalıysa bu liste doğrudan son sıra olur.",
      input: "RRF listesi + soru + aday metinleri", output: "Reranker aday havuzu / korunan sıra",
      example: [{ label: "Giren birleşik sıra", value: order(rows.map((row) => row.id)) }, { label: "Bu laboratuvarda", value: rerank ? "Yazılmış temsili yeniden sıralama gösteriliyor" : "Reranker kapalı" }],
      note: "Ürün aday havuzunu max(k×4, 32) ile ister; bu kurgu belgede yalnız 5 aday var. Laboratuvar cross-encoder çalıştırmaz.", codePath: `${RAG_PATH}engine.py`, codeLabel: "RAGEngine.search",
    },
    "rerank-context": {
      description: "Son sıranın ilk k pasajı alınır; bu seçimin dışındaki metinler prompt'a girmez.",
      input: "Son sıralı adaylar", output: "Seçilen top-k pasajlar",
      example: [{ label: "Son sıra", value: order(finalIds) }, { label: "Bağlama alınan", value: order(selectedIds) }],
      note: `Demo k=${contexts.length}; ürün varsayılanı k=8. Reranker kapalı olduğunda aynı bağlantı RRF sırasını taşır.`, codePath: `${RAG_PATH}engine.py`, codeLabel: "search / answer_prompt",
    },
    "context-answer": {
      description: "Soru, talimat ve numaralı pasajlar tek prompt'ta buluşur. LLM açıksa bu metin yanıt üretimi için gönderilir.",
      input: "Kaynak numaralı prompt", output: "Yanıt üretimine gönderilen kanıt",
      example: [{ label: "Kaynak numaralarının karşılığı", value: contexts.map((chunk, index) => `[${index + 1}] → ${chunk.id} → ${sourceId(chunk)}`).join("\n") }],
      note: "Bu laboratuvar LLM'e istek göndermez. Üründe OpenRouter anahtarı olmadan hazır prompt kullanılabilir.", codePath: `${RAG_PATH}engine.py`, codeLabel: "answer_prompt",
    },
  };
  const from = ARCHITECTURE_NODES.find((item) => item.id === metadata.from);
  const to = ARCHITECTURE_NODES.find((item) => item.id === metadata.to);
  return { title: `${from.title} → ${to.title}`, kicker: `OK ÜZERİNDE: ${metadata.label.toLocaleUpperCase("tr-TR")}`, phase: metadata.phase, ...edgeDetails[metadata.id] };
}
