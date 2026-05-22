# 打字练习选词算法

`GET /api/words` 不再只用 `ORDER BY RANDOM()` 随机取词。当前实现使用“分桶 + 加权随机”的方式，从 Anki 已学习单词中挑选更适合本次练习的词。

## 目标

- 提高薄弱词和近期错词出现概率。
- 保留一部分随机词，避免每次只练错题。
- 让已经掌握但很久没练的词重新进入复习。
- 保持接口不变，前端仍然调用：

```text
GET /api/words?limit=20&category=all
```

## 数据来源

候选词来自 Anki `collection.anki2`：

- 只读取指定牌组中已学习的卡片。
- 支持 `category` 分类筛选。

选词权重来自统计库 `stats.db`：

- `word_mastery`：总次数、正确次数、错误次数、掌握等级、平均耗时、最近练习时间。
- `word_attempts`：最近一次练习是否正确。

如果统计库读取失败，后端会回退到原来的随机选词，避免练习页面不可用。

## 分桶比例

默认按 `limit` 分配：

```text
40% 薄弱词：weak、最近一次错误、错误次数多于正确次数
25% 学习中：learning、familiar 且还没进入复习周期
20% 到期复习：mastered/familiar 且 7 天以上没练
15% 随机词：未练过或其他候选词
```

以 `limit=20` 为例：

```text
8 个薄弱词
5 个学习中
4 个到期复习
3 个随机词
```

如果某个桶数量不足，会从剩余候选词中继续按权重补满。

## 权重规则

每个词会计算一个分数，分数越高，越容易被抽中。

基础分：

```text
weak:      80
learning:  45
new:       30
familiar:  20
mastered:   5
```

附加分：

```text
每次错误: +8
每次正确: -2
最近一次错误: +25
3 天以上没练: +10
7 天以上没练: +25
14 天以上没练: +35
平均耗时 > 3 秒: +5
平均耗时 > 5 秒: +10
平均耗时 > 8 秒: +15
```

最低分为 `1`，保证任何词都有机会出现。

## 行为特点

- 不是固定取最高分，而是加权随机抽样。
- 同一次返回结果不会重复同一个 Anki note。
- 已掌握词不会消失，只是出现概率降低。
- 久未练习的熟词会进入复习桶。

## 关键代码

- `typing-practice/backend/handlers/api.go`：`/api/words` 调用智能选词。
- `typing-practice/backend/anki/reader.go`：读取 Anki 已学习候选池。
- `typing-practice/backend/stats/queries.go`：读取选词所需统计数据。
- `typing-practice/backend/practice/selector.go`：分桶、打分和加权随机抽样。
