# 驗收

基線晚餐需重查人數、住宿保留、旅客 C 趕不上票券。模擬執行先要求核准，再執行一次，同參數重送回報已處理。使用相同 key 但不同人數回報衝突。

```bash
python3 course.py 06
python3 -m unittest discover -s tests -v
```
