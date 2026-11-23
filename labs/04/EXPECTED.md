# 驗收

Q1 在 k=2 漏 D1，k=3 補回。Q2 未過濾時 D4 排第一，過濾後 D4 不出現且 D5、D6 俱全。Q3 在 k=2 的 nDCG 為 1，但證據仍少一條。

```bash
python3 course.py 04
python3 -m unittest discover -s tests -v
```
