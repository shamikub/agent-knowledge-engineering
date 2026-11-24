# 持續學習、模型選擇與行為控制

[課程首頁](../../README.md) · [Lab 06](../../labs/06/README.md)

## 本章小節

- [6.1 一次人工改判能更新哪一層](01-feedback-and-learning.md)
- [6.2 微調與蒸餾從權重怎麼看](02-fine-tuning-and-distillation.md)
- [6.3 執行控制從一筆寫入看](03-execution-control.md)
- [6.4 發版前重播](04-release-and-replay.md)

## Week 11 · 修知識、修策略、修權重
知識修正更新版本和來源。策略更新調整何時詢問、查詢和執行。DAgger 讓現有策略走到自己的狀態分布，再向專家詢問那些狀態該怎麼做，重複聚合資料。Continual learning 必須驗證新任務和舊任務，replay 以過去樣本監測及緩解遺忘。LoRA 凍結原始權重，以低秩更新適配；QLoRA 將基礎權重量化再訓練 adapter。蒸餾則讓小模型學教師產生的分布或示範。評估小模型時同時報告錯誤率、延遲和人工介入率。

## Week 12 · 發布、授權與工具結果
Constrained decoding 限定輸出結構。OPA／Cedar 用政策決定動作是否授權。執行層還要檢查業務參數與狀態。用 idempotency key 綁定同一次操作和請求內容，重送時回報原結果。示範用記憶體；跨程序與並發服務需要持久化、交易及唯一約束。

知識發布保留舊版本，以修改項連回受影響的測試。新版本先跑回歸；必要時回滾並記下當時決策所用版本。工具呼叫紀錄區分提議、核准、執行、最終狀態。

練習。玩家因改航班晚到，問了兩次是否要改晚餐。設計同 key 同參數和同 key 不同參數的預期結果，再畫狀態轉移。

閱讀：[DAgger](https://proceedings.mlr.press/v15/ross11a.html)、[LoRA](https://arxiv.org/abs/2106.09685)、[QLoRA](https://arxiv.org/abs/2305.14314)、[Knowledge Distillation](https://arxiv.org/abs/1503.02531)、[OPA](https://www.openpolicyagent.org/docs/)。前沿作業挑一個小模型評估，核對語言、延遲硬體、量化設定和場景是否可重現。

## 延伸閱讀關鍵字

- **先讀**：DAgger covariate shift、continual learning replay、catastrophic forgetting。比較更新知識、策略與權重分別解哪種錯。
- **再讀**：LoRA rank ablation、QLoRA NF4、knowledge distillation temperature。查小模型的品質、延遲和成本怎麼對照。
- **實務入口**：OPA policy testing、Cedar authorization、idempotency key semantics、shadow deployment。驗證重送、權限和發版行為。
