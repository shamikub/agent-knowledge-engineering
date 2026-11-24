# 2.2 命名實體識別與事件抽取

## 學習目標

完成本節後，你能夠：

- 分辨 NER mention（命名實體識別提及）、entity linking（實體連結）、事件抽取（event extraction）三層的輸入與輸出
- 說明 BIO tagging 的標記邏輯並手算一個序列解碼步驟
- 解釋為何 JSON 解析成功不等於語義正確，以及相對時間未解析會造成什麼問題
- 比較 CRF、Transformer token 分類、受限生成三種方法的適用場景

**先備知識**：知道什麼是 token（文字切割單位）；能看懂基本 Python 型別（dict、list、str）。

---

## 任務定義

### 三層抽取的輸入輸出

給定一段對話文字，資訊萃取系統要依序完成三件事：

| 層次 | 輸入 | 輸出 |
|---|---|---|
| NER mention | 原始文字 | 文字片段（span）與類別，例如 `「10 點」→ TIME` |
| Entity linking | mention + 知識庫 | mention 對應哪個真實物件（例如哪張票） |
| 事件抽取 | 文字 + 預定義 schema | 填好欄位的事件紀錄 |

三層是疊加關係——下層錯了，上層必定錯；但下層對了，上層仍可能連錯。

### 以訂位改票情境為例

原始輸入（旅客對客服說的話）：

```
我退掉 8 點那張，訂了 10 點。
```

期望輸出（兩筆事件各一個 JSON 物件）：

```json
[
  {
    "event_type": "CANCEL",
    "agent": "旅客",
    "ticket_ref": "8 點那張",
    "time_mentioned": "8 點",
    "time_resolved": null
  },
  {
    "event_type": "BOOK",
    "agent": "旅客",
    "ticket_ref": null,
    "time_mentioned": "10 點",
    "time_resolved": null
  }
]
```

注意 `time_resolved` 目前為 `null`：「8 點」是當天哪一天哪個時區的班次？沒有發言時間與時區，就無法從相對時間推算成絕對時間。

### 事件 Schema 的四個欄位

以 CANCEL 事件為例，定義如下：

```
CANCEL
  ├── agent      （誰取消）→ 旅客識別碼或代稱
  ├── ticket_ref （取消哪張）→ 指向知識庫中某筆票券
  ├── time_mentioned（文字裡提到的時間原文）
  └── time_resolved （換算後的 ISO 8601 時間戳，可空）
```

---

## 架構說明：從 token 到 JSON

### 步驟一：BIO 標記（token 分類）

BIO 是一種標籤體系：

- **B-XXX**：某類別 span 的開頭 token
- **I-XXX**：同類別 span 的延續 token
- **O**：不屬於任何 span 的 token

以「我 退掉 8 點 那張 ，訂了 10 點 。」為例（已切 token）：

```
token:  我    退掉   8    點   那張  ，   訂了   10   點   。
label:  O     O    B-TIME I-TIME O   O    O    B-TIME I-TIME O
```

「8 點」跨兩個 token，所以第一個標 `B-TIME`，第二個標 `I-TIME`。

### 步驟二：CRF 加入相鄰標籤的約束

單純的 token 分類器對每個位置獨立打分，可能輸出「O → I-TIME」這種非法序列（沒有 B 就出現 I）。線性鏈 CRF（linear-chain Conditional Random Field）加上**轉移分數矩陣**，給不合法的轉移一個很低的分數，再用 Viterbi 演算法找全域最高分的標籤序列。

**Viterbi 核心邏輯（偽碼）**：
```
dp[0][tag] = emission[0][tag]
for t in 1..T:
    for tag in TAGS:
        dp[t][tag] = max over prev_tag (dp[t-1][prev_tag] + trans[prev_tag][tag]) + emission[t][tag]
最優序列 = 從 dp[T] 最大值反向回溯
```

### 步驟三：Transformer 提供上下文表示

BERT 等 Transformer 模型把整段文字一起編碼，每個 token 的表示都含有上下文資訊。把 Transformer 輸出接上一層分類頭，就能預測每個 token 的 BIO 標籤。好處是不需要手工設計特徵；代價是需要 GPU 與標注資料。

### 步驟四：受限生成輸出 JSON

讓語言模型直接輸出 JSON，配合 token 層面的 logit 遮罩（logit masking），強制模型只能生成符合 schema 的字元序列。搭配 Pydantic `BaseModel.model_validate` 做型別與必填欄位檢查：

```python
from pydantic import BaseModel
from typing import Optional

class CancelEvent(BaseModel):
    event_type: str
    agent: str
    ticket_ref: Optional[str]
    time_mentioned: Optional[str]
    time_resolved: Optional[str]  # 必須是 ISO 8601 或 null

raw = '{"event_type":"CANCEL","agent":"旅客","ticket_ref":"8點那張","time_mentioned":"8點","time_resolved":null}'
event = CancelEvent.model_validate_json(raw)
print(event)
```

Pydantic 只驗證**形狀與型別**，不驗證語義。`time_resolved` 是 `null` 能通過驗證，但業務上可能需要它有值才能查票。

---

## 完整算例

### 情境

時間：2024 年 3 月 15 日上午 10:30，旅客 A 在台灣（UTC+8）傳送訊息：

```
我退掉 8 點那張，訂了 10 點。
```

### 步驟一：切 token 並打 BIO 標籤

```
我(O) 退掉(O) 8(B-TIME) 點(I-TIME) 那張(O) ，(O) 訂了(O) 10(B-TIME) 點(I-TIME) 。(O)
```

### 步驟二：CRF 轉移分數算例

假設 Transformer 給出第 3 個 token「8」的 emission 分數：

```
emission["8"][B-TIME] = 4.0
emission["8"][I-TIME] = 1.0
emission["8"][O]      = 0.5
```

前一個 token「退掉」的最佳標籤是 O，分數為 2.0。轉移矩陣片段：

```
trans[O → B-TIME] =  0.0  （合法，不懲罰）
trans[O → I-TIME] = -5.0  （非法，重懲罰）
trans[O → O]      =  0.5
```

計算「8」的各標籤候選分數：

```
dp[O→B-TIME] = 2.0 + 0.0 + 4.0 = 6.0  ← 最高
dp[O→I-TIME] = 2.0 + (-5.0) + 1.0 = -2.0
dp[O→O]      = 2.0 + 0.5 + 0.5 = 3.0
```

因此「8」選 B-TIME，序列延續到「點」時 I-TIME 的前驅是 B-TIME，轉移合法，整段得到正確標記。

### 步驟三：NER 結果 → Entity linking

NER 識別出兩個 TIME mention：「8 點」和「10 點」。

Entity linking 要把這兩個時間對應到票券系統中的班次。**所需資訊**：

1. 發言時間（2024-03-15T10:30+08:00）→ 推斷「8 點」指的是當天
2. 旅客 A 的歷史訂單 → 找到「2024-03-15 08:00」的那張票
3. 路線與出發地 → 確認「10 點」有無對應可訂班次

缺少任何一項，entity linking 就會回傳多個候選或失敗。

### 步驟四：填入 schema

```json
{
  "event_type": "CANCEL",
  "agent": "旅客A",
  "ticket_ref": "ORDER-20240315-0800",
  "time_mentioned": "8 點",
  "time_resolved": "2024-03-15T08:00:00+08:00"
}
```

---

## 反例

### 反例一：JSON 格式正確，但時間未解析

模型輸出：

```json
{"event_type": "CANCEL", "time_resolved": "8 點"}
```

Pydantic 驗證時 `time_resolved` 型別是 `Optional[str]`，「8 點」是合法字串，**驗證通過**。但業務系統拿「8 點」去查票券會失敗，因為它不是 ISO 8601 格式。

正確做法：在 Pydantic model 加上驗證器，或規定 `time_resolved` 只接受 `datetime` 型別。

### 反例二：Entity linking 把兩張不同票連成同一個

A 和 B 同日都訂了早上 8 點的票。訊息是：

```
我們退掉 8 點那張。
```

entity linking 若只依日期和時間排序取第一筆，可能誤把 B 的票連到 A 的取消事件。需要加入旅客 ID 作為過濾條件。

---

## 方法比較與選型

| 方法 | 核心假設 | 優點 | 缺點 | 評估指標 |
|---|---|---|---|---|
| CRF（線性鏈） | 標籤僅與相鄰標籤有依賴 | 訓練資料少也能學轉移約束 | 需要手工特徵；長距依賴弱 | Span F1 |
| Transformer token 分類 | 上下文表示已夠豐富 | 無需手工特徵；跨句理解佳 | 需 GPU；小資料易過擬合 | Span F1、欄位精確率/召回率 |
| 受限生成（LLM + schema） | LLM 已有世界知識，schema 控制格式 | 零/少樣本即可用；處理跨句複雜事件 | 推論成本高；需獨立驗證 entity 正確性 | 欄位精確率/召回率、完整事件完全比對 |

**選型建議**：
- 格式固定、訓練資料 > 1000 筆 → Transformer token 分類
- 格式多變、例外多、資料少 → 受限生成 + Pydantic 驗證
- 有轉移約束需求但算力有限 → CRF 作為後處理層疊加在 Transformer 上（BERT-CRF）

---

## 工具

- **Pydantic `BaseModel.model_validate`**：驗證 JSON 物件的型別與必填欄位
- **HuggingFace Transformers**：`AutoModelForTokenClassification` 實作 BIO token 分類
- **spaCy**：內建 NER pipeline，可自訂標籤集
- **outlines / guidance**：受限生成，強制 LLM 輸出符合 JSON schema 的序列

---

## 習題

**習題 1**：畫出事件 schema

給定旅客對話：
> 「幫我把週五晚上 9 點的高鐵票退掉，然後改訂週六早上 7 點的。」

請畫出 CANCEL 和 BOOK 兩個事件的 schema，列出各欄位名稱、資料型別，以及哪些欄位在沒有更多資訊時必須設為 null。

<details><summary>解答</summary>

```
CANCEL
  ├── event_type: "CANCEL"
  ├── agent: str           ← 對話中未明確說旅客姓名，可從 session 取得
  ├── ticket_ref: str|null ← 需要 entity linking 才能確認是哪張票
  ├── time_mentioned: "週五晚上 9 點"
  └── time_resolved: datetime|null ← 需知道「週五」是哪個日期，沒有發言日期則 null

BOOK
  ├── event_type: "BOOK"
  ├── agent: str
  ├── ticket_ref: null     ← 新票尚未建立，沒有 ref
  ├── time_mentioned: "週六早上 7 點"
  └── time_resolved: datetime|null ← 同上
```

關鍵說明：「週五」是相對時間，必須知道**發言當天的日期**（以及時區）才能換算成絕對時間。在沒有這項資訊的情況下，`time_resolved` 必須設為 `null`，不能填入推測值。

</details>

---

**習題 2**：解釋 BIO 標記失敗情境

以下是一個模型輸出的 BIO 標記序列（token 與標籤對應）：

```
週(B-DATE) 五(I-DATE) 晚(I-DATE) 上(I-DATE) 9(B-TIME) 點(I-TIME)
```

請指出哪裡可能出問題，並解釋若改用加了合法轉移約束的 CRF，會如何避免這類問題。

<details><summary>解答</summary>

**問題**：「週五晚上」被當成同一個 DATE span（B-DATE 後面跟三個 I-DATE），但「晚上」是時段修飾語，應該和「9 點」合在一起形成 TIME span，或單獨處理。這個錯誤源自 schema 設計不清楚（DATE 和 TIME 的邊界在哪）。

另一個常見失敗情境是模型直接輸出「O → I-DATE」的非法序列（沒有 B 就出現 I），例如：

```
週(O) 五(I-DATE) 晚(I-DATE)
```

**CRF 如何避免**：CRF 的轉移矩陣會對 `O → I-DATE` 這種非法轉移加極低分（如 -∞ 或 -5.0），使 Viterbi 解碼時永遠不會選出這條路徑。但 CRF 只能修正**相鄰標籤**的合法性，無法修正更深層的 schema 設計問題（例如 DATE 和 TIME 邊界不清）。

</details>

---

**習題 3**：方法選型

你負責一個旅遊客服系統，每天收到約 500 則訊息，格式相當固定（確認信模板），但偶爾會有旅客用非標準的口語說法。目前人工標注資料約 300 筆。應選哪種抽取方法？請說明理由，並指出若標注資料增加到 2000 筆時是否應改方法。

<details><summary>解答</summary>

**目前建議**：Transformer token 分類（例如 BERT-CRF）。

理由：
1. 300 筆資料已足夠微調一個小型 Transformer，可取得不錯的 span F1
2. 格式相對固定，token 分類的標籤集容易定義
3. 若有非標準口語，Transformer 的上下文表示比純 CRF 更有彈性

**不建議受限生成**的原因：500 則/天的量不大，推論成本和延遲對正式系統有壓力；且格式固定時，受限生成的優勢（處理多變格式）發揮不出來。

**資料增到 2000 筆時**：仍建議 Transformer token 分類為主，可考慮加入 CRF 層（BERT-CRF）提升序列合法性。若未來格式變多、例外增加，才值得評估切換到受限生成。

</details>

---

[章節導覽](intro.md) · [上一節](01-schema-design.md) · [下一節](03-weak-supervision.md)
