# 1.3 從軌跡到流程樹

Directly-follows graph 統計相鄰活動。Alpha Miner 用先後關係推因果與並行，對短迴圈和未觀察到的路徑敏感。Heuristics Miner 用相依度與頻數抗噪音，過高門檻會捨棄罕見取消流程。Inductive Miner 找循序、互斥、並行或迴圈切分，再對各子日誌遞迴，直到單一活動等基底。流程樹可轉 Petri net 做一致性檢查。

**走一遍切分。** 軌跡 ABC、ADC 先切 A、{B,D}、C，再把中間切成互斥選擇。加入 ABDC 後，B 與 D 能同時出現，互斥假設要重查。若模型預期 A→B→C、實際 A→C，alignment 會對齊 A 和 C，中間以一個 model move 表示缺 B。那一步可能真的跳過，也可能是事件漏記。

**實驗。** Lab 01 刪掉取消事件，寫出兩條變動的相鄰邊。再比較 DFG 與 PM4Py 流程樹能表達的資訊。保留罕見取消路徑加入驗證集，觀察 fitness 和 precision 的取捨。

[章節導覽](intro.md) · [上一節](02-audio-and-ui.md)
