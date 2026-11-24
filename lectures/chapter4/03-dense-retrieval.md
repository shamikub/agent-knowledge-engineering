# 4.3 稠密檢索：向量如何表達語意

## 學習目標

讀完本節後，你應該能：

- 說明 bi-encoder（雙編碼器）和 cross-encoder（交叉編碼器）的計算差異，以及各自能部署在哪個階段
- 解釋為何向量相似度高不等於答案正確，並舉出反例
- 描述對比學習（contrastive learning）和 in-batch negatives 的訓練邏輯
- 說明 HNSW 的 recall-latency trade-off，以及 m 和 ef 兩個參數的直觀意義
- 知道 SPLADE 和 E5 各自的一句話定位

**先備知識：** 向量內積、cosine 相似度、4.2 節 BM25 的概念。

---

## 任務定義：用語意橋接字面差異

BM25 只能匹配字面上相同（或詞幹相同）的詞。如果使用者問「夜車幾點到」，但文件裡寫的是「夜間列車抵達時間」，BM25 分數很低，因為「夜車」≠「夜間列車」、「到」≠「抵達」。

**Dense retrieval（密集向量檢索）**的思路是：先把查詢和文件都映射到同一個連續向量空間，讓語意相近的句子在空間中位置相近，再用向量相似度排名。

| 項目 | 說明 |
|------|------|
| 輸入 | 查詢 q（自然語言字串）、文件集合 D |
| 輸出 | 以向量相似度排名的 top-k 文件 |
| 核心元件 | Query encoder（查詢編碼器）、Passage encoder（段落編碼器） |
| 相似度函數 | Dot product 或 cosine similarity |

---

## 架構：從文字到向量再到 ANN

```
離線（建索引）：
  文件 d → Passage Encoder → 向量 v_d → 存入向量索引（HNSW）

線上（查詢）：
  查詢 q → Query Encoder → 向量 v_q
         → ANN 搜尋（HNSW） → top-k 候選
         → （可選）Cross-encoder 重排 → 最終排名
```

**Bi-encoder（雙編碼器）：** Query encoder 和 Passage encoder 分開運作，兩者可以是同一個模型（shared weights）或不同模型。關鍵是**查詢和文件各自獨立編碼**，彼此之間沒有 token-level 的互相注意（attention）。好處是文件向量可以預先計算並快取；代價是細粒度的詞語對齊資訊在 pooling 步驟中被壓縮掉了。

**Cross-encoder（交叉編碼器）：** 把查詢和文件**串在一起**，送進同一個 Transformer 做完整的 self-attention，讓每個查詢 token 能直接看到每個文件 token。精確度高，但每一對 (q, d) 都要重新計算，不能預先快取，只能用在候選集已縮小（通常 top-20 到 top-100）的重排階段。Cross-encoder 的詳細說明在 4.4 節。

---

## 訓練目標：對比學習

### 訓練資料格式

每筆訓練樣本是一個三元組（triplet）：

```
(q,  d⁺,  d⁻)
 ↑    ↑     ↑
查詢  正例  負例
```

正例 d⁺ 是已知能回答查詢的文件，負例 d⁻ 是不相關的文件。

### 訓練目標

讓 sim(v_q, v_{d⁺}) 盡量高、sim(v_q, v_{d⁻}) 盡量低。最常用的 loss 是 **InfoNCE / in-batch cross-entropy**：

```
loss = -log( exp(sim(q, d⁺)) / Σⱼ exp(sim(q, dⱼ)) )
```

其中 Σⱼ 跑遍 batch 內所有文件，包含正例和其他樣本的正例（in-batch negatives）。

### In-batch Negatives 的陷阱

假設 batch size = 32，那麼有 31 個 in-batch negatives。如果這 31 份文件都是「毫不相關的廣告頁」，模型很容易學會把「旅遊條款」和「廣告頁」分開，但沒有學會分辨「含洗衣機的住宿說明」和「含洗衣機費用但需預約的住宿說明」。

解法是加入 **hard negatives**：詞彙相近但條件不符的文件（例如：「本館有洗衣機，限入住 3 晚以上旅客使用」），迫使模型學習更細緻的語意差異。DPR（Dense Passage Retrieval）論文驗證了 hard negatives 對效果的顯著提升。

---

## 完整算例：「夜車幾點到」的查詢對比

### 語料庫設定

```
D1（班次表）：「夜車於 23:40 從維也納中央車站出發，次日 06:15 抵達薩爾斯堡。」
D2（住宿說明）：「旅館提供洗衣機與烘衣機，洗烘費用另計。」
D3（行程說明）：「夜間列車是跨日旅行的首選，抵達時刻因路線而異。」
```

### BM25 查詢（字面匹配）

查詢：「夜車 幾點 到」

```text
「夜車」：只在 D1 出現 → D1 得分
「幾點」：三份都沒有 → 貢獻 0
「到」（停用詞，可能被移除）→ 貢獻 0

BM25 排名：D1（有「夜車」）> D2 ≈ D3（都沒有相關詞）
```

BM25 能找到 D1，但找不到 D3（「夜間列車」≠「夜車」）。

### 向量檢索（語意匹配）

假設使用訓練良好的多語 E5 模型（以下向量為示意，非真實值）：

```text
v_q（「夜車幾點到」）      ≈ 語意中心：夜間交通 + 時刻詢問
v_{D1}（「23:40 出發…」） ≈ 語意中心：具體時刻 + 交通
v_{D2}（「洗衣機費用…」） ≈ 語意中心：住宿設施
v_{D3}（「夜間列車…」）   ≈ 語意中心：夜間交通（與 v_q 語意接近）

cosine 相似度示意：
  sim(v_q, v_{D1}) ≈ 0.82（高，明確回答時刻）
  sim(v_q, v_{D2}) ≈ 0.21（低，主題不同）
  sim(v_q, v_{D3}) ≈ 0.74（中高，「夜間列車」≈「夜車」）

向量排名：D1 > D3 > D2
```

**關鍵差異：** 向量檢索把 D3（「夜間列車」）排到第二名，而 BM25 因為字面不匹配幾乎忽略了它。

### 反例：向量相似度高但答案錯誤

假設語料庫中還有：

```
D4（舊版班次表，已過期）：「夜車於 22:10 從維也納出發，次日 05:30 抵達薩爾斯堡。」
```

```text
sim(v_q, v_{D4}) ≈ 0.81（高，因為語意完全一樣：夜車 + 時刻）
```

向量排名可能是 D1 ≈ D4 > D3 > D2。如果 D4 的時刻資訊已過期，向量檢索**會回傳錯誤的答案**，因為它只看語意相似，不看發佈日期或版本。

**這就是「向量相似度 ≠ 答案正確」的核心教訓：** 版本控管、生效日期、適用條件仍然需要在 metadata 層面過濾，不能只靠向量相似度。

---

## HNSW：大規模 ANN 的 recall-latency trade-off

當文件數超過幾萬，逐一計算與所有文件的相似度（exact search）太慢，需要用**近似近鄰搜尋（Approximate Nearest Neighbor, ANN）**。最主流的方法是 HNSW（Hierarchical Navigable Small World）。

### HNSW 的直觀說明

HNSW 把向量組成一個多層圖：
- 頂層是稀疏的「高速公路」，節點少，每個節點連到遠距節點
- 底層是密集的「城市道路」，節點多，每個節點連到近鄰

查詢時從頂層入口進入，貪婪地往相似度更高的節點走，逐層往下縮小搜尋範圍，最後在底層找到近似最近鄰。

### 兩個關鍵參數

| 參數 | 意義 | 效果 |
|------|------|------|
| M | 每個節點在建圖時連接的鄰居數 | M 越大，recall 越高，索引越大、建圖越慢 |
| ef (efSearch) | 查詢時維持的候選集大小 | ef 越大，recall 越高，查詢越慢 |

```text
trade-off 示意（同一個資料集）：
  ef=10：latency=2ms，recall@10=0.85
  ef=50：latency=8ms，recall@10=0.95
  ef=200：latency=30ms，recall@10=0.99
  exact search：latency=200ms，recall@10=1.00
```

**使用建議：** 先用 exact search 量「索引本身漏掉多少候選」，確認 recall@k 的上限，再調整 ef 找到可接受的 latency。如果 recall@10 連 exact search 都只有 0.60，問題在 embedding 模型的品質，不在 HNSW 參數。

---

## SPLADE 和 E5 的一句話定位

**SPLADE（Sparse Lexical and Expansion）：**
用 Transformer 為每個詞彙表中的詞產生稀疏權重，讓同義詞和未出現的詞也能參與匹配，同時保留倒排索引的查詢速度。語義能力強於 BM25，查詢速度快於 bi-encoder，但需要額外的模型推論和索引膨脹（索引大小可達 BM25 的 10 倍以上）。

**E5（EmbEddings from bidirEctional Encoder rEpresentations）：**
使用 query 和 passage 前綴（`query:` / `passage:`）提示的 bi-encoder，在 MTEB 多語言 benchmark 上效果優秀。實作要依照模型卡在前綴上加正確的 prefix，否則效果大幅下降。

---

## 方法比較

### BM25 vs Bi-encoder

| 比較項目 | BM25 | Bi-encoder |
|----------|------|------------|
| 語意覆蓋 | 只有字面匹配 | 能橋接同義詞與改寫 |
| 查詢速度 | 極快（倒排索引） | 快（ANN，預計算文件向量） |
| 索引大小 | 小 | 中（每份文件一個向量） |
| 訓練需求 | 無（統計方法） | 需要標註資料或蒸餾 |
| 精確術語 | 優（代碼、法規條款） | 劣（如果訓練資料沒有此類術語） |
| 解釋性 | 高（可追哪個詞貢獻了分數） | 低（向量空間不直觀） |
| 成本 | 低 | 中（GPU 編碼、向量儲存） |

### Bi-encoder vs Cross-encoder

| 比較項目 | Bi-encoder | Cross-encoder |
|----------|------------|---------------|
| 推論方式 | 文件可預計算，查詢時 1 次前向傳播 | 每對 (q, d) 都要重新計算 |
| 查詢延遲 | 低（ANN） | 高（O(k) 次前向傳播） |
| 語意精確度 | 中（token 互動資訊被 pooling 壓縮） | 高（query-document token 完整互相注意） |
| 適用階段 | 第一階段粗排（retrieval） | 第二階段精排（reranking） |
| 典型候選數 | 整個語料庫 → top-k | top-k → top-m（m < k） |

---

## 工具：Sentence Transformers

[Sentence Transformers](https://www.sbert.net/) 是最常用的 bi-encoder 實作庫，CPU 可執行。

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("intfloat/multilingual-e5-small")

# 注意 E5 需要加前綴
queries = ["query: 夜車幾點到薩爾斯堡"]
passages = [
    "passage: 夜車於 23:40 從維也納出發，次日 06:15 抵達薩爾斯堡。",
    "passage: 旅館提供洗衣機與烘衣機。",
]

q_emb = model.encode(queries, normalize_embeddings=True)
p_emb = model.encode(passages, normalize_embeddings=True)
scores = q_emb @ p_emb.T  # cosine similarity（已 normalize）
print(scores)  # 預期第一份分數較高
```

---

## 習題

**題 1（機制）：** 為什麼 bi-encoder 無法像 cross-encoder 那樣區分「洗衣機可使用」和「洗衣機需額外付費」這兩個語意差異細微的句子？

<details>
<summary>解答</summary>

Bi-encoder 把每個句子壓縮成一個固定長度向量（pooling）。在 pooling 之後，「可使用」和「需額外付費」的細節資訊已被壓縮，兩個句子的向量可能在空間中很近。

Cross-encoder 把兩個句子串在一起做完整的 self-attention，查詢中的「費用」token 能直接注意到文件中的「額外付費」，細粒度語意差異得以保留。

實際應用：用 bi-encoder 快速取回 top-20 候選，再用 cross-encoder 重排，讓精確度和效率兼顧。

</details>

---

**題 2（手算）：** 查詢向量 q = (1, 0)，文件向量 d₁ = (3, 0)，d₂ = (2, 2)。
(a) 計算 dot product 排名；(b) 計算 cosine 排名；(c) 兩者排名是否相同？說明差異。

<details>
<summary>解答</summary>

```text
(a) Dot product：
  q · d₁ = 1×3 + 0×0 = 3
  q · d₂ = 1×2 + 0×2 = 2
  排名：d₁ > d₂

(b) Cosine similarity（先正規化）：
  |q|  = 1
  |d₁| = 3，cosine(q, d₁) = 3 / (1×3) = 1.000
  |d₂| = √(4+4) = 2.83，cosine(q, d₂) = 2 / (1×2.83) = 0.707
  排名：d₁ > d₂

(c) 本例兩者排名相同，但這不保證一定相同。
```

反例：q = (1, 0)，d₃ = (1, 0)（長度 1），d₄ = (10, 0)（長度 10）。
Dot product：d₄（=10）> d₃（=1）；Cosine：d₃ = d₄ = 1.0（排名相同）。

**結論：** 向量長度（範數）不一致時，dot product 和 cosine 排名可能不同。E5 等模型通常建議先 `normalize_embeddings=True`，讓兩者等價。在比較方法前，要先確認用的是哪種距離函數。

</details>

---

**題 3（選型）：** 你的系統要在 100 萬份旅遊法規文件中即時回應查詢（要求延遲 < 50ms）。你應該用 exact search 還是 HNSW？如果發現 recall@10 比預期低，第一步應該怎麼排查？

<details>
<summary>解答</summary>

選 HNSW。100 萬份文件做 exact search，每次查詢需要計算 100 萬次內積，在 CPU 上可能需要數秒，遠超 50ms 的限制。HNSW 可以在 10ms 量級達成 recall@10 ≈ 0.95。

排查 recall@10 低的步驟：

1. 先用 exact search 量「理論上限 recall@10」。如果 exact search 的 recall 也低（例如 0.60），問題在 embedding 模型品質，不是 HNSW 參數。
2. 如果 exact search recall 高但 HNSW recall 低，調大 ef（efSearch），直到 recall 與 exact search 接近。
3. 確認文件向量的 normalization 方式與查詢向量一致。
4. 確認 M 值夠大（通常 M=16 或 M=32），小 M 值會讓圖結構不夠連通。

</details>

---

[章節導覽](intro.md) · [上一節](02-sparse-retrieval.md) · [下一節](04-reranking-and-fusion.md)
