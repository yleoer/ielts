# 选词策略

`/api/words` 使用的是带统计信号的加权选词，而不是纯随机抽取。

## 目标

- 让薄弱词和最近错词更常出现。
- 保留一部分随机覆盖，避免练习过于单一。
- 让较久没练的熟词重新进入复习。
- 保持前端调用方式不变。

## 数据来源

- Anki 已学习词池
- SQLite 里的练习历史
- 单词级掌握状态

## 选词分组

候选词会按大类分组：

- 薄弱词
- 学习中词
- 到期复习词
- 随机词或新词

如果某一组不够，后端会从剩余候选词中补齐。

## 权重信号

这些信号会提高词条被选中的概率：

- 最近出错
- 错误次数多于正确次数
- 平均耗时较长
- 距离上次练习时间较久

重复答对后，权重会下降，但词条不会被永久移除。

## 相关文件

- `typing-practice/backend/handlers/api.go`
- `typing-practice/backend/anki/reader.go`
- `typing-practice/backend/practice/selector.go`
- `typing-practice/backend/stats/queries.go`

## 回退行为

如果统计库无法提供选词信号，后端会退回到只依赖 Anki 的练习词池，以保证页面可用。
