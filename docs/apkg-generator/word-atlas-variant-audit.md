# Word Atlas 英美与拼写变体核对清单

核对日期：2026-11-06。按“整词等价过滤、单侧变体优先常用写法”核对；31 条过滤和 48 条改写已接入生成流程，并实际应用到本机 Anki。服务器过滤代码已通过测试与 typetest 镜像检查，尚未部署；新版桌面资源包已生成，需在设置中重新导入。

## 结果

- 原始词库 **7,298** 条；唯一 SourceId 和唯一词头均为 7,298。
- 合并两类后共 **79 条建议处理**：**31 条过滤重复词条**（27 条英美变体、4 条其他拼写），以及 **48 条改写词头**。
- 本次补查 **133 组**另一形式不在库内的候选；其中 48 组建议改写，其余给出保留或待定理由。
- 改写词头保留原 SourceId，不新增笔记、不减少数量；连同 31 条过滤建议应用后，预计 **7,267** 条。
- 仍有 5 组库内变体源义项未对齐、7 组库内变体常用形式未定，暂不纳入处理。
- 上游源文件仍为 7,298 条且未修改。本机 Anki 保留 7,298 条笔记，其中 31 张重复卡已暂停；按新版服务器规则读取为 7,267 条有效词条。

## 数据与口径

- 源文件：`D:/me/word-atlas-main/data/word-atlas.json`。
- SHA-256：`e4e3410809047711cd2a25fccafcebb46124ce1eeb98829dc12de0335de71234`。
- 全量扫描 7,298 条的词头、词性、义项及用法提示；全字段地域/拼写关键词命中 **550** 条，全义项中文归一化得到 **48** 组重复，拼写归一化得到 **32** 组候选。上述集合有重叠，且包含普通近义词、假匹配，不能把命中数当作可过滤数。
- 同义判断比较全部已收录词性和中英文义项，不要求中文逐字相同；词义顺序和解释详略不单独视为新义项。仅主释义相同、另一条有额外独立词性或义项时保留两条；真正拼写变体但当前源义项未对齐的另列待处理。
- 频率参考固定版本 [wordfreq 3.1.1](https://pypi.org/project/wordfreq/3.1.1/)，以 `zipf_frequency(word, "en", wordlist="large")` 读取综合英语词频；数值越大越常见，差 1 约代表十倍频率。它是混合地区、文体的历史语料参考，不是实时词频，也不表示每个地区均偏好保留项。
- 不按所有词汇一律选择美式：例如本清单保留英式更常用的 `towards` 和 `afterwards`。频率很接近的 `gray/grey`、`kilometer/kilometre`、`liter/litre` 和同分的 `catalog/catalogue` 不强行选边。
- `wordfreq` 会把连字符词拆开估算，不能拿 `make-up` 的估计值证明它比 `makeup` 常见。连字符组只有源提示明确现代通常写法时才列入直接建议。另尝试 Google Books Ngram 原文拼写比较，HTTPS 连接超时，未取得数据，因此相关未定组不采用该来源。
- 原词库中不存在的另一形式现在进入“改写词头”核对：有效变体、对应义项成立且更常用时建议改写；它不作为删除唯一词条的过滤项。普通近义词、屈折形式以及会丢失原义项的简称替换仍不直接处理。
- 单侧变体的可直接比较词头以 Zipf 差至少 0.10 作为本轮统一选择口径；接近时保留，含空格或连字符时不比较拆词估计。源提示明确现代常用形式的可以据此整理。总词频明显混入其他含义、词性或专名时不单凭高分替换。

## 所有建议处理的词条

本表是已批准的 79 条处理名单。过滤行的目标词在原库内；改写行的目标词不在原库内。生成器与本机 Anki 已应用；服务器运行实例待部署，本地媒体需重新导入。

| 当前词条 | 保留／改为 | 处理方式 | 中文义项 |
| --- | --- | --- | --- |
| acknowledgment | acknowledgement | 改写词头 | 承认；认可；致谢；鸣谢；收悉通知；回执 |
| aeroplane | airplane | 过滤重复词条 | 飞机 |
| afterward | afterwards | 过滤重复词条 | 之后；后来 |
| aluminium | aluminum | 过滤重复词条 | 铝 |
| analogue | analog | 改写词头 | 类似物；对应物；模拟式的；非数字的 |
| analyse | analyze | 过滤重复词条 | 分析 |
| anticlockwise | counterclockwise | 改写词头 | 逆时针地；逆时针方向的 |
| apologise | apologize | 过滤重复词条 | 道歉 |
| armour | armor | 改写词头 | 盔甲；装甲；装甲车辆；装甲部队 |
| baby-sit | babysit | 改写词头 | 临时照看小孩 |
| baby-sitter | babysitter | 过滤重复词条 | 临时保姆 |
| behaviour | behavior | 过滤重复词条 | 行为；运行特性 |
| bookshop | bookstore | 过滤重复词条 | 书店 |
| calory | calorie | 过滤重复词条 | 卡路里 |
| centimetre | centimeter | 改写词头 | 厘米；公分 |
| centre | center | 改写词头 | 中心；中央；活动中心；服务机构；以…为中心；集中于 |
| chilli | chili | 改写词头 | 辣椒；辣味肉末豆子炖菜 |
| colour | color | 改写词头 | 颜色；色彩；给……涂色；染色 |
| coloured | colored | 改写词头 | 有颜色的；着色的 |
| colourful | colorful | 改写词头 | 色彩鲜艳的；五彩缤纷的；生动有趣的；丰富多彩的 |
| cosy | cozy | 改写词头 | 温暖舒适的；亲密愉快的 |
| defence | defense | 改写词头 | 防御；保护；辩护；答辩；防守；防守队员 |
| despatch | dispatch | 过滤重复词条 | 派遣；发送；报道 |
| dining-room | dining room | 改写词头 | 餐厅；饭厅 |
| dishonour | dishonor | 改写词头 | 耻辱；名誉受损；使蒙羞；使丢脸；违背；不履行 |
| distil | distill | 改写词头 | 蒸馏；用蒸馏法提取；提炼；概括精华 |
| encyclopaedia | encyclopedia | 过滤重复词条 | 百科全书 |
| endeavour | endeavor | 过滤重复词条 | 努力；尝试 |
| enquire | inquire | 改写词头 | 询问；打听 |
| enquiry | inquiry | 过滤重复词条 | 询问；调查 |
| enrol | enroll | 改写词头 | 注册；报名；招收 |
| favour | favor | 过滤重复词条 | 帮忙；支持；偏爱 |
| favourite | favorite | 过滤重复词条 | 最喜欢的；热门人选 |
| fibre | fiber | 改写词头 | 纤维；膳食纤维 |
| fibreglass | fiberglass | 改写词头 | 玻璃纤维；玻璃钢 |
| flavour | flavor | 改写词头 | 风味；味道；给……调味；特色；风格 |
| fulfil | fulfill | 改写词头 | 履行；完成；满足；符合；实现 |
| gaol | jail | 过滤重复词条 | 监狱；监禁 |
| gramme | gram | 过滤重复词条 | 克 |
| harbour | harbor | 改写词头 | 海港；港湾；心怀；藏有；藏匿；庇护 |
| humour | humor | 改写词头 | 幽默；幽默感；心情；情绪；迁就；顺着 |
| jeopardise | jeopardize | 过滤重复词条 | 危及 |
| jewellery | jewelry | 过滤重复词条 | 珠宝；首饰 |
| judgement | judgment | 改写词头 | 判断力；看法；评价；判决；裁决 |
| kilogramme | kilogram | 改写词头 | 千克；公斤 |
| ladybird | ladybug | 改写词头 | 瓢虫 |
| loth | loath | 过滤重复词条 | 不情愿的 |
| marvellous | marvelous | 过滤重复词条 | 极好的；令人惊叹的 |
| maths | math | 改写词头 | 数学 |
| mid-day | midday | 过滤重复词条 | 中午；正午 |
| millimetre | millimeter | 改写词头 | 毫米 |
| moustache | mustache | 改写词头 | 上唇胡须；小胡子 |
| neighbour | neighbor | 改写词头 | 邻居；邻近的人或事物 |
| neighbourhood | neighborhood | 改写词头 | 街区；附近地区；街坊邻里 |
| odour | odor | 改写词头 | 气味；异味 |
| offence | offense | 改写词头 | 违法行为；犯规；冒犯；被冒犯的感受 |
| organisation | organization | 过滤重复词条 | 组织机构；组织安排 |
| organise | organize | 过滤重复词条 | 组织；整理 |
| paralyse | paralyze | 过滤重复词条 | 使瘫痪；使停摆 |
| petrol | gasoline | 过滤重复词条 | 汽油 |
| plough | plow | 改写词头 | 犁；犁地；耕地 |
| propellent | propellant | 改写词头 | 推进剂；喷射剂；起推进作用的 |
| pyjamas | pajamas | 改写词头 | 睡衣裤 |
| realise | realize | 过滤重复词条 | 意识到；实现 |
| recognise | recognize | 过滤重复词条 | 认出；承认；认可 |
| rubbish | garbage | 过滤重复词条 | 垃圾；废话 |
| salability | saleability | 改写词头 | 适销性；可销售性 |
| sceptical | skeptical | 改写词头 | 怀疑的；不轻信的 |
| specialised | specialized | 改写词头 | 专业的；专用的 |
| sulphide | sulfide | 改写词头 | 硫化物 |
| sulphur | sulfur | 改写词头 | 硫；硫磺 |
| tape-recorder | tape recorder | 改写词头 | 磁带录音机 |
| toward | towards | 过滤重复词条 | 朝向；对于；用于 |
| travelling | traveling | 改写词头 | 旅行；出行；巡回的；四处流动的；旅行；行进 |
| tumour | tumor | 改写词头 | 肿瘤 |
| utilise | utilize | 过滤重复词条 | 利用；使用 |
| vapour | vapor | 改写词头 | 蒸气；汽 |
| whisky | whiskey | 改写词头 | 威士忌酒 |
| windscreen | windshield | 改写词头 | 汽车挡风玻璃 |

过滤指从未来练习词池排除重复项，清单不授权删除历史。改写指保留原稳定 ID 的词头调整；真正应用时，词性、全部义项以及音标、用法提示、例句、搭配和音频须核对到相应形式，不能机械全文替换或把媒体文件改名冒充新读音。

## 新增：另一形式不在库内的改写建议

共 48 条。普通单词给出两种词频；复合词只有源提示明确现代写法时才直接列入。

| 原词头 | 建议词头 | 原 Zipf | 目标 Zipf | 补充说明 |
| --- | --- | --- | --- | --- |
| acknowledgment | acknowledgement | 3.11 | 3.32 | 保留原词性和全部义项。 |
| analogue | analog | 3.28 | 3.73 | 名词类似物和形容词模拟式均保留，仅采用另一拼写。 |
| anticlockwise | counterclockwise | 1.95 | 2.62 | 保留原词性和全部义项。 |
| armour | armor | 3.75 | 3.97 | 保留原词性和全部义项。 |
| baby-sit | babysit | 不作拆词比较 | 不作拆词比较 | 源提示明确“更常写作 babysit”；过去式等配套说明需一起整理。 |
| centimetre | centimeter | 2.55 | 2.89 | 保留原词性和全部义项。 |
| centre | center | 4.95 | 5.19 | 保留原词性和全部义项。 |
| chilli | chili | 3.29 | 3.73 | 保留原词性和全部义项。 |
| colour | color | 4.49 | 4.91 | 保留原词性和全部义项。 |
| coloured | colored | 3.92 | 4.19 | 保留原词性和全部义项。 |
| colourful | colorful | 3.55 | 3.80 | 保留原词性和全部义项。 |
| cosy | cozy | 3.31 | 3.64 | 保留原词性和全部义项。 |
| defence | defense | 4.51 | 4.93 | 保留原词性和全部义项。 |
| dining-room | dining room | 不作拆词比较 | 不作拆词比较 | 源提示明确“现代通常写作 dining room”；保留名词词性。 |
| dishonour | dishonor | 2.71 | 2.88 | 保留原词性和全部义项。 |
| distil | distill | 2.04 | 2.47 | 保留原词性和全部义项。 |
| enquire | inquire | 2.91 | 3.38 | 保留原词性和全部义项。 |
| enrol | enroll | 2.67 | 3.45 | 保留原词性和全部义项。 |
| fibre | fiber | 3.67 | 4.06 | 保留原词性和全部义项。 |
| fibreglass | fiberglass | 2.53 | 3.04 | 保留原词性和全部义项。 |
| flavour | flavor | 3.73 | 4.04 | 保留原词性和全部义项。 |
| fulfil | fulfill | 3.55 | 3.86 | 保留原词性和全部义项。 |
| harbour | harbor | 3.98 | 4.15 | 保留原词性和全部义项。 |
| humour | humor | 3.83 | 4.19 | 保留原词性和全部义项。 |
| judgement | judgment | 3.86 | 4.28 | 保留原词性和全部义项。 |
| kilogramme | kilogram | 1.66 | 3.01 | 源提示也明确 kilogram 更常用；与简称 kilo 分开。 |
| ladybird | ladybug | 2.54 | 2.67 | 保留原词性和全部义项。 |
| maths | math | 3.75 | 4.45 | 保留原词性和全部义项。 |
| millimetre | millimeter | 2.60 | 3.13 | 保留原词性和全部义项。 |
| moustache | mustache | 3.24 | 3.41 | 保留原词性和全部义项。 |
| neighbour | neighbor | 3.69 | 4.11 | 保留原词性和全部义项。 |
| neighbourhood | neighborhood | 3.94 | 4.50 | 保留原词性和全部义项。 |
| odour | odor | 2.96 | 3.49 | 保留原词性和全部义项。 |
| offence | offense | 3.96 | 4.26 | 保留原词性和全部义项。 |
| plough | plow | 3.09 | 3.21 | 保留原词性和全部义项。 |
| propellent | propellant | 1.30 | 2.92 | 源提示也明确优先用 propellant。 |
| pyjamas | pajamas | 2.96 | 3.31 | 保留原词性和全部义项。 |
| salability | saleability | 1.04 | 1.34 | 两种均为低频词；当前混合语料偏向 saleability。 |
| sceptical | skeptical | 3.09 | 3.68 | 保留原词性和全部义项。 |
| specialised | specialized | 3.45 | 4.07 | 保留原词性和全部义项。 |
| sulphide | sulfide | 2.37 | 2.92 | 同时符合现代国际化学命名的 sulfide 写法。 |
| sulphur | sulfur | 3.18 | 3.43 | 同时符合现代国际化学命名的 sulfur 写法。 |
| tape-recorder | tape recorder | 不作拆词比较 | 不作拆词比较 | 源提示明确“现代通常写作 tape recorder，不加连字符”。 |
| travelling | traveling | 4.16 | 4.27 | 保留原词性和全部义项。 |
| tumour | tumor | 3.39 | 3.97 | 保留原词性和全部义项。 |
| vapour | vapor | 3.02 | 3.56 | 保留原词性和全部义项。 |
| whisky | whiskey | 3.63 | 3.78 | 泛称选 whiskey；Scotch whisky 等地区、酒种及专名写法仍须保留，不能全文机械替换。 |
| windscreen | windshield | 2.91 | 3.41 | 保留原词性和全部义项。 |

这里包含 `maths → math` 这种成对的英美学科简称；并不将数学的完整词 `mathematics` 过滤或改成简称。`whisky → whiskey` 仅统一泛称词头，地区、酒种及专名中的 whisky 拼写仍按原用法保留。

## 单侧变体暂不改写的完整名单

“现有词头更常见”和“证据不足”均保留原词头；这些不是遗漏项。

| 现有词头 | 另一形式 | 结论 | 原因 |
| --- | --- | --- | --- |
| metre | meter | 词频混义 | meter 可作米、格律的美式拼写，但总词频还包含仪表及计量用法，不能据此确认当前两个义项的写法更常用；暂不改写。 |
| traveler | traveller | 频率接近 | 两种写法的 Zipf 差小于 0.10，当前证据不足以称另一写法明显更常见。 |
| yogurt | yoghurt | 现有写法更常见 | 现有词头的综合英语词频更高，不改为更低频写法。 |
| railway | railroad | 现有写法更常见 | 现有词头的综合英语词频更高，不改为更低频写法。 |
| theatre | theater | 现有写法更常见 | 现有词头的综合英语词频更高，不改为更低频写法。 |
| woollen | woolen | 频率接近 | 两种写法的 Zipf 差小于 0.10，当前证据不足以称另一写法明显更常见。 |
| zipper | zip | 不直接互换或词频混义 | zip 另有动词及其他名词义，总词频不能证明拉链义更常用；严格整词等价口径不替换。 |
| neighboring | neighbouring | 现有写法更常见 | 现有词头的综合英语词频更高，不改为更低频写法。 |
| labor | labour | 频率接近 | 两种写法的 Zipf 差小于 0.10，当前证据不足以称另一写法明显更常见。 |
| mold | mould | 现有写法更常见 | 现有词头的综合英语词频更高，不改为更低频写法。 |
| sympathize | sympathise | 现有写法更常见 | 现有词头的综合英语词频更高，不改为更低频写法。 |
| fertilizer | fertiliser | 现有写法更常见 | 现有词头的综合英语词频更高，不改为更低频写法。 |
| color-blind | colour-blind | 缺少原文拼写频率 | 两种形式有效，但不使用连字符/分词估计值强选；源提示未明确其中一种更常用。 |
| civilization | civilisation | 现有写法更常见 | 现有词头的综合英语词频更高，不改为更低频写法。 |
| colorless | colourless | 现有写法更常见 | 现有词头的综合英语词频更高，不改为更低频写法。 |
| advisor | adviser | 频率接近 | 两种写法的 Zipf 差小于 0.10，当前证据不足以称另一写法明显更常见。 |
| specialty | speciality | 现有写法更常见 | 现有词头的综合英语词频更高，不改为更低频写法。 |
| organizational | organisational | 现有写法更常见 | 现有词头的综合英语词频更高，不改为更低频写法。 |
| computerize | computerise | 现有写法更常见 | 现有词头的综合英语词频更高，不改为更低频写法。 |
| wagon | waggon | 现有写法更常见 | 现有词头的综合英语词频更高，不改为更低频写法。 |
| modernize | modernise | 现有写法更常见 | 现有词头的综合英语词频更高，不改为更低频写法。 |
| specialize | specialise | 现有写法更常见 | 现有词头的综合英语词频更高，不改为更低频写法。 |
| self-defence | self-defense | 缺少原文拼写频率 | 两种形式有效，但不使用连字符/分词估计值强选；源提示未明确其中一种更常用。 |
| criticize | criticise | 现有写法更常见 | 现有词头的综合英语词频更高，不改为更低频写法。 |
| stabilize | stabilise | 现有写法更常见 | 现有词头的综合英语词频更高，不改为更低频写法。 |
| installment | instalment | 现有写法更常见 | 现有词头的综合英语词频更高，不改为更低频写法。 |
| summarize | summarise | 现有写法更常见 | 现有词头的综合英语词频更高，不改为更低频写法。 |
| laborer | labourer | 频率接近 | 两种写法的 Zipf 差小于 0.10，当前证据不足以称另一写法明显更常见。 |
| maximize | maximise | 现有写法更常见 | 现有词头的综合英语词频更高，不改为更低频写法。 |
| phony | phoney | 现有写法更常见 | 现有词头的综合英语词频更高，不改为更低频写法。 |
| tranquilizer | tranquilliser | 现有写法更常见 | 现有词头的综合英语词频更高，不改为更低频写法。 |
| authorize | authorise | 现有写法更常见 | 现有词头的综合英语词频更高，不改为更低频写法。 |
| oxidize | oxidise | 现有写法更常见 | 现有词头的综合英语词频更高，不改为更低频写法。 |
| subsidize | subsidise | 现有写法更常见 | 现有词头的综合英语词频更高，不改为更低频写法。 |
| mobilize | mobilise | 现有写法更常见 | 现有词头的综合英语词频更高，不改为更低频写法。 |
| dishonorable | dishonourable | 现有写法更常见 | 现有词头的综合英语词频更高，不改为更低频写法。 |
| fulfillment | fulfilment | 现有写法更常见 | 现有词头的综合英语词频更高，不改为更低频写法。 |
| postmortem | post-mortem | 缺少原文拼写频率 | 两种形式有效，但不使用连字符/分词估计值强选；源提示未明确其中一种更常用。 |
| agonize | agonise | 现有写法更常见 | 现有词头的综合英语词频更高，不改为更低频写法。 |
| neutralize | neutralise | 现有写法更常见 | 现有词头的综合英语词频更高，不改为更低频写法。 |
| generalization | generalisation | 现有写法更常见 | 现有词头的综合英语词频更高，不改为更低频写法。 |
| normalization | normalisation | 现有写法更常见 | 现有词头的综合英语词频更高，不改为更低频写法。 |
| popularize | popularise | 现有写法更常见 | 现有词头的综合英语词频更高，不改为更低频写法。 |
| globalize | globalise | 现有写法更常见 | 现有词头的综合英语词频更高，不改为更低频写法。 |
| tranquility | tranquillity | 现有写法更常见 | 现有词头的综合英语词频更高，不改为更低频写法。 |
| plagiarize | plagiarise | 现有写法更常见 | 现有词头的综合英语词频更高，不改为更低频写法。 |
| computerization | computerisation | 现有写法更常见 | 现有词头的综合英语词频更高，不改为更低频写法。 |
| glamour | glamor | 现有写法更常见 | 现有词头的综合英语词频更高，不改为更低频写法。 |
| characterize | characterise | 现有写法更常见 | 现有词头的综合英语词频更高，不改为更低频写法。 |
| dramatize | dramatise | 现有写法更常见 | 现有词头的综合英语词频更高，不改为更低频写法。 |
| materialize | materialise | 现有写法更常见 | 现有词头的综合英语词频更高，不改为更低频写法。 |
| industrialize | industrialise | 现有写法更常见 | 现有词头的综合英语词频更高，不改为更低频写法。 |
| monopolize | monopolise | 现有写法更常见 | 现有词头的综合英语词频更高，不改为更低频写法。 |
| visualize | visualise | 现有写法更常见 | 现有词头的综合英语词频更高，不改为更低频写法。 |
| civilize | civilise | 现有写法更常见 | 现有词头的综合英语词频更高，不改为更低频写法。 |
| clamor | clamour | 频率接近 | 两种写法的 Zipf 差小于 0.10，当前证据不足以称另一写法明显更常见。 |
| furor | furore | 现有写法更常见 | 现有词头的综合英语词频更高，不改为更低频写法。 |
| tantalize | tantalise | 现有写法更常见 | 现有词头的综合英语词频更高，不改为更低频写法。 |
| glycerin | glycerine | 现有写法更常见 | 现有词头的综合英语词频更高，不改为更低频写法。 |
| tape-recording | tape recording | 缺少原文拼写频率 | 两种形式有效，但不使用连字符/分词估计值强选；源提示未明确其中一种更常用。 |
| audio-visual | audiovisual | 缺少原文拼写频率 | 两种形式有效，但不使用连字符/分词估计值强选；源提示未明确其中一种更常用。 |
| check-out | checkout | 缺少原文拼写频率 | 两种形式有效，但不使用连字符/分词估计值强选；源提示未明确其中一种更常用。 |
| fund-raising | fundraising | 缺少原文拼写频率 | 两种形式有效，但不使用连字符/分词估计值强选；源提示未明确其中一种更常用。 |
| mid-term | midterm | 缺少原文拼写频率 | 两种形式有效，但不使用连字符/分词估计值强选；源提示未明确其中一种更常用。 |
| reexport | re-export | 缺少原文拼写频率 | 两种形式有效，但不使用连字符/分词估计值强选；源提示未明确其中一种更常用。 |
| commonsense | common-sense | 缺少原文拼写频率 | 两种形式有效，但不使用连字符/分词估计值强选；源提示未明确其中一种更常用。 |
| northeast | north-east | 缺少原文拼写频率 | 两种形式有效，但不使用连字符/分词估计值强选；源提示未明确其中一种更常用。 |
| southwest | south-west | 缺少原文拼写频率 | 两种形式有效，但不使用连字符/分词估计值强选；源提示未明确其中一种更常用。 |
| soy | soya | 现有写法更常见 | 现有词头的综合英语词频更高，不改为更低频写法。 |
| campsite | campground | 频率接近 | 两种写法的 Zipf 差小于 0.10，当前证据不足以称另一写法明显更常见。 |
| nightgown | nightdress | 现有写法更常见 | 现有词头的综合英语词频更高，不改为更低频写法。 |
| gramophone | phonograph | 频率接近 | 两种写法的 Zipf 差小于 0.10，当前证据不足以称另一写法明显更常见。 |
| hotelling | hoteling | 现有写法更常见 | 现有词头的综合英语词频更高，不改为更低频写法。 |
| archaeology | archeology | 现有写法更常见 | 现有词头的综合英语词频更高，不改为更低频写法。 |
| archaeologist | archeologist | 现有写法更常见 | 现有词头的综合英语词频更高，不改为更低频写法。 |
| medieval | mediaeval | 现有写法更常见 | 现有词头的综合英语词频更高，不改为更低频写法。 |
| naive | naïve | 现有写法更常见 | 现有词头的综合英语词频更高，不改为更低频写法。 |
| cafe | café | 现有写法更常见 | 现有词头的综合英语词频更高，不改为更低频写法。 |
| fiance | fiancé | 频率接近 | 两种写法的 Zipf 差小于 0.10，当前证据不足以称另一写法明显更常见。 |
| transship | tranship | 现有写法更常见 | 现有词头的综合英语词频更高，不改为更低频写法。 |
| gaily | gayly | 现有写法更常见 | 现有词头的综合英语词频更高，不改为更低频写法。 |
| tram | streetcar | 现有写法更常见 | 现有词头的综合英语词频更高，不改为更低频写法。 |
| kerosene | paraffin | 不直接互换或词频混义 | paraffin 还可能指石蜡；不满足整词等价，且本语料中也未更常用。 |
| orientate | orient | 不直接互换或词频混义 | orient 的总词频混入方位、名词、专名等；不据总词频把这一英式动词直接替换。 |
| invigilate | proctor | 不直接互换或词频混义 | proctor 总词频包含名词、姓氏等，不能证明动词监考义更常用；暂不替换。 |

## 建议过滤的 27 条英美变体

方向为“过滤左列，保留右列”。两列均是原词库现有词条；稳定标识见 JSON，不重写 SourceId。

| 过滤词 | 保留词 | 共同含义 | 过滤词 Zipf | 保留词 Zipf |
| --- | --- | --- | --- | --- |
| aeroplane | airplane | 飞机 | 3.18 | 3.92 |
| afterward | afterwards | 之后；后来 | 3.83 | 4.42 |
| aluminium | aluminum | 铝 | 3.73 | 4.01 |
| analyse | analyze | 分析 | 3.47 | 3.84 |
| apologise | apologize | 道歉 | 3.66 | 4.16 |
| behaviour | behavior | 行为；运行特性 | 4.36 | 4.69 |
| bookshop | bookstore | 书店 | 3.11 | 3.42 |
| despatch | dispatch | 派遣；发送；报道 | 2.69 | 3.76 |
| encyclopaedia | encyclopedia | 百科全书 | 2.81 | 3.52 |
| endeavour | endeavor | 努力；尝试 | 3.45 | 3.56 |
| enquiry | inquiry | 询问；调查 | 3.41 | 4.25 |
| favourite | favorite | 最喜欢的；热门人选 | 4.57 | 4.97 |
| favour | favor | 帮忙；支持；偏爱 | 4.31 | 4.58 |
| gaol | jail | 监狱；监禁 | 2.84 | 4.62 |
| gramme | gram | 克 | 1.64 | 3.76 |
| jeopardise | jeopardize | 危及 | 2.41 | 3.10 |
| jewellery | jewelry | 珠宝；首饰 | 3.74 | 4.12 |
| marvellous | marvelous | 极好的；令人惊叹的 | 3.40 | 3.53 |
| organisation | organization | 组织机构；组织安排 | 4.36 | 4.92 |
| organise | organize | 组织；整理 | 3.50 | 3.98 |
| paralyse | paralyze | 使瘫痪；使停摆 | 2.09 | 2.65 |
| petrol | gasoline | 汽油 | 3.72 | 3.85 |
| realise | realize | 意识到；实现 | 4.26 | 4.83 |
| recognise | recognize | 认出；承认；认可 | 3.92 | 4.52 |
| rubbish | garbage | 垃圾；废话 | 3.87 | 4.18 |
| toward | towards | 朝向；对于；用于 | 4.72 | 5.06 |
| utilise | utilize | 利用；使用 | 2.96 | 3.75 |

`endeavour/endeavor` 和 `petrol/gasoline` 的综合词频差距较小；此处是按该语料给出的统一建议，不表示前者少见或不规范。两种写法在各自地区都有效。

## 另外可清理的 4 条拼写变体

这部分不全是英美差异，独立列出，避免扩大英美词汇过滤的范围。

| 过滤词 | 保留词 | 共同含义 | 依据 |
| --- | --- | --- | --- |
| baby-sitter | babysitter | 临时保姆 | 源提示明确现代更常写 babysitter；不使用连字符拆词后的词频比较。 |
| calory | calorie | 卡路里 | 罕用拼写；源提示明确现代用 calorie。 |
| loth | loath | 不情愿的 | 较少见拼写变体；同一形容词义。 |
| mid-day | midday | 中午；正午 | 源提示明确现代通常写 midday；不与普通近义词 noon 合并。 |

## 5 组源义项未对齐：本轮保留

不能仅因为它们常被列为拼写变体，就按当前数据直接丢掉一条。若将来允许先整理并保留全部义项，可以再核对；下表箭头仅给出可能的主词方向，不属于本轮过滤清单。

| 候选次词 | 候选主词 | 当前不直接过滤的原因 |
| --- | --- | --- |
| counsellor | counselor | counselor 多收录“律师；法律顾问”；当前全部义项未对齐。 |
| dialog | dialogue | dialog 多收录计算机“对话框”；不能直接丢弃该义项。 |
| esthetic | aesthetic | aesthetic 另有名词“美学风格；审美理念”，esthetic 当前只有形容词。 |
| honour | honor | honour 明列“荣幸”，honor 当前名词释义只列荣誉、敬意；严格口径先对齐义项。 |
| reflexion | reflection | reflexion 明列物理“反射”，reflection 另列“反映；体现”，当前释义未完整对齐。 |

## 7 组常用写法未定：本轮保留

| 写法一 | 写法二 | 原因 |
| --- | --- | --- |
| gray | grey | Zipf 4.45 / 4.48，频率接近；gray 有阴沉义，grey 有动词头发变灰义，源义项也未对齐。 |
| catalog | catalogue | Zipf 均为 3.91；catalogue 还列出“一连串坏事”。不据相同词频强选一边。 |
| kilometer | kilometre | 单数 Zipf 3.19 / 3.21；计入复数后略偏向 kilometer，结论随词形变化，暂不强选。 |
| liter | litre | 单数 Zipf 3.46 / 3.50；差异很小，两种均常用，暂不强选。 |
| make-up | makeup | 源义项等价，但连字符会被 wordfreq 拆成普通词；当前证据不足以可靠比较实际拼写频率。 |
| best-seller | bestseller | 源义项等价；源提示仅说也常连写，没有明确哪个更常见；不采用拆词词频。 |
| second-hand | secondhand | 源义项等价；英美连写偏好不同，当前没有可直接比较的连字符原文计数。 |

## 部分义项相同或范围不一致：保留两条

严格口径下，保留词多一个独立义项也不采用“覆盖后过滤”；例如 `truck` 能覆盖 `lorry` 的卡车义，但两条整词数据仍不等价。

| 词条一 | 词条二 | 保留原因 |
| --- | --- | --- |
| practice | practise | 英式区分名词和动词；源 practice 为名词，practise 为动词，不能整词互换。 |
| license | licence | 英式 license 为动词、licence 为名词；源 license 还含批准义，licence 还含自由发挥义。 |
| program | programme | 英式计算机程序只用 program；源两条主释义和义项范围也不同。 |
| tire | tyre | tire 还表示使疲倦、厌倦；tyre 只表示轮胎。 |
| story | storey | story 还表示故事、报道；仅楼层义对应。 |
| truck | lorry | truck 还包含用卡车运输的动词义；用户本轮不采用义项覆盖式过滤。 |
| backpack | rucksack | backpack 还有背包旅行的动词义。 |
| apartment | flat | flat 还有平坦的、没气的两个形容词义。 |
| elevator | lift | lift 还有举起和搭便车义。 |
| pants | trousers | pants 另有英式内裤义。 |
| cookie | biscuit | cookie 有网站数据义；biscuit 有美式松软面包义；食品范围也不完全相同。 |
| movie | film | film 还有拍摄及薄膜、胶卷义。 |
| autumn | fall | fall 还有落下、跌倒、下降义。 |
| holiday | vacation | holiday 另有节日、法定假日义。 |
| sweet | candy | sweet 还有甜的、贴心的形容词义。 |
| football | soccer | football 还可指美式橄榄球。 |
| garden | yard | garden 有园艺动词义，yard 有长度单位码义。 |
| eraser | rubber | rubber 另有橡胶义。 |
| sneaker | trainer | trainer 另有教练、培训师义。 |
| sweater | jumper | jumper 还有跳跃者和美式无袖连衣裙义。 |
| handbag | purse | purse 还有零钱包、资金以及噘嘴动词义。 |
| mail | post | post 另有发布和职位、岗位义。 |
| shop | store | store 另有储存动词义及储备名词义。 |
| line | queue | line 还有线条、线路等义；只在排队义对应。 |
| boot | trunk | 仅汽车后备箱义对应，其他义项分别有靴子、启动和树干、象鼻。 |
| torch | flashlight | torch 还包含火把、火炬义。 |
| pavement | sidewalk | pavement 另有美式硬质路面义。 |
| toilet | restroom | toilet 还指马桶；restroom 当前限定公共洗手间。 |
| bath | bathtub | bath 另有洗澡、泡澡义。 |
| mailbox | postbox | mailbox 还有电子邮箱义，postbox 指公共寄信邮筒。 |
| canteen | cafeteria | canteen 还有便携水壶义。 |
| package | parcel | package 另有整套方案；parcel 另有土地、分配义。 |
| review | revise | 复习义重叠，但 review 还有评论，revise 还有修订等差异。 |
| tortoise | turtle | 陆龟、海龟及美式泛称的范围不同。 |
| wardrobe | closet | wardrobe 另有全部衣物义，closet 有储藏间和隐藏身份形容词义。 |
| transport | transportation | transport 另有运输的动词义。 |
| timetable | schedule | 名词课程/班次时刻表与一般日程、进度安排范围不完全相同；不是纯拼写变体。 |
| cooker | stove | cooker 泛指烹饪器具；stove 另有取暖火炉义，范围不完全相同。 |
| drugstore | pharmacy | drugstore 限兼售日用品的美式药店；pharmacy 还有医院药房和药剂学义。 |
| postcode | ZIP code | ZIP code 特指美国邮编；postcode 为邮编泛称，不是整词等价。 |
| car park | parking lot | 源 parking lot 限露天停车场，car park 范围更广。 |
| motorway | expressway | 虽然中文均译高速公路，各地对出入口控制、平交路口等道路分类不同，不能仅据中文整词等同。 |
| junction | intersection | junction 泛指连接处，intersection 另有交集等义。 |
| outward | outwards | outward 还可作形容词；只有副词部分等价。 |
| backward | backwards | backward 还有向后的、落后的形容词义；不能整词互换。 |
| timber | lumber | lumber 还有笨重地移动的动词义，timber 另有用材林义。 |
| raincoat | mackintosh | mackintosh 通常指橡胶防水材料雨衣，是雨衣类型和旧式称呼，不按整词等价过滤。 |
| suncream | sunscreen | suncream 限霜状制品，sunscreen 在源中包括防晒用品泛称；严格口径不按覆盖关系过滤。 |
| sunblock | sunscreen | 普通近义用词，不是稳定的一对英美拼写；本轮不扩展到所有同义词。 |
| lonesome | lonely | 源义项高度重合，但属于带地域/语体倾向的普通近义词；严格变体清单不据同义关系过滤。 |
| dorm | dormitory | 非正式简称与完整词，不属于本轮英美或拼写变体。 |
| maths | mathematics | 学科简称与完整词；真正美式对应 math 不在词库中。 |
| auto | automobile | 简称与完整词；不按普通同义或语体差异去重。 |
| automobile | car | 正式用词与日常近义词；不属于同一词的单纯拼写变体。 |
| kilogramme | kilo | 完整单位名与简称；常用完整拼写 kilogram 不在词库中。 |

## 同中文不等于变体

全义项中文归一化命中的所有组列在下表，用来复核“中文一样”筛选是否误伤。列表包含普通近义词、简称或词形，只有前面明确建议的条目才过滤。

| 原词条组 | 当前共同中文 |
| --- | --- |
| aeroplane / airplane | 飞机 |
| beginning / outset | 开始；开端 |
| maths / mathematics | 数学 |
| bookshop / bookstore | 书店 |
| delicious / tasty / delectable | 美味的；可口的 |
| begin / commence | 开始；着手 |
| everyone / everybody | 每个人；所有人 |
| someone / somebody | 某人；有人 |
| miss / missed | 错过；未赶上；想念；未击中；未察觉 |
| jewelry / jewellery | 珠宝；首饰 |
| mid-day / midday / noon | 中午；正午 |
| completely / utterly | 完全地；彻底地 |
| raincoat / mackintosh | 雨衣 |
| motorway / expressway | 高速公路 |
| petrol / gasoline | 汽油 |
| kilometer / kilometre | 千米；公里 |
| extremely / exceedingly / eminently | 极其；非常 |
| gram / gramme | 克 |
| kilogramme / kilo | 千克；公斤 |
| nearly / almost | 几乎；差不多 |
| make-up / makeup | 化妆品；组成；构成 |
| advertisement / ad | 广告 |
| necessary / needful | 必要的；必需的 |
| mostly / mainly | 主要地；大多 |
| suncream / sunblock | 防晒霜 |
| fashionable / modish | 时髦的；流行的 |
| enormous / immense | 巨大的；极大的 |
| unnecessary / needless | 不必要的；多余的 |
| obvious / evident | 明显的；显而易见的 |
| calory / calorie | 卡路里；热量单位 |
| auto / automobile | 汽车 |
| outskirts / outskirt | 市郊；城镇边缘 |
| encyclopedia / encyclopaedia | 百科全书 |
| fort / fortress | 堡垒；要塞 |
| tactics / tactic | 策略；手段；战术 |
| aluminium / aluminum | 铝 |
| relevant / pertinent | 相关的；切题的 |
| bestseller / best-seller | 畅销书；畅销商品 |
| comparatively / relatively | 相对地；比较而言 |
| expiry / expiration | 到期；期满 |
| inherent / intrinsic | 固有的；内在的 |
| dispatch / despatch | 派遣；发送；发送；派遣；新闻报道；公文 |
| hinder / impede | 阻碍；妨碍 |
| seaman / mariner | 海员；水手 |
| scornful / contemptuous | 轻蔑的；鄙视的 |
| utilise / utilize | 利用；使用 |
| consecutive / successive | 连续的；接连的 |
| loth / loath | 不情愿的；不愿意的 |

单条 `cheque/check`（SourceId 为 `cheque-check`）已在同一笔记中列出两个答案，不是两条重复词；本轮不拆分、不把总词频很高但多义的 check 当作支票义更常见的证据。

## 可复核数据与验证

- [完整 JSON 清单及 7,298 条扫描索引](word-atlas-variant-audit.json)：`decisions` 记录库内变体分组，`replacement_reviews` 记录单侧候选及拟改词头，`coverage` 逐条保留源词库 ID、词头和结论。暂保留记录的 related/proposed 字段仅是对照形式，不是处理指令。
- 已通过本地 Python 数据检查：源数量及唯一性；全部库内候选对应项存在；31 个过滤 ID 无重复且不与保留 ID 交叉；48 个改写 ID 无重复、目标词当前均未入库，应用后的目标词头无冲突；两类处理 ID 不交叉；全部 7,298 条索引与源文件一致；预计剩余 7,267 条。
- 已在当前 Anki 集合的备份副本及原集合上通过官方 Anki API 执行更新；31 张卡暂停、48 条词头修订，卡片稳定标识、调度数据和全部 695 条原复习日志保持不变。官方集合备份及原笔记字段保存在更新报告目录。
- 已运行 APKG 生成器全量 Python 测试、同步服务全量 Python 测试；typetest 构建实际镜像并复用 check_image.py 验证标签过滤、资格继承与服务冒烟，临时容器、镜像和目录均已清理。
- [运行时修订表与已有 Anki 更新说明](../../apkg-generator/data/word-atlas-revisions/README.md)。Anki 的暂停标签必须由已部署的新版服务器读取后才会作用于 typing 词库；本次尚未发布服务器代码。
