# 3.2 把關係存起來再查

建兩筆三元組 trainA affects checkin、checkin affects roomChange。SPARQL 以變數比對圖樣，可用 affects+ 取至少一跳。查 trainA 會找到 checkin 和 roomChange。SHACL 檢查例如每項訂位至少有一個來源。PROV-O 的 wasDerivedFrom 指向輸入證據。多個版本或互相衝突的陳述，可各自留在具名圖再按有效版本查。Property Graph 可把時間與來源直接放在邊上。

同一查詢可用 SQLite 的 edge 表和 recursive CTE。遍歷用 UNION 去重或記錄已訪問節點，否則 A→B→A 可持續展開。關聯資料容易整合交易和約束，圖譜適合多種關係、多跳查詢與跨資料語意。兩個工具都能查上述例子，選型要量查詢頻率、資料更新與維護成本。

[章節導覽](intro.md) · [上一節](01-decision-tables.md) · [下一節](03-bitemporal-modeling.md)
