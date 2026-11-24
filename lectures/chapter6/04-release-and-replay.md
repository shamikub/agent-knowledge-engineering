# 6.4 發版前重播

[← 上一頁](03-execution-control.md) · [本章導覽](intro.md) · [總目錄](../../README.md#課程地圖) · [期末 Lab →](../../labs/06/README.md)

## 學習目標

完成本節後，你能夠：

1. 描述知識發布的版本保留策略，說明為何舊版本不能直接刪除。
2. 說明 shadow deployment（影子部署）的用途，以及如何設定升級門檻。
3. 設計回歸測試套件，讓新版本上線前先驗證不破壞現有功能。
4. 給定一個策略版本升級情境，說明測試案例的設計、驗收標準和回滾程序。

**先備知識：** 6.1 節知識修正與 bitemporal，6.3 節工具呼叫狀態，第三章版本模型。

---

## 1. 情境設定：政策升級帶來的風險

**故事背景：** 旅行助理使用的「取消政策（Cancellation Policy）」從 v1 升到 v2：

```
v1（舊政策）：
  Check-in 前 72 小時以上取消：全額退款
  Check-in 前 24-72 小時取消：退款 50%
  Check-in 前 24 小時內取消：不退款

v2（新政策）：
  Check-in 前 72 小時以上取消：全額退款
  Check-in 前 48-72 小時取消：退款 75%  ← 這段改了
  Check-in 前 24-48 小時取消：退款 25%  ← 這段改了
  Check-in 前 24 小時內取消：不退款
```

**直接覆蓋上去的後果（反例）：**

```
問題一：過去的決策無法重播
  日誌顯示：「2024-01-10 依取消政策退款 50%」
  但現在政策 v2 說同樣情況應退 75%
  → 無法確認當時用的是哪個版本，客訴無法舉證

問題二：出問題無法回滾
  v2 上線後發現退款計算有 bug
  → 舊的 v1 規則已被覆蓋，無法切回

問題三：回歸測試無從設計
  不知道 v2 改動影響了哪些測試案例
  → 測試跑過，但沒有針對「差異點」驗證
```

---

## 2. 版本保留策略

### 2.1 核心原則：舊版本不刪

每個政策版本都作為獨立記錄保留，透過有效時間（valid time）管理當前生效的版本。

```python
# 知識庫中的政策版本記錄（示意）

CANCELLATION_POLICY = [
    {
        "version": "v1",
        "valid_from": "2023-01-01",
        "valid_until": "2024-02-01",   # 關閉，但不刪除
        "rules": {
            "72h+":    {"refund_pct": 100},
            "24h-72h": {"refund_pct": 50},
            "0h-24h":  {"refund_pct": 0},
        }
    },
    {
        "version": "v2",
        "valid_from": "2024-02-01",
        "valid_until": None,           # 目前生效
        "rules": {
            "72h+":    {"refund_pct": 100},
            "48h-72h": {"refund_pct": 75},
            "24h-48h": {"refund_pct": 25},
            "0h-24h":  {"refund_pct": 0},
        }
    }
]

def get_policy_at(cancellation_time: datetime) -> dict:
    """根據取消時間找到當時生效的政策版本"""
    for policy in reversed(CANCELLATION_POLICY):
        if policy["valid_from"] <= cancellation_time.date().isoformat():
            if policy["valid_until"] is None or \
               cancellation_time.date().isoformat() < policy["valid_until"]:
                return policy
    raise ValueError(f"找不到 {cancellation_time} 的政策版本")
```

### 2.2 決策記錄中保存版本資訊

每筆決策不只記錄結果，還記錄「用了哪個版本的政策」：

```json
{
  "decision_id": "DEC-2024-0120-005",
  "booking_id": "BRG-2024-0120",
  "action": "process_cancellation",
  "cancellation_time": "2024-01-20T14:30:00Z",
  "hours_before_checkin": 60,
  "policy_version_used": "v1",
  "policy_snapshot": {
    "24h-72h": {"refund_pct": 50}
  },
  "refund_amount": 150.00,
  "refund_pct": 50,
  "decided_at": "2024-01-20T14:30:05Z"
}
```

**這樣設計的好處：**
- 客訴時能舉證：「當時用的是 v1，規定 50% 退款，沒有錯」
- 出問題時能重播：用相同的 `policy_version_used` 跑舊案件，確認問題是否來自政策升級

---

## 3. 受影響的測試案例識別

升級到 v2 時，哪些測試案例會受到影響？

```
v1 → v2 的差異：
  原本 "24h-72h" 的案例（取消前 24 到 72 小時）
  → 在 v2 中被拆成兩段（48h-72h 退 75%，24h-48h 退 25%）

受影響的測試案例：
  ✗ 取消前 60 小時（原 v1 退 50%，v2 應退 75%）
  ✗ 取消前 36 小時（原 v1 退 50%，v2 應退 25%）

不受影響的測試案例：
  ✓ 取消前 80 小時（v1 和 v2 都是退 100%）
  ✓ 取消前 12 小時（v1 和 v2 都是退 0%）
```

**修改項連回受影響的測試** 是版本管理的核心要求：每次知識或策略改動，必須明確標出影響範圍，並針對那個範圍新增測試案例。

---

## 4. 回歸測試套件設計

### 4.1 測試案例結構

```python
# tests/test_cancellation_policy.py
import pytest

CANCELLATION_CASES = [
    # (案例名稱, 取消前小時數, v1 預期退款%, v2 預期退款%, 受影響?)
    ("取消前 80 小時", 80,  100, 100, False),  # 不受影響
    ("取消前 72 小時", 72,  100, 100, False),  # 邊界，不受影響
    ("取消前 60 小時", 60,  50,  75,  True),   # 受影響
    ("取消前 48 小時", 48,  50,  75,  True),   # 邊界，受影響
    ("取消前 36 小時", 36,  50,  25,  True),   # 受影響
    ("取消前 24 小時", 24,  50,  25,  True),   # 邊界，受影響
    ("取消前 12 小時", 12,  0,   0,   False),  # 不受影響
]

@pytest.mark.parametrize(
    "case_name,hours_before,v1_pct,v2_pct,affected",
    CANCELLATION_CASES
)
def test_cancellation_v1(case_name, hours_before, v1_pct, v2_pct, affected):
    """驗證 v1 政策的計算仍然正確（回歸測試）"""
    policy = get_policy_version("v1")
    result = calculate_refund(policy, hours_before=hours_before, booking_amount=300)
    expected = 300 * v1_pct / 100
    assert result == expected, f"{case_name}: v1 計算錯誤"

@pytest.mark.parametrize(
    "case_name,hours_before,v1_pct,v2_pct,affected",
    CANCELLATION_CASES
)
def test_cancellation_v2(case_name, hours_before, v1_pct, v2_pct, affected):
    """驗證 v2 政策的計算正確"""
    policy = get_policy_version("v2")
    result = calculate_refund(policy, hours_before=hours_before, booking_amount=300)
    expected = 300 * v2_pct / 100
    assert result == expected, f"{case_name}: v2 計算錯誤"

@pytest.mark.parametrize(
    "case_name,hours_before,v1_pct,v2_pct,affected",
    [(c[0], c[1], c[2], c[3], c[4]) for c in CANCELLATION_CASES if c[4]]
)
def test_v1_v2_differ_at_affected_cases(case_name, hours_before, v1_pct, v2_pct, affected):
    """確認受影響的案例，v2 確實和 v1 不同（防止測試無意義）"""
    assert v1_pct != v2_pct, f"{case_name}: 受影響案例的 v1/v2 應不同，但兩者都是 {v1_pct}%"
```

### 4.2 新版本先跑所有舊版本的測試

```bash
# 在部署 v2 前，確保 v2 通過 v1 的所有不受影響案例
pytest tests/test_cancellation_policy.py::test_cancellation_v2 -v

# 預期輸出
PASSED test_cancellation_v2[取消前 80 小時]
PASSED test_cancellation_v2[取消前 72 小時]
PASSED test_cancellation_v2[取消前 60 小時]  # 新政策 75% 也通過
PASSED test_cancellation_v2[取消前 12 小時]
...
8 passed in 0.12s
```

---

## 5. Shadow Deployment（影子部署）

### 5.1 什麼是 Shadow Deployment

Shadow deployment（影子部署）讓新版本「平行執行但不影響結果」：

```
使用者請求
     │
     ├──► 現行版本（v1）─── 回傳結果給使用者
     │
     └──► 影子版本（v2）─── 只記錄，不回傳結果
                             比較 v1 和 v2 的差異
```

**用途：**
- 在真實流量下觀察 v2 的行為，不影響使用者體驗
- 比較「v1 和 v2 在同一個輸入上的差異」
- 收集差異比例，作為升級決策的依據

### 5.2 Shadow Deployment 設計

```python
class ShadowDeployment:
    def __init__(self, current: PolicyEngine, shadow: PolicyEngine,
                 shadow_traffic_pct: float = 100.0):
        self.current = current
        self.shadow = shadow
        self.shadow_traffic_pct = shadow_traffic_pct  # 100% = 所有請求都影子執行
        self.diff_log = []

    def process(self, request: CancellationRequest) -> RefundResult:
        # 現行版本：決定最終結果
        current_result = self.current.calculate_refund(request)

        # 影子版本：只記錄，不影響結果
        if random.random() < self.shadow_traffic_pct / 100:
            shadow_result = self.shadow.calculate_refund(request)
            if current_result != shadow_result:
                self.diff_log.append({
                    "request": request,
                    "current": current_result,
                    "shadow": shadow_result,
                    "diff": shadow_result.amount - current_result.amount
                })

        return current_result  # 只回傳 current 的結果

    def get_diff_report(self) -> dict:
        total = len(self.diff_log)
        avg_diff = sum(d["diff"] for d in self.diff_log) / total if total else 0
        return {
            "total_differences": total,
            "avg_refund_diff": avg_diff,
            "cases": self.diff_log
        }
```

### 5.3 升級門檻設計

```
Shadow Deployment 觀察期間的指標目標：

指標                    門檻              說明
─────────────────────────────────────────────────────
差異比例               ≤ 預期差異比例     差異太多表示有非預期的 bug
人工介入率（v2 shadow） ≤ 現行版本 + 2%  v2 不應引入新的人工處理需求
p99 延遲（v2 shadow）  ≤ 現行版本 × 1.1  v2 不應大幅增加延遲
錯誤率（v2 shadow）    ≤ 現行版本        v2 不應引入新的技術錯誤

觀察期間：72 小時（至少覆蓋一個完整週期）
最小樣本數：500 筆請求
```

**驗收後才切流量：**
```
Phase 1：Shadow（100% 請求影子執行，0% 切到 v2）
  → 觀察 72 小時，確認上述指標達標

Phase 2：Canary（5% 切到 v2，觀察真實使用者回饋）
  → 觀察 24 小時，客訴率未上升

Phase 3：逐步切流（20% → 50% → 100%）
  → 每階段觀察 24 小時

Phase 4：完全切換（100% 使用 v2）
  → 保留 v1 備用 7 天後才下線
```

---

## 6. 回滾程序

### 6.1 保存決策所用的版本資訊（複習）

如 2.2 節所示，每筆決策記錄 `policy_version_used`。出問題時：

```python
def rollback_to_v1():
    """
    回滾程序：
    1. 把流量切回 v1（修改 policy router 的設定）
    2. 記錄回滾時間點
    3. 對回滾後到來的請求，用 v1 重新處理
    4. 注意：已經用 v2 執行的動作（例如已退款）無法撤銷
    """
    policy_router.set_active_version("v1")
    audit_log.record(
        action="rollback",
        from_version="v2",
        to_version="v1",
        reason="退款計算 bug：48-72h 段退款比例錯誤",
        rolled_back_at=datetime.utcnow()
    )
    # 標記 v2 期間的決策，供後續人工審查
    db.mark_decisions_for_review(
        policy_version="v2",
        from_time=v2_deployment_time,
        to_time=datetime.utcnow()
    )
```

### 6.2 重要限制：回滾 ≠ 撤銷已執行的副作用

```
回滾切回 v1 後：

✓ 新進來的請求：用 v1 政策計算
✓ 歷史決策：有記錄，可以人工比對和補救

✗ 已執行的退款：錢已打出去，回滾模型不會把錢追回來
✗ 已發送的確認信：通知已發出，回滾不會撤回

→ 因此，v2 期間所有用 v2 政策退款的案件，
  需要人工比對「v1 應退多少」vs「v2 實際退了多少」，
  差額多退的需要個案追回，差額少退的需要補退。
```

---

## 7. 完整算例：取消政策 v1 → v2 升級流程

**輸入：** 要把取消政策從 v1 升到 v2（見第 1 節的差異描述）

```
步驟 1：識別受影響的測試案例
  受影響：取消前 24-72 小時的所有案例（原本一段，現在拆成兩段）
  具體案例：
    - 取消前 60h：v1=50%，v2=75%  ← 差異
    - 取消前 36h：v1=50%，v2=25%  ← 差異

步驟 2：設計回歸測試（使用 pytest parametrize）
  共 7 個測試案例（如 4.1 節所示）
  受影響案例 4 個，不受影響案例 3 個

步驟 3：本地驗證 v2 政策
  pytest tests/test_cancellation_policy.py -v
  → 8 passed（包含驗證 v2 在受影響案例上確實改變了結果）

步驟 4：Shadow deployment（72 小時）
  觀察結果：
    差異比例：18.2%（符合預期，24-72h 段約佔 20% 的取消請求）
    人工介入率：11.3% vs 現行 11.1%（差 0.2%，在門檻內）
    p99 延遲：1,120 ms vs 現行 1,080 ms（差 3.7%，在門檻內）
  → 通過，進入 Canary

步驟 5：Canary（5%，24 小時）
  客訴率：2.1 筆/千次 vs 現行 2.3 筆/千次（未上升）
  → 通過，開始逐步切流

步驟 6：完全切換
  100% 使用 v2
  v1 保留 7 天備用

步驟 7（若出問題）：回滾
  切回 v1
  標記 v2 期間的決策供人工審查
```

---

## 8. 習題

**習題 1（機制）**
某版本知識庫在 2024-03-01 更新了「旅館早餐政策」，把「早餐包含在房費內」改成「早餐需額外付費」。一位旅客在 2024-02-28 訂房，2024-03-05 Check-in。請問系統在 Check-in 當日查詢「這位旅客有包含早餐嗎？」時，應使用哪個版本的政策？為什麼？

<details><summary>解答</summary>

**應使用 2024-02-28 當時生效的舊政策（早餐包含在房費內）。**

**理由：**

使用 bitemporal 模型時，要區分：
- **有效時間（valid time）**：事實在現實世界成立的時間
- **交易時間（transaction time）**：知識被系統記錄的時間

這位旅客在 2024-02-28 訂房，當時簽的合約（訂房確認信）是以「早餐包含在房費內」的舊政策為基礎。旅客有合理期待在 Check-in 時能享用早餐。

知識庫在 2024-03-01 更新，代表「從 2024-03-01 之後新訂的房」才適用新政策。這位旅客是在 2024-02-28 訂房，他的訂單有效時間應使用訂房時的政策版本。

**正確查詢邏輯：**
```python
policy = get_policy_at(
    valid_time=booking.created_at,  # 2024-02-28，不是 Check-in 日期
    policy_type="breakfast"
)
# 返回：舊政策（早餐包含在房費內）
```

</details>

---

**習題 2（設計回歸測試）**
某 AI Agent 的「訂房推薦策略」從 v3 升到 v4，唯一的改動是：「當旅館距離景點超過 5 公里時，主動提示計程車費用估算」。請用 pytest parametrize 格式，設計至少 4 個回歸測試案例，說明哪些受影響、哪些不受影響。

<details><summary>解答</summary>

```python
HOTEL_RECOMMENDATION_CASES = [
    # (案例名稱, 距離km, v3預期行為, v4預期行為, 受影響?)
    ("距離 2 公里",    2,  "不提示計程車費用", "不提示計程車費用", False),
    ("距離 5 公里",    5,  "不提示計程車費用", "不提示計程車費用", False),  # 邊界
    ("距離 5.1 公里",  5.1,"不提示計程車費用", "提示計程車費用估算", True),   # 邊界+1
    ("距離 10 公里",   10, "不提示計程車費用", "提示計程車費用估算", True),
]
```

**說明：**
- 距離 ≤ 5 公里：v3 和 v4 行為相同（不受影響）
- 距離 > 5 公里：v4 新增了提示（受影響）
- 邊界 5 公里：不受影響（`> 5` 而非 `>= 5`），需特別確認
- 邊界 5.1 公里：受影響，確認 5.1 能正確觸發新行為

每個案例的斷言應檢查回應中是否包含（或不包含）「計程車費用」相關文字，以及是否呼叫了計程車費用計算工具。

</details>

---

**習題 3（選型）**
你的系統要把「退款政策計算邏輯」從硬編碼改成從知識庫讀取，同時政策規則本身也從 v1 升到 v2。請說明：
(a) 這次升級應該一次性同時做，還是分兩步驟做？
(b) 如果分兩步驟，順序應該怎麼安排？為什麼？

<details><summary>解答</summary>

**答案：應該分兩步驟，順序如下。**

**步驟一：先把「從硬編碼改成從知識庫讀取」（架構改動），政策內容維持 v1**

此時：
- 程式邏輯改了，但計算結果應與原本完全相同
- 回歸測試應全部通過（因為政策內容沒變）
- 若有任何差異，表示架構改動有 bug，可以安全回滾（政策 v1 還在知識庫裡）

**步驟二：再把知識庫中的政策從 v1 升到 v2**

此時：
- 程式邏輯不動，只改資料
- 回歸測試中「受影響的案例」預期會有不同結果（v2 和 v1 不同）
- 若出問題，只需把知識庫切回 v1，不需要改程式碼

**為什麼不能一次同時做：**
如果架構改動和政策升級同時發生，出問題時無法判斷是「程式有 bug」還是「政策規則有問題」，debug 難度大幅增加，回滾也複雜（需要同時回滾程式和資料）。

</details>

---

## 延伸閱讀

- pytest 官方文件：[parametrize](https://docs.pytest.org/en/stable/how-to/parametrize.html)
- Kleppmann, M. (2017). *Designing Data-Intensive Applications*. Ch. 11: Stream Processing.（版本與演化的系統思考）
- Sculley, D. et al. (2015). Hidden Technical Debt in Machine Learning Systems. *NeurIPS*.（ML 系統版本管理的常見陷阱）

---

[← 上一頁](03-execution-control.md) · [本章導覽](intro.md) · [總目錄](../../README.md#課程地圖) · [期末 Lab →](../../labs/06/README.md)
