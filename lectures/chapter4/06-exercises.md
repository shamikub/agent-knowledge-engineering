# 4.6 習題與解答

本節包含五道綜合習題，涵蓋 BM25 / RRF 手算、指標計算、dense retrieval 選型、RAG 管線偵錯，以及一個偵錯流程圖。

---

## 習題一：RRF 手算

系統 A 排名為 X(1)、Y(2)；系統 B 排名為 Y(1)、Z(2)。RRF 的 c=60。算三份文件的 RRF 分數，並寫出最終排名。

<details>
<summary>解答</summary>

```text
X：只在 A 有排名（第 1）
  RRF(X) = 1/(60+1) = 1/61 ≈ 0.01639

Y：A 第 2、B 第 1
  RRF(Y) = 1/(60+2) + 1/(60+1) = 1/62 + 1/61 ≈ 0.01613 + 0.01639 = 0.03252

Z：只在 B 有排名（第 2）
  RRF(Z) = 1/(60+2) = 1/62 ≈ 0.01613
```

**最終排名：Y(0.03252) > X(0.01639) > Z(0.01613)**

Y 被兩個系統共同支持（A 第 2、B 第 1），綜合分數遠高於只有單一系統支持的 X 和 Z。X 雖然在 A 是第 1 名，但在 B 完全不出現（無分），所以不如 Y 的穩定性。

</details>

---

## 習題二：Recall 和 nDCG 的計算

某查詢需要三筆文件才能完整回答（D1、D2、D3 都是相關文件）。系統回傳的 top-2 是 [D1, D2]。

計算以下指標並解釋含義：
1. Recall@2
2. 二元 nDCG@2（所有相關文件 rel=1）
3. 完整集合命中（Answer Hit = 三筆證據全在 top-2）

<details>
<summary>解答</summary>

**1. Recall@2**

相關文件共 3 筆，top-2 中找到 2 筆（D1、D2）：
```
Recall@2 = 2 / 3 ≈ 0.667
```

**2. 二元 nDCG@2**

DCG@2（實際） = rel(1)/log₂(2) + rel(2)/log₂(3) = 1/1 + 1/1.585 = 1 + 0.631 = 1.631

IDCG@2（理想，前兩名都相關） = 1/1 + 1/log₂(3) = 1 + 0.631 = 1.631

nDCG@2 = DCG@2 / IDCG@2 = 1.631 / 1.631 = **1.0**

注意：nDCG@2 = 1.0 並不代表回答一定正確，只代表「在 k=2 的截點內，能找到的相關文件都排到了最好的位置」。

**3. 完整集合命中**

需要三筆都在 top-2，但 top-2 只有 D1 和 D2，缺少 D3：
```
完整集合命中 = 0
```

**關鍵教訓：** nDCG@2 = 1.0 和「能正確回答」是兩件事。若回答需要三份文件全部到齊，k=2 在結構上就無法滿足，要提高 k 才有機會解決。

</details>

---

## 習題三：Cross-encoder 能否補救 top-k 外的答案？

第一階段 top-20 沒有旅館的入住確認信（正確答案是 D6，BM25 排名第 23）。把 cross-encoder 的重排範圍從 top-10 加到 top-20，是否足以補回 D6？

<details>
<summary>解答</summary>

**無法補回。**

Cross-encoder 的重排範圍從 top-10 擴大到 top-20，只是讓它處理更多已有的候選，但 D6 在第一階段就已排在第 23 名，完全不在 top-20 的候選集中。Cross-encoder 只能對「已進入候選集的文件」重新排序，無法把候選集外的文件帶回來。

**正確的修復方向（往上游）：**

1. 把粗排 top-k 從 20 擴大到 30 或 50，讓 D6 有機會進入候選集
2. 分析 D6 為何排名低：是詞彙不匹配（文件用「確認信」而查詢用「入住確認」）還是文件長度問題？
3. 若是詞彙不匹配，加入同義詞擴展或換用 bi-encoder 路徑
4. 若兩種路徑都找不到 D6，檢查文件解析和 metadata 過濾是否誤刪了 D6

</details>

---

## 習題四：Dense Retrieval 選型

你的系統要處理三種查詢類型：
- A 類：「PNR 代碼 XYZ789 的行程」（精確代碼查詢）
- B 類：「夜車到薩爾斯堡大概幾點」（口語語意查詢）
- C 類：「有洗烘設備且可帶寵物的住宿」（多條件組合查詢）

請為每種類型推薦一種檢索方法，並說明理由和潛在陷阱。

<details>
<summary>解答</summary>

**A 類（精確代碼）→ BM25 / 精確匹配**

PNR 代碼是不能有歧義的精確字串，不需要語意相似度。BM25 在精確術語匹配上速度快、成本低、解釋性高。向量檢索反而有風險：「XYZ789」和「XYZ790」可能在向量空間中很接近，回傳錯誤的訂位。陷阱：確認切詞工具沒有把代碼切壞（例如把「XYZ789」切成「XYZ」和「789」）。

**B 類（口語語意）→ Bi-encoder（如 multilingual-e5-small）**

口語表達（「大概幾點」）和文件用語（「抵達時間」、「班次表」）字面差異大，BM25 命中率低。Bi-encoder 能橋接語意差異。陷阱：如果訓練資料沒有旅遊領域的樣本，模型可能把「夜車」和「夜間巴士」混淆，需要用 hard negatives fine-tune 或選用有旅遊領域覆蓋的預訓練模型。

**C 類（多條件組合）→ BM25 + Bi-encoder + RRF，再加 Cross-encoder 重排**

「洗烘設備 AND 可帶寵物」是兩個條件必須同時成立的查詢。BM25 能精確匹配「洗烘設備」，Bi-encoder 能找到語意相近的「laundry facilities」。RRF 融合後，再用 Cross-encoder 確認「兩個條件都在同一份文件且同時成立（非被否定）」。陷阱：Cross-encoder 只在候選集已有答案時才有效，要先確認 Recall@k 夠高。

</details>

---

## 習題五：RAG 管線偵錯

你的 RAG 系統對查詢「取消訂位的退款期限是幾天？」回答「取消後 7 天退款」，但正確答案是「取消後 3 個工作日退款」。你懷疑可能是任何一個模組出問題。請描述你的偵錯步驟。

<details>
<summary>解答</summary>

按照偵錯流程，依序排查每個模組：

**步驟 1：排查 Retriever（Oracle Retrieval Test）**

手動找到正確的文件段落（「取消後 3 個工作日退款」），直接插入 prompt 的第一位，觀察 LLM 是否能正確回答「3 個工作日」。

- 若 LLM 能正確回答 → Retriever 是問題所在（沒有把正確文件取回）
- 若 LLM 仍然回答錯誤 → 問題在 Prompt Builder 或 LLM 本身，繼續下一步

**步驟 2：排查 Reranker（排名位置檢查）**

若 Retriever 確實取回了正確文件，確認它在 Reranker 輸出中的排名。若正確文件排在第 5 名以後，可能被 Prompt Builder 截斷了。

**步驟 3：排查 Prompt Builder（Lost in the Middle 測試）**

把正確文件移到 prompt 的第一位重跑，若答案變正確，確認是 Prompt Builder 的文件排列問題（Lost in the Middle 效應）。

**步驟 4：排查 LLM（引用評估 / 幻想測試）**

用 ALCE 評估 LLM 的引用：若 LLM 引用了正確文件但仍說「7 天」，可能是 LLM 在訓練資料中記住了「7 天」這個錯誤資訊，並覆蓋了 prompt 中的正確資訊（幻想 / sycophancy）。解法：在 prompt 中明確要求「僅依據以下文件回答，若文件與你的知識衝突，以文件為準」。

**另一個可能：** 語料庫中同時存在「7 天退款」和「3 個工作日退款」兩份文件（舊條款 vs 新條款），Retriever 取到的是舊版文件。解法：在 metadata 層加版本過濾，只保留最新生效的條款。

</details>

---

## 偵錯流程圖：當 RAG 答錯時

當 RAG 回答錯誤，先不要急著換模型。按以下流程定位問題所在的模組：

```
RAG 回答錯誤
      │
      ▼
[步驟 1] Oracle Retrieval Test
  把正確答案文件手動插入 prompt
      │
      ├── LLM 仍答錯 → 問題在 Prompt Builder 或 LLM
      │                    │
      │                    ▼
      │               [步驟 3] 把正確文件移到 prompt 第一位
      │                    │
      │                    ├── 答對 → Lost in the Middle（Prompt Builder）
      │                    └── 仍錯 → LLM 幻想 / 訓練記憶覆蓋
      │
      └── LLM 答對 → 問題在上游檢索
                         │
                         ▼
                   [步驟 2] 量 Recall@k
                         │
                         ├── 答案不在 top-k → Retriever 失敗
                         │     → 診斷：詞彙不匹配？切詞問題？過濾錯誤？
                         │     → 修復：擴大 k、加同義詞、加 bi-encoder 路徑
                         │
                         └── 答案在 top-k 但排名靠後 → Reranker 失敗
                               → 診斷：Cross-encoder 訓練資料是否覆蓋此類問題？
                               → 修復：fine-tune cross-encoder 或換用更強的模型
```

**使用 Ablation 量化每個模組的貢獻：**

| 測試配置 | 目的 |
|----------|------|
| 只用 BM25，無 reranker | BM25 基線 |
| BM25 + cross-encoder | 量 reranker 的貢獻 |
| BM25 + bi-encoder（RRF），無 reranker | 量融合的貢獻 |
| BM25 + bi-encoder + cross-encoder | 完整管線 |
| Oracle passage（人工放入正確段落）| 上限估計 |

每個配置在同一批測試集上跑，比較 F1 / nDCG@k，就能看出每一層帶來的增益和代價。

---

[章節導覽](intro.md) · [上一節](05-rag.md)
