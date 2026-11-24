# 資訊檢索與 RAG

[← 上一頁](../chapter3/03-bitemporal-modeling.md) · [總目錄](../../README.md#課程地圖) · [下一頁 →](01-why-retrieval.md)

[本章 Lab](../../labs/04/README.md)

## 本章小節

- [4.1 為什麼不能直接把所有知識送給 LLM](01-why-retrieval.md)
- [4.2 稀疏檢索：倒排索引與 BM25](02-sparse-retrieval.md)
- [4.3 稠密檢索：向量如何表達語意](03-dense-retrieval.md)
- [4.4 從候選到重排](04-reranking-and-fusion.md)
- [4.5 從檢索到回答](05-rag.md)
- [4.6 習題與整合練習](06-exercises.md)

## 學習目標與先備知識
本章涵蓋第 7–8 週。先備知識為集合運算、對數與向量內積。讀完後應能從文件建倒排索引、手算 BM25 和融合排名、解釋向量檢索與重排的計算差異，並用標註證據驗收一條 RAG 管線。

## 問題定義
給定查詢 q、文件集合 D 與回傳預算 k，檢索器輸出有序的至多 k 份候選。重排序器接收固定候選並重新排列。多跳取證可能根據第一批證據再發出查詢。回答模組才負責用證據解題與引用。這四步可以各自失敗，因此各有驗收方式。

## 參考閱讀
閱讀：[DPR](https://arxiv.org/abs/2004.04906)、[SPLADE](https://arxiv.org/abs/2107.05720)、[E5](https://arxiv.org/abs/2212.03533)、[ColBERTv2](https://arxiv.org/abs/2112.01488)、[BEIR](https://arxiv.org/abs/2104.08663)、[MIRACL](https://arxiv.org/abs/2210.09984)。前沿作業挑一個語言與固定切分，核對候選模型、reranker 和訓練資料。

## 延伸閱讀關鍵字

- **先讀**：Lucene BM25Similarity、SPLADE vocabulary expansion、E5 query passage prefixes、ColBERT MaxSim。比較各方法在哪一層做匹配。
- **再讀**：cross-encoder reranking、RRF rank fusion、HNSW recall latency、filtered ANN。查同一個 k 和同一批候選下如何公平比較。
- **研究入口**：BEIR zero-shot retrieval、MIRACL zh qrels、multi-hop evidence retrieval。追查高 nDCG 是否代表主條款與例外都找齊。

[← 上一頁](../chapter3/03-bitemporal-modeling.md) · [總目錄](../../README.md#課程地圖) · [下一頁 →](01-why-retrieval.md)
