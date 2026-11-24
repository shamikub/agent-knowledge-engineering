# 3.2 把關係存起來再查（Knowledge Graphs）

[章節導覽](intro.md) · [上一節](01-decision-tables.md) · [下一節](03-bitemporal-modeling.md)

---

## 學習目標

完成本節後，你能夠：

1. 用 RDF 三元組（triple）表示旅程訂位之間的依賴關係。
2. 寫出一個使用 property path 的 SPARQL 查詢，找出「改哪段班車影響哪些住宿」。
3. 說明 Property Graph 和 RDF 在選型上的關鍵差異，以及各自適合哪種查詢場景。

**先備知識：** 看得懂關聯式資料庫的外鍵（foreign key）概念即可。不需要事先了解圖資料庫。

---

## 1. 背景橋樑：從外鍵到知識圖譜

在關聯式資料庫，你可能這樣存旅程訂位：

```sql
CREATE TABLE booking (
    id       TEXT PRIMARY KEY,
    type     TEXT,  -- 'train', 'hotel', 'room_upgrade'
    depends_on TEXT REFERENCES booking(id)
);

INSERT INTO booking VALUES ('trainA',     'train',         NULL);
INSERT INTO booking VALUES ('checkin',    'hotel',         'trainA');
INSERT INTO booking VALUES ('roomChange', 'room_upgrade',  'checkin');
```

外鍵只能存「這筆記錄依賴哪一筆」，不能直接存：
- 依賴的**原因**（例如：因為火車延誤，所以入住時間改變）
- 依賴的**有效期間**（這條依賴在哪個時間窗口成立）
- 依賴的**來源**（這是誰記錄的，根據哪封郵件）

知識圖譜（Knowledge Graph）把「關係本身」也當成一個可以附加屬性的物件。這使得「為什麼有這條邊」和「這條邊在什麼條件下成立」都能被記錄和查詢。

---

## 2. 任務定義

**輸入：** 結構化的旅程事件清單（班車、入住、房型異動），可能附有時間戳與來源說明。

**輸出：** 可遍歷的知識圖譜，能回答「修改 X 會間接影響哪些 Y」這類多跳查詢。

**子任務：**
1. **建模（Modeling）：** 決定哪些實體是節點、哪些關係是邊、邊上放哪些屬性。
2. **匯入（Ingestion）：** 把資料轉成 Turtle（RDF 文字格式）或 Cypher（Property Graph）。
3. **查詢（Query）：** 用 SPARQL 或 Cypher 寫多跳遍歷。
4. **驗證（Validation）：** 用 SHACL 確認必要欄位存在（例如每條 dependsOn 邊都有來源）。

---

## 3. 架構說明

### 3.1 RDF 三元組（Triple）

RDF（Resource Description Framework）的基本單位是三元組：

```
主詞（Subject）  述詞（Predicate）  受詞（Object）
<trainA>         <dependsOn>        <checkin>
```

三個元素都是 URI（Uniform Resource Identifier），確保語意跨系統一致。

### 3.2 Turtle 語法

Turtle 是 RDF 的人類可讀文字格式：

```turtle
@prefix trip: <http://example.org/trip#> .
@prefix prov: <http://www.w3.org/ns/prov#> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .

trip:trainA a trip:TrainSegment ;
    trip:departureTime "2024-04-10T14:30:00+02:00"^^xsd:dateTime ;
    trip:delayMinutes 35 .

trip:checkin a trip:HotelCheckin ;
    trip:scheduledTime "2024-04-10T20:00:00+02:00"^^xsd:dateTime ;
    trip:deadline      "2024-04-10T21:00:00+02:00"^^xsd:dateTime .

trip:roomChange a trip:RoomUpgrade ;
    trip:requestedAt "2024-04-10T20:45:00+02:00"^^xsd:dateTime .

# dependsOn 邊：入住依賴火車班次
trip:dep1 a trip:Dependency ;
    trip:from   trip:trainA ;
    trip:to     trip:checkin ;
    trip:reason "train delay may push arrival past 21:00" ;
    trip:validFrom "2024-04-10"^^xsd:date ;
    prov:wasAttributedTo trip:agentAssistant .

# dependsOn 邊：換房依賴入住
trip:dep2 a trip:Dependency ;
    trip:from   trip:checkin ;
    trip:to     trip:roomChange ;
    trip:reason "room upgrade only possible after checkin confirmed" ;
    trip:validFrom "2024-04-10"^^xsd:date ;
    prov:wasAttributedTo trip:agentAssistant .
```

**關鍵設計：** `dep1` 和 `dep2` 是獨立節點（reified triples），讓依賴關係本身可以附加屬性（原因、有效期、來源）。

### 3.3 SPARQL 查詢

SPARQL 以圖樣比對（graph pattern matching）查詢：

```sparql
# 查詢：trainA 透過 dependsOn 鏈，間接影響哪些事件？
PREFIX trip: <http://example.org/trip#>

SELECT ?affected
WHERE {
    # 以 trainA 為起點，沿 from/to 兩跳查依賴
    trip:trainA ^trip:from / trip:to  ?dep1target .
    ?dep1target ^trip:from / trip:to  ?affected .
}
```

**Property path 語法：**
```sparql
^trip:from        → 逆向：找 trip:from 指向 trainA 的節點（即 dep1）
^trip:from / trip:to  → 從 dep1 往 trip:to 方向走一步
```

若要查任意深度（遞迴）：

```sparql
# 一跳或多跳的所有間接影響
SELECT DISTINCT ?affected
WHERE {
    {
        trip:trainA ^trip:from / trip:to ?affected .
    } UNION {
        trip:trainA ^trip:from / trip:to / ^trip:from / trip:to ?affected .
    }
}
```

### 3.4 SHACL 約束驗證

SHACL（Shapes Constraint Language）定義圖的「形狀」規範：

```turtle
@prefix sh:   <http://www.w3.org/ns/shacl#> .
@prefix trip: <http://example.org/trip#> .

trip:DependencyShape a sh:NodeShape ;
    sh:targetClass trip:Dependency ;
    sh:property [
        sh:path trip:from ;
        sh:minCount 1 ;
        sh:message "每條 Dependency 必須有 from 欄位" ;
    ] ;
    sh:property [
        sh:path trip:to ;
        sh:minCount 1 ;
        sh:message "每條 Dependency 必須有 to 欄位" ;
    ] ;
    sh:property [
        sh:path prov:wasAttributedTo ;
        sh:minCount 1 ;
        sh:message "每條 Dependency 必須記錄是誰建立的" ;
    ] .
```

### 3.5 PROV-O 衍生關係

PROV-O（Provenance Ontology）提供標準術語記錄知識的來源：

```turtle
trip:checkin prov:wasDerivedFrom trip:trainA ;
    prov:wasGeneratedBy trip:delayAnalysis .
```

---

## 4. 完整算例：兩跳影響查詢

### 4.1 情境

雙人歐洲自由行場景：
- `trainA`：薩爾斯堡 ICE 班次，延誤 35 分鐘
- `checkin`：Hotel Amadeus 入住，截止 21:00
- `roomChange`：雙人房升等申請，需先完成入住

**問題：** 若 `trainA` 的時刻表異動，哪些後續事件會受影響？

### 4.2 建圖

依照上方 Turtle，圖的結構為：

```
trainA ──(dep1.from)──► dep1 ──(dep1.to)──► checkin
                                              │
                                          (dep2.from)
                                              │
                                              ▼
                                            dep2 ──(dep2.to)──► roomChange
```

### 4.3 一跳查詢

```sparql
PREFIX trip: <http://example.org/trip#>

SELECT ?directlyAffected
WHERE {
    trip:trainA ^trip:from ?dep .
    ?dep trip:to ?directlyAffected .
}
```

結果：`?directlyAffected = trip:checkin`

### 4.4 兩跳查詢（property path）

```sparql
PREFIX trip: <http://example.org/trip#>

SELECT DISTINCT ?affected
WHERE {
    trip:trainA (^trip:from / trip:to)+ ?affected .
}
```

`(^trip:from / trip:to)+` 表示「沿著 dep 節點，從 from 逆向再往 to 走，重複一次或多次」。

結果：`?affected = {trip:checkin, trip:roomChange}`

### 4.5 附帶依賴原因的查詢

```sparql
PREFIX trip: <http://example.org/trip#>

SELECT ?affected ?reason
WHERE {
    trip:trainA ^trip:from ?dep .
    ?dep trip:to ?affected .
    ?dep trip:reason ?reason .
}
```

結果：

| ?affected | ?reason |
|-----------|---------|
| trip:checkin | "train delay may push arrival past 21:00" |

---

## 5. 反例：只存實體節點，沒存 dependsOn 邊

**錯誤做法：** 把依賴關係直接存成節點屬性：

```turtle
# 錯誤：把依賴關係存成字串屬性，而不是圖邊
trip:checkin trip:dependsOnId "trainA" .
```

**問題：** SPARQL property path 無法遍歷字串屬性，查詢結果為空集合。

```sparql
# 這個查詢找不到任何結果
SELECT ?affected
WHERE {
    trip:trainA (^trip:from / trip:to)+ ?affected .
    # 因為 trip:from / trip:to 是圖邊，
    # 而 dependsOnId 只是字串屬性，不是圖結構
}
```

**正確做法：** 依賴關係必須用圖邊（或具名節點）表示，才能被圖查詢遍歷。這是知識圖譜和一般文件資料庫的核心差異。

---

## 6. Property Graph vs RDF

以同一個旅程依賴查詢，比較兩種圖模型。

### 6.1 Neo4j Cypher（Property Graph）

```cypher
// 建圖
CREATE (a:Segment {name: 'trainA', delayMin: 35})
CREATE (b:Event   {name: 'checkin', deadline: '21:00'})
CREATE (c:Event   {name: 'roomChange'})
CREATE (a)-[:DEPENDS_ON {reason: 'delay may exceed deadline'}]->(b)
CREATE (b)-[:DEPENDS_ON {reason: 'upgrade requires checkin'}]->(c)

// 查詢：trainA 的所有間接影響（任意深度）
MATCH (start {name: 'trainA'})-[:DEPENDS_ON*1..]->(affected)
RETURN affected.name
```

**Property Graph 的邊可以直接附加屬性**（`reason`），不需要具名節點。

### 6.2 SPARQL（RDF）

如上方算例，需要透過具名 `dep1`、`dep2` 節點存放屬性。語法稍複雜，但換來：
- 標準化 URI，可跨資料集合（linked data）
- OWL 推論（ontology reasoning）
- 與 W3C 標準工具鏈整合

### 6.3 選型比較

| 面向 | Property Graph（Neo4j） | RDF（SPARQL） |
|------|------------------------|---------------|
| 邊屬性 | 原生支援 | 需 reification 或 named graph |
| 查詢語言 | Cypher（較直覺） | SPARQL（較標準） |
| 推論能力 | 有限 | OWL 完整推論 |
| 跨資料整合 | 需自行設計 | Linked Data 標準 |
| 生態工具 | Neo4j、Amazon Neptune | RDFLib、Fuseki、Stardog |
| 適合場景 | 應用程式內部圖查詢 | 知識庫、語意網整合 |

**選型原則：**
- 只需應用程式內部的圖遍歷，且邊屬性豐富 → Property Graph（Neo4j）
- 需要與外部本體（ontology）整合、或資料語意要跨組織共享 → RDF + SPARQL

---

## 7. 工具

### RDFLib（Python）

```python
# pip install rdflib
from rdflib import Graph, URIRef, Namespace, Literal
from rdflib.namespace import RDF, XSD

TRIP = Namespace("http://example.org/trip#")

g = Graph()
g.parse("trip.ttl", format="turtle")

# 執行 SPARQL 查詢
qres = g.query("""
    PREFIX trip: <http://example.org/trip#>
    SELECT DISTINCT ?affected
    WHERE {
        trip:trainA (^trip:from / trip:to)+ ?affected .
    }
""")

for row in qres:
    print(row.affected)
```

### pySHACL（驗證）

```python
# pip install pyshacl
from pyshacl import validate

data_graph  = Graph().parse("trip.ttl",   format="turtle")
shape_graph = Graph().parse("shapes.ttl", format="turtle")

conforms, results_graph, results_text = validate(
    data_graph,
    shacl_graph=shape_graph,
    inference='rdfs'
)
print("驗證通過：", conforms)
if not conforms:
    print(results_text)
```

---

## 8. 習題

**題 1（機制）：** SPARQL 中 `^trip:from / trip:to` 和 `trip:from / trip:to` 有什麼不同？為什麼本節的 reified triple 設計需要用 `^` 逆向？

<details><summary>解答</summary>

- `trip:from / trip:to`：從節點出發，先沿 `trip:from` 走，再沿 `trip:to` 走。
- `^trip:from / trip:to`：從節點出發，先沿 `trip:from` **逆向**走（即找「誰的 from 指向我」），再沿 `trip:to` 走。

本節設計中，`dep1` 是一個中間節點：
```
trainA ←──(trip:from)── dep1 ──(trip:to)──► checkin
```

從 `trainA` 出發要找 `checkin`，必須：
1. 逆向找「誰的 `trip:from` 指向 trainA」→ 找到 `dep1`
2. 再從 `dep1` 往 `trip:to` 走 → 找到 `checkin`

所以要用 `^trip:from / trip:to`。如果用 `trip:from / trip:to`，是「從 trainA 沿 from 走再沿 to 走」，但 trainA 沒有任何 `trip:from` 出去的邊，結果為空。

</details>

---

**題 2（手算）：** 假設新增了第三條依賴：`roomChange` 依賴 `payment`（付款確認）。請寫出新增的 Turtle 三元組，並說明在兩跳 SPARQL 查詢下，`trainA` 的查詢結果集合會如何變化。

<details><summary>解答</summary>

新增 Turtle：
```turtle
trip:payment a trip:PaymentConfirmation .

trip:dep3 a trip:Dependency ;
    trip:from   trip:roomChange ;
    trip:to     trip:payment ;
    trip:reason "room upgrade requires payment confirmation" ;
    prov:wasAttributedTo trip:agentAssistant .
```

查詢變化：
- 原本兩跳查詢結果：`{checkin, roomChange}`
- 新增 dep3 後，`payment` 是 `roomChange` 的一跳影響，也是 `trainA` 的三跳影響。
- 原本的兩跳固定查詢（`(^trip:from / trip:to){2}`）**不會**找到 `payment`。
- 若改用 `(^trip:from / trip:to)+`（一跳或多跳），結果會變成 `{checkin, roomChange, payment}`。

這個例子說明：當依賴鏈可能增長時，property path 的 `+`（一次以上）比固定跳數更有彈性。

</details>

---

**題 3（選型）：** 旅行社想建立一套系統，整合自家訂位資料庫、外部航班本體（IATA 標準）以及旅遊局的景點分類。應選 Property Graph 還是 RDF？說明三個選型理由。

<details><summary>解答</summary>

**建議選 RDF。**

三個理由：
1. **跨資料集整合：** IATA 標準和旅遊局景點分類很可能已發布為 Linked Data（以 URI 標識概念）。RDF 可以直接 `owl:sameAs` 對齊外部 URI，不需要自行設計對應層。
2. **語意推論：** 若 IATA 本體定義「直飛航班是航班的子類」，OWL/RDFS 推論引擎可自動推導查詢結果包含直飛，無需手寫額外查詢邏輯。
3. **標準互操作：** 未來若要把資料開放給第三方（例如旅遊 API 聚合商），RDF + SPARQL endpoint 有標準規範可遵循；Property Graph 格式目前沒有等效的跨廠商標準。

注意：如果整合需求較低且查詢複雜度高，Property Graph 的 Cypher 查詢語法仍然較直覺，可考慮混合架構（Property Graph 做應用層，RDF 做語意層）。

</details>

---

[章節導覽](intro.md) · [上一節](01-decision-tables.md) · [下一節](03-bitemporal-modeling.md)
