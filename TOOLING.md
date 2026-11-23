# 工具與實務案例

正課學方法，這份指南學怎麼把方法跑起來。表格中的 API 是查文件的入口。現有 Lab 的標準函式庫基線仍可離線重跑。先挑一個工具替換一層，沿用同一批輸入與驗收，才看得出差異。

| 章 | 先熟悉的工具與 API | 真正在做的事 |
|---|---|---|
| 1 文件、音訊、操作 | [Docling](https://docling-project.github.io/docling/) 的 `DocumentConverter.convert`、[PM4Py](https://processintelligence.solutions/pm4py/) 的 `discover_process_tree_inductive`、[rrweb](https://github.com/rrweb-io/rrweb) 的 `record`、[WhisperX](https://github.com/m-bain/whisperX) | 匯入 PDF、從事件找流程、重播網頁狀態、對齊逐字稿與音訊時間。保留頁碼、事件 ID 和時間戳。 |
| 2 萃取與校對 | [Pydantic](https://docs.pydantic.dev/) 的 `BaseModel.model_validate`、[Snorkel](https://snorkel.readthedocs.io/) 的 `PandasLFApplier` 和 `LabelModel`、[Label Studio](https://labelstudio.io/guide/) 的 predictions 匯入 | 驗證抽取欄位、合併弱標籤、讓人看到預標結果直接校對。驗證過的 JSON 仍要對照原文。 |
| 3 表示與版本 | [SQLite](https://sqlite.org/lang_with.html) 的 recursive CTE、[RDFLib](https://rdflib.readthedocs.io/) 的 `Graph.query`、[pySHACL](https://github.com/RDFLib/pySHACL) 的 `validate`、[Camunda DMN](https://docs.camunda.io/docs/components/modeler/dmn/) | 查改班影響、執行 SPARQL、驗證關係和必填欄位、執行決策表。 |
| 4 檢索 | [Pyserini](https://github.com/castorini/pyserini) 的 `LuceneSearcher`、[Sentence Transformers](https://sbert.net/) 的 `SentenceTransformer.encode` 和 `CrossEncoder.predict`、[Qdrant](https://qdrant.tech/documentation/) 的 `query_points` | 跑 BM25、產生向量、重排候選、加 metadata filter 與融合。小語料可先把向量留在記憶體。 |
| 5 評估與追蹤 | [ir-measures](https://ir-measur.es/) 的 `calc_aggregate`、[scikit-learn](https://scikit-learn.org/stable/modules/calibration.html) 的 `calibration_curve`、[Langfuse](https://langfuse.com/docs) 的 tracing 與 datasets | 從 qrels 和排名算檢索指標、看信心校準、追查一筆回覆使用的證據和工具。完整證據集合仍由課程的案例標註驗收。 |
| 6 更新與執行 | [pytest](https://docs.pytest.org/) 的 `parametrize`、[PEFT](https://huggingface.co/docs/peft/) 的 `LoraConfig`、[OPA](https://www.openpolicyagent.org/docs/) 的 `opa test` | 把人工改判變成回歸案例、配置 LoRA、測工具政策。先用模擬訂位執行層驗證。 |

想認識整合框架，可以讀 [Haystack pipelines](https://docs.haystack.deepset.ai/docs/pipelines) 或 [LlamaIndex](https://docs.llamaindex.ai/)，試著把文件載入、檢索和重排串成一條流程。保留每一層的輸入、輸出與指標，換框架時就能比較。

## 三個可以拆來讀的實務案例

- **GitHub Copilot Chat 的程式碼上下文。** GitHub 說明如何以程式碼索引與檢索提供回答所需上下文。讀完畫出索引、查詢、候選與回答的關係，再把同樣思路套到旅行資料。比較只讀群聊、加上訂位信後，哪些問題開始有足夠證據。 [GitHub Engineering](https://github.blog/engineering/architecture-optimization/how-github-copilot-chat-helps-you-understand-your-codebase/)
- **Microsoft GraphRAG 的局部問題與整體問題。** 對照 Local Search 和 Global Search。拿「B 的門票是否受影響」與「這趟旅程有哪些可能來不及的安排」做兩組問題。逐題記錄圖譜是否有正確關係、引用是否足夠，以及索引成本。 [Microsoft GraphRAG](https://microsoft.github.io/graphrag/)
- **Langfuse 的 trace 到 dataset。** 從一筆真實執行軌跡切出輸入、證據、輸出與人工改判，變成下次可重跑的案例。用「舊取消政策排在第一」重現錯案，更新過濾後重跑整組。 [Langfuse 評估文件](https://langfuse.com/docs/evaluation/overview)

## 每次模型換代，做一張實務案例卡

先從 [Hugging Face 論壇](https://discuss.huggingface.co/)、[Hacker News](https://news.ycombinator.com/) 或開源工具的 GitHub Discussions 找一篇有實際輸入、結果或踩坑紀錄的貼文。論壇當作待驗證的線索，去官方文件或原始程式確認版本及功能。

記錄原帖日期、模型與 SDK 版本、作者的任務、輸入和評估法、改善、退步、延遲與成本。若作者同時改了模型、提示詞與索引，先註明歸因不清。課堂上固定旅行案例與 qrels，每回只替換一層。例子是同一份訂位信與聊天紀錄分別用舊、新模型抽欄位，量完整欄位正確率、每案耗時及人工修正率，再挑一筆新模型反而做錯的例子。
