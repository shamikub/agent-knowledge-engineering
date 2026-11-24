# 6.3 執行控制從一筆寫入看

## 學習目標

完成本節後，你能夠：

1. 說明 idempotency key（冪等鍵）的設計要求，包含「同 key 同參數」和「同 key 不同參數」兩種情況的預期行為。
2. 解釋 OPA（Open Policy Agent）的 policy-as-code 模式，能描述一個基本授權規則的結構。
3. 描述工具呼叫的四個狀態（proposed → approved → executed → final_state），並說明每個狀態的可見性與可操作性。
4. 設計一個完整的「改航班後改晚餐訂位」流程，涵蓋授權、冪等性和狀態機。

**先備知識：** 6.1 節策略更新，第三章 bitemporal 模型，第五章評估設計。

---

## 1. 情境設定：Agent 要執行寫入操作

**故事背景（延續）：** 旅客 B 改航班晚到，旅客 A 照常入住。由於 B 晚到，原本訂的兩人晚餐需要確認是否調整。A 在旅館 Check-in 後，傳訊息詢問助理：「今晚的晚餐還可以去嗎？」助理判斷需要把晚餐從「2 人份」改為「1 人份」，並向餐廳提交修改請求。

**這個寫入操作帶來的三個風險：**

1. **沒有授權就執行**：誰說可以改訂位？A 有沒有授權？
2. **重複執行**：A 傳了兩次訊息，系統送了兩次修改請求，餐廳收到兩筆修改
3. **狀態不一致**：修改請求送出去了，但餐廳回說座位已滿取消了，系統沒有更新狀態

執行控制（execution control）就是在寫入操作發生前後，防止這三種風險。

---

## 2. 工具呼叫的四個狀態

每一筆寫入工具呼叫，都應該經過以下四個狀態：

```
proposed → approved → executed → final_state
```

### 2.1 狀態定義

| 狀態 | 意義 | 可見性 | 可操作 |
|------|------|-------|-------|
| **proposed** | Agent 提出動作，但尚未執行 | 可讓使用者確認 | 可取消、可修改 |
| **approved** | 使用者或 policy 已授權 | 記錄授權者和時間 | 只能執行或撤銷 |
| **executed** | 動作已送出（例如 API 已呼叫）| 外部系統已收到 | 不可撤回（只能補救） |
| **final_state** | 外部系統回應已確認 | 成功 / 失敗 / 超時 | 依結果決定後續 |

### 2.2 狀態機圖（改航班晚餐操作）

```
           使用者確認                工具呼叫
  proposed ──────────► approved ──────────► executed
     │                    │                    │
     │ 使用者取消          │ 授權撤銷            │
     ▼                    ▼                    │
  cancelled            cancelled              │ 外部系統回應
                                              ▼
                                   ┌──────────────────┐
                                   │   final_state    │
                                   │  success / fail  │
                                   │  / timeout       │
                                   └──────────────────┘
```

**每個狀態的記錄結構：**

```json
{
  "tool_call_id": "tc-DIN-0214-001",
  "tool_name": "update_dinner_reservation",
  "params": {
    "reservation_id": "DIN-0214-A",
    "new_party_size": 1,
    "reason": "guest_B_late_arrival"
  },
  "state": "approved",
  "state_history": [
    {"state": "proposed", "at": "2024-02-14T18:30:01Z", "by": "agent"},
    {"state": "approved", "at": "2024-02-14T18:30:15Z", "by": "user:A"}
  ],
  "idempotency_key": "tc-DIN-0214-001-v1"
}
```

---

## 3. 授權層：OPA Policy-as-Code

### 3.1 什麼是 Policy-as-Code

OPA（Open Policy Agent）讓授權規則寫成程式碼（Rego 語言），可以版本控制、可以單元測試、可以在執行前查詢。

**核心模式：**
```
Agent 想執行動作 → 問 OPA「這個動作被允許嗎？」→ OPA 回傳 allow / deny
```

### 3.2 晚餐訂位修改的授權規則

```rego
# policy/dinner.rego

package travel.dinner

import future.keywords.if
import future.keywords.in

# 預設拒絕
default allow := false

# 允許條件：
# 1. 請求者是訂位的其中一位旅客
# 2. 訂位狀態是 CONFIRMED
# 3. 新人數大於 0 且不超過原訂人數
allow if {
    input.actor in input.reservation.guests
    input.reservation.status == "CONFIRMED"
    input.new_party_size > 0
    input.new_party_size <= count(input.reservation.guests)
}

# 拒絕並說明原因
deny_reason := "請求者不在訂位名單中" if {
    not input.actor in input.reservation.guests
}

deny_reason := "訂位狀態不允許修改" if {
    input.reservation.status != "CONFIRMED"
}
```

**查詢範例：**
```bash
# 使用 OPA CLI 測試
echo '{
  "actor": "A",
  "reservation": {
    "id": "DIN-0214-A",
    "guests": ["A", "B"],
    "status": "CONFIRMED",
    "party_size": 2
  },
  "new_party_size": 1
}' | opa eval -d policy/dinner.rego -I 'data.travel.dinner.allow'
# 輸出：{"result": [{"expressions": [{"value": true}]}]}
```

```bash
# 測試：非訂位旅客嘗試修改
echo '{
  "actor": "C",
  ...
}' | opa eval -d policy/dinner.rego -I 'data.travel.dinner.allow'
# 輸出：{"result": [{"expressions": [{"value": false}]}]}
```

### 3.3 opa test 寫單元測試

```rego
# policy/dinner_test.rego
package travel.dinner_test

test_guest_can_modify if {
    allow with input as {
        "actor": "A",
        "reservation": {"guests": ["A","B"], "status": "CONFIRMED", "party_size": 2},
        "new_party_size": 1
    }
}

test_non_guest_denied if {
    not allow with input as {
        "actor": "C",
        "reservation": {"guests": ["A","B"], "status": "CONFIRMED", "party_size": 2},
        "new_party_size": 1
    }
}

test_cancelled_booking_denied if {
    not allow with input as {
        "actor": "A",
        "reservation": {"guests": ["A","B"], "status": "CANCELLED", "party_size": 2},
        "new_party_size": 1
    }
}
```

```bash
opa test policy/
# PASS: 3/3
```

---

## 4. 業務參數驗證：執行前再確認狀態

**重要原則：** 即使授權通過（approved），執行前仍要重新查詢當前狀態，因為從 approved 到 executed 之間，外部狀態可能已經改變。

```python
def execute_dinner_modification(tool_call: ToolCall) -> Result:
    """
    執行前的業務參數驗證
    """
    # 1. 再次查詢最新狀態（不信任 proposed 時的快照）
    current_reservation = db.get_reservation(tool_call.params["reservation_id"])

    # 2. 檢查狀態是否仍然有效
    if current_reservation.status != "CONFIRMED":
        return Result.fail(
            reason=f"訂位狀態已變更為 {current_reservation.status}，無法修改",
            tool_call_id=tool_call.id
        )

    # 3. 檢查參數是否仍然合理
    if tool_call.params["new_party_size"] > len(current_reservation.guests):
        return Result.fail(
            reason="人數超過訂位旅客數",
            tool_call_id=tool_call.id
        )

    # 4. 實際執行
    result = restaurant_api.update_reservation(
        reservation_id=tool_call.params["reservation_id"],
        party_size=tool_call.params["new_party_size"],
        idempotency_key=tool_call.idempotency_key  # 見第 5 節
    )

    return Result.from_api_response(result)
```

---

## 5. Idempotency Key（冪等鍵）

### 5.1 問題：重複請求產生兩筆訂位

**反例（沒有冪等鍵）：**

```
時間線：
  T1: A 發訊息「幫我把晚餐改成 1 人份」
  T2: 系統送出 update_reservation(party_size=1) → 餐廳確認 OK
  T3: A 網路不穩，沒收到確認，再問「有改成功嗎？」
  T4: 系統再次送出 update_reservation(party_size=1)
  T5: 餐廳系統把這當成第二筆「再改一次」的請求，記錄兩筆修改

問題：
  - 餐廳系統日誌出現兩筆修改紀錄，對帳困難
  - 若餐廳系統設計不良，可能產生兩筆獨立的修改流水號
```

### 5.2 Idempotency Key 的設計

冪等鍵（idempotency key）是一個唯一識別符，綁定「同一次業務操作」。規則：

| 情況 | 預期行為 |
|------|---------|
| 同 key + 同參數（重送）| 回傳原始結果，不重複執行 |
| 同 key + 不同參數 | 回傳錯誤（衝突），不執行 |
| 不同 key | 視為新操作，正常執行 |

**Key 的命名慣例：**

```python
def generate_idempotency_key(
    operation: str,
    reservation_id: str,
    actor: str,
    intent_hash: str   # 操作意圖的 hash（防止同 key 偷換參數）
) -> str:
    """
    格式：{operation}-{reservation_id}-{actor}-{intent_hash[:8]}
    例子：update-DIN-0214-A-A-a3f9b2c1
    """
    return f"{operation}-{reservation_id}-{actor}-{intent_hash[:8]}"
```

### 5.3 完整算例：玩家因改航班晚到，問了兩次是否要改晚餐

**情境：** A 在 18:30 和 18:35 各傳了一次「幫我把晚餐改成 1 人份」。

```
第一次請求（T=18:30）：
  idempotency_key: "update-DIN-0214-A-A-a3f9b2c1"
  params:
    reservation_id: "DIN-0214-A"
    new_party_size: 1
    reason: "guest_B_late_arrival"

系統處理：
  1. 查詢 key="update-DIN-0214-A-A-a3f9b2c1" → 未找到
  2. 授權檢查 → PASS
  3. 業務驗證 → PASS
  4. 執行修改 → 餐廳 API 回 {"status": "success", "confirmation": "REST-7788"}
  5. 儲存結果：
     key: "update-DIN-0214-A-A-a3f9b2c1"
     result: {"status": "success", "confirmation": "REST-7788"}
     params_hash: "a3f9b2c1"
  回傳：{"status": "success", "confirmation": "REST-7788"}
```

```
第二次請求（T=18:35，同 key 同參數）：
  idempotency_key: "update-DIN-0214-A-A-a3f9b2c1"
  params: （與第一次完全相同）

系統處理：
  1. 查詢 key="update-DIN-0214-A-A-a3f9b2c1" → 找到！
  2. 比對 params_hash → 相同（"a3f9b2c1"）
  3. 直接回傳原始結果，不重複執行
  回傳：{"status": "success", "confirmation": "REST-7788"}  ← 同一筆確認號

結果：餐廳 API 只被呼叫一次，A 收到相同的確認，體驗正常。
```

```
假設第二次請求改了參數（同 key 不同參數）：
  idempotency_key: "update-DIN-0214-A-A-a3f9b2c1"
  params:
    reservation_id: "DIN-0214-A"
    new_party_size: 2   ← 改成 2 人份（偷換參數！）
    reason: "..."

系統處理：
  1. 查詢 key="update-DIN-0214-A-A-a3f9b2c1" → 找到！
  2. 比對 params_hash → 不同！原始是 "a3f9b2c1"，新的是 "d9e1f4a2"
  3. 回傳衝突錯誤，不執行
  回傳：{"status": "conflict", "error": "相同 key 但參數不一致，請用新 key 提交新操作"}
```

### 5.4 記憶體實作 vs 持久化實作

| 特性 | 記憶體（單程序）| 持久化 + 交易（分散式）|
|------|--------------|-------------------|
| 適用場景 | Lab 示範、單機測試 | 生產服務、多實例部署 |
| 並發安全 | 否（單執行緒可用） | 是（唯一約束 + DB 交易）|
| 重啟後保留 | 否 | 是 |
| 實作複雜度 | 低 | 高（需唯一索引、樂觀鎖）|

**記憶體實作（Lab 06 用）：**

```python
class InMemoryIdempotencyStore:
    def __init__(self):
        self._store = {}  # key → {params_hash, result, created_at}

    def check_or_create(self, key: str, params_hash: str):
        if key in self._store:
            existing = self._store[key]
            if existing["params_hash"] != params_hash:
                raise ConflictError(f"Key {key} 已存在但參數不同")
            return existing["result"]  # 回傳原始結果
        return None  # 未找到，表示可以執行

    def store_result(self, key: str, params_hash: str, result: dict):
        self._store[key] = {
            "params_hash": params_hash,
            "result": result,
            "created_at": datetime.utcnow().isoformat()
        }
```

**持久化實作（生產用，PostgreSQL 示意）：**

```sql
CREATE TABLE idempotency_keys (
    key          VARCHAR(255) PRIMARY KEY,   -- 唯一約束
    params_hash  VARCHAR(64)  NOT NULL,
    result       JSONB        NOT NULL,
    created_at   TIMESTAMPTZ  DEFAULT NOW()
);

-- 插入時若 key 已存在會 conflict，應用層比對 params_hash 決定回傳還是報錯
INSERT INTO idempotency_keys (key, params_hash, result)
VALUES ($1, $2, $3)
ON CONFLICT (key) DO NOTHING;
```

---

## 6. Constrained Decoding：限定輸出結構

在工具呼叫之前，Agent 的輸出必須符合嚴格的結構（JSON schema），避免 LLM 產生格式錯誤的工具呼叫。

```python
DINNER_UPDATE_SCHEMA = {
    "type": "object",
    "properties": {
        "reservation_id": {
            "type": "string",
            "pattern": "^DIN-[0-9]{4}-[A-Z]$"
        },
        "new_party_size": {
            "type": "integer",
            "minimum": 1,
            "maximum": 20
        },
        "reason": {
            "type": "string",
            "enum": ["guest_late_arrival", "guest_cancellation", "user_request"]
        }
    },
    "required": ["reservation_id", "new_party_size", "reason"],
    "additionalProperties": False
}
```

Constrained decoding 在 LLM 生成 token 時，只允許符合 schema 的 token 被選取，確保輸出在送到授權層之前就已經是合法格式。

---

## 7. 習題

**習題 1（機制）**
設計一個 idempotency key，用於「旅客 A 更改 Check-in 日期從 2024-02-14 改為 2024-02-15」這個操作。說明這個 key 應包含哪些元素，以及為什麼每個元素都是必要的。

<details><summary>解答</summary>

**Key 設計：**
```
格式：change-checkin-{booking_id}-{actor}-{new_date}-{request_uuid}
範例：change-checkin-BRG-2024-0214-A-20240215-7f3a9b2c
```

**各元素的必要性：**

| 元素 | 理由 |
|------|------|
| `change-checkin` | 區分不同操作類型（避免和取消、改人數混淆） |
| `BRG-2024-0214` | 綁定到特定訂房，不跨訂房生效 |
| `A` | 綁定到特定請求者，B 無法用 A 的 key |
| `20240215` | 把目標日期納入 key，改成不同日期視為新操作 |
| `request_uuid` | 若 A 改了主意（先想改到 15 號，後來想改到 16 號），每次意圖各有獨立 UUID，不會因為同日期重送而衝突 |

**兩種行為驗證：**
- 同 key 重送（網路重試）→ 回傳原始確認結果
- 同 key 改目標日期（偷換參數）→ 因為 `new_date` 不同，`intent_hash` 不同，回傳衝突錯誤

</details>

---

**習題 2（狀態機）**
畫出「改 Check-in 日期」操作的狀態機。包含以下邊界情況：
- 授權被拒絕
- 執行時餐廳（或旅館系統）回傳錯誤
- 請求逾時（無法確認成功或失敗）

<details><summary>解答</summary>

```
                   agent 提出
  ─────────────► proposed
                     │
         ┌───────────┼───────────┐
         │ OPA deny  │ OPA allow │
         ▼           ▼           │
      rejected    approved       │
                     │           │
                 使用者確認       │
                     │           │
                     ▼           │
                  executing ◄────┘
                     │
         ┌───────────┼─────────────┐
         │ API error │ API success │ 逾時（無回應）
         ▼           ▼             ▼
       failed     succeeded      timeout
                                  │
                              手動查詢補確認
                                  │
                        ┌─────────┴─────────┐
                        ▼                   ▼
                     succeeded           failed
```

**各狀態的處理方式：**
- `rejected`：回告使用者，不執行任何寫入
- `failed`：記錄錯誤原因，提示使用者重試或聯絡客服
- `timeout`：**不能假設成功也不能假設失敗**，需要另外查詢外部系統確認實際狀態，再更新本地狀態

</details>

---

**習題 3（除錯）**
系統日誌顯示，同一筆晚餐訂位修改被送往餐廳 API 兩次，間隔 4 秒。已知系統有實作 idempotency key。請提出三個可能的原因，說明冪等機制為何失效。

<details><summary>解答</summary>

**可能原因一：兩次請求使用了不同的 key**
- 例如 key 生成邏輯包含時間戳，4 秒內產生了兩個不同 key
- 修正：key 應綁定「業務意圖」而非「請求時間」

**可能原因二：記憶體 store 在兩次請求之間被重置**
- 例如程式 restart、記憶體被清空，第一次的記錄消失了
- 修正：使用持久化 store（資料庫 + 唯一約束）

**可能原因三：並發競爭（race condition）**
- 兩個請求幾乎同時到達，第一個請求的 `store_result` 還沒寫入，第二個請求的 `check` 就已經查到「未找到」，兩個都進入執行流程
- 修正：在資料庫層用唯一約束 + `INSERT ... ON CONFLICT` 保障原子性，不能只靠應用層的 check-then-write

</details>

---

## 延伸閱讀

- [Open Policy Agent 官方文件](https://www.openpolicyagent.org/docs/)
- [Cedar Policy Language](https://www.cedarpolicy.com/)
- Kleppmann, M. (2017). *Designing Data-Intensive Applications*. Ch. 7: Transactions.（idempotency 和原子性的基礎）

---

[章節導覽](intro.md) · [上一節](02-fine-tuning-and-distillation.md) · [下一節](04-release-and-replay.md)
