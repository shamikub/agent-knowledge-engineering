# 2.1 在抽取之前：定義你要的結構

[← 上一頁](intro.md) · [本章導覽](intro.md) · [總目錄](../../README.md#課程地圖) · [下一頁 →](02-ner-and-events.md)

## 學習目標

完成本節後，你能夠：

- 能設計一個「訂位確認」的抽取 schema（包含欄位名稱、型別、必填性）
- 能說明 flat schema 和 nested schema 的取捨
- 能識別 schema 設計中三種常見錯誤

**先備知識**：知道什麼是 JSON；能看懂基本 Python 型別（dict、list、str、Optional）。

---

## 為什麼 schema 設計比抽取更重要

在開始寫任何抽取程式碼之前，你必須先回答一個問題：**你到底要抽什麼？**

這個問題聽起來簡單，但實務中大多數資訊抽取專案失敗，不是因為抽取技術不好，而是因為 schema 設計錯了——抽到了資料，但下游系統根本用不了。

### 壞的 schema：能抽到，但下游用不了

考慮一個旅遊訂位確認信的抽取任務。假設你設計了以下 schema：

```json
{
  "flight": "TPE-NRT",
  "time": "09:00-12:00",
  "passenger": "王小明",
  "price": "NT$5,200"
}
```

這個 schema 表面上「抽到了」資料，但下游系統要做什麼？

- **查詢「出發時間是幾點的班次」** → 沒辦法，因為 `"09:00-12:00"` 是一個字串，無法直接比較
- **計算「飛行時長」** → 沒辦法，出發和抵達被存在同一個字串裡
- **篩選「NT$5,200 以下的票」** → 要先剝除「NT$」前綴才能比較數字

**根本問題**：把兩個不同語意的值（出發時間和抵達時間）塞進同一個欄位，把有單位的數字存成字串——這讓每個下游查詢都要先解析字串，既脆弱又低效。

### 好的 schema：每個欄位都有明確的型別和語意

```json
{
  "route": {
    "origin": "TPE",
    "destination": "NRT"
  },
  "departure_time": "2024-03-15T09:00:00+08:00",
  "arrival_time": "2024-03-15T12:00:00+09:00",
  "passenger_name": "王小明",
  "price_ntd": 5200
}
```

現在每個下游查詢都很直接：
- 「出發時間幾點？」→ 解析 `departure_time` 的 ISO 8601 字串
- 「飛行時長？」→ `arrival_time - departure_time`
- 「NT$5,200 以下？」→ `price_ntd <= 5200`

---

## Schema 設計的四個步驟

好的 schema 設計是由**下游需求**驅動的，而不是由原始文字的格式驅動的。

### 步驟一：列出下游需要回答哪些問題

在設計任何欄位之前，先和下游系統的負責人開會，列出他們最常查詢的問題清單。例如：

- 這張票的出發時間是幾點？
- 這張票是哪條航線（起點和終點）？
- 旅客姓名是什麼？
- 票價是多少（數字，不含單位）？
- 是否含行李額度？如果有，幾公斤？

### 步驟二：從問題推出需要哪些欄位

每個問題對應一個（或一組）欄位：

| 問題 | 欄位 |
|---|---|
| 出發時間 | `departure_time` |
| 抵達時間 | `arrival_time` |
| 起點 | `origin_airport` |
| 終點 | `destination_airport` |
| 旅客姓名 | `passenger_name` |
| 票價（數字） | `price_ntd` |
| 含行李 | `baggage_kg`（null 表示不含） |

### 步驟三：決定每個欄位的型別

常用的四種基本型別：

| 型別 | 適用場景 | 範例 |
|---|---|---|
| `string` | 自然語言文字、識別碼 | 旅客姓名、訂單編號 |
| `datetime` | 時間點（需要計算或排序） | 出發時間、抵達時間 |
| `enum` | 固定集合中的一個值 | 艙等（ECONOMY / BUSINESS / FIRST） |
| `list` | 多個同型別的值 | 旅客清單、附加服務清單 |

**選型原則**：如果下游要排序、比較、或計算這個欄位，就不能用 `string`。

### 步驟四：決定哪些欄位在抽取失敗時可以是 null

並非所有欄位都能從每封確認信中抽取出來。設計時要明確標出：

- **必填（required）**：沒有這個值就無法使用這筆資料，抽取失敗直接丟棄
- **選填（optional / nullable）**：沒有也沒關係，下游可以處理 null

例如：
- `departure_time` → 必填（沒有出發時間的票沒有意義）
- `baggage_kg` → 選填（部分票種不包含行李額度）
- `meal_preference` → 選填（大多數訂單不填）

---

## 完整算例：訂位確認信的 schema 設計

### 原始輸入

```
親愛的王小明先生：

您的訂位已確認。

航班：CI 100
路線：台北（TPE）→ 東京成田（NRT）
出發：2024 年 3 月 15 日 09:00（台灣時間）
抵達：2024 年 3 月 15 日 12:00（日本時間）
艙等：商務艙
票價：新台幣 25,800 元
行李：30 公斤
訂單號碼：CI-20240315-100-SMW
```

### 壞的 schema 一：過於扁平（Flat Schema）

```json
{
  "info": "CI 100, TPE-NRT, 2024/3/15, 09:00-12:00, 商務艙, 25800, 30kg, CI-20240315-100-SMW"
}
```

**問題**：把所有資訊塞進一個字串，完全無法查詢或比較任何欄位。這是最糟糕的 schema。

### 壞的 schema 二：過於巢狀（Nested Schema）

```json
{
  "booking": {
    "flight": {
      "info": {
        "number": {
          "value": "CI 100"
        }
      },
      "schedule": {
        "departure": {
          "location": {
            "code": "TPE",
            "name": "台北桃園"
          },
          "time": {
            "local": "09:00",
            "date": "2024-03-15",
            "timezone": "Asia/Taipei"
          }
        }
      }
    }
  }
}
```

**問題**：每個值都被埋在深層巢狀結構裡，查詢航班號要寫 `booking.flight.info.number.value`，結構複雜但沒有增加任何語意清晰度。巢狀超過三層通常是設計過度的訊號。

### 好的 schema

```json
{
  "flight_number": "CI100",
  "origin": "TPE",
  "destination": "NRT",
  "departure_time": "2024-03-15T09:00:00+08:00",
  "arrival_time": "2024-03-15T12:00:00+09:00",
  "cabin_class": "BUSINESS",
  "price_ntd": 25800,
  "baggage_kg": 30,
  "passenger_name": "王小明",
  "booking_ref": "CI-20240315-100-SMW"
}
```

**每個設計決定的說明**：

| 欄位 | 設計決定 | 理由 |
|---|---|---|
| `departure_time` | ISO 8601 完整時間戳（含時區） | 需要和其他時區的時間比較和計算 |
| `cabin_class` | enum 字串（全大寫） | 艙等是有限集合，大寫方便比較 |
| `price_ntd` | 整數（不含單位） | 下游要比較和加總，不需要「NT$」前綴 |
| `baggage_kg` | 整數或 null | 有些票不含行李，需要能表示「不含」 |
| `origin` / `destination` | IATA 三碼 | 標準化代碼，不用擔心中英文混用 |

### 用 Pydantic 寫出對應的程式碼

```python
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from enum import Enum

class CabinClass(str, Enum):
    ECONOMY = "ECONOMY"
    BUSINESS = "BUSINESS"
    FIRST = "FIRST"

class FlightBooking(BaseModel):
    flight_number: str
    origin: str                        # IATA 三碼，例如 "TPE"
    destination: str                   # IATA 三碼，例如 "NRT"
    departure_time: datetime           # 必填，含時區
    arrival_time: datetime             # 必填，含時區
    cabin_class: CabinClass            # 必填，只接受三種值
    price_ntd: int                     # 必填，整數
    baggage_kg: Optional[int] = None   # 選填，不含行李時為 null
    passenger_name: str                # 必填
    booking_ref: str                   # 必填，訂單代號

# 驗證範例
raw = {
    "flight_number": "CI100",
    "origin": "TPE",
    "destination": "NRT",
    "departure_time": "2024-03-15T09:00:00+08:00",
    "arrival_time": "2024-03-15T12:00:00+09:00",
    "cabin_class": "BUSINESS",
    "price_ntd": 25800,
    "baggage_kg": 30,
    "passenger_name": "王小明",
    "booking_ref": "CI-20240315-100-SMW"
}

booking = FlightBooking.model_validate(raw)
print(booking.departure_time)  # datetime 物件，可直接計算
```

---

## 方法比較：選哪種 schema 格式？

在實務中，你通常有三種方式來定義 schema：

| 方式 | 優點 | 缺點 | 適用情境 |
|---|---|---|---|
| **JSON Schema** | 語言無關；有標準驗證工具；LLM prompt 易讀 | 寫起來繁瑣；沒有業務邏輯 | API 契約；跨語言團隊；給 LLM 的 prompt |
| **Pydantic（Python）** | 整合 Python 生態；支援驗證邏輯；型別提示完整 | 綁定 Python；非工程師難讀 | Python 後端；需要自訂驗證規則的系統 |
| **純文字規格表** | 任何人都能讀和寫 | 無法自動驗證；容易有歧義 | 與非工程人員（如業務、法務）討論需求的初稿 |

**建議流程**：先用純文字規格表和下游確認需求 → 轉成 Pydantic 實作 → 有跨語言需求時再生成 JSON Schema。

### 嚴格 schema vs 寬鬆 schema

**嚴格 schema**：所有欄位必填，沒有抽到就丟棄這筆資料。

```python
class StrictBooking(BaseModel):
    departure_time: datetime   # 必填
    passenger_name: str        # 必填
    booking_ref: str           # 必填
    # 所有欄位都沒有 Optional
```

優點：資料品質高，下游不需要處理 null。
缺點：召回率低，許多有用的部分資料被丟棄。

**寬鬆 schema**：大量欄位允許 null，抽多少算多少。

```python
class LooseBooking(BaseModel):
    departure_time: Optional[datetime] = None
    passenger_name: Optional[str] = None
    booking_ref: Optional[str] = None
    # 幾乎所有欄位都是 Optional
```

優點：召回率高，部分抽取的資料也能保留。
缺點：下游每次查詢都要處理 null；資料品質難以保證。

**取捨原則**：根據下游的容錯能力決定。如果下游是即時訂票系統，嚴格 schema 比較安全；如果是離線分析報表，寬鬆 schema 可以保留更多資訊。

---

## 常見錯誤

### 錯誤一：把「不知道」存成空字串而不是 null

```json
{
  "baggage_kg": "",       ← 錯誤
  "baggage_kg": null      ← 正確
}
```

**問題**：空字串和「沒有值」是不同的語意。空字串表示「有抽取到，但是個空值」，null 表示「這個欄位不適用或無法得知」。下游若用 `if booking.baggage_kg:` 判斷，空字串是 falsy 但不是 null，行為不一致。

### 錯誤二：欄位語意不清（"date" 是什麼日期？）

```json
{
  "date": "2024-03-15"    ← 哪個日期？訂單日期？出發日？抵達日？
}
```

**問題**：`date` 這個名稱沒有指出「是什麼事件的日期」。在訂位確認信中，可能有訂單建立日期、出發日期、抵達日期、退票截止日期等多個日期。每個欄位的名稱應該要完整描述它的語意：`departure_date`、`created_at`、`cancellation_deadline`。

### 錯誤三：schema 設計沒有和下游確認

最常見的浪費：工程師花兩週設計了一個精緻的 schema，結果業務說「我們只需要出發城市和票價，其他欄位我們用不到」，或者「我們還需要乘客的護照號碼，你沒有抽」。

**修正**：在開始任何抽取工作之前，先用純文字規格表（或一個填好的假資料 JSON 範例）和下游確認，取得明確的書面確認。

---

## 習題

**習題 1**：給一份旅館政策，列出需要抽取的欄位和型別

給定以下旅館退訂政策文字：

> 本旅館採浮動取消費用政策。入住日前 7 天以上取消：免費退款。入住日前 3–6 天取消：收取一晚房費（新台幣 3,800 元）。入住日前 1–2 天取消：收取兩晚房費。當日取消或未到：收取全額（三晚，共新台幣 11,400 元）。

請列出需要抽取的欄位名稱、資料型別，以及哪些欄位允許 null。

<details><summary>解答</summary>

這份政策需要抽取的是「取消費用規則表」，每一條規則是一筆記錄：

```python
from pydantic import BaseModel
from typing import Optional

class CancellationTier(BaseModel):
    days_before_checkin_min: Optional[int]  # 距入住日最少幾天（null 表示無下限，例如「7天以上」）
    days_before_checkin_max: int            # 距入住日最多幾天（必填）
    fee_nights: int                         # 收取幾晚費用（0 表示免費）
    fee_ntd: int                            # 收取金額（新台幣，整數）

class HotelCancellationPolicy(BaseModel):
    hotel_name: Optional[str] = None       # 此文字未提及旅館名稱，null
    nightly_rate_ntd: int                  # 每晚房費，3800
    tiers: list[CancellationTier]          # 多條規則
```

四個取消費用層級：
1. `days_before_checkin_min=7, days_before_checkin_max=999, fee_nights=0, fee_ntd=0`
2. `days_before_checkin_min=3, days_before_checkin_max=6, fee_nights=1, fee_ntd=3800`
3. `days_before_checkin_min=1, days_before_checkin_max=2, fee_nights=2, fee_ntd=7600`
4. `days_before_checkin_min=0, days_before_checkin_max=0, fee_nights=3, fee_ntd=11400`

**關鍵設計決定**：
- 費用用「晚數」和「金額」兩個欄位分別記錄，因為下游可能需要分別查詢
- `days_before_checkin_min` 允許 null，因為「7 天以上」沒有上限

</details>

---

**習題 2**：找出壞 schema 中的問題

以下是一個旅遊保險投保記錄的 schema：

```json
{
  "customer": "陳大明/男/1985-07-22",
  "coverage": "海外急難救助+行李遺失+班機延誤",
  "valid": "2024-03-15 to 2024-03-22",
  "premium": "$1,250",
  "status": ""
}
```

請找出這個 schema 中的至少三個設計問題，並說明每個問題會如何影響下游查詢。

<details><summary>解答</summary>

**問題一：`customer` 把姓名、性別、生日塞在一個字串**

`"陳大明/男/1985-07-22"` 是三個不同語意的欄位合併成一個字串。若下游要：
- 篩選「35 歲以上旅客」→ 要先解析字串取出生日再計算年齡
- 分析男女比例 → 要先解析字串取出性別
- 寄信給旅客 → 要先解析取出姓名

應拆成 `customer_name: str`、`gender: enum`、`birth_date: date` 三個欄位。

**問題二：`coverage` 把多個保障項目存成逗號分隔字串**

下游若要查「有沒有班機延誤保障」，必須用字串比對 `"班機延誤" in coverage`，脆弱且難以維護。應改成 `coverages: list[str]` 或更好地定義一個 enum 清單。

**問題三：`premium` 包含貨幣符號**

`"$1,250"` 是字串，下游要做數字計算（加總、比較）時必須先剝除 `$` 和逗號。應改成 `premium_ntd: int = 1250`。

**問題四：`status` 是空字串而不是 null**

`""` 表示「有這個欄位但值是空的」，語意不清。應該用 `null` 或明確的 enum（例如 `"ACTIVE"` / `"CANCELLED"` / `"PENDING"`）。

**問題五：`valid` 把開始和結束日期合成一個字串**

`"2024-03-15 to 2024-03-22"` 是兩個日期。應拆成 `start_date: date` 和 `end_date: date`。

</details>

---

**習題 3**：給兩個 schema 選型情境，說明為何選某個方案

以下是兩個情境，請為每個情境選擇最適合的 schema 格式（JSON Schema / Pydantic / 純文字規格表），並說明理由：

**情境 A**：你的團隊要設計一個新的抽取任務，需要先和業務部門、法務部門、工程部門三方確認 schema 的內容，然後才開始實作。

**情境 B**：你已經確認好 schema，要在 Python 後端實作抽取邏輯，並且需要驗證 LLM 輸出的 JSON 格式和型別是否符合規格。

<details><summary>解答</summary>

**情境 A → 純文字規格表**

理由：
- 業務和法務部門不懂 JSON Schema 語法，但能讀純文字說明
- 此階段目的是「對齊需求」，不是「實作驗證」
- 純文字規格表可以在 Google Doc 上直接修改和留言，協作成本最低
- 等三方確認後，再由工程師把純文字規格轉成 Pydantic 或 JSON Schema

**情境 B → Pydantic**

理由：
- 已進入 Python 實作階段，Pydantic 能直接整合到程式碼中
- `model_validate_json()` 可以直接驗證 LLM 輸出的 JSON 字串，一行搞定型別檢查和必填驗證
- Pydantic 支援自訂驗證器（`@field_validator`），可以加入業務邏輯（例如「departure_time 必須早於 arrival_time」）
- 型別提示讓 IDE 能提供自動補全和錯誤提示，降低維護成本

**補充**：若未來需要把 schema 開放給其他語言（Java、Go）的系統使用，可以從 Pydantic model 自動生成 JSON Schema：`FlightBooking.model_json_schema()`

</details>

---

[← 上一頁](intro.md) · [本章導覽](intro.md) · [總目錄](../../README.md#課程地圖) · [下一頁 →](02-ner-and-events.md)
