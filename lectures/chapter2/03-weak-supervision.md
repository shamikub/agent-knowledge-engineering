# 2.3 弱監督標注

[← 上一頁](02-ner-and-events.md) · [本章導覽](intro.md) · [總目錄](../../README.md#課程地圖) · [下一頁 →](04-expert-review.md)

## 學習目標

完成本節後，你能夠：

- 說明 Snorkel labeling function（標籤函數）的 abstain 機制，以及為何不回答比回答錯更好
- 解釋為何複製同一模板的兩個 LF 會讓 LabelModel 高估信心
- 比較 uncertainty sampling、query by committee、core-set 三種主動學習選件策略，並說明各自的盲點
- 設計至少兩條針對訂位情境的 LF，並手算 label matrix

**先備知識**：知道什麼是分類任務（輸入文字，輸出類別）；看得懂 Python 函式。

---

## 任務定義

弱監督（weak supervision）解決的問題是：**有大量無標籤文字，但人工標注成本高，如何低成本產生訓練資料？**

```
輸入  → 無標籤文字（例如一萬封旅客訊息）
過程  → 多條 labeling function 各自給出雜訊標籤
輸出  → 帶機率的標籤分布（probabilistic labels）→ 訓練下游分類模型
```

這不是要取代標注，而是讓**少量規則 + 少量人工標注**撐起大量訓練資料。

---

## 架構說明

### LF 設計

Labeling function（標籤函數，簡稱 LF）是一個 Python 函式：

```python
from snorkel.labeling import labeling_function

CANCEL = 0
BOOK   = 1
ABSTAIN = -1

@labeling_function()
def lf_keyword_cancel(x):
    """若文字含「退票」或「取消」，標 CANCEL"""
    if "退票" in x.text or "取消" in x.text:
        return CANCEL
    return ABSTAIN  # 沒把握就棄權，不猜

@labeling_function()
def lf_regex_book(x):
    """若文字符合「訂了 N 點」模式，標 BOOK"""
    import re
    if re.search(r"訂了?\s*\d+\s*點", x.text):
        return BOOK
    return ABSTAIN
```

**abstain（棄權）的意義**：LF 沒把握時返回 `ABSTAIN`，讓 LabelModel 忽略該 LF 對這筆資料的投票。強迫每個 LF 都回答，反而會引入更多雜訊。

### PandasLFApplier：批次套用所有 LF

```python
from snorkel.labeling import PandasLFApplier

lfs = [lf_keyword_cancel, lf_regex_book]
applier = PandasLFApplier(lfs=lfs)
L_train = applier.apply(df=df_train)
# L_train 是 shape (n_samples, n_lfs) 的矩陣，值為 0、1 或 -1
```

### LabelModel：合併多個弱訊號

```python
from snorkel.labeling.model import LabelModel

label_model = LabelModel(cardinality=2, verbose=True)
label_model.fit(L_train=L_train, n_epochs=500, lr=0.001)
probs = label_model.predict_proba(L=L_train)
# probs[i] = [P(CANCEL|資料i), P(BOOK|資料i)]
```

LabelModel 不是多數決，它估計每個 LF 的可靠度（精確率），再加權合併投票。**關鍵假設**：各 LF 在給定真實標籤的條件下是獨立的。若兩個 LF 共享同一資訊來源，這個假設就會被違反。

### 輸出：軟標籤訓練集

```python
df_train["label"] = label_model.predict(L=L_train, tie_break_policy="abstain")
# 丟掉 abstain 的筆，剩下的送去訓練 BERT 或其他分類器
```

---

## 算例：設計 LF 並展示 label matrix

### 情境

有 5 封旅客訊息，分別是：

```
msg_0: "我要退票，退掉明天早上的"
msg_1: "我訂了 10 點的"
msg_2: "請幫我取消訂位"
msg_3: "我退了又訂了一張"
msg_4: "票還沒到，可以查一下嗎"
```

設計三條 LF：

```python
@labeling_function()
def lf_keyword_cancel(x):
    if "退票" in x.text or "退掉" in x.text:
        return CANCEL
    return ABSTAIN

@labeling_function()
def lf_keyword_cancel2(x):
    # 注意：這條和 lf_keyword_cancel 都只看「退」字
    if "取消" in x.text or "退了" in x.text:
        return CANCEL
    return ABSTAIN

@labeling_function()
def lf_regex_book(x):
    import re
    if re.search(r"訂了?\s*\d+\s*點", x.text):
        return BOOK
    return ABSTAIN
```

### Label Matrix

套用三條 LF 後得到矩陣（行=訊息，列=LF）：

```
         lf_cancel  lf_cancel2  lf_book
msg_0:     0(C)      -1(A)       -1(A)
msg_1:    -1(A)      -1(A)        1(B)
msg_2:    -1(A)       0(C)       -1(A)
msg_3:     0(C)       0(C)       -1(A)
msg_4:    -1(A)      -1(A)       -1(A)
```

（C=CANCEL, B=BOOK, A=ABSTAIN）

### 為何兩條同源 LF 會高估信心？

`lf_cancel` 和 `lf_cancel2` 本質上都在偵測「這句話是取消請求」，只是關鍵字不同。LabelModel 假設兩者條件獨立，但它們共享同一個底層訊號（訊息的語意）。

以 msg_3「我退了又訂了一張」為例，兩條 LF 都投 CANCEL。LabelModel 以為有兩個獨立訊源同意，信心大增；但實際上只是同一件事被數了兩次。若事後人工驗收，msg_3 其實同時包含取消和訂票，正確做法是抽取兩筆事件，而不是只標一個類別。

### 修正方式

在 Snorkel `LabelModel.fit` 加入依賴關係宣告：

```python
# 告訴 LabelModel 兩條 LF 相關
label_model.fit(L_train, deps=[(0, 1)])  # LF 0 和 LF 1 有依賴
```

或用覆蓋率分析找出高度相關的 LF 對，合併成一條。

---

## 主動學習三策略比較

當弱標注精準度仍不夠，需要少量人工標注時，主動學習（active learning）幫你挑最有價值的案件。

假設總標注預算 = 100 筆，資料池 = 10,000 筆未標注訊息。

### 策略一：Uncertainty Sampling（不確定性抽樣）

選模型最沒把握的案件（預測機率最接近 0.5 的）。

```
選法：|P(CANCEL) - 0.5| 最小的前 100 筆
優點：直接命中模型的弱點
缺點：若分數校準不良（模型過度自信），高信心的錯誤完全撈不到
```

### 策略二：Query by Committee（委員會查詢）

訓練多個模型（或用 ensemble），選模型間**分歧最大**的案件。

```
選法：5 個模型中，預測不一致筆數最多的前 100 筆
優點：不依賴單一模型的分數校準
缺點：若所有模型都在同一個方向犯錯（系統性偏差），分歧小但仍然全錯
```

### 策略三：Core-set（代表性選取）

把資料嵌入向量空間，選能覆蓋最大區域的 100 個「代表點」（貪婪最遠點算法）。

```
選法：在向量空間中，每次選距離現有已選點最遠的案件
優點：覆蓋多樣化的輸入分布，不偏向任何特定的不確定類型
缺點：向量表示若抓不到任務相關特徵（例如只看詞頻），稀有但重要的例外仍被忽略
```

### 同一預算下的覆蓋率比較

以訂位訊息資料池為例（模擬結果，說明原理）：

| 策略 | 100 筆標注後的模型 F1 | 覆蓋到的罕見情境比例 |
|---|---|---|
| Uncertainty Sampling | 高（快速修補邊界） | 低（集中在決策邊界附近） |
| Query by Committee | 中高（找出系統分歧） | 中（依賴 ensemble 多樣性） |
| Core-set | 中（覆蓋廣但每類樣本少） | 高（刻意挑遠離已知點的樣本） |

**結論**：三種策略沒有絕對優劣。資料分布不均時 core-set 更穩；模型分數可靠時 uncertainty sampling 收斂快。

---

## 反例

### 反例：分歧抽樣優先撈異常，錯誤率估計偏樂觀

假設你用 Query by Committee 挑了 100 筆，發現其中 30 筆錯（錯誤率 30%）。如果用這 30% 代表全庫錯誤率，會**嚴重高估**錯誤率——因為你刻意挑了最難的案件，普通案件的錯誤率遠低於 30%。

反過來，如果你只看模型最有把握的案件，錯誤率看起來很低，但遺漏了真正困難的情境。

**修正**：在主動學習的批次中，**保留一定比例（建議 10–20%）的隨機抽查**，用隨機樣本估計母體錯誤率，用主動學習樣本改進模型邊界。

```python
# 範例：80% 主動學習 + 20% 隨機抽查
n_active = 80
n_random = 20
active_indices  = uncertainty_sampling(model, unlabeled_pool, n=n_active)
random_indices  = random.sample(range(len(unlabeled_pool)), n_random)
to_label = active_indices + random_indices
```

---

## 工具

- **Snorkel `PandasLFApplier`**：把多條 LF 批次套用到 DataFrame，產生 label matrix
- **Snorkel `LabelModel`**：用 label matrix 學習各 LF 的可靠度，輸出機率標籤
- **modAL / scikit-activeml**：主動學習框架，支援 uncertainty sampling 和 query by committee
- **FAISS**：向量近鄰搜尋，用於 core-set 的最遠點計算

---

## 習題

**習題 1**：設計 LF 並分析依賴關係

針對以下三封訊息，設計兩條 LF（關鍵字比對和正規表達式各一），並手動填出 2×3 的 label matrix：

```
msg_A: "我的票訂好了，10:30 出發"
msg_B: "請幫我退掉那張票"
msg_C: "班次查詢，不是要訂票"
```

然後說明：若再加一條 LF 只是把第一條的關鍵字換成同義詞，會對 LabelModel 造成什麼影響？

<details><summary>解答</summary>

**LF 設計範例**：

```python
@labeling_function()
def lf_kw_book(x):
    if "訂好" in x.text or "訂了" in x.text:
        return BOOK
    return ABSTAIN

@labeling_function()
def lf_re_cancel(x):
    import re
    if re.search(r"退掉|退票", x.text):
        return CANCEL
    return ABSTAIN
```

**Label Matrix**：

```
       lf_kw_book  lf_re_cancel
msg_A:    1(B)        -1(A)
msg_B:   -1(A)         0(C)
msg_C:   -1(A)        -1(A)
```

**新增同義詞 LF 的影響**：

若新增 `lf_kw_book2`，把「訂好」換成「預訂成功」，兩條 LF 的觸發條件雖然不同，但底層偵測的都是「訂票成功」語意。

LabelModel 在獨立性假設下，會認為這是兩個獨立訊源同時投票，信心提升；但實際上只是同一訊號的兩種寫法。當兩條 LF 一起犯錯（例如「我沒訂好」也被兩條都偵測到），模型信心依然高，但預測是錯的。

修正方式：合併成一條 LF，或在 `LabelModel.fit` 中宣告依賴關係。

</details>

---

**習題 2**：解釋 abstain 的作用

以下是兩種 LF 設計方式：

```python
# 版本 A
def lf_A(x):
    if "票" in x.text:
        return CANCEL
    return ABSTAIN

# 版本 B
def lf_B(x):
    if "票" in x.text:
        return CANCEL
    return BOOK   # 沒有「票」就猜是 BOOK
```

哪個版本比較好？為什麼？如果資料中 70% 是 BOOK、30% 是 CANCEL，版本 B 的精確率估算會出現什麼偏差？

<details><summary>解答</summary>

**版本 A 比較好**。

理由：
- LF 的核心原則是「有把握才投票」。版本 B 在沒有任何訊號時猜 BOOK，引入了和任務無關的雜訊。
- LabelModel 估計 LF 精確率時，版本 B 的「猜測」票會被當成真正的投票計入，導致精確率估算偏低（看起來這條 LF 常猜錯）。

**版本 B 的偏差**：
- 若 70% 是 BOOK，「票」字在 BOOK 訊息也會出現，版本 B 在這些 BOOK 訊息上投 CANCEL，降低 CANCEL 的精確率估算
- 若 30% 是 CANCEL，沒有「票」字的 CANCEL 訊息（例如「取消預約」），版本 B 會錯誤地投 BOOK
- 整體來說，版本 B 表面上覆蓋率（coverage）高，但雜訊率（noise rate）也同步升高，LabelModel 的加權效果會被稀釋

</details>

---

**習題 3**：主動學習策略選型

你的訂位分類系統已部署三個月，模型整體準確率 92%，但你發現在「旅客表示候補成功後改訂」這種情境下，準確率只有 60%。你有 50 筆額外標注預算。應選哪種主動學習策略？為什麼？是否需要加入隨機抽查？

<details><summary>解答</summary>

**建議策略**：Uncertainty Sampling + 人工篩選特定情境。

推論過程：
1. 你已知問題所在（候補轉訂的情境），這是有方向的改進，不需要廣泛覆蓋（core-set 的優勢在此用不到）
2. 對已知困難情境，uncertainty sampling 能快速命中模型在這類案件上的決策邊界
3. 若模型在候補相關案件的分數校準不良，可以配合 Query by Committee 做交叉確認

**隨機抽查的必要性**：
- 是的，建議用 10 筆（20%）做隨機抽查
- 原因：你想知道候補情境的改進是否影響了其他類型的案件（regression）。只看候補情境無法得知全庫的錯誤率變化
- 50 筆分配建議：40 筆針對候補情境的 uncertainty sampling，10 筆全庫隨機抽查

</details>

---

[← 上一頁](02-ner-and-events.md) · [本章導覽](intro.md) · [總目錄](../../README.md#課程地圖) · [下一頁 →](04-expert-review.md)
