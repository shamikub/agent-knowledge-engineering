# 文件、語音與流程探勘

[課程首頁](../../README.md) · [Lab 01](../../labs/01/README.md)

## 本章小節

- [1.1 文件解析的每一層](01-documents.md)
- [1.2 音訊與操作的事件證據](02-audio-and-ui.md)
- [1.3 從軌跡到流程樹](03-process-mining.md)

## Week 1 · 從訊號到證據
文件理解包含文字辨識、版面分區、閱讀順序、表格列欄復原。文字型 PDF 可先讀文字層，掃描需 OCR。LayoutLMv3 結合字詞、框的位置和影像 patch 進行預訓練。Table Transformer 用物件偵測模型標表格與表格結構。拿「住宿欄跨兩列」作例子，文字全認對仍可能把洗衣設備掛錯住宿。OCR 可用 CER（字元編輯距離除以參考字數），表格另外量儲存格對齊與結構。

Whisper 做語音轉文字。WhisperX 以 forced alignment 對齊字詞時間，搭配 diarization 把片段分給講者。逐字稿字對了，仍可能判錯發言人。操作證據優先考慮應用程式事件；rrweb 重播 DOM，Accessibility Tree 表達介面語意。實際輸入保留來源定位和事件時間。

## Week 2 · 流程發現與一致性
流程發現從事件日誌推模型。一個 case 可是一筆訂位。OCEL 2.0 允許同一事件同時關聯車票、旅客和整趟旅程。Directly-follows graph 統計緊鄰活動；Alpha Miner 用先後關係辨識流程結構，Heuristics Miner 用頻率和相依度處理噪音，Inductive Miner 遞迴尋找循序、選擇、平行或迴圈的切分並生成流程樹。觀察到「取消 → 重訂」證明兩個步驟相鄰，原因仍需來源補足。

Alignment 把觀察軌跡對齊模型行為。Fitness 量觀察記錄能否被模型重現，precision 懲罰模型容許太多未觀察行為。讓所有動作都能任意發生，fitness 可能很好，precision 會下降。

練習。對 AB、AC、ABC 三條軌跡手算邊的頻次。刪去 ABC 後解釋 B→C 消失的含義。

閱讀：[LayoutLMv3](https://arxiv.org/abs/2204.08387)、[PubTables-1M](https://arxiv.org/abs/2110.00061)、[WhisperX](https://arxiv.org/abs/2303.00747)、[OCEL 2.0](https://www.ocel-standard.org/)、[PM4Py](https://processintelligence.solutions/static/api/2.7.17/api.html)。前沿作業挑文件版面或表格辨識，查一個公開資料集上同一指標的兩個結果。

## 延伸閱讀關鍵字

- **先讀**：OCR reading order、LayoutLMv3 word-patch alignment、Table Transformer、GriTS。查文字辨識正確時，表格結構還可能怎麼錯。
- **再讀**：WhisperX forced alignment、pyannote diarization error rate、rrweb incremental snapshots。比較轉錄、講者分配和操作重播可提供的證據。
- **研究入口**：OCEL 2.0、Inductive Miner IMf、alignment-based conformance checking。用 PM4Py 查 fitness、precision 及罕見路徑的取捨。
