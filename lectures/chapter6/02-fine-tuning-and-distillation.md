# 6.2 微調與蒸餾從權重怎麼看

## 學習目標

完成本節後，你能夠：

1. 解釋 LoRA（Low-Rank Adaptation）的低秩假設，並手算一個具體的參數量比較。
2. 說明 QLoRA 為何能在消費級 GPU（consumer GPU）上跑，以及 NF4 量化帶來的記憶體節省。
3. 設計小模型的三指標評估框架（錯誤率、延遲、人工介入率），並說明為何不能只看準確率。
4. 在 Full FT、LoRA、QLoRA、蒸餾四種方法中，根據具體條件選擇合適方法。

**先備知識：** 6.1 節三種更新層次，第五章評估指標設計。

---

## 1. 為什麼不直接用大模型？

在旅行助理系統中，每筆 API 請求都需要推論。當請求量大時，大模型的三個代價會快速累積：

| 問題 | 具體影響 |
|------|---------|
| **成本** | 7B 模型的推論費用可能是 1B 模型的 5-10 倍 |
| **延遲** | 大模型 p99 延遲可能超過業務 timeout（例如 2 秒） |
| **隱私** | 旅客資料若送往第三方 API，可能違反 GDPR 等法規 |

**微調（fine-tuning）** 和 **蒸餾（distillation）** 分別從不同角度解決這個問題：
- 微調：讓較小的模型學會特定任務，降低參數浪費
- 蒸餾：讓小模型學大模型的「軟知識」，在品質接近的前提下大幅降低大小

---

## 2. Full Fine-Tuning：所有參數都更新

Full fine-tuning 直接對預訓練模型的所有參數進行梯度更新。

```
原始模型：每個線性層有 W（例如 4096 × 4096 = 16,777,216 個參數）
Full FT ：直接更新 W，optimizer 需要為每個參數存梯度和動量

記憶體需求估算（以單層為例）：
  模型權重（float32）：4096 × 4096 × 4 bytes = 64 MB
  梯度：同樣 64 MB
  Adam optimizer 狀態（m, v）：128 MB
  單層合計：≈ 256 MB

一個 7B 參數模型（float32）：
  模型本身：~28 GB
  訓練所需總記憶體：~112 GB   ← 需要多張高階 GPU
```

**優點：** 品質最好，所有層都能適應新任務。
**缺點：** 成本極高，大多數場景難以負擔。

---

## 3. LoRA：低秩假設與參數計算

### 3.1 核心假設

LoRA（Hu et al., 2021）的假設：**預訓練模型在下游任務上的權重更新 ΔW，本質上是低秩的**。

意思是說，ΔW（4096 × 4096 的矩陣）雖然很大，但它的「有效資訊量」可以用兩個小矩陣的乘積來近似：

```
ΔW ≈ B × A

其中：
  W  ∈ R^(d_out × d_in)      原始凍結權重
  A  ∈ R^(rank × d_in)       下游適配矩陣 A
  B  ∈ R^(d_out × rank)      下游適配矩陣 B
  rank << min(d_out, d_in)   rank 是關鍵超參

推論時：
  output = (W + B × A) × input
         = W × input + B × A × input
```

A 用隨機高斯初始化，B 初始化為全零（確保訓練開始時 ΔW = 0，不破壞預訓練能力）。

### 3.2 LoRA 參數量計算（完整算例）

**設定：**
- 模型維度 d = 4096（輸入與輸出維度相同）
- rank = 8
- 一個線性層（Query 或 Value 投影矩陣）

**Full Fine-Tuning 的參數量：**
```
一個線性層：d_out × d_in = 4096 × 4096 = 16,777,216 個參數

假設模型有 32 層，每層有 4 個需要適配的矩陣（Q, K, V, O）：
Full FT 可訓練參數 = 32 × 4 × 16,777,216
                   = 2,147,483,648
                   ≈ 2.1 × 10⁹（約 21 億個參數）
```

**LoRA（rank=8）的參數量：**
```
矩陣 A：rank × d_in  = 8 × 4096 = 32,768 個參數
矩陣 B：d_out × rank = 4096 × 8 = 32,768 個參數
單層單矩陣：32,768 + 32,768 = 65,536 個參數

假設同樣 32 層，4 個矩陣：
LoRA 可訓練參數 = 32 × 4 × 65,536
               = 8,388,608
               ≈ 8.4 × 10⁶（約 840 萬個參數）

參數比例：8,388,608 / 2,147,483,648 ≈ 0.39%
```

**結論：** LoRA 只需更新原本 0.39% 的參數量。

**注意事項：** 這個比例只比較「可訓練參數」。訓練時記憶體仍包含：
- 凍結的基礎模型權重（需要載入）
- 前向傳播的中間 activation
- adapter 本身的梯度與 optimizer 狀態

### 3.3 rank 的影響

| rank | 可訓練參數（單層） | 適合場景 |
|------|---------------|---------|
| 4    | 33,792        | 極輕量適配，任務差異小 |
| 8    | 65,536        | 常用預設值 |
| 16   | 131,072       | 任務差異較大 |
| 64   | 524,288       | 接近 Full FT 品質，但成本仍遠低於 Full FT |

---

## 4. QLoRA：在消費級 GPU 上跑

### 4.1 核心思路

QLoRA（Dettmers et al., 2023）在 LoRA 基礎上加了一層：**先把凍結的基礎模型量化到 4-bit，再在其上訓練 LoRA adapter**。

```
QLoRA 流程：
  ① 載入預訓練模型，用 NF4（4-bit NormalFloat）量化
  ② 凍結量化後的基礎模型（不更新）
  ③ 在基礎模型上加 LoRA adapter（仍用 BFloat16 精度）
  ④ 只更新 adapter 的參數
  ⑤ 推論時，用 DoubleQuantization 和 paged optimizer 管理記憶體
```

### 4.2 記憶體節省的直觀說明

```
基礎模型 7B 參數的記憶體佔用：

  FP32（32 bit）：7 × 10⁹ × 4 bytes = 28 GB
  FP16（16 bit）：7 × 10⁹ × 2 bytes = 14 GB
  NF4 （4 bit） ：7 × 10⁹ × 0.5 bytes = 3.5 GB  ← QLoRA 的基礎模型部分

加上 LoRA adapter（rank=8，FP16）：
  adapter 參數量約 840 萬（以上述計算為例）
  adapter 記憶體：8.4 × 10⁶ × 2 bytes ≈ 17 MB（可忽略不計）

QLoRA 訓練時總記憶體（估算）：
  量化基礎模型：~3.5 GB
  Activation：~2-4 GB（視 batch size）
  Adapter 梯度與 optimizer：~0.1 GB
  合計：~6-8 GB   ← 24 GB VRAM 的消費級 GPU 可以執行
```

### 4.3 NF4 量化的直觀說明

NF4（4-bit NormalFloat）針對「預訓練模型的權重通常接近正態分布」這個觀察設計量化區間，使量化誤差在統計上最小，比一般的 INT4 量化精度損失更小。

### 4.4 工具：PEFT LoraConfig

```python
from peft import LoraConfig, get_peft_model, TaskType
from transformers import AutoModelForCausalLM, BitsAndBytesConfig
import torch

# QLoRA：先載入 4-bit 量化的基礎模型
bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",          # NormalFloat 4-bit
    bnb_4bit_compute_dtype=torch.bfloat16,
    bnb_4bit_use_double_quant=True,     # DoubleQuantization 進一步節省記憶體
)

base_model = AutoModelForCausalLM.from_pretrained(
    "meta-llama/Llama-2-7b-hf",
    quantization_config=bnb_config,
    device_map="auto",
)

# 設定 LoRA adapter
lora_config = LoraConfig(
    r=8,                          # rank
    lora_alpha=16,                # 縮放因子（通常設為 2 × rank）
    target_modules=["q_proj", "v_proj"],  # 只在 Q、V 加 adapter
    lora_dropout=0.05,
    bias="none",
    task_type=TaskType.CAUSAL_LM,
)

model = get_peft_model(base_model, lora_config)
model.print_trainable_parameters()
# 輸出示例：trainable params: 4,194,304 || all params: 6,742,609,920 || trainable%: 0.0622
```

---

## 5. 蒸餾（Distillation）

### 5.1 基本概念

蒸餾（Hinton et al., 2015）讓小模型（學生）從大模型（教師）學習，不只學硬標籤（哪個答案對），而是學**軟標籤（soft label）**：教師對每個答案的信心分布。

```
一般分類（硬標籤）：
  正確答案 = [0, 0, 1, 0]  （第三類）

教師的軟標籤（temperature=4）：
  教師輸出 = [0.05, 0.10, 0.75, 0.10]

軟標籤的資訊量更豐富：
  → 告訴學生「第二類和第四類都有一定相似性」
  → 學生不只學「這個例子是第三類」，還學「什麼樣的例子容易和第二類混淆」
```

在旅行助理場景，教師（大模型）對「取消 / 延後 / 保留」三種處置各有信心度，學生（小模型）學習這個完整的概率分布，而不是只知道「正確答案是保留」。

### 5.2 注意事項：教師偏差會遺傳

如果教師模型本身有偏差（例如習慣性把「旅客晚到」判斷為「取消」），學生會學到同樣的偏差。

**驗證建議：**
- 用獨立人工標注集，同時評估教師、學生和規則基線
- 比較三者的錯誤模式，確認學生的錯誤不是從教師繼承的

---

## 6. 小模型評估：三指標框架

### 6.1 為什麼不能只看準確率

**反例（實際部署失敗案例）：**

```
評估報告（僅看 accuracy）：
  小模型 accuracy：87.3%
  大模型 accuracy：89.1%

判斷：「小模型品質差距只有 1.8%，可以上線」

部署後實際情況：
  小模型 p99 延遲：4.2 秒   ← 超過業務 timeout 2 秒
  前端 timeout 比例：23%
  客服工單激增 → 緊急回滾
```

準確率達標，但延遲不達標，導致系統實際不可用。

### 6.2 三指標評估框架

| 指標 | 定義 | 測量方式 | 門檻範例 |
|------|------|---------|---------|
| **錯誤率（Error Rate）** | 系統做出錯誤決策的比例 | 測試集 accuracy 的反面 | ≤ 10% |
| **p99 延遲（p99 Latency）** | 99% 請求的回應時間 | 壓力測試 1000 筆 | ≤ 2000 ms |
| **人工介入率（Human Intervention Rate）** | 需要轉給人工處理的比例 | 生產環境實際記錄 | ≤ 15% |

**三個指標缺一不可：**
- 只看錯誤率：模型可能準但慢
- 只看延遲：模型可能快但錯
- 只看錯誤率和延遲：模型可能在長尾案例（罕見情境）上一直失敗，但被 aggregate 指標掩蓋，直到人工介入率居高不下才發現

### 6.3 完整評估報告範例

```
模型版本：travel-assistant-small-v2.1
評估日期：2024-02-20
評估集：1,200 筆（含 15% 長尾案例）
硬體：一張 A10G GPU（消費級伺服器）

指標摘要：
  錯誤率          8.3%  ✓  (門檻 ≤ 10%)
  p99 延遲       1,840 ms ✓  (門檻 ≤ 2,000 ms)
  人工介入率      12.1%  ✓  (門檻 ≤ 15%)

切片分析：
  一般入住查詢    錯誤率 4.2%  延遲 820 ms
  改 Check-in     錯誤率 7.8%  延遲 1,200 ms
  多人訂房操作    錯誤率 18.5% ← 超標！需進一步處理
  餐廳訂位查詢    錯誤率 6.1%  延遲 950 ms

結論：整體指標達標，但「多人訂房操作」切片錯誤率偏高，
      建議在此切片補充訓練資料後再全面上線。
```

---

## 7. 方法比較與選型

| 方法 | 品質 | 訓練成本 | 推論成本 | 硬體需求 | 適用場景 |
|------|------|---------|---------|---------|---------|
| **Full FT** | 最高 | 最高 | 取決於模型大小 | 多張高階 GPU | 有大量標注資料，且有充足算力 |
| **LoRA** | 高（接近 Full FT） | 低（只更新 0.4%） | 同基礎模型 | 1-2 張 GPU | 任務定義清晰，有適量標注資料 |
| **QLoRA** | 稍低於 LoRA | 低 | 略慢（量化開銷） | 消費級 GPU 可跑 | 資源受限，需在本地部署 |
| **蒸餾** | 取決於學生架構 | 中（需教師推論） | 學生模型的成本 | 視學生大小 | 需大幅降低推論延遲，有大量教師示範 |

**選型建議：**

```
我有多少 GPU 記憶體？
  ≥ 40 GB：可考慮 Full FT 或 LoRA（大模型）
  16-24 GB：LoRA（中型模型）
  < 16 GB：QLoRA

我的目標是什麼？
  降低推論成本 / 延遲：蒸餾（訓練一個更小的學生模型）
  讓現有模型適應新任務：LoRA / QLoRA
  最高品質無視成本：Full FT

我有多少標注資料？
  < 1,000 筆：LoRA（Full FT 容易 overfit）
  1,000-10,000 筆：LoRA 或 QLoRA
  > 10,000 筆：Full FT 或蒸餾（有足夠資料訓練學生）
```

---

## 8. 習題

**習題 1（手算 LoRA 參數量）**
某模型的一個線性層維度為 d_in = 2048、d_out = 2048。若使用 LoRA rank = 16，請計算：
(a) LoRA adapter（A + B 兩個矩陣）的總參數量。
(b) 相比 Full Fine-Tuning 此層的參數，LoRA 的參數比例是多少？

<details><summary>解答</summary>

**(a) LoRA adapter 參數量：**
```
矩陣 A：rank × d_in  = 16 × 2048 = 32,768
矩陣 B：d_out × rank = 2048 × 16 = 32,768
合計：32,768 + 32,768 = 65,536 個參數
```

**(b) 比例：**
```
Full FT 此層參數量：d_out × d_in = 2048 × 2048 = 4,194,304
比例：65,536 / 4,194,304 ≈ 1.56%
```

</details>

---

**習題 2（QLoRA 記憶體估算）**
一個 13B 參數的模型，請估算以下三種載入方式的基礎模型記憶體佔用（不含 activation 和 optimizer）：
(a) FP32 精度
(b) FP16 精度
(c) NF4 量化（4-bit）

<details><summary>解答</summary>

```
13B = 13 × 10⁹ 個參數

(a) FP32（每個參數 4 bytes）：
    13 × 10⁹ × 4 = 52 × 10⁹ bytes = 52 GB

(b) FP16（每個參數 2 bytes）：
    13 × 10⁹ × 2 = 26 × 10⁹ bytes = 26 GB

(c) NF4（每個參數 0.5 bytes）：
    13 × 10⁹ × 0.5 = 6.5 × 10⁹ bytes = 6.5 GB
```

**實務意義：** QLoRA 讓 13B 的基礎模型在約 6.5 GB（加上 activation 和 adapter 約 10-12 GB）的 GPU 上訓練，24 GB VRAM 的消費級 GPU 即可應付。

</details>

---

**習題 3（選型）**
旅行助理需要部署一個「訂位狀態分類器」，把輸入文字分成「已確認 / 待確認 / 已取消」三類。已知：
- 訓練資料：5,000 筆，人工標注
- 目標延遲：p99 ≤ 500 ms（非常嚴格）
- 部署環境：公司內網伺服器，無法使用第三方 API，有一張 RTX 4090（24 GB VRAM）

請說明應選哪種方法，並解釋理由。

<details><summary>解答</summary>

**建議：蒸餾（Distillation）**，或 **LoRA 微調一個小型基礎模型**（例如 1B 以下）。

**理由：**

1. **延遲要求嚴格（≤ 500 ms）**：大型模型（7B+）的推論延遲通常超過 500 ms p99，需要用較小的模型。

2. **資料量適中（5,000 筆）**：足以訓練一個小型分類器或 LoRA adapter，不需要 Full FT。

3. **部署環境限制**：公司內網，24 GB VRAM 的 RTX 4090，可以輕鬆跑 QLoRA 或小模型的 LoRA。

**具體建議流程：**
- 先用大模型（如 GPT-4）標注 5,000 筆生成軟標籤（教師的信心分布）
- 訓練一個 BERT-base 或 DeBERTa-small 等級的分類模型（學生）
- 評估三指標：錯誤率應 ≤ 10%，p99 延遲應遠低於 500 ms，人工介入率應 ≤ 15%

**如果蒸餾後品質不足：** 改用 LoRA 微調 Llama-3.2-1B，仍在 24 GB VRAM 範圍內，延遲也相對可控。

</details>

---

## 延伸閱讀

- Hu, E. et al. (2021). [LoRA: Low-Rank Adaptation of Large Language Models](https://arxiv.org/abs/2106.09685). ICLR 2022.
- Dettmers, T. et al. (2023). [QLoRA: Efficient Finetuning of Quantized LLMs](https://arxiv.org/abs/2305.14314). NeurIPS.
- Hinton, G. et al. (2015). [Distilling the Knowledge in a Neural Network](https://arxiv.org/abs/1503.02531). NIPS Workshop.

---

[章節導覽](intro.md) · [上一節](01-feedback-and-learning.md) · [下一節](03-execution-control.md)
