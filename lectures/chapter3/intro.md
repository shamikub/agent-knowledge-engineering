# 知識表示、版本與壓縮

[← 上一頁](../chapter2/04-expert-review.md) · [總目錄](../../README.md#課程地圖) · [下一頁 →](01-decision-tables.md)

[本章 Lab](../../labs/03/README.md)

## 本章小節

- [3.1 把自然語言落成可執行規則](01-decision-tables.md)
- [3.2 把關係存起來再查](02-knowledge-graphs.md)
- [3.3 版本的兩個時鐘](03-bitemporal-modeling.md)

> **注意：** 壓縮（context 管理）相關內容已移至第 4 章「[4.1 為什麼不能直接把所有知識送給 LLM](../chapter4/01-why-retrieval.md)」中討論。

## Week 5 · 表、圖與規則
DMN 的決策表由條件和輸出組成。Unique 要求至多一列命中，First 按列優先順序選擇，Collect 蒐集多個命中。FEEL 讓時間、數字和區間可被機器計算。「不知是否能延後」應保存為未知，避免和「不能延後」套同一分支。

RDF 用主詞、述詞、受詞表示陳述。SPARQL 以圖樣比對查關係，SHACL 檢查必要欄位及形狀，PROV-O 可以表示衍生關係。Property Graph 允許把屬性放在節點與邊。當查詢是「改哪一段會影響哪些憑證」，從行程項目沿 dependsOn 邊遍歷。SQLite 也可用關聯表及 recursive CTE 做同一查詢。

## Week 6 · 時間
Bitemporal 記 valid time 與 transaction time。例如取消政策 4/1 起有效，4/5 才匯入。重放 4/3 的助理決定時，必須以當時已知的版本還原。實作可用半開區間避免相鄰版本在邊界同時適用。

練習。畫出延誤 → 入住、入住 → 換房的兩條邊，補效期與來源，再查兩跳影響。加一個環並說明遍歷如何終止。

閱讀：[DMN](https://www.omg.org/dmn/)、[SHACL](https://www.w3.org/TR/shacl/)、[PROV-O](https://www.w3.org/TR/prov-o/)、[RAPTOR](https://arxiv.org/abs/2401.18059)、[LongLLMLingua](https://arxiv.org/abs/2310.06839)。前沿作業比較兩種壓縮方法，排齊 token 預算、回答模型和任務。

## 延伸閱讀關鍵字

- **先讀**：DMN hit policies、FEEL null semantics、SHACL closed shapes、SPARQL property paths。沿著同一筆入住案例比較表格、約束與圖查詢。
- **再讀**：W3C PROV-O wasDerivedFrom、bitemporal valid time transaction time、recursive CTE cycle detection。查如何重播助理在某天能看到的版本。
- **研究入口**：RAPTOR hierarchical retrieval、LongLLMLingua context compression、fact retention。查如何在相同 token 預算下比較例外條件保留率。

[← 上一頁](../chapter2/04-expert-review.md) · [總目錄](../../README.md#課程地圖) · [下一頁 →](01-decision-tables.md)
