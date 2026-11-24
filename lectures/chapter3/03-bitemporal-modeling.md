# 3.3 版本的兩個時鐘（Bitemporal Modeling）

[← 上一頁](02-knowledge-graphs.md) · [本章導覽](intro.md) · [總目錄](../../README.md#課程地圖) · [下一頁 →](../chapter4/intro.md)

---

## 學習目標

完成本節後，你能夠：

1. 說明 valid time（有效時間）和 transaction time（交易時間）的差異，並舉例說明何時兩者都需要記錄。
2. 設計一個含半開區間的 bitemporal 表結構，能正確表示版本的起訖邊界。
3. 重播任意時間點的系統視角：寫出 SQL 查詢，回答「系統在某天能看到什麼版本的政策」。

**先備知識：** 看得懂 SQL 的 `WHERE` 與 `BETWEEN` 子句，了解 Git 的 commit 概念即可。

---

## 1. 背景橋樑：從 Git Commit History 到 Bitemporal

Git 記錄的是每次提交的時間（`commit timestamp`），這是一種「什麼時候知道的」時間。如果你在 4/5 修正了一個 4/1 就應生效的政策，Git 能告訴你「4/5 有一次提交」，但無法直接回答「4/3 當天系統應該用哪個版本」。

```
Git commit log（只有 transaction time）：
4/1  commit a1b2: 初始版本（取消政策 v1）
4/5  commit c3d4: 更新取消政策（v2，溯及 4/1 生效）

問題：4/3 助理做決策時，看的是 v1 還是 v2？
─── Git 無法回答這個問題 ───
```

**Bitemporal 模型** 同時記錄兩個時間維度：

| 維度 | 名稱 | 意義 | 類比 |
|------|------|------|------|
| 第一個時鐘 | Valid Time | 事實在現實世界「有效的時段」 | 政策的生效日期 |
| 第二個時鐘 | Transaction Time | 資料「匯入系統的時段」 | Git commit 的時間 |

有了兩個時鐘，就能回答：
- 「4/3 當天，系統已知的最新政策內容是什麼？」（重播歷史決策）
- 「今天已知，4/3 當天應該適用的政策是什麼？」（稽核更正）

---

## 2. 任務定義

**輸入：** 帶有生效日期（valid date）和匯入日期（ingestion date）的政策文件版本序列。

**輸出：** 可在任意（valid_time, transaction_time）座標重播的知識版本，支援稽核、回溯偵錯與爭議解析。

**子任務：**
1. 設計含四個時間欄位的表結構。
2. 定義半開區間語意，避免版本邊界重疊。
3. 寫出四種查詢模式（現在/過去 × 有效/已知）。
4. 實作 CHECK 約束確保區間不重疊。

---

## 3. 架構說明

### 3.1 四個時間欄位

```sql
CREATE TABLE policy_version (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    policy_id        TEXT    NOT NULL,       -- 政策識別碼
    content          TEXT    NOT NULL,       -- 政策內容

    -- Valid Time：這個版本「在現實中生效的時段」
    valid_from       DATE    NOT NULL,       -- 開始有效（含）
    valid_to         DATE,                  -- 結束有效（不含），NULL = 目前仍有效

    -- Transaction Time：這筆記錄「何時被匯入系統」
    tx_from          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    tx_to            DATETIME,              -- 何時被新版本取代，NULL = 仍是最新紀錄

    CHECK (valid_to IS NULL OR valid_from < valid_to),
    CHECK (tx_to   IS NULL OR tx_from   < tx_to)
);
```

### 3.2 半開區間語意

**半開區間（half-open interval）：** `[valid_from, valid_to)`

- 包含 `valid_from`（左閉）
- 不包含 `valid_to`（右開）

**為什麼不用閉區間 `[valid_from, valid_to]`？**

假設 v1 有效期是 `2024-04-01` 到 `2024-04-14`，v2 從 `2024-04-14` 起生效：
- 閉區間：`4/14` 同時落在 v1 的結束和 v2 的開始，發生 overlap。
- 半開區間：v1 是 `[4/1, 4/14)`，v2 是 `[4/14, ...)`，`4/14` 只落在 v2，沒有重疊。

```
valid time axis:
─── v1 ──────────────)[──── v2 ────────────────────
    4/1               4/14
    ↑含                ↑不含（v1）/ 含（v2）
```

### 3.3 四種查詢模式

| 查詢 | Valid Time 條件 | Transaction Time 條件 | 用途 |
|------|-----------------|-----------------------|------|
| 現在已知、現在有效 | `valid_from <= TODAY AND (valid_to IS NULL OR valid_to > TODAY)` | `tx_to IS NULL` | 當前最新狀態 |
| 現在已知、過去有效 | `valid_from <= @past_date AND (valid_to IS NULL OR valid_to > @past_date)` | `tx_to IS NULL` | 今天回查某天的有效政策 |
| 過去已知、現在有效 | `valid_from <= TODAY AND (valid_to IS NULL OR valid_to > TODAY)` | `tx_from <= @past_tx AND (tx_to IS NULL OR tx_to > @past_tx)` | 系統在某天看到的「現行版本」 |
| 過去已知、過去有效 | `valid_from <= @vt AND (valid_to IS NULL OR valid_to > @vt)` | `tx_from <= @tt AND (tx_to IS NULL OR tx_to > @tt)` | **重播歷史決策** |

---

## 4. 完整算例：取消政策版本追蹤

### 4.1 情境

雙人歐洲自由行場景：

| 事件 | 日期 | 說明 |
|------|------|------|
| 旅館發布取消政策 v1 | 2024-04-01 | 生效日期 4/1，規則：7 天前免費取消 |
| 旅館更新取消政策 v2 | 2024-04-10（但 4/1 起溯及生效） | 規則改為：5 天前免費取消 |
| 系統匯入 v1 | 2024-04-05 | 知道 v1，但還不知道 v2 |
| 系統匯入 v2 | 2024-04-12 | 更新，同時將 v1 的 tx_to 設為 4/12 |
| 助理在 4/3 做取消決策 | 2024-04-03 | 助理當時只知道 v1 |
| 稽核員在今天（4/20）重播 | 2024-04-20 | 要確認助理當時看到的是什麼版本 |

### 4.2 資料狀態

匯入後，資料表的狀態如下：

```sql
-- v1：4/5 匯入，4/12 被 v2 取代
INSERT INTO policy_version VALUES
    (1, 'hotel_amadeus_cancel', '7天前免費取消',
     '2024-04-01', NULL,
     '2024-04-05 09:00:00', '2024-04-12 14:00:00');

-- v2：4/12 匯入，溯及 4/1 生效，目前仍有效
INSERT INTO policy_version VALUES
    (2, 'hotel_amadeus_cancel', '5天前免費取消',
     '2024-04-01', NULL,
     '2024-04-12 14:00:00', NULL);
```

### 4.3 步驟：重播 4/3 助理的視角

**問題：** 助理在 2024-04-03 做決策，當時系統看到的政策是什麼？

**條件：**
- Valid Time：4/3 要在政策的有效期內 → `valid_from <= '2024-04-03' AND (valid_to IS NULL OR valid_to > '2024-04-03')`
- Transaction Time：4/3 當天系統已知的版本 → `tx_from <= '2024-04-03 23:59:59' AND (tx_to IS NULL OR tx_to > '2024-04-03 23:59:59')`

```sql
SELECT policy_id, content, valid_from, valid_to, tx_from, tx_to
FROM policy_version
WHERE policy_id = 'hotel_amadeus_cancel'
  AND valid_from <= '2024-04-03'
  AND (valid_to IS NULL OR valid_to > '2024-04-03')
  AND tx_from <= '2024-04-03 23:59:59'
  AND (tx_to IS NULL OR tx_to > '2024-04-03 23:59:59');
```

**結果：**

| policy_id | content | valid_from | valid_to | tx_from | tx_to |
|-----------|---------|------------|----------|---------|-------|
| hotel_amadeus_cancel | 7天前免費取消 | 2024-04-01 | NULL | 2024-04-05 09:00:00 | 2024-04-12 14:00:00 |

**解讀：** 4/3 當天，系統只有 v1（因為 v2 在 4/12 才匯入），所以助理看到的是「7 天前免費取消」。這筆查詢結果可用於稽核：助理依據當時已知的規則做決策，決策本身是正確的。

### 4.4 步驟：查今天已知、4/3 當天有效的政策

**問題：** 以今天（4/20）的視角，4/3 當天應該適用什麼政策（包含事後更正的資訊）？

```sql
SELECT policy_id, content, valid_from, valid_to, tx_from, tx_to
FROM policy_version
WHERE policy_id = 'hotel_amadeus_cancel'
  AND valid_from <= '2024-04-03'
  AND (valid_to IS NULL OR valid_to > '2024-04-03')
  AND tx_to IS NULL;  -- 今天已知的最新版本
```

**結果：**

| policy_id | content | valid_from | valid_to | tx_from | tx_to |
|-----------|---------|------------|----------|---------|-------|
| hotel_amadeus_cancel | 5天前免費取消 | 2024-04-01 | NULL | 2024-04-12 14:00:00 | NULL |

**解讀：** 今天的視角下，4/1 起生效的應是 v2（5 天前免費取消），但助理在 4/3 無法知道這一點。Bitemporal 模型讓這兩個答案都能被正確查出，互不混淆。

---

## 5. 反例：只有 valid_to IS NULL，沒有 transaction time

**常見錯誤設計：**

```sql
CREATE TABLE policy_simple (
    policy_id   TEXT,
    content     TEXT,
    valid_from  DATE,
    valid_to    DATE   -- NULL 表示「目前版本」
);
```

**問題一：無法重播歷史決策**

當 v2 更新時，你必須把 v1 的 `valid_to` 填入或刪除 v1。一旦刪除，就無法知道「4/3 當天系統看到的是什麼」。

**問題二：無法區分「已知過去有效」vs「過去已知有效」**

用 `valid_to IS NULL` 只能表示「這是最新版本」，無法記錄「什麼時候這筆資料才被系統知道」。

**正確做法：** 採用 append-only 策略：絕對不刪除或修改舊記錄，每次更新都是插入新列，並把舊列的 `tx_to` 設為當前時間。

---

## 6. 方法比較

| 方法 | 能回答「過去有效什麼」 | 能回答「過去已知什麼」 | 儲存成本 | 查詢複雜度 |
|------|------------------------|------------------------|----------|------------|
| 只存 valid time | 是 | 否 | 低 | 低 |
| SCD Type 2 | 是（effective_date） | 部分（depends on design） | 中 | 中 |
| Bitemporal（valid + tx） | 是 | 是 | 高（append-only） | 高 |

**SCD Type 2（Slowly Changing Dimension Type 2）** 是資料倉儲常見做法，用 `effective_from`/`effective_to` 追蹤歷史，但通常沒有獨立的 transaction time，無法區分「這筆資料何時被載入系統」。

**選型原則：**
- 只需知道政策在什麼時間段有效 → 只存 valid time
- 需要稽核「系統在某天看到什麼」、或需要重播 AI 助理的歷史決策 → 完整 bitemporal

---

## 7. SQLite 實作：半開區間 CHECK 約束

```sql
-- 建表
CREATE TABLE policy_version (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    policy_id   TEXT    NOT NULL,
    content     TEXT    NOT NULL,
    valid_from  DATE    NOT NULL,
    valid_to    DATE,
    tx_from     TEXT    NOT NULL DEFAULT (datetime('now')),
    tx_to       TEXT,
    -- 約束：有填 valid_to 時必須大於 valid_from
    CHECK (valid_to IS NULL OR valid_from < valid_to),
    CHECK (tx_to   IS NULL OR tx_from   < tx_to)
);

-- 插入 v1
INSERT INTO policy_version (policy_id, content, valid_from, valid_to, tx_from, tx_to)
VALUES ('amadeus_cancel', '7天前免費取消',
        '2024-04-01', NULL,
        '2024-04-05 09:00:00', '2024-04-12 14:00:00');

-- 插入 v2（溯及 4/1 生效）
INSERT INTO policy_version (policy_id, content, valid_from, valid_to, tx_from, tx_to)
VALUES ('amadeus_cancel', '5天前免費取消',
        '2024-04-01', NULL,
        '2024-04-12 14:00:00', NULL);

-- 重播 4/3 助理視角（參數化版本）
SELECT content
FROM policy_version
WHERE policy_id  = 'amadeus_cancel'
  AND valid_from <= '2024-04-03'
  AND (valid_to IS NULL OR valid_to > '2024-04-03')
  AND tx_from   <= '2024-04-03 23:59:59'
  AND (tx_to    IS NULL OR tx_to > '2024-04-03 23:59:59');
-- 預期輸出：7天前免費取消
```

**防止相鄰版本邊界重疊的 trigger（進階）：**

```sql
-- 確保同一 policy_id 的 valid time 區間不重疊
CREATE TRIGGER check_valid_time_overlap
BEFORE INSERT ON policy_version
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Valid time overlap detected')
    WHERE EXISTS (
        SELECT 1 FROM policy_version
        WHERE policy_id = NEW.policy_id
          AND tx_to IS NULL          -- 只檢查目前有效的記錄
          AND valid_from < COALESCE(NEW.valid_to, '9999-12-31')
          AND COALESCE(valid_to, '9999-12-31') > NEW.valid_from
    );
END;
```

---

## 8. 習題

**題 1（機制）：** 為什麼 bitemporal 模型要用 `[valid_from, valid_to)` 半開區間，而不是 `valid_from <= date AND valid_to >= date`（閉區間）？用 4/14 邊界舉例說明差異。

<details><summary>解答</summary>

**閉區間的問題：**
假設 v1 有效期是 `[4/1, 4/14]`，v2 從 `4/14` 起生效 `[4/14, ...]`。用閉區間查 `4/14`：
```sql
WHERE valid_from <= '2024-04-14' AND valid_to >= '2024-04-14'
```
v1（`valid_to = '2024-04-14'`）和 v2（`valid_from = '2024-04-14'`）都符合條件，造成 overlap，查詢返回兩筆。

**半開區間的解法：**
v1 設為 `[4/1, 4/14)`，`valid_to = '2024-04-14'`；v2 設為 `[4/14, ...)`，`valid_from = '2024-04-14'`。
查詢條件：
```sql
WHERE valid_from <= '2024-04-14' AND (valid_to IS NULL OR valid_to > '2024-04-14')
```
- v1：`valid_to = '2024-04-14'`，不滿足 `valid_to > '2024-04-14'`，不命中。
- v2：`valid_from = '2024-04-14' <= '2024-04-14'`，`valid_to IS NULL`，命中。

只有 v2 返回，邊界無 overlap。

</details>

---

**題 2（手算）：** 假設政策 v3 在 4/15 匯入系統，並宣告從 4/10 起生效（`valid_from = '2024-04-10'`）。請用 bitemporal 查詢，分別寫出「助理在 4/11 看到的版本」和「今天（4/20）知道 4/11 應適用的版本」的 SQL 查詢，並說明結果差異。

<details><summary>解答</summary>

資料狀態（假設 v2 被 v3 取代，v2 的 `valid_to = '2024-04-10'`，v3 的 `valid_from = '2024-04-10'`）：

| id | content | valid_from | valid_to | tx_from | tx_to |
|----|---------|------------|----------|---------|-------|
| 2  | 5天前免費取消 | 2024-04-01 | 2024-04-10 | 2024-04-12 | null |
| 3  | 3天前免費取消 | 2024-04-10 | NULL | 2024-04-15 | null |

**助理在 4/11 看到的版本（過去已知、過去有效）：**
```sql
SELECT content FROM policy_version
WHERE valid_from <= '2024-04-11'
  AND (valid_to IS NULL OR valid_to > '2024-04-11')
  AND tx_from <= '2024-04-11 23:59:59'
  AND (tx_to IS NULL OR tx_to > '2024-04-11 23:59:59');
-- 結果：5天前免費取消（v2，因為 v3 在 4/15 才匯入）
```

**今天（4/20）知道 4/11 應適用的版本（現在已知、過去有效）：**
```sql
SELECT content FROM policy_version
WHERE valid_from <= '2024-04-11'
  AND (valid_to IS NULL OR valid_to > '2024-04-11')
  AND tx_to IS NULL;
-- 結果：3天前免費取消（v3，valid_from = 4/10，涵蓋 4/11）
```

**差異：** 4/11 當天助理做決策時只能看到 v2；但事後從今天的角度看，4/11 應適用 v3。Bitemporal 模型讓兩個答案都可正確查出，可用於稽核「助理當時決策是否合理」。

</details>

---

**題 3（選型）：** 一個線上訂票系統想記錄票價的歷史變動，需求如下：(a) 客服需要知道「客戶購票當天的票價是多少」；(b) 財務需要稽核「系統在某個時點記錄的票價」。應用哪種模型？如果只有需求 (a) 而沒有 (b)，可以用更簡單的方案嗎？

<details><summary>解答</summary>

**有需求 (a) 和 (b) → Bitemporal 模型。**

- 需求 (a) 是 valid time 查詢：客戶購票那天，哪個票價處於有效狀態？
- 需求 (b) 是 transaction time 查詢：系統在那個時點記錄的是什麼值？
- 兩個維度都需要 → bitemporal。

**只有需求 (a) → 只存 valid time 的 SCD Type 2 即可。**

例如：
```sql
CREATE TABLE fare_history (
    route_id    TEXT,
    price       DECIMAL,
    valid_from  DATE NOT NULL,
    valid_to    DATE          -- NULL = 目前有效
);
```

查客戶購票當天票價：
```sql
SELECT price FROM fare_history
WHERE route_id = 'VIE-SZG'
  AND valid_from <= '2024-04-11'
  AND (valid_to IS NULL OR valid_to > '2024-04-11');
```

這個方案成本較低，查詢較簡單，在不需要稽核「系統記錄的歷史」時是合理選擇。

</details>

---

[← 上一頁](02-knowledge-graphs.md) · [本章導覽](intro.md) · [總目錄](../../README.md#課程地圖) · [下一頁 →](../chapter4/intro.md)
