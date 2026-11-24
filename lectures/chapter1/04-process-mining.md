# 1.3 從軌跡到流程樹

[← 上一頁](03-ui-operations.md) · [本章導覽](intro.md) · [總目錄](../../README.md#課程地圖) · [下一頁 →](../chapter2/intro.md)

## 學習目標

完成本節後，你應能：

1. 給定三條軌跡，手算**直接相鄰圖（Directly-follows graph，DFG）**的所有邊及其頻次。
2. 說明 Inductive Miner 的遞迴切分邏輯，並辨識循序（→）、互斥（×）、並行（∧）、迴圈（↺）四種算符。
3. 解釋 fitness 與 precision 的意義，以及「允許任意活動」的反例如何讓 fitness 高但 precision 低。
4. 說明 OCEL 2.0 的多物件關聯如何改善傳統單一 case ID 的限制。

---

## 任務定義

### 輸入：事件日誌（Event Log）

流程探勘的標準輸入是一張表，每筆記錄代表一個事件：

| case_id | activity | timestamp |
|---------|----------|-----------|
| trip_001 | 搜尋班次 | 2026-11-01 09:00 |
| trip_001 | 選擇班次 | 2026-11-01 09:02 |
| trip_001 | 付款 | 2026-11-01 09:05 |
| trip_002 | 搜尋班次 | 2026-11-01 10:00 |
| trip_002 | 取消訂位 | 2026-11-01 10:03 |
| trip_002 | 搜尋班次 | 2026-11-01 10:04 |
| trip_002 | 選擇班次 | 2026-11-01 10:06 |
| trip_002 | 付款 | 2026-11-01 10:10 |

一個 `case_id` 對應一條**軌跡（trace）**，是該案例的活動序列。

### 輸出：流程模型

流程探勘的輸出是**流程模型**，常見形式為：

- **流程樹（Process Tree）**：用算符組合成樹狀結構，可轉為 Petri net
- **Petri net**：用於一致性檢查（conformance checking）

### OCEL 2.0：多物件關聯

傳統事件日誌每個事件只屬於一個 case。OCEL 2.0（Object-Centric Event Log 2.0）允許一個事件同時關聯多個物件：

```
事件：付款
  關聯物件：
    - 車票 BK001（object type: booking）
    - 旅客 user_A（object type: traveller）
    - 旅程 trip_paris_2026（object type: trip）
```

**優點**：「訂票」與「行程」可各自有獨立的流程視角，不需為每個視角重複產生不同的 event log。PM4Py 2.7+ 支援 OCEL 2.0 格式。

---

## 架構說明：四種發現演算法的演進

### Directly-follows Graph（DFG）

最基礎的結構：統計「活動 A 之後緊接著活動 B」的次數。

```
節點：每個不同的活動
邊 A→B：在所有軌跡中，A 緊鄰 B 出現的次數
```

DFG 只描述「什麼跟著什麼」，不表達選擇或並行語意。

### Alpha Miner

從 DFG 的先後關係推導因果結構：

- 若 A 在某些軌跡先於 B，在另一些軌跡 B 先於 A → 判定為**並行**
- 若 A 總是先於 B，且 B 不在 A 之前 → 判定為**因果（→）**
- 假設：所有路徑都在日誌中出現過（噪音敏感）

**缺點**：短迴圈（A→A）和未觀察到的路徑會讓模型不完整。

### Heuristics Miner

以**相依度（dependency measure）**過濾弱邊：

```
dependency(A→B) = (count(A→B) - count(B→A)) / (count(A→B) + count(B→A) + 1)
```

值接近 1 表示 A 幾乎總是在 B 前面。設定門檻（如 0.5）可過濾噪音邊，但過高門檻會捨棄罕見但真實的路徑（如「取消 → 重訂」）。

### Inductive Miner

以**遞迴切分（recursive splitting）**為核心邏輯：

1. 對當前子日誌的 DFG 尋找「切割點（cut）」
2. 若找到循序切割（→）：左子日誌與右子日誌不相互連結
3. 若找到互斥切割（×）：不同活動集合從不共存
4. 若找到並行切割（∧）：兩個集合的活動可任意順序出現
5. 若找到迴圈切割（↺）：某個活動集合可重複執行
6. 遞迴對子日誌重複，直到只剩單一活動（基底情況）

**優點**：保證產出可聲音的（sound）Petri net；IMf 變體以頻率過濾噪音後再切分。

---

## 完整算例：手算 DFG 邊頻次

### 給定軌跡

```
軌跡 1：A → B
軌跡 2：A → C
軌跡 3：A → B → C
```

### 步驟一：列出所有相鄰對

| 軌跡 | 相鄰對 |
|------|--------|
| A→B | (A,B) |
| A→C | (A,C) |
| A→B→C | (A,B)、(B,C) |

### 步驟二：統計邊頻次

| 邊 | 出現次數 |
|----|---------|
| A→B | 2（軌跡1、軌跡3） |
| A→C | 1（軌跡2） |
| B→C | 1（軌跡3） |

**直接相鄰圖：**

```
      2         1
A ────────► B ──────► C
  ╲                  ▲
   ╲ 1               │
    ╲─────────────────╯
```

### 步驟三：Inductive Miner 切分

從 DFG 看出：
- A 在所有軌跡最先出現 → A 是起點
- C 在有 C 的軌跡最後出現 → C 是終點
- B 只出現在部分軌跡 → B 與「直接到 C」是**互斥選擇（×）**

產生流程樹：

```
→( A, ×( →(B, C), C ) )
```

解讀：先執行 A，再選擇「執行 B 然後 C」或「直接執行 C」。

### 反例：刪去軌跡 3（A→B→C）後的變化

若事件日誌只剩：

```
軌跡 1：A → B
軌跡 2：A → C
```

重新統計邊：

| 邊 | 出現次數 |
|----|---------|
| A→B | 1 |
| A→C | 1 |
| B→C | **0**（消失） |

**B→C 這條邊消失**，代表 Inductive Miner 看不到「B 之後接 C」的證據。推斷出的流程樹變為：

```
→( A, ×( B, C ) )
```

解讀：先執行 A，再選擇 B 或 C（B 和 C 是互斥的，B 後不再需要 C）。

**含義**：這個模型會**拒絕**軌跡 `A→B→C`（fitness 下降），因為模型認為選了 B 就結束，不能再有 C。這說明「軌跡 3 的缺失不只是少一條路，而是改變了 B 的角色定義」。

---

## 一致性檢查（Conformance Checking）

### Alignment（對齊）

將觀察到的軌跡與模型的可行執行路徑做**最小成本對齊**：

```
觀察軌跡：  A  →  C  （跳過 B）
模型軌跡：  A  →  B  →  C
                 ↑
            Model Move（模型走了 B，觀察沒有）
```

每個 model move 或 log move 都有成本。對齊成本越低，表示軌跡越符合模型。

### Fitness（適合度）

```
fitness = 1 - (對齊總成本 / 最大可能成本)
```

值域 [0, 1]，1 表示所有觀察軌跡都能被模型完美重現。

### Precision（精確度）

```
precision = 1 - (模型能產生但日誌從未觀察到的行為比例)
```

**「允許任意活動」的反例**：

假設有一個模型允許 A、B、C、D 四個活動可以任意順序執行任意次，不受任何約束（相當於一個空的 Petri net）。

- 日誌中的軌跡（如 `A→B→C`）在這個模型裡都可以被重現 → **fitness = 1.0（完美）**
- 但這個模型也允許 `D→C→B→A→D→D` 這種從未出現的軌跡 → **precision 趨近 0**

因此，fitness 高不代表模型有用，必須同時評估 precision。好的模型需要在兩者之間取得平衡。

---

## 方法比較：四種發現演算法

| 演算法 | 核心假設 | 噪音處理 | 輸出結構 | 保證聲音性 | 適用場景 |
|--------|----------|----------|----------|------------|----------|
| **DFG** | 無 | 無（全部保留） | 有向圖 | 否 | 快速探索、視覺化 |
| **Alpha Miner** | 所有路徑都在日誌出現過 | 無 | Petri net | 有限制 | 教學、小型完整日誌 |
| **Heuristics Miner** | 高頻邊代表真實流程 | 相依度門檻 | Petri net | 否 | 大型日誌、有噪音 |
| **Inductive Miner** | 可找到切分點 | IMf 變體以頻率過濾 | 流程樹（可轉 Petri net） | **是** | 一般用途、需要一致性檢查 |

**選型建議**

- 快速了解資料分布 → DFG
- 有噪音、追求覆蓋率 → Heuristics Miner
- 需要正式一致性檢查 → Inductive Miner（IMf 變體）
- 罕見取消路徑很重要 → 調低 Heuristics Miner 或 IMf 的頻率門檻

---

## 研究與實務

- **OCEL 2.0 標準**：[ocel-standard.org](https://www.ocel-standard.org/)，解決多物件事件日誌的建模問題
- **PM4Py 文件**：[processintelligence.solutions](https://processintelligence.solutions/static/api/2.7.17/api.html)，Python 流程探勘主流套件
- **Inductive Miner 論文**：Leemans et al., 2013，提出 IMf（Inductive Miner - infrequent）變體以頻率過濾噪音

---

## 工具與實驗

### PM4Py：用 Inductive Miner 發現流程樹

```python
import pm4py
import pandas as pd

# 建立事件日誌（DataFrame 格式）
log_data = pd.DataFrame([
    {"case:concept:name": "trip_001", "concept:name": "搜尋班次", "time:timestamp": "2026-11-01 09:00"},
    {"case:concept:name": "trip_001", "concept:name": "選擇班次", "time:timestamp": "2026-11-01 09:02"},
    {"case:concept:name": "trip_001", "concept:name": "付款",    "time:timestamp": "2026-11-01 09:05"},
    {"case:concept:name": "trip_002", "concept:name": "搜尋班次", "time:timestamp": "2026-11-01 10:00"},
    {"case:concept:name": "trip_002", "concept:name": "取消訂位", "time:timestamp": "2026-11-01 10:03"},
    {"case:concept:name": "trip_002", "concept:name": "搜尋班次", "time:timestamp": "2026-11-01 10:04"},
    {"case:concept:name": "trip_002", "concept:name": "付款",    "time:timestamp": "2026-11-01 10:10"},
])
log_data["time:timestamp"] = pd.to_datetime(log_data["time:timestamp"])

event_log = pm4py.format_dataframe(
    log_data,
    case_id="case:concept:name",
    activity_key="concept:name",
    timestamp_key="time:timestamp"
)

# 發現流程樹（Inductive Miner）
process_tree = pm4py.discover_process_tree_inductive(event_log)
print(process_tree)

# 轉為 Petri net 並計算 fitness 與 precision
net, im, fm = pm4py.convert_to_petri_net(process_tree)
fitness = pm4py.fitness_alignments(event_log, net, im, fm)
precision = pm4py.precision_alignments(event_log, net, im, fm)
print(f"fitness: {fitness['average_trace_fitness']:.3f}")
print(f"precision: {precision:.3f}")
```

**PM4Py 實作了哪一層**：

- `discover_process_tree_inductive`：Inductive Miner（包含 IMf 變體）
- `fitness_alignments`：alignment-based fitness 計算
- `precision_alignments`：alignment-based precision 計算
- 注意：`fitness_alignments` 是精確計算，大型日誌建議改用 `fitness_token_based_replay`（近似但快速）

---

## 習題

**習題 1（手算 DFG）**：給定以下四條軌跡（使用「雙人歐洲自由行」情境，活動以字母代替）：

```
軌跡 1：A → B → D
軌跡 2：A → C → D
軌跡 3：A → B → C → D
軌跡 4：A → D
```

請手算所有邊及其頻次，並指出哪條邊只出現一次（最脆弱的邊）。若刪去軌跡 3，說明哪條邊消失，以及這對模型推論有何影響。

<details>
<summary>解答</summary>

**所有相鄰對統計：**

| 軌跡 | 相鄰對 |
|------|--------|
| A→B→D | (A,B)、(B,D) |
| A→C→D | (A,C)、(C,D) |
| A→B→C→D | (A,B)、(B,C)、(C,D) |
| A→D | (A,D) |

**邊頻次：**

| 邊 | 頻次 |
|----|------|
| A→B | 2 |
| A→C | 1 |
| A→D | 1 |
| B→D | 1 |
| B→C | 1 |
| C→D | 2 |

**只出現一次的邊**：A→C、A→D、B→D、B→C（共 4 條）。其中 B→C 是「最脆弱」的業務路徑之一——它代表「做完 B 之後繼續做 C」的組合行為。

**刪去軌跡 3（A→B→C→D）後**：

- B→C 這條邊消失（從 1 次變為 0 次）
- C→D 頻次從 2 降為 1

**影響**：模型不再能看到「B 之後可接 C」的路徑。Inductive Miner 或 Alpha Miner 推導的模型會認為 B 和 C 是**互斥選擇**（做了 B 就不走 C，做了 C 就不走 B），軌跡 `A→B→C→D` 在新模型中的 alignment 會有 model move（補插 B→C 這條缺失的轉換），fitness 下降。

</details>

---

**習題 2（機制：Inductive Miner 切分）**：給定三條軌跡：

```
軌跡 1：搜尋 → 選擇 → 付款
軌跡 2：搜尋 → 取消
軌跡 3：搜尋 → 選擇 → 取消 → 搜尋 → 選擇 → 付款
```

請說明 Inductive Miner 如何辨識「這裡有一個迴圈（↺）」的切分，哪個活動集合構成迴圈體，哪個是迴圈外的部分。

<details>
<summary>解答</summary>

Inductive Miner 的迴圈切分（loop cut）條件：存在一個活動集合 $L$，它可以在某個活動 $do$ 之後重複出現，每次重複前有一個「重入活動（redo）」。

觀察三條軌跡：

- 「搜尋」出現了兩次（在軌跡 3 中），且每次「取消」之後會再次出現「搜尋」。
- 「選擇 → 付款」是一條結束路徑，「取消 → 搜尋」是重入路徑。

Inductive Miner 會偵測到：

```
↺(
  do:   →( 搜尋, 選擇 )    ← 主體（至少執行一次）
  redo: →( 取消, 搜尋 )    ← 重入體（執行後回到 do 的起點）
)
```

然後在 do 的出口加一個選擇：付款（離開迴圈）或進入 redo 體。

最終流程樹大致為：

```
↺(
  →( 搜尋, 選擇, ×( 付款, →( 取消 ) ) )
)
```

（確切結構依 PM4Py 實作而略有差異，但「取消」觸發重回「搜尋」的迴圈語意是核心。）

</details>

---

**習題 3（選型：fitness vs precision 的取捨）**：你從旅遊 App 的事件日誌中發現，99% 的軌跡走「搜尋 → 選擇 → 付款」這條主路徑，1% 的軌跡走「搜尋 → 取消 → 搜尋 → 選擇 → 付款」（取消後重訂）。你的同事說：「把取消路徑直接從日誌刪掉，模型更簡潔，fitness 也不會差多少。」請說明：（1）刪去取消路徑後，fitness 和 precision 分別如何變化？（2）在知識工程的場景下，為什麼這 1% 的取消路徑可能比 99% 的主路徑更有研究價值？

<details>
<summary>解答</summary>

**(1) 指標變化**

刪去取消路徑後，模型只學到「搜尋 → 選擇 → 付款」：

- **Fitness**：對 99% 的主路徑完全符合，fitness 接近 1.0；但對那 1% 的取消軌跡，模型無法重現，若這些軌跡仍保留在驗證集，fitness 會略微下降。若連驗證集也刪掉，fitness 就「人工提升」到 1.0，但這是偽造的結果。
- **Precision**：模型更精簡（不允許取消路徑），precision 通常上升——因為模型不再「多容許」取消行為。

**結論**：同事說的話在數字上部分正確，但只看 fitness 而不保留驗證取消路徑，是一種評估作弊。

**(2) 知識工程價值**

罕見路徑往往代表**例外情況（exception handling）**，而例外情況是知識最密集的地方：

- 取消後重訂的使用者，可能遭遇了班次售完、價格跳動、同行者意見分歧等問題——這正是業務需要優化的痛點。
- 若只學主路徑，知識庫永遠不知道「取消發生的前因」，也無法建立預警規則（如「超過 X 分鐘未付款可能即將取消」）。
- 建議：保留取消路徑在日誌中，以 Heuristics Miner 或 IMf 調低頻率門檻，確保模型能表達這條路徑，再分析其 alignment 以了解取消前的操作序列。

</details>

---

[← 上一頁](03-ui-operations.md) · [本章導覽](intro.md) · [總目錄](../../README.md#課程地圖) · [下一頁 →](../chapter2/intro.md)
