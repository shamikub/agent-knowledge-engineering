# 評估、錯誤診斷與能力邊界

[課程首頁](../../README.md) · [Lab 05](../../labs/05/README.md)

## 本章小節

- [5.1 一筆評估案例有哪些部分](01-evaluation-datasets.md)
- [5.2 Oracle 實驗：用受控環境定位錯誤模組](02-oracle-ablation.md)
- [5.3 切片分析：找出系統的弱點](03-slice-analysis.md)
- [5.4 信心校準與放行門檻](04-calibration-and-abstention.md)

## Week 9 · 用對照測試分離錯因

離線標註一筆案例的預期處置、完整證據集合和可接受引用。用不同旅程或政策版本切分 train、validation、test，以免同一則訂位信換改寫就進兩邊。

固定案件與答案模組，替換實際檢索為人工選定的證據做 Oracle Retrieval。若表現改善，追查候選、排序與版本過濾。若仍失敗，追查條件表示、必填資料和下游處置。對照加入舊版且調換證據位置，比較干擾效應。每次實驗只改一個變數，不能同時改動多個模組。

按跨日、版本衝突、缺資料與別名切片報告，確認哪種失敗模式最嚴重。整體準確率會隱藏邊緣情境的問題，切片報告才能找出系統的真正弱點。找到最弱切片後，用切片驅動的改進循環針對性修改，並確認其他切片未退步。

## Week 10 · 轉人工的代價

Selective prediction 允許 abstain。Coverage=放行數/總案件數。Selective risk=放行錯案/放行數，無放行時風險未定義。門檻在 validation 決定，保留 test 報告。模型自報機率要做 calibration 查核，可畫 reliability diagram，或計算 Brier score。Conformal Risk Control 在特定可交換性和損失條件下控制預期風險，旅程資料分布改變時要重驗。

練習。100 筆中放行 80 筆錯 8 筆，另一門檻放行 60 筆錯 3 筆。計算兩點並寫出選門檻需要的成本資訊。

閱讀：[ALCE](https://arxiv.org/abs/2305.14627)、[Lost in the Middle](https://arxiv.org/abs/2307.03172)、[Conformal Risk Control](https://arxiv.org/abs/2208.02814)。前沿作業找一份有拒答能力的 benchmark，核對不可回答標記與評分如何算。

## 延伸閱讀關鍵字

- **先讀**：Oracle Retrieval ablation、ALCE citation support、counterfactual RAG evaluation。找出如何控制證據，分辨檢索與下游判斷錯誤。
- **再讀**：selective classification AURC、reliability diagram、Brier score、Conformal Risk Control exchangeability。查可接受的轉人工門檻怎麼在盲測前選定。
- **實務入口**：slice-based evaluation、grouped train-test split、Langfuse trace to dataset。練習把一次錯答變成可重跑的測試。
