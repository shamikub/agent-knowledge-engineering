# 1.2 語音轉文字與說話者識別

[← 上一頁](01-documents.md) · [本章導覽](intro.md) · [總目錄](../../README.md#課程地圖) · [下一頁 →](03-ui-operations.md)

## 學習目標

完成本節後，你應能：

1. 描述 Whisper 與 WhisperX 的架構差異，說明強制對齊（forced alignment）的作用與輸出格式。
2. 解釋說話者分離（speaker diarization）的輸出與轉錄合併時可能產生的錯誤，並說明應如何驗收。

---

## 任務定義

### 子任務：語音辨識與說話者標記

**輸入**：音訊檔（WAV / MP3 / M4A）或即時音訊串流

**輸出**：帶時間戳與說話者標籤的逐字稿，每段記錄結構如下：

```json
{
  "start": 10.24,
  "end": 13.81,
  "speaker": "SPEAKER_01",
  "text": "那我先把八點那張退掉",
  "word_segments": [
    {"word": "那", "start": 10.24, "end": 10.41, "score": 0.98},
    {"word": "我", "start": 10.41, "end": 10.56, "score": 0.97},
    ...
  ]
}
```

**關鍵指標**

| 指標 | 全名 | 衡量對象 |
|------|------|----------|
| **WER**（詞錯誤率） | Word Error Rate | 辨識出的詞序列與參考序列的編輯距離比率 |
| **DER**（說話者錯誤率） | Diarization Error Rate | 說話者片段被錯誤分配的時間比例 |

---

## 架構說明

### 語音處理三層管線

```
音訊檔
   │
   ▼ [層 1] 語音辨識（ASR）：Whisper
   │  輸入：log-Mel 頻譜（80 個 Mel bin，30 秒為單位）
   │  輸出：段落文字（無詞級時間戳）
   │
   ▼ [層 2] 強制對齊（Forced Alignment）：WhisperX / wav2vec2
   │  輸入：音訊 + Whisper 轉錄文字
   │  輸出：每個詞的 [start, end, score]
   │
   ▼ [層 3] 說話者分離（Diarization）：pyannote.audio
      輸入：音訊
      輸出：說話者片段清單 [start, end, speaker_id]
      合併：以詞的時間戳對齊說話者片段，決定每個詞屬於哪位說話者
```

### Whisper vs WhisperX 核心差異

**Whisper**（OpenAI，2022）
- 編碼器：Transformer，輸入 log-Mel 頻譜
- 解碼器：自迴歸（autoregressive），逐 token 生成
- 輸出：段落層級時間戳（每個段落一個 start/end）
- 限制：無詞級時間戳；無說話者資訊

**WhisperX**（Bain et al., 2023，[arXiv:2303.00747](https://arxiv.org/abs/2303.00747)）
- 以 Whisper 做初步轉錄
- 以 wav2vec2 / phoneme 模型做**強制對齊**，將每個詞對到音訊時間軸
- 再以 pyannote.audio 做說話者分離，合併詞級時間與說話者片段
- 輸出：詞級時間戳 + 說話者標籤

---

## 完整算例：字對了但說話者錯誤的反例

### 情境

雙人歐洲自由行，A 與 B 在討論是否取消訂位：

**原始音訊片段（真實說話者）**

```
00:10–00:13  SPEAKER_A：「我退掉八點那張，改十點。」
00:13–00:16  SPEAKER_B：「先等一下，我看看有沒有更便宜的。」
```

### WhisperX 輸出（詞級時間戳正確）

```json
[
  {"start": 10.1, "end": 13.2, "text": "我退掉八點那張，改十點。", "speaker": "SPEAKER_A"},
  {"start": 13.3, "end": 16.5, "text": "先等一下，我看看有沒有更便宜的。", "speaker": "SPEAKER_B"}
]
```

此時 WER = 0（字完全正確）、說話者也對，是理想情況。

### 反例：說話者分離錯誤

假設 pyannote 把 00:12–00:16 那段錯誤地分配給 SPEAKER_A，合併後：

```json
[
  {"start": 10.1, "end": 11.9, "text": "我退掉八點那張", "speaker": "SPEAKER_A"},
  {"start": 12.0, "end": 16.5, "text": "改十點。先等一下，我看看有沒有更便宜的。", "speaker": "SPEAKER_A"}
]
```

**只改了一個條件**（說話者分段邊界從 00:13 移到 00:12）：

- WER 仍為 0：所有字都辨識正確
- DER > 0：有約 3.5 秒被分配到錯誤說話者

**後果**：知識工程師若直接用這份逐字稿判斷「誰決定取消訂位」，會誤以為 A 自說自話，看不到 B 的反對意見，導致決議「A 同意取消」——但實際上決議仍待確認。

### 正確處理方式

1. 存入**原始音訊區間 + 說話者 + 原話**，不直接推論決議。
2. 說話者置信度低（DER 較高片段）的記錄，另加標記送人工佇列。
3. 決議萃取模組需核對「另一位說話者是否有反對/改口」。

---

## 方法比較：Whisper vs WhisperX

| 面向 | Whisper | WhisperX |
|------|---------|----------|
| 時間戳粒度 | 段落（sentence-level） | 詞（word-level） |
| 說話者資訊 | 無 | 有（需 pyannote） |
| 多說話者場景 | 轉錄混在一起 | 可分割不同說話者的台詞 |
| 額外依賴 | 無 | wav2vec2 + pyannote（需 Hugging Face token） |
| 推論速度 | 快（large-v3 約 20× 實時） | 稍慢（需額外對齊步驟） |
| 適用場景 | 單一說話者錄音、無需說話者標記 | 會議錄音、訪談、多人對話 |

---

## 研究與實務

- **WhisperX 論文**：Bain et al., 2023，[arXiv:2303.00747](https://arxiv.org/abs/2303.00747)
- **pyannote.audio**：Bredin et al.，說話者分離的業界標準開源工具，支援 DER 評估

**注意**：WhisperX 需要 Hugging Face 存取 token 才能使用 pyannote 模型（`pyannote/speaker-diarization-3.1`），使用前請確認授權。

---

## 工具與實驗

### WhisperX 基本用法

```python
import whisperx

# 步驟 1：載入模型並轉錄
model = whisperx.load_model("large-v2", device="cpu", compute_type="int8")
audio = whisperx.load_audio("meeting.wav")
result = model.transcribe(audio, batch_size=16)
# result["segments"]：段落清單，含 start/end/text

# 步驟 2：強制對齊（詞級時間戳）
model_a, metadata = whisperx.load_align_model(
    language_code=result["language"], device="cpu"
)
result = whisperx.align(
    result["segments"], model_a, metadata, audio, device="cpu"
)
# result["word_segments"]：每個詞的 start/end/score

# 步驟 3：說話者分離（需 HuggingFace token）
diarize_model = whisperx.DiarizationPipeline(
    use_auth_token="YOUR_HF_TOKEN", device="cpu"
)
diarize_segments = diarize_model(audio)
result = whisperx.assign_word_speakers(diarize_segments, result)
# 每個 segment 與 word 現在有 "speaker" 欄位
```

**WhisperX 實作了哪一層**：
- 步驟 1 → Whisper 轉錄（段落時間戳）
- 步驟 2 → wav2vec2 強制對齊（詞級時間戳）
- 步驟 3 → pyannote.audio 說話者分離 + 合併

---

## 習題

**習題 1（機制）**：Whisper 在輸出段落「先等一下，我看看有沒有更便宜的。」時，只給出該段落的 start=13.3、end=16.5，沒有詞級時間戳。請說明：若你想知道「更便宜」這三個字是在哪個時間點說的，WhisperX 的強制對齊步驟如何提供這個資訊？強制對齊的輸入是什麼？

<details>
<summary>解答</summary>

強制對齊（forced alignment）的輸入是：

1. **音訊波形**（或 log-Mel 頻譜）
2. **已知的文字序列**（Whisper 轉錄結果）

步驟：wav2vec2 等聲學模型先將音訊編碼為逐幀的音素機率，再使用**動態時間規整（DTW）**或 **CTC 路徑對齊**，強迫文字序列中每個字元（音素）對應到音訊時間軸上的某個幀，從而推算出每個詞的 start 和 end。

與 Whisper 純解碼不同，強制對齊已知「正確答案是哪些字」，只需找出每個字在時間軸的位置，不需要重新預測文字，因此在已有轉錄的情況下速度較快、對齊精度較高。

</details>

---

**習題 2（算例）**：以下是一段四人討論的 DER 計算場景。真實說話者分段（以秒為單位）：

```
0–5    SPEAKER_A
5–10   SPEAKER_B
10–15  SPEAKER_A
15–20  SPEAKER_C
```

模型預測的分段：

```
0–5    SPEAKER_A   ← 正確
5–12   SPEAKER_A   ← 錯誤（應為 B 和 A）
12–20  SPEAKER_C   ← 部分正確
```

請計算這 20 秒錄音的**說話者錯誤時間**（以秒計），並說明 DER 的計算方式。

<details>
<summary>解答</summary>

DER 的完整定義包含三種錯誤：

```
DER = (Miss + False Alarm + Speaker Error) / Total Reference Time
```

本題簡化只算 Speaker Error（說話者被分配到錯誤標籤的時間）：

逐秒比對：
- 0–5 秒：預測 A，真實 A → 正確，0 秒錯誤
- 5–10 秒：預測 A，真實 B → **全錯**，5 秒錯誤
- 10–12 秒：預測 A，真實 A → 正確，0 秒錯誤
- 12–15 秒：預測 C，真實 A → **全錯**，3 秒錯誤
- 15–20 秒：預測 C，真實 C → 正確，0 秒錯誤

總說話者錯誤時間 = 5 + 3 = **8 秒**

```
DER（Speaker Error 部分）= 8 / 20 = 0.40（40%）
```

實際 DER 工具（如 pyannote）還會考慮說話者標籤的最佳匹配（Hungarian algorithm），以最小化 speaker confusion 後再計算，本題已假設標籤直接可對比。

</details>

---

[← 上一頁](01-documents.md) · [本章導覽](intro.md) · [總目錄](../../README.md#課程地圖) · [下一頁 →](03-ui-operations.md)
