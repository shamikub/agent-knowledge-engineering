# 1.3 操作錄製與使用者行為捕捉

[← 上一頁](02-speech.md) · [本章導覽](intro.md) · [總目錄](../../README.md#課程地圖) · [下一頁 →](04-process-mining.md)

## 學習目標

完成本節後，你應能：

1. 比較三種操作證據來源（應用程式事件、rrweb DOM 重播、Accessibility Tree）的語意層級與適用場景。
2. 說明 rrweb 的增量快照（incremental snapshot）機制與事件類型。
3. 解釋 Accessibility Tree 在語意豐富度與跨平台上的優勢與限制。
4. 針對特定分析目標，選擇合適的操作證據來源組合，並指出資料缺口。

---

## 任務定義

**輸入**：瀏覽器錄影（DOM snapshot + event log）、應用程式後端日誌，或無障礙 API 擷取的介面樹

**輸出**：帶語意的操作事件序列，每筆記錄包含：

```json
{
  "event_time": "2026-11-24T09:15:32Z",
  "arrived_time": "2026-11-24T09:15:32.045Z",
  "case_id": "booking_2024_paris_001",
  "actor": "user_A",
  "action": "booking.cancelled",
  "target": {"booking_id": "BK001", "train": "08:00 TPE→KHH"},
  "before_state": {"status": "confirmed"},
  "after_state": {"status": "cancelled"}
}
```

---

## 架構說明

### 三種操作證據來源

| 來源 | 語意層級 | 優點 | 缺點 |
|------|----------|------|------|
| **應用程式事件**（後端 API / webhook） | 業務語意（如 `booking.updated`） | 直接反映資料狀態變更；有 before/after | 只記錄成功寫入；使用者的試探行為看不到 |
| **rrweb DOM 重播** | UI 狀態（HTML/CSS 變化 + 滑鼠軌跡） | 可重播完整操作過程；看到「猶豫」行為 | 資料量大；需解析 DOM diff 才能取語意 |
| **Accessibility Tree** | 介面語意（按鈕名稱、欄位標籤） | 比 DOM 層更接近使用者意圖；無障礙 API 標準化 | 不同框架實作品質不一；無法捕捉視覺樣式 |

**選型原則**：先問「我需要分辨哪兩種狀態？」

- 分辨「訂單送出成功 vs 失敗」→ 應用程式事件最直接
- 分辨「使用者填完表單後猶豫取消 vs 直接送出」→ rrweb DOM 重播
- 分辨「使用者點了哪個功能按鈕」→ Accessibility Tree

### rrweb 的運作方式

rrweb（[github.com/rrweb-io/rrweb](https://github.com/rrweb-io/rrweb)）以**增量快照（incremental snapshot）**重播完整 DOM 狀態。

**初始快照（full snapshot）**：錄製開始時，對整個 DOM 樹做一次完整序列化，記錄所有節點、樣式與屬性。

**增量事件（incremental snapshot）**：之後只記錄變化量，事件類型包含：

| 事件類型 | 說明 |
|----------|------|
| `Mutation` | DOM 節點的新增、移除、屬性變更、文字內容變更 |
| `MouseMove` | 滑鼠座標軌跡（取樣後壓縮） |
| `MouseInteraction` | 滑鼠點擊、hover、focus、blur 等互動 |
| `Scroll` | 捲動位置變更 |
| `ViewportResize` | 視窗大小變更 |
| `Input` | 輸入框的值變更 |
| `TouchMove` | 觸控軌跡（行動端） |

**重播**：將快照與增量事件按時間軸重播，可在沙盒 iframe 中精確還原使用者當時看到的畫面與操作過程。

**資料量考量**：rrweb 採用差異壓縮與 requestAnimationFrame 取樣，但對複雜 SPA（Single-Page Application）仍可能產生大量 mutation 事件。建議在錄製端設定取樣率，並在分析前過濾純樣式或動畫 mutation。

### Accessibility Tree 的優勢

Accessibility Tree（無障礙樹）是作業系統或瀏覽器提供的介面語意層，位於 DOM 與使用者之間。

**為什麼語意比 DOM 豐富？**

原始 DOM 可能是：

```html
<div class="btn-primary" data-id="cancel-btn" onclick="...">取消訂票</div>
```

在 Accessibility Tree 中，這個節點的語意是：

```
role: button
name: "取消訂票"
state: enabled
```

無論前端框架用什麼元件庫（React、Vue、原生 HTML），無障礙 API 都標準化了「這是一個可點按的按鈕，名稱是取消訂票」。

**跨平台標準 API**：

| 平台 | 無障礙 API |
|------|-----------|
| Linux（X11/Wayland） | AT-SPI2 |
| Windows | UI Automation（UIA） |
| macOS / iOS | Accessibility API（AXUIElement） |
| Android | AccessibilityService |
| 瀏覽器 | ARIA + AOM（Accessibility Object Model） |

**限制**：
- 不同框架對 ARIA role 的實作品質不一，自訂元件可能缺少正確的 `role` 或 `aria-label`
- 無法捕捉純視覺樣式（如顏色、動畫）
- 無法重播操作過程（只能取得當下快照）

---

## 完整算例：同一個「退票改票」操作，三種來源各自看到什麼

### 情境

雙人歐洲自由行，使用者 A 在旅遊 App 的 Web 介面操作「退掉八點班次、改訂十點班次」。操作過程如下：

1. 進入訂單頁，查看 BK001（08:00 TPE→KHH）
2. 點擊「取消訂票」按鈕，停留 4 秒（猶豫中）
3. 再次點擊確認取消
4. 系統送出取消 API，回傳成功
5. 搜尋 10:00 班次
6. 選擇 TR202，點擊「確認訂票」
7. 付款完成

### 來源 A：應用程式事件（後端 Webhook）

後端只在資料狀態實際變更時發出事件：

```json
[
  {
    "event_time": "2026-11-24T09:15:36Z",
    "action": "booking.cancelled",
    "target": {"booking_id": "BK001", "train": "08:00 TPE→KHH"},
    "before_state": {"status": "confirmed"},
    "after_state": {"status": "cancelled"}
  },
  {
    "event_time": "2026-11-24T09:18:52Z",
    "action": "booking.created",
    "target": {"booking_id": "BK002", "train": "10:00 TPE→KHH"},
    "after_state": {"status": "confirmed"}
  }
]
```

**看得到**：取消成功的時間點、新訂單的建立。
**看不到**：使用者在點擊取消前猶豫了 4 秒、搜尋時查看了哪些班次選項。

### 來源 B：rrweb DOM 重播

rrweb 記錄了所有 UI 變化：

```
t=0ms      full snapshot（整個訂單頁 DOM）
t=1200ms   MouseMove → 游標移向「取消訂票」按鈕
t=2800ms   MouseInteraction(click) → 彈出確認對話框
t=2801ms   Mutation → 對話框 div 插入 DOM
t=6900ms   MouseInteraction(click) → 再次點擊「確認取消」  ← 猶豫 4 秒可見
t=6901ms   Input / Mutation → 訂單狀態欄位變為「已取消」
t=8500ms   MouseMove → 游標移向搜尋框
t=9100ms   Input → 搜尋框輸入「10:00」
...
```

**看得到**：整個操作過程、4 秒猶豫（兩次點擊間隔）、游標路徑、搜尋時鍵入的內容。
**看不到**：這次取消背後的業務語意（是因為價格問題？還是時間衝突？）

### 來源 C：Accessibility Tree 快照

在使用者點擊確認取消的瞬間，取得 Accessibility Tree 快照：

```
dialog（確認對話框）
  ├── heading: "確認取消訂票"
  ├── text: "BK001 · 08:00 TPE→KHH · NT$1,280"
  ├── button: "確認取消"  [focused, enabled]
  └── button: "返回"      [enabled]
```

**看得到**：使用者當下面對的元件語意（按鈕名稱、訂單金額）、焦點位置。
**看不到**：猶豫時間、游標軌跡、操作前後的完整頁面脈絡。

### 彙整比較

| 分析問題 | 應用程式事件 | rrweb | Accessibility Tree |
|----------|------------|-------|-------------------|
| 取消是否成功？ | 直接可知 | 需解析 DOM | 無 |
| 使用者有猶豫嗎？ | 看不到 | 可量化（點擊間隔） | 看不到 |
| 使用者點了哪個按鈕？ | 看不到 | 需解析座標 | 直接可知（role + name） |
| 當下介面顯示什麼金額？ | 看不到 | 需解析 DOM text | 直接可知 |
| 行動端也能用嗎？ | 是 | 否（僅瀏覽器） | 是（iOS/Android API） |

---

## 方法比較：三種來源詳細對照

| 面向 | 應用程式事件 | rrweb DOM 重播 | Accessibility Tree |
|------|-------------|---------------|-------------------|
| 資料量 | 低（結構化 JSON） | 高（DOM snapshot + delta） | 中 |
| 語意豐富度 | 高（業務語意） | 低（需解析） | 中（元件語意） |
| 能否看到失敗操作 | 否（只有成功寫入） | 是 | 部分 |
| 跨平台 | 需各平台各自實作 | 僅瀏覽器 | 各平台有標準 API |
| 典型工具 | Webhook / 後端 ORM hook | rrweb | AT-SPI（Linux）、UIA（Windows） |

---

## 習題

**習題 1（機制）**：rrweb 錄製一個 SPA（Single-Page Application），當使用者點擊一個按鈕導致頁面局部更新時，rrweb 會記錄哪些事件類型？請說明「Mutation 事件」包含哪些子類型，以及為什麼不需要每次都記錄完整 DOM 快照。

<details>
<summary>解答</summary>

rrweb 在使用者點擊按鈕導致局部更新時，會記錄：

1. **MouseInteraction（click）**：記錄點擊事件發生的時間與目標節點 ID。
2. **Mutation**：記錄 DOM 變化，子類型包含：
   - `attributes`：節點屬性變更（如 `class`、`data-*`、`aria-*`）
   - `childList`：子節點的新增（`addedNodes`）與移除（`removedNodes`）
   - `characterData`：文字節點的內容變更

**為什麼不需要每次記錄完整快照？**

rrweb 在錄製開始時做一次 full snapshot，之後只記錄增量 mutation。重播時從 full snapshot 出發，依序套用每個增量事件，就能還原到任意時間點的 DOM 狀態。這與 git 的 commit-diff 模型類似：只需儲存「變化量」，不需每次儲存完整狀態，大幅降低儲存空間與傳輸量。

</details>

---

**習題 2（比較）**：一個行動 App（iOS）中，使用者嘗試訂票但在付款頁面遇到錯誤，重試兩次後成功。請分析：後端 Webhook、iOS Accessibility Tree 各自能提供什麼資訊？哪些資訊是兩者都無法提供的？

<details>
<summary>解答</summary>

**後端 Webhook 能提供**：
- 第一次付款 API 失敗的錯誤碼與時間
- 第二次付款 API 失敗的錯誤碼與時間
- 第三次付款 API 成功的時間與訂單資訊

**iOS Accessibility Tree 能提供**：
- 付款頁面上各元件的名稱與狀態（如錯誤訊息的文字、重試按鈕的 label）
- 在擷取快照的時間點，使用者焦點停在哪個元件

**兩者都無法提供的**：
- 使用者在重試之間等待的時間（Webhook 只記錄 API 呼叫，Accessibility Tree 是靜態快照）
- 使用者是否切換到其他 App（例如去查信用卡號）後再回來
- 使用者的情緒反應或操作猶豫（需要 rrweb 等級的連續錄製，但 iOS 無原生 rrweb 等效工具）
- 若要完整還原行動端的操作過程，需要在 App 內埋設自訂事件（custom analytics）配合 Accessibility Tree 快照。

</details>

---

**習題 3（選型）**：你正在為一個旅遊 App 建立「使用者操作知識庫」，目標是了解使用者訂票失敗的原因。App 同時有 Web 介面（瀏覽器）和行動 App（iOS/Android）兩個端點。你有以下可選工具：後端 Webhook（訂單 API 成功/失敗事件）、rrweb（僅限 Web 端）、Accessibility Tree（iOS VoiceOver / Android TalkBack）。請說明：你會用哪種組合？各工具負責回答哪個問題？最大的資料缺口在哪裡？

<details>
<summary>解答</summary>

**建議組合**：

1. **後端 Webhook**（全平台）：回答「訂單最終成功還是失敗、在哪個 API 步驟失敗」。語意最清楚，是所有分析的主軸事件。

2. **rrweb**（Web 端）：回答「使用者在送出前做了什麼操作、有沒有反覆修改或猶豫的行為」。可補足 Webhook 看不到的「試探性操作」。

3. **Accessibility Tree**（iOS/Android）：回答「使用者在行動端點了哪個元件、填了哪個欄位」。比 rrweb 語意層高，但無法捕捉視覺樣式和微互動。

**資料缺口**：rrweb 只涵蓋 Web，行動端的「試探性操作」（如多次修改日期、切換頁面後回來）無法用 Accessibility Tree 完整還原。若要覆蓋行動端，需要在 App 內埋設自訂事件（custom analytics）才能填補這個缺口。

</details>

---

[← 上一頁](02-speech.md) · [本章導覽](intro.md) · [總目錄](../../README.md#課程地圖) · [下一頁 →](04-process-mining.md)
