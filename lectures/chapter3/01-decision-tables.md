# 3.1 把自然語言落成可執行規則（Decision Tables）

[← 上一頁](intro.md) · [本章導覽](intro.md) · [總目錄](../../README.md#課程地圖) · [下一頁 →](02-knowledge-graphs.md)

---

## 學習目標

完成本節後，你能夠：

1. 把一段取消政策文字逐步轉成 DMN 決策表（Decision Model and Notation decision table）。
2. 解釋 Unique、First、Collect 三種 hit policy 的差異，並說明各自適用的情境。
3. 用 FEEL（Friendly Enough Expression Language）表示時間區間、日期比較與 null 語意。
4. 說明為何不能把「不知道是否能延後」當成 false，並避免誤套分支。

**先備知識：** 看得懂 Excel 的 `IF` 函數、了解關聯式資料庫的基本概念即可。

---

## 1. 背景橋樑：從 Excel 巢狀 IF 到決策表

假設你在 Excel 裡管理取消費率：

```
=IF(DAYS(A2, TODAY()) >= 7, "免費取消",
   IF(DAYS(A2, TODAY()) >= 3, "收 50%",
      IF(DAYS(A2, TODAY()) >= 1, "收 80%", "不退款")))
```

這段邏輯在試算表裡還算可讀，但一旦需求變動（例如「VIP 會員永遠免費取消」），你必須：

- 在巢狀 `IF` 中插入新層，測試後才知道順序是否正確。
- 若有多個工作表共用同一邏輯，要一份一份修改，容易漏掉。
- 無法自動生成「這套規則涵蓋了哪些組合」的文件。

**決策表（Decision Table）** 解決了這三個問題：

| 問題 | Excel IF | 決策表 |
|------|----------|--------|
| 新增規則 | 插入巢狀層，要重測 | 新增一列，可視化 |
| 規則文件 | 程式碼即文件，難讀 | 表格即文件 |
| 完備性驗證 | 人工檢查 | 工具可自動檢查 gap/overlap |

DMN（Decision Model and Notation）是 OMG 制定的開放標準，定義了決策表的語法與語意，可匯入 Camunda、Drools 等引擎直接執行。

---

## 2. 任務定義

**輸入：** 自然語言政策文件，例如一段住宿取消政策。

**輸出：** 可由規則引擎執行的 DMN 決策表，包含：
- 輸入欄（input expression）：條件變數及其比較方式
- 輸出欄（output expression）：決策結果
- 規則列（rules）：每一列是一條 if-then 規則
- Hit policy：多列命中時的處理策略

**子任務：**
1. 識別政策文字中的條件變數（例如「預計抵達時間」）。
2. 識別輸出變數（例如「建議處置」）。
3. 把每個情境對應到一列規則。
4. 選擇適合的 hit policy。
5. 用 FEEL 語法表達比較式。

---

## 3. DMN 決策表架構

### 3.1 四個組成要素

```
┌──────────────────────────────────────────────────────────────┐
│  Hit Policy: U (Unique)                                      │
├────────────────────┬──────────────────┬──────────────────────┤
│  INPUT             │  INPUT           │  OUTPUT              │
│  預計抵達時間       │  旅館已確認可晚到 │  建議處置            │
│  arrivalTime       │  hotelConsented  │  action              │
├────────────────────┼──────────────────┼──────────────────────┤
│  rule 1            │  -               │  "照原安排"           │
│  rule 2            │  -               │  "向住宿確認"         │
│  rule 3            │  -               │  "補抵達時間"         │
│  rule 4            │  -               │  "查入住條件"         │
└────────────────────┴──────────────────┴──────────────────────┘
```

### 3.2 FEEL 語法重點

FEEL（Friendly Enough Expression Language）是 DMN 的配套運算語言。

**區間（Interval）：**
```
[a..b]  → 閉區間，包含 a 和 b
(a..b)  → 開區間，不包含 a 和 b
[a..b)  → 半開區間，包含 a 但不包含 b（常用於時間）
```

**時間與日期：**
```feel
time("21:00")               → 21 點整
date("2024-04-01")          → 日期字面值
date and time("2024-04-01T21:00:00+01:00")  → 含時區的時間點
duration("P1D")             → 1 天的 duration
```

**null 語意（null semantics）：**
- FEEL 中 `null` 表示「不知道」或「不適用」，不等於 false。
- `null < time("21:00")` 的結果是 `null`（不是 true 也不是 false）。
- 規則引擎對 null 輸入的處理：這一列規則不命中（因為條件無法確定為 true）。

**萬用（Any）：**
```feel
-   → 此輸入欄不限制（任何值均符合）
```

---

## 4. 完整算例：薩爾斯堡住宿取消政策

### 4.1 原始政策文字

```
薩爾斯堡 Hotel Amadeus 住宿條款（2024）

入住截止時間：晚間 21:00。
旅客若無法在 21:00 前抵達，須提前與旅館聯繫。
旅館確認可晚到者，不視為逾時。

取消政策：
- 入住日前 7 天（含）以前取消：全額退款。
- 入住日前 3 天（含）至 6 天取消：退款 50%。
- 入住日前 1 天取消：退款 20%。
- 入住日當天或未到（no-show）：不退款。
```

### 4.2 步驟一：識別條件與輸出

從政策文字提取：

| 角色 | 變數名稱 | 型別 | 說明 |
|------|----------|------|------|
| 輸入 | `arrivalTime` | `time` | 旅客預計入住時間 |
| 輸入 | `hotelConsented` | `boolean` 或 `null` | 旅館是否確認可晚到 |
| 輸入 | `daysBeforeCheckin` | `integer` | 取消距入住幾天 |
| 輸出 | `action` | `string` | 建議處置 |
| 輸出 | `refundRate` | `number` | 退款比率（0.0–1.0） |

### 4.3 步驟二：建決策表（入住時間判斷）

Hit policy **U（Unique）**：每一筆輸入至多命中一列。

| # | arrivalTime（FEEL） | hotelConsented | action |
|---|---------------------|----------------|--------|
| 1 | `<= time("21:00")`  | `-`            | `"照原安排"` |
| 2 | `> time("21:00")`   | `true`         | `"照原安排（旅館已確認）"` |
| 3 | `> time("21:00")`   | `false`        | `"向住宿確認或更改計劃"` |
| 4 | `> time("21:00")`   | `null`         | `"先確認旅館是否同意晚到"` |
| 5 | `null`              | `-`            | `"補充預計抵達時間"` |

**如何讀這張表：**
- 第 1 列：只要抵達不超過 21:00，不管旅館有沒有確認，都照原安排。
- 第 2–4 列：超過 21:00 但需分三種子情況（已確認/明確不能/不確定）。
- 第 5 列：根本不知道幾點到，優先補資訊。

### 4.4 步驟三：建決策表（取消退款）

| # | daysBeforeCheckin（FEEL） | refundRate | action |
|---|--------------------------|------------|--------|
| 1 | `>= 7`                   | `1.0`      | `"全額退款"` |
| 2 | `[3..7)`                 | `0.5`      | `"退款 50%"` |
| 3 | `1`                      | `0.2`      | `"退款 20%"` |
| 4 | `0`                      | `0.0`      | `"不退款（no-show 或當天取消）"` |
| 5 | `null`                   | `null`     | `"補充取消日期"` |

**FEEL 區間說明：**
- `[3..7)` 表示「大於等於 3、小於 7」，即 3、4、5、6 天前。
- 這避免了第 1 列與第 2 列在第 7 天邊界的 overlap。

### 4.5 完整欄位對照

以輸入「`arrivalTime = time("21:30")`、`hotelConsented = null`」為例：

1. 引擎評估第 1 列：`time("21:30") <= time("21:00")` → false，跳過。
2. 引擎評估第 2 列：`time("21:30") > time("21:00")` → true；`hotelConsented = true` → `null = true` → null，整列 null，跳過。
3. 引擎評估第 3 列：同上，`null = false` → null，跳過。
4. 引擎評估第 4 列：`time("21:30") > time("21:00")` → true；`hotelConsented = null` → true。**命中。**
5. 輸出：`action = "先確認旅館是否同意晚到"`。

---

## 5. 反例：null 語意被忽略的後果

**問題情境：** 開發者把表格匯出成 Python，直接寫成：

```python
def check_arrival(arrival_time, hotel_consented):
    if arrival_time > "21:00":
        if hotel_consented:          # ← 把 None 當 falsy
            return "照原安排（旅館已確認）"
        else:                        # ← None 和 False 走同一條路
            return "向住宿確認或更改計劃"
    return "照原安排"
```

**後果：**
- 旅客還沒查過旅館意見（`hotel_consented = None`），系統誤判為「旅館不同意」。
- 助理發出「請更改計劃」的通知，但旅館其實同意晚到。
- 旅客信任系統，取消了原本不必取消的安排。

**正確 Python 寫法：**

```python
def check_arrival(arrival_time, hotel_consented):
    if arrival_time is None:
        return "補充預計抵達時間"
    if arrival_time > time(21, 0):
        if hotel_consented is True:
            return "照原安排（旅館已確認）"
        elif hotel_consented is False:
            return "向住宿確認或更改計劃"
        else:  # hotel_consented is None
            return "先確認旅館是否同意晚到"
    return "照原安排"
```

**核心原則：** null（未知）≠ false（已知為否）。規則表達要三值邏輯：true / false / null。

---

## 6. 方法比較與選型

### 6.1 三種 Hit Policy

| Hit Policy | 符號 | 語意 | 適用情境 |
|------------|------|------|----------|
| Unique | U | 至多一列命中，多列命中視為錯誤 | 互斥決策（取消費率、入住判斷） |
| First | F | 按列順序，第一個命中即回傳 | 有優先例外的規則（VIP > 一般） |
| Collect | C | 蒐集所有命中列的輸出 | 一個動作觸發多個後續步驟 |

**Unique 的優點：** 工具可以自動驗證「是否有缺口（gap）」與「是否有重疊（overlap）」，讓規則完備性可機器驗證。

**First 的陷阱：** 規則順序就是業務邏輯的一部分，調換列順序可能改變輸出，不易維護。

**Collect 範例：** 若一個訂單滿足「超重」與「跨境」兩條規則，系統可同時觸發「加收行李費」與「申報關稅」兩個動作。

### 6.2 DMN vs Python if-else vs 規則引擎

| 面向 | Python if-else | DMN 決策表 | 規則引擎（Camunda/Drools） |
|------|---------------|------------|---------------------------|
| 假設 | 開發者寫死邏輯 | 業務分析師可直接編輯 | 分離規則與應用程式 |
| 可維護性 | 低（需改碼） | 高（表格即文件） | 高（熱更新） |
| 完備性驗證 | 人工 | 工具支援 | 工具支援 |
| 偵錯難度 | 中（加 print） | 低（逐列命中可追蹤） | 低（有審計日誌） |
| 適用規模 | < 10 條規則 | 10–100 條 | > 100 條或需熱更新 |
| 學習成本 | 無 | 低 | 中 |

**選型建議：**
- 規則少且不常改 → Python if-else 夠用。
- 規則由業務部門維護且需要文件 → DMN 決策表。
- 規則需要在不停機的情況下上線 → 規則引擎。

---

## 7. 工具

### Camunda DMN Modeler

- 免費桌面應用（macOS / Windows / Linux）。
- 可視化編輯決策表，自動高亮 gap 與 overlap。
- 匯出 `.dmn` XML，可直接部署到 Camunda 引擎。
- 下載：https://camunda.com/download/modeler/

### Python 驗證範例（不需引擎）

```python
# pip install dmn-eval-js (Node) 或直接用 Python dict 模擬
rules = [
    {"days": (7, None),  "refund": 1.0,  "action": "全額退款"},
    {"days": (3, 7),     "refund": 0.5,  "action": "退款 50%"},
    {"days": (1, 3),     "refund": 0.2,  "action": "退款 20%"},
    {"days": (0, 1),     "refund": 0.0,  "action": "不退款"},
]

def evaluate(days_before: int | None):
    if days_before is None:
        return {"action": "補充取消日期", "refund": None}
    for rule in rules:
        lo, hi = rule["days"]
        if (lo is None or days_before >= lo) and (hi is None or days_before < hi):
            return rule
    return {"action": "無符合規則", "refund": None}

print(evaluate(5))   # → 退款 50%
print(evaluate(0))   # → 不退款
print(evaluate(None)) # → 補充取消日期
```

---

## 8. 習題

**題 1（機制）：** FEEL 的 `[3..7)` 與 `(3..7]` 分別包含哪些整數？為什麼取消政策要用半開區間而非閉區間？

<details><summary>解答</summary>

- `[3..7)` 包含 3、4、5、6（包含左端點，不含右端點）。
- `(3..7]` 包含 4、5、6、7（不含左端點，包含右端點）。
- 取消政策用半開區間 `[3..7)` 配合 `>= 7`，可以讓兩列規則在邊界（第 7 天）不重疊：第 7 天恰好落在「>= 7」的第 1 列，不會同時落在「[3..7)」的第 2 列。如果用閉區間 `[3..7]`，第 7 天就會同時命中兩列，在 Unique hit policy 下引擎會報錯。

</details>

---

**題 2（手算）：** 旅客在入住日前 2 天取消，且取消日期為 `null`。請逐列說明退款決策表如何處理，最終輸出什麼？

<details><summary>解答</summary>

輸入：`daysBeforeCheckin = null`

逐列評估（Unique hit policy）：
1. 第 1 列：`null >= 7` → null，不命中。
2. 第 2 列：`null in [3..7)` → null，不命中。
3. 第 3 列：`null = 1` → null，不命中。
4. 第 4 列：`null = 0` → null，不命中。
5. 第 5 列：`null = null` → true，**命中**。

輸出：`action = "補充取消日期"`，`refundRate = null`。

注意：FEEL 中 `null = null` 在規則比對語境下為 true（表示「這個欄位是 null 時觸發此規則」），而非一般語言的 `NULL = NULL` 為 unknown。

</details>

---

**題 3（選型）：** 旅行社需要在不停機的情況下，每週更新一次機票退款規則（由法務部門維護試算表）。應選 Python if-else、DMN 決策表還是規則引擎？說明理由，並指出各方案的主要風險。

<details><summary>解答</summary>

**建議選：DMN 決策表 + 規則引擎（例如 Camunda）。**

理由：
1. 法務部門維護試算表，說明規則維護者不是工程師 → 需要非工程師可操作的介面（DMN 表格）。
2. 每週更新 → 每週都要改碼並部署的 Python if-else 成本高且易出錯。
3. 不停機 → 規則引擎支援熱更新，不需重啟服務。

各方案風險：
- **Python if-else：** 每次修改需工程師介入、重新部署、測試。法務無法自行驗證邏輯。
- **DMN 只用 Camunda Modeler（不接引擎）：** 法務可編輯表格，但還是要工程師手動同步到程式碼，仍有落差風險。
- **DMN + 規則引擎：** 主要風險是初期建置成本較高，且需要法務學習 DMN 工具操作。可以透過培訓降低。

</details>

---

[← 上一頁](intro.md) · [本章導覽](intro.md) · [總目錄](../../README.md#課程地圖) · [下一頁 →](02-knowledge-graphs.md)
