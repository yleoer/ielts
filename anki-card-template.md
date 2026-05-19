# 雅思词汇 Anki 卡片设计方案（一年记忆计划）

> 本方案针对一年时间记忆雅思词汇设计，包含完整的数据处理脚本、卡片模板和学习算法优化。

## 目录
- [一、卡片字段设置](#一卡片字段设置)
- [二、正向卡片模板](#二正向卡片模板英文中文)
- [三、反向卡片模板](#三反向卡片模板中文英文)
- [四、卡片样式](#四卡片样式)
- [五、完整数据处理脚本](#五完整数据处理脚本)
- [六、音频处理方案](#六音频处理方案)
- [七、一年记忆计划算法设置](#七一年记忆计划算法设置)
- [八、导入和使用指南](#八导入和使用指南)
- [九、常见问题解答](#九常见问题解答faq)
- [十、高级技巧](#十高级技巧)
- [十一、学习资源推荐](#十一学习资源推荐)
- [十二、总结与建议](#十二总结与建议)

---

## 一、卡片字段设置

在Anki中创建笔记类型时，需要以下字段：

### 基础字段
1. **Word** - 单词
2. **Phonetic** - 音标（通过API自动获取）
3. **PartOfSpeech** - 词性
4. **ChineseMeaning** - 中文释义
5. **ExampleEN** - 英文例句（高亮显示单词）
6. **ExampleCN** - 中文例句（AI翻译，高亮对应词）
7. **Audio** - 音频文件（从现有音频切割）
8. **Category** - 主题分类（21个主题）

### 增强字段
9. **Etymology** - 词根词缀（如：atmo-蒸汽 + sphere-球）
13. **Tags** - 标签（难度、频率、掌握度）
14. **Notes** - 额外注释（发音技巧、用法说明等）

---

## 二、正向卡片模板（英文→中文）

### 正面模板（Front Template - Forward）

```html
<div class="card-front">
  <div class="header-section">
    <div class="category">{{Category}}</div>
    <div class="tags">{{Tags}}</div>
  </div>
  
  <div class="word-container">
    <div class="word">{{Word}}</div>
    <div class="phonetic">{{Phonetic}}</div>
  </div>
  
  {{#Image}}
  <div class="image-container">
    <img src="{{Image}}" alt="{{Word}}" class="word-image">
  </div>
  {{/Image}}
</div>
```

### 背面模板（Back Template - Forward）

```html
<div class="card-back">
  <!-- 显示正面内容 -->
  <div class="header-section">
    <div class="category">{{Category}}</div>
    <div class="tags">{{Tags}}</div>
  </div>
  
  <div class="word-container">
    <div class="word">{{Word}} <span class="audio-icon">{{Audio}}</span></div>
    <div class="phonetic">{{Phonetic}}</div>
  </div>
  
  <hr class="divider">
  
  <!-- 词性和释义 -->
  <div class="meaning-section">
    <span class="part-of-speech">{{PartOfSpeech}}</span>
    <span class="chinese-meaning">{{ChineseMeaning}}</span>
  </div>
  
  <!-- 词根词缀 -->
  {{#Etymology}}
  <div class="etymology-section">
    <span class="etymology-icon">🌱</span>
    <span class="etymology-content">{{Etymology}}</span>
  </div>
  {{/Etymology}}
  
  <!-- 例句部分 -->
  <div class="example-section">
    <div class="example-label">📖 例句</div>
    <div class="example-en">
      {{ExampleEN}}
    </div>
    <div class="example-cn">
      {{ExampleCN}}
    </div>
  </div>
  
  <!-- 额外注释 -->
  {{#Notes}}
  <div class="notes-section">
    <div class="notes-label">💡 补充说明</div>
    <div class="notes-content">{{Notes}}</div>
  </div>
  {{/Notes}}
</div>
```

---

## 三、反向卡片模板（中文→英文）

### 正面模板（Front Template - Reverse）

```html
<div class="card-front reverse">
  <div class="header-section">
    <div class="category">{{Category}}</div>
    <div class="reverse-indicator">🔄 反向卡片</div>
  </div>
  
  <div class="chinese-prompt">
    <div class="prompt-label">请回忆这个单词：</div>
    <div class="chinese-meaning-large">{{ChineseMeaning}}</div>
    <div class="part-of-speech-hint">{{PartOfSpeech}}</div>
  </div>
</div>
```

### 背面模板（Back Template - Reverse）

```html
<div class="card-back reverse">
  <div class="header-section">
    <div class="category">{{Category}}</div>
    <div class="reverse-indicator">🔄 反向卡片</div>
  </div>
  
  <!-- 答案：单词 -->
  <div class="answer-section">
    <div class="answer-label">答案</div>
    <div class="word-container">
      <div class="word">{{Word}} <span class="audio-icon">{{Audio}}</span></div>
      <div class="phonetic">{{Phonetic}}</div>
    </div>
  </div>
  
  <hr class="divider">
  
  <!-- 释义确认 -->
  <div class="meaning-section">
    <span class="part-of-speech">{{PartOfSpeech}}</span>
    <span class="chinese-meaning">{{ChineseMeaning}}</span>
  </div>
  
  <!-- 词根词缀 -->
  {{#Etymology}}
  <div class="etymology-section">
    <span class="etymology-icon">🌱</span>
    <span class="etymology-content">{{Etymology}}</span>
  </div>
  {{/Etymology}}
  
  <!-- 例句 -->
  <div class="example-section">
    <div class="example-label">📖 例句</div>
    <div class="example-en">{{ExampleEN}}</div>
    <div class="example-cn">{{ExampleCN}}</div>
  </div>
</div>
```

---

## 四、卡片样式（Styling）

```css
/* ========== 通用样式 ========== */
.card {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  max-width: 600px;
  margin: 0 auto;
  padding: 20px;
  background: #ffffff;
  line-height: 1.6;
}

.card-front, .card-back {
  background: #ffffff;
  padding: 20px;
}

/* ========== 头部区域 ========== */
.header-section {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
  padding-bottom: 10px;
  border-bottom: 1px solid #e5e7eb;
  flex-wrap: wrap;
  gap: 8px;
}

.category {
  display: inline-block;
  background: #f3f4f6;
  color: #6b7280;
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}

.tags {
  font-size: 11px;
  color: #9ca3af;
  padding: 3px 8px;
  background: #f9fafb;
  border-radius: 3px;
}

.reverse-indicator {
  background: #e5e7eb;
  color: #6b7280;
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}

/* ========== 单词区域 ========== */
.word-container {
  text-align: left;
  margin: 20px 0;
  padding: 15px 0;
}

.word {
  font-size: 28px;
  font-weight: 600;
  color: #1f2937;
  margin-bottom: 8px;
  letter-spacing: 0.5px;
}

.phonetic {
  font-size: 16px;
  color: #6b7280;
  font-family: "Lucida Sans Unicode", "Arial Unicode MS", sans-serif;
}

/* ========== 音频图标 ========== */
.audio-icon {
  display: inline-block;
  font-size: 14px;
  margin-left: 8px;
  opacity: 0.6;
  vertical-align: middle;
}

/* ========== 音频提示 ========== */
.audio-hint {
  text-align: left;
  color: #9ca3af;
  font-size: 12px;
  margin-top: 15px;
  padding: 8px 10px;
  background: #f9fafb;
  border-radius: 4px;
  border-left: 2px solid #d1d5db;
}

/* ========== 分隔线 ========== */
.divider {
  border: none;
  height: 1px;
  background: #e5e7eb;
  margin: 20px 0;
}

/* ========== 释义区域 ========== */
.meaning-section {
  margin: 15px 0;
  padding: 12px 15px;
  background: #f9fafb;
  border-radius: 4px;
  border-left: 3px solid #9ca3af;
  line-height: 1.6;
}

.part-of-speech {
  display: inline-block;
  background: #e5e7eb;
  color: #4b5563;
  padding: 2px 8px;
  border-radius: 3px;
  font-size: 12px;
  font-weight: 600;
  margin-right: 10px;
  text-transform: lowercase;
}

.chinese-meaning {
  font-size: 16px;
  font-weight: 500;
  color: #1f2937;
  line-height: 1.6;
}

/* ========== 词根词缀区域 ========== */
.etymology-section {
  margin: 15px 0;
  padding: 10px 12px;
  background: #f9fafb;
  border-radius: 4px;
  border-left: 3px solid #d1d5db;
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.etymology-icon {
  font-size: 14px;
  color: #9ca3af;
}

.etymology-content {
  font-size: 14px;
  color: #4b5563;
  line-height: 1.5;
}

/* ========== 例句区域 ========== */
.example-section {
  margin: 15px 0;
  padding: 12px 15px;
  background: #ffffff;
  border-radius: 4px;
  border: 1px solid #e5e7eb;
}

.example-label {
  font-size: 12px;
  font-weight: 600;
  color: #6b7280;
  margin-bottom: 8px;
}

.example-en {
  font-size: 15px;
  line-height: 1.6;
  color: #1f2937;
  margin-bottom: 8px;
}

.example-cn {
  font-size: 14px;
  line-height: 1.6;
  color: #6b7280;
}

/* 高亮例句中的单词 */
.example-en b, .example-en strong {
  color: #1f2937;
  font-weight: 600;
  text-decoration: underline;
  text-decoration-color: #d1d5db;
  text-decoration-thickness: 2px;
  text-underline-offset: 2px;
}

.example-cn b, .example-cn strong {
  color: #4b5563;
  font-weight: 600;
}

/* ========== 注释区域 ========== */
.notes-section {
  margin-top: 15px;
  padding: 10px 12px;
  background: #f9fafb;
  border-radius: 4px;
  border-left: 3px solid #9ca3af;
}

.notes-label {
  font-size: 11px;
  font-weight: 600;
  color: #6b7280;
  margin-bottom: 6px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.notes-content {
  font-size: 13px;
  color: #4b5563;
  line-height: 1.5;
}

/* ========== 反向卡片特殊样式 ========== */
.card-front.reverse {
  background: #f9fafb;
}

.chinese-prompt {
  text-align: left;
  margin: 30px 0;
}

.prompt-label {
  font-size: 14px;
  color: #6b7280;
  margin-bottom: 15px;
}

.chinese-meaning-large {
  font-size: 24px;
  font-weight: 600;
  color: #1f2937;
  margin-bottom: 12px;
  line-height: 1.4;
}

.part-of-speech-hint {
  font-size: 14px;
  color: #6b7280;
  font-weight: 500;
}

.hint-section {
  text-align: left;
  margin-top: 20px;
  padding: 10px 12px;
  background: #f9fafb;
  border-radius: 4px;
  border-left: 3px solid #d1d5db;
}

.hint-text {
  font-size: 13px;
  color: #6b7280;
}

.answer-section {
  text-align: left;
  margin: 20px 0;
  padding: 15px;
  background: #f9fafb;
  border-radius: 4px;
  border: 1px solid #e5e7eb;
}

.answer-label {
  font-size: 12px;
  font-weight: 600;
  color: #6b7280;
  margin-bottom: 10px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

/* ========== 响应式设计 ========== */
@media (max-width: 480px) {
  .word {
    font-size: 24px;
  }
  
  .phonetic {
    font-size: 14px;
  }
  
  .chinese-meaning {
    font-size: 15px;
  }
  
  .chinese-meaning-large {
    font-size: 20px;
  }
  
  .example-en {
    font-size: 14px;
  }
  
  .example-cn {
    font-size: 13px;
  }
  
  .word-image {
    max-height: 150px;
  }
}

/* ========== 夜间模式 ========== */
.night_mode .card {
  background: #1f2937;
}

.night_mode .card-front,
.night_mode .card-back {
  background: #1f2937;
  color: #e5e7eb;
}

.night_mode .header-section {
  border-bottom-color: #374151;
}

.night_mode .category,
.night_mode .reverse-indicator {
  background: #374151;
  color: #9ca3af;
}

.night_mode .tags {
  background: #374151;
  color: #6b7280;
}

.night_mode .word {
  color: #f3f4f6;
}

.night_mode .phonetic {
  color: #9ca3af;
}

.night_mode .meaning-section {
  background: #374151;
  border-left-color: #6b7280;
}

.night_mode .chinese-meaning {
  color: #e5e7eb;
}

.night_mode .etymology-section {
  background: #374151;
  border-left-color: #6b7280;
}

.night_mode .etymology-content {
  color: #d1d5db;
}

.night_mode .synonyms,
.night_mode .antonyms {
  background: #374151;
  border-left-color: #6b7280;
}

.night_mode .relation-label,
.night_mode .relation-words {
  color: #d1d5db;
}

.night_mode .example-section {
  background: #1f2937;
  border-color: #374151;
}

.night_mode .example-en {
  color: #e5e7eb;
}

.night_mode .example-cn {
  color: #9ca3af;
}

.night_mode .example-en b,
.night_mode .example-en strong {
  color: #f3f4f6;
  text-decoration-color: #6b7280;
}

.night_mode .notes-section {
  background: #374151;
  border-left-color: #6b7280;
}

.night_mode .notes-label {
  color: #9ca3af;
}

.night_mode .notes-content {
  color: #d1d5db;
}

.night_mode .chinese-meaning-large {
  color: #f3f4f6;
}

.night_mode .answer-section {
  background: #374151;
  border-color: #4b5563;
}

.night_mode .hint-section {
  background: #374151;
  border-left-color: #6b7280;
}

.night_mode .audio-hint {
  background: #374151;
  border-left-color: #6b7280;
}

.night_mode .word-image {
  border-color: #374151;
}
```

---

## 五、完整数据处理脚本

将以下脚本保存为 `generate_anki_cards.py`，用于处理词汇数据。

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
雅思词汇 Anki 卡片生成脚本
功能：
1. 解析 vocabulary.txt
2. 通过API获取音标
3. 使用AI翻译例句
4. 提取词根词缀
5. 生成标签
6. 导出CSV格式
"""

import csv
import re
import time
import requests
from pathlib import Path
from typing import Dict, List, Optional
import json

# ==================== 配置区域 ====================

# OpenAI API配置（用于翻译和词根词缀分析）
OPENAI_API_KEY = "your-api-key-here"  # 替换为你的API密钥
OPENAI_API_BASE = "https://api.openai.com/v1"  # 或使用其他兼容的API

# 图片搜索API（可选，使用Unsplash）
UNSPLASH_ACCESS_KEY = "your-unsplash-key"  # 可选

# 输入输出路径
INPUT_FILE = "src/pages/vocabulary/vocabulary.txt"
OUTPUT_CSV = "anki_vocabulary.csv"
IMAGES_DIR = "anki_images"

# 需要下载图片的词性（具象名词）
IMAGE_POS = ["n."]

# 标签配置
DIFFICULTY_TAGS = {
    "easy": ["the", "is", "are"],  # 示例，需根据实际调整
    "medium": [],
    "hard": []
}

# ==================== 工具函数 ====================

def get_phonetic(word: str) -> str:
    """通过免费API获取音标"""
    # 方案1: Free Dictionary API
    url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list) and len(data) > 0:
                phonetics = data[0].get('phonetics', [])
                for p in phonetics:
                    if 'text' in p and p['text']:
                        return p['text']
    except Exception as e:
        print(f"获取音标失败 ({word}): {e}")
    
    # 方案2: 备用API（如果需要）
    # 可以添加其他API作为备选
    
    return ""

def translate_with_ai(text: str, word: str) -> str:
    """使用AI翻译例句并高亮对应单词"""
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    
    prompt = f"""请将以下英文句子翻译成中文，并在翻译中用<b></b>标签标注出与英文单词"{word}"对应的中文词汇。

英文句子：{text}
目标单词：{word}

要求：
1. 翻译要准确、自然
2. 用<b></b>标签包裹对应的中文词汇
3. 只返回翻译结果，不要其他说明

翻译："""
    
    data = {
        "model": "gpt-3.5-turbo",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3
    }
    
    try:
        response = requests.post(
            f"{OPENAI_API_BASE}/chat/completions",
            headers=headers,
            json=data,
            timeout=30
        )
        if response.status_code == 200:
            result = response.json()
            translation = result['choices'][0]['message']['content'].strip()
            return translation
    except Exception as e:
        print(f"翻译失败 ({word}): {e}")
    
    return ""

def get_etymology(word: str) -> str:
    """使用AI分析词根词缀"""
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    
    prompt = f"""请分析英文单词"{word}"的词根词缀构成。

要求：
1. 如果有明确的词根词缀，按格式返回：词根1(含义) + 词根2(含义)
2. 如果没有明显的词根词缀结构，返回空字符串
3. 只返回分析结果，不要其他说明
4. 示例格式：atmo-(蒸汽) + sphere(球)

单词：{word}
词根词缀："""
    
    data = {
        "model": "gpt-3.5-turbo",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3
    }
    
    try:
        response = requests.post(
            f"{OPENAI_API_BASE}/chat/completions",
            headers=headers,
            json=data,
            timeout=30
        )
        if response.status_code == 200:
            result = response.json()
            etymology = result['choices'][0]['message']['content'].strip()
            # 如果返回的是"无"、"没有"等，返回空字符串
            if etymology.lower() in ['无', '没有', 'none', 'n/a', '']:
                return ""
            return etymology
    except Exception as e:
        print(f"词根词缀分析失败 ({word}): {e}")
    
    return ""

def generate_tags(word: str, category: str, pos: str) -> str:
    """生成标签"""
    tags = []
    
    # 添加分类标签
    tags.append(f"#{category}")
    
    # 添加难度标签（简单示例，可根据词频等优化）
    word_len = len(word)
    if word_len <= 5:
        tags.append("#easy")
    elif word_len <= 8:
        tags.append("#medium")
    else:
        tags.append("#hard")
    
    # 添加词性标签
    if 'n.' in pos:
        tags.append("#noun")
    elif 'v.' in pos:
        tags.append("#verb")
    elif 'adj.' in pos:
        tags.append("#adjective")
    elif 'adv.' in pos:
        tags.append("#adverb")
    
    return ' '.join(tags)

def highlight_word_in_sentence(sentence: str, word: str) -> str:
    """在例句中高亮显示单词（包括变形）"""
    # 处理单词的各种形式
    word_base = word.lower().strip()
    # 匹配单词及其变形（简单处理）
    pattern = re.compile(
        r'\b(' + re.escape(word_base) + r'[a-z]*)\b',
        re.IGNORECASE
    )
    return pattern.sub(r'<b>\1</b>', sentence)

# ==================== 主处理函数 ====================

def parse_vocabulary_file(file_path: str) -> List[Dict]:
    """解析vocabulary.txt文件并生成完整的卡片数据"""
    cards = []
    current_category = ""
    
    print(f"开始解析文件: {file_path}")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    total_lines = len(lines)
    processed = 0
    
    for line in lines:
        line = line.strip()
        
        # 跳过空行和分隔符
        if not line or line in ['+++', '---']:
            continue
        
        # 检查是否是分类标题
        if '|' not in line:
            parts = line.split('\t')
            if len(parts) >= 2:
                current_category = parts[-1]
                print(f"\n处理分类: {current_category}")
            continue
        
        # 解析单词条目
        parts = line.split('\t')
        if len(parts) < 2:
            continue
        
        word_data = parts[1].split('|')
        if len(word_data) < 4:
            continue
        
        word = word_data[0].strip()
        pos = word_data[1].strip()
        meaning = word_data[2].strip()
        example = word_data[3].strip()
        notes = word_data[4].strip() if len(word_data) > 4 else ""
        
        print(f"  处理单词: {word}")
        
        # 1. 获取音标
        phonetic = get_phonetic(word)
        time.sleep(0.5)  # 避免API限流
        
        # 2. 高亮例句中的单词
        example_highlighted = highlight_word_in_sentence(example, word)
        
        # 3. 翻译例句
        example_cn = translate_with_ai(example, word)
        time.sleep(1)  # 避免API限流
        
        # 4. 获取词根词缀
        etymology = get_etymology(word)
        time.sleep(1)
        
        # 5. 生成标签
        tags = generate_tags(word, current_category, pos)
        
        # 6. 构建卡片数据
        card = {
            'Word': word,
            'Phonetic': phonetic,
            'PartOfSpeech': pos,
            'ChineseMeaning': meaning,
            'ExampleEN': example_highlighted,
            'ExampleCN': example_cn,
            'Audio': f'[sound:{word.replace(" ", "_")}.mp3]',
            'Category': current_category,
            'Etymology': etymology,
            'Synonyms': synonyms,
            'Antonyms': antonyms,
            'Image': image,
            'Tags': tags,
            'Notes': notes
        }
        
        cards.append(card)
        processed += 1
        
        # 每处理10个单词保存一次（防止中断丢失数据）
        if processed % 10 == 0:
            print(f"  已处理: {processed} 个单词")
            save_checkpoint(cards, f"{OUTPUT_CSV}.checkpoint")
    
    print(f"\n总共处理了 {len(cards)} 个单词")
    return cards

def save_checkpoint(cards: List[Dict], filepath: str):
    """保存检查点"""
    with open(filepath, 'w', encoding='utf-8', newline='') as f:
        if cards:
            writer = csv.DictWriter(f, fieldnames=cards[0].keys())
            writer.writeheader()
            writer.writerows(cards)

def export_to_csv(cards: List[Dict], output_path: str):
    """导出为Anki CSV格式"""
    fieldnames = [
        'Word', 'Phonetic', 'PartOfSpeech', 'ChineseMeaning',
        'ExampleEN', 'ExampleCN', 'Audio', 'Category',
        'Etymology', 'Tags', 'Notes'
    ]
    
    with open(output_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(cards)
    
    print(f"\n数据已导出到: {output_path}")

# ==================== 主程序 ====================

def main():
    print("=" * 60)
    print("雅思词汇 Anki 卡片生成器")
    print("=" * 60)
    
    # 检查配置
    if OPENAI_API_KEY == "your-api-key-here":
        print("\n警告: 请先配置 OPENAI_API_KEY")
        print("脚本将继续运行，但翻译和词根词缀功能将不可用\n")
    
    # 解析文件
    cards = parse_vocabulary_file(INPUT_FILE)
    
    # 导出CSV
    export_to_csv(cards, OUTPUT_CSV)
    
    # 生成统计信息
    print("\n" + "=" * 60)
    print("统计信息:")
    print(f"  总单词数: {len(cards)}")
    print(f"  有音标: {sum(1 for c in cards if c['Phonetic'])}")
    print(f"  有翻译: {sum(1 for c in cards if c['ExampleCN'])}")
    print(f"  有词根词缀: {sum(1 for c in cards if c['Etymology'])}")
    print("=" * 60)
    
    print("\n完成！请将以下文件导入Anki：")
    print(f"  1. CSV文件: {OUTPUT_CSV}")
    print(f"  2. 音频文件: 需要单独处理（见下一节）")

if __name__ == "__main__":
    main()
```

---

## 六、音频处理方案

### 方案说明

项目中的音频文件是按主题打包的（如 `01_自然地理.mp3`），需要切割成单个单词的音频文件。

### 音频切割脚本

将以下脚本保存为 `split_audio.py`：

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
音频切割脚本
根据 audacity_tags.txt 文件切割主题音频为单个单词音频
"""

import os
import re
from pathlib import Path
from pydub import AudioSegment

# ==================== 配置 ====================

AUDIO_DIR = "public/vocabulary/audio"
OUTPUT_DIR = "anki_audio"

# ==================== 函数 ====================

def parse_audacity_tags(tags_file: str) -> list:
    """解析Audacity标签文件"""
    tags = []
    with open(tags_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            # Audacity标签格式: start_time\tend_time\tlabel
            parts = line.split('\t')
            if len(parts) >= 3:
                start = float(parts[0])
                end = float(parts[1])
                label = parts[2].strip()
                tags.append({
                    'start': start,
                    'end': end,
                    'label': label
                })
    return tags

def split_audio_by_tags(audio_file: str, tags: list, output_dir: str):
    """根据标签切割音频"""
    print(f"加载音频: {audio_file}")
    audio = AudioSegment.from_mp3(audio_file)
    
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    for tag in tags:
        start_ms = int(tag['start'] * 1000)
        end_ms = int(tag['end'] * 1000)
        label = tag['label']
        
        # 提取单词（去除音标等）
        word = re.split(r'[/\[\(]', label)[0].strip()
        if not word:
            continue
        
        # 切割音频
        segment = audio[start_ms:end_ms]
        
        # 保存
        output_file = Path(output_dir) / f"{word.replace(' ', '_')}.mp3"
        segment.export(output_file, format="mp3")
        print(f"  导出: {output_file.name}")

def process_all_categories():
    """处理所有分类的音频"""
    audio_base = Path(AUDIO_DIR)
    
    # 遍历所有分类目录
    for category_dir in audio_base.iterdir():
        if not category_dir.is_dir():
            continue
        
        category_name = category_dir.name
        print(f"\n处理分类: {category_name}")
        
        # 查找标签文件
        tags_file = category_dir / "audacity_tags.txt"
        if not tags_file.exists():
            print(f"  警告: 未找到标签文件 {tags_file}")
            continue
        
        # 查找对应的音频文件
        audio_file = audio_base / f"{category_name}.mp3"
        if not audio_file.exists():
            print(f"  警告: 未找到音频文件 {audio_file}")
            continue
        
        # 解析标签
        tags = parse_audacity_tags(str(tags_file))
        print(f"  找到 {len(tags)} 个标签")
        
        # 切割音频
        split_audio_by_tags(str(audio_file), tags, OUTPUT_DIR)

# ==================== 主程序 ====================

def main():
    print("=" * 60)
    print("音频切割工具")
    print("=" * 60)
    
    # 检查依赖
    try:
        import pydub
    except ImportError:
        print("\n错误: 请先安装 pydub 库")
        print("运行: pip install pydub")
        print("\n注意: pydub 需要 ffmpeg 支持")
        print("Windows: 下载 ffmpeg 并添加到 PATH")
        print("Mac: brew install ffmpeg")
        print("Linux: sudo apt-get install ffmpeg")
        return
    
    # 处理音频
    process_all_categories()
    
    print("\n" + "=" * 60)
    print(f"完成！音频文件已保存到: {OUTPUT_DIR}/")
    print("=" * 60)

if __name__ == "__main__":
    main()
```

### 安装依赖

```bash
# 安装Python库
pip install pydub

# 安装ffmpeg（音频处理必需）
# Windows: 下载 https://ffmpeg.org/download.html 并添加到PATH
# Mac: brew install ffmpeg
# Linux: sudo apt-get install ffmpeg
```

### 使用方法

1. 确保项目中有 `public/vocabulary/audio/` 目录
2. 每个分类目录下有 `audacity_tags.txt` 标签文件
3. 运行脚本：`python split_audio.py`
4. 切割后的音频保存在 `anki_audio/` 目录

### 标签文件格式

Audacity标签文件格式示例：
```
0.000000	1.500000	atmosphere /ˈætməsfɪə(r)/
1.500000	3.200000	hydrosphere /ˈhaɪdrəsfɪə(r)/
3.200000	4.800000	lithosphere /ˈlɪθəsfɪə(r)/
```

---

## 七、一年记忆计划算法设置

### 目标分析

- **总词汇量**：约 3000-4000 个雅思词汇
- **学习周期**：365 天
- **每天新词**：10-12 个（考虑复习负担）
- **目标**：一年内完成所有词汇的学习和巩固

### Anki 算法优化设置

#### 1. 新卡片设置（New Cards）

```
每天新卡片数量: 10-12 张
新卡片顺序: 按添加顺序（Order added）
新卡片步长: 15分钟 1天 3天
毕业间隔: 7天
简单间隔: 10天
起始简便度: 250%
```

**说明**：
- **15分钟**：第一次复习，检查短期记忆
- **1天**：第二次复习，巩固记忆
- **3天**：第三次复习，确认掌握
- **毕业间隔7天**：适合一年计划，不会太激进
- **简单间隔10天**：点击"简单"时直接跳到10天后

#### 2. 复习设置（Reviews）

```
每天最大复习数: 200 张
最大间隔: 365 天
简便度修正: -20%（困难）、0%（一般）
困难间隔: 1.2
间隔修正: 100%
新间隔: 0%（重新学习时从头开始）
最小间隔: 1天
```

**说明**：
- **最大间隔365天**：一年计划的上限
- **每天最大复习200张**：后期复习量会增加，需要足够容量
- **困难间隔1.2**：点击"困难"时，间隔只增加20%

#### 3. 遗忘设置（Lapses）

```
重新学习步长: 10分钟 1天
最小间隔: 1天
水蛭阈值: 8次
水蛭操作: 标记卡片（Tag Only）
```

**说明**：
- **重新学习步长**：忘记的卡片需要快速复习
- **水蛭阈值8次**：失败8次标记为"难词"
- **标记而不暂停**：继续学习，但可以单独复习

#### 4. 高级设置（Advanced）

```
最大间隔: 365天
起始简便度: 250%
简便度修正:
  - 再来一次: -20%
  - 困难: -15%
  - 一般: 0%
  - 简单: +15%
间隔修正: 100%
新间隔: 0%
```

### 一年学习计划时间表

#### 第一阶段：建立基础（1-3个月）

```
目标: 学习 900-1080 个单词
每天新词: 10-12 个
每天复习: 20-50 个
每天总时间: 30-45 分钟
重点: 高频词汇、基础分类
```

**策略**：
- 先学习高频分类（自然地理、学校教育、社会经济等）
- 重点掌握正向卡片（英文→中文）
- 建立学习习惯和节奏

#### 第二阶段：稳步推进（4-8个月）

```
目标: 学习 1500-1800 个单词
每天新词: 10-12 个
每天复习: 80-120 个
每天总时间: 45-60 分钟
重点: 中频词汇、专业分类
```

**策略**：
- 继续学习新词，复习量逐渐增加
- 开始使用反向卡片（中文→英文）
- 关注"水蛭卡片"，单独强化

#### 第三阶段：冲刺巩固（9-12个月）

```
目标: 完成所有单词，全面复习
每天新词: 0-5 个（收尾）
每天复习: 100-150 个
每天总时间: 40-60 分钟
重点: 全面复习、查漏补缺
```

**策略**：
- 减少新词，专注复习
- 使用"自定义学习"功能复习薄弱环节
- 模拟考试场景，实战应用

### 学习节奏建议

#### 每日学习流程

```
1. 早晨（10-15分钟）
   - 复习昨天学习的新词
   - 快速过一遍到期的复习卡片

2. 中午/下午（15-20分钟）
   - 学习今天的新词（10-12个）
   - 完成新词的第一轮复习（15分钟后）

3. 晚上（15-25分钟）
   - 完成所有到期的复习卡片
   - 重点复习标记为"困难"的卡片
```

#### 每周复盘

```
周末安排:
- 回顾本周学习的所有新词
- 使用"自定义学习"功能：
  * 筛选本周添加的卡片
  * 筛选标记为"困难"的卡片
  * 筛选"水蛭"卡片
- 调整下周学习计划
```

### Anki 插件推荐

#### 必装插件

1. **Review Heatmap** - 学习进度可视化
   - 显示每天学习情况
   - 激励持续学习

2. **Advanced Browser** - 增强搜索和筛选
   - 快速找到特定卡片
   - 批量编辑

3. **AwesomeTTS** - 自动生成发音
   - 补充缺失的音频
   - 支持多种TTS引擎

4. **Image Occlusion Enhanced** - 图片遮挡
   - 用于图片辅助记忆
   - 适合地理、生物类词汇

#### 可选插件

5. **Anki Simulator** - 学习预测
   - 预测未来复习负担
   - 优化学习计划

6. **Batch Editing** - 批量编辑
   - 快速修改多张卡片
   - 批量添加标签

7. **Frozen Fields** - 冻结字段
   - 添加卡片时保持某些字段不变
   - 提高输入效率

### 学习技巧

#### 1. 利用标签系统

```
按难度筛选:
- #easy - 简单词汇，快速过
- #medium - 中等难度，重点记
- #hard - 困难词汇，反复练

按掌握度筛选:
- #mastered - 已掌握
- #reviewing - 复习中
- #difficult - 困难词

按主题筛选:
- #自然地理
- #学校教育
- #社会经济
- ...
```

#### 2. 自定义学习

```
场景1: 考前冲刺
- 筛选: 标签:#high-frequency
- 模式: 复习所有卡片
- 顺序: 随机

场景2: 攻克难词
- 筛选: 标签:#difficult 或 水蛭卡片
- 模式: 重新学习
- 顺序: 按添加顺序

场景3: 主题复习
- 筛选: 标签:#自然地理
- 模式: 复习所有卡片
- 顺序: 按间隔（最久未复习的优先）
```

#### 3. 记忆技巧

- **词根词缀法**：利用Etymology字段理解单词构成
- **联想记忆法**：结合图片和例句建立联想
- **对比记忆法**：利用同义词/反义词对比记忆
- **场景记忆法**：在例句场景中理解单词用法
- **反向测试法**：使用反向卡片检验真实掌握度

### 监控和调整

#### 关键指标

```
1. 保留率（Retention Rate）
   - 目标: >85%
   - 低于80%: 减少新词数量或增加复习

2. 每天学习时间
   - 目标: 40-60分钟
   - 超过90分钟: 减少新词数量

3. 到期卡片积压
   - 目标: <50张
   - 超过100张: 暂停新词，专注复习

4. 水蛭卡片数量
   - 目标: <5%
   - 超过10%: 需要改进学习方法
```

#### 调整策略

```
情况1: 复习负担过重
- 减少每天新词数量（10→8）
- 增加毕业间隔（7天→10天）
- 增加最大间隔（365天→180天）

情况2: 学习进度落后
- 增加每天新词数量（10→15）
- 减少新卡片步长（15分钟 1天 3天 → 15分钟 1天）
- 周末加强学习

情况3: 遗忘率过高
- 减少毕业间隔（7天→5天）
- 增加复习频率
- 重点复习困难卡片
```

---

## 八、导入和使用指南

### 步骤1：准备数据文件

1. **运行数据生成脚本**
   ```bash
   python generate_anki_cards.py
   ```
   
2. **运行音频切割脚本**
   ```bash
   python split_audio.py
   ```

3. **检查生成的文件**
   - `anki_vocabulary.csv` - 卡片数据
   - `anki_audio/` - 音频文件
   - `anki_images/` - 图片文件（如果配置了）

### 步骤2：创建Anki笔记类型

1. 打开Anki，点击 **工具 → 管理笔记类型**
2. 点击 **添加**，选择 **添加：基础**
3. 命名为 `IELTS Vocabulary Enhanced`
4. 点击 **字段**，添加以下14个字段：
   - Word, Phonetic, PartOfSpeech, ChineseMeaning
   - ExampleEN, ExampleCN, Audio, Category
   - Etymology, Synonyms, Antonyms, Image, Tags, Notes

### 步骤3：设置卡片模板

1. 在笔记类型管理界面，点击 **卡片**
2. 创建两个卡片模板：

**卡片1：正向（英文→中文）**
- 复制本文档"二、正向卡片模板"中的HTML代码
- 粘贴到对应的正面/背面模板

**卡片2：反向（中文→英文）**
- 点击 **添加卡片类型**
- 复制本文档"三、反向卡片模板"中的HTML代码
- 粘贴到对应的正面/背面模板

3. 点击 **样式**，复制本文档"四、卡片样式"中的CSS代码

### 步骤4：导入CSV数据

1. 点击 **文件 → 导入**
2. 选择 `anki_vocabulary.csv`
3. 设置导入选项：
   - 类型：`IELTS Vocabulary Enhanced`
   - 牌组：创建新牌组 `IELTS Vocabulary`
   - 字段分隔符：逗号
   - 允许HTML：✓
   - 字段映射：确保CSV列与Anki字段一一对应
4. 点击 **导入**

### 步骤5：导入媒体文件

1. **音频文件**
   - 找到Anki的媒体文件夹：
     - Windows: `C:\Users\[用户名]\AppData\Roaming\Anki2\[配置文件]\collection.media\`
     - Mac: `~/Library/Application Support/Anki2/[配置文件]/collection.media/`
   - 将 `anki_audio/` 中的所有MP3文件复制到该文件夹

2. **图片文件**
   - 将 `anki_images/` 中的所有图片文件复制到同一媒体文件夹

### 步骤6：配置学习算法

1. 选择 `IELTS Vocabulary` 牌组
2. 点击牌组右侧的 **⚙️ 选项**
3. 按照"七、一年记忆计划算法设置"中的参数配置

### 步骤7：开始学习

1. 点击牌组开始学习
2. 建议每天固定时间学习
3. 使用Anki移动端同步学习进度

---

## 九、常见问题解答（FAQ）

### 1. 为什么音标显示不正常？

**原因**：字体不支持IPA音标符号

**解决方案**：
- 安装支持IPA的字体（如 Arial Unicode MS, Lucida Sans Unicode）
- 在CSS中指定字体：
  ```css
  .phonetic {
    font-family: "Lucida Sans Unicode", "Arial Unicode MS", sans-serif;
  }
  ```

### 2. 音频无法自动播放？

**原因**：
- 音频文件名与CSV中的不匹配
- 音频文件未正确导入到媒体文件夹

**解决方案**：
- 检查音频文件名格式：`[sound:word.mp3]`
- 确认音频文件在 `collection.media` 文件夹中
- 在Anki中点击 **工具 → 检查媒体** 查看缺失文件

### 3. 如何调整每天的学习量？

**方案**：
- 点击牌组 **选项 → 新卡片 → 每天新卡片数量**
- 根据复习负担调整（建议8-15张）
- 使用 **Anki Simulator** 插件预测未来负担

### 4. 反向卡片太难，总是忘记怎么办？

**建议**：
- 初期可以暂停反向卡片，专注正向学习
- 3个月后再启用反向卡片
- 或者降低反向卡片的出现频率：
  - 选择反向卡片模板
  - 设置不同的学习参数（更长的间隔）

### 5. 如何批量修改已导入的卡片？

**方法**：
1. 安装 **Advanced Browser** 插件
2. 在浏览器中筛选需要修改的卡片
3. 选中多张卡片
4. 右键 → **批量编辑** → 选择字段修改

### 6. 水蛭卡片（Leech）是什么？如何处理？

**定义**：失败次数超过阈值（默认8次）的卡片

**处理方法**：
- 使用 `tag:leech` 筛选水蛭卡片
- 分析原因：
  - 单词太难？→ 添加更多记忆线索（图片、词根）
  - 释义不准确？→ 修改中文释义
  - 例句太复杂？→ 简化例句
- 重置卡片：右键 → **重新安排** → **放入学习队列**

### 7. 如何在手机上同步学习？

**步骤**：
1. 注册AnkiWeb账号（https://ankiweb.net）
2. 在桌面端：**工具 → 同步 → 登录**
3. 下载移动端App：
   - iOS: AnkiMobile（付费）
   - Android: AnkiDroid（免费）
4. 在移动端登录同一账号
5. 点击同步按钮

**注意**：
- 首次同步会上传所有媒体文件（可能较慢）
- 建议在WiFi环境下同步

### 8. 如何导出学习进度和统计数据？

**方法**：
1. **导出牌组**：
   - 选择牌组 → **导出**
   - 格式：Anki牌组包（.apkg）
   - 包含：✓ 包含媒体文件

2. **查看统计**：
   - 点击牌组 → **统计**
   - 查看学习时间、保留率、预测等

3. **使用插件**：
   - **Review Heatmap**：可视化学习日历
   - **Anki Stats**：详细统计报告

### 9. 可以同时学习多个牌组吗？

**可以，但不建议**

**原因**：
- 复习负担会叠加
- 容易超出每天时间预算
- 影响记忆效果

**建议**：
- 专注一个主牌组（IELTS Vocabulary）
- 其他牌组设置较少的每天新卡片数
- 或者使用子牌组分类学习

### 10. 学习中断了几天，如何恢复？

**不要慌张**：
- Anki会累积到期卡片
- 不要试图一次性完成所有复习

**恢复策略**：
1. **暂停新词**：设置每天新卡片数为0
2. **分批复习**：每天复习50-100张到期卡片
3. **使用筛选牌组**：
   - 创建筛选牌组
   - 筛选条件：`is:due`
   - 限制数量：50张
   - 逐步清理积压
4. **恢复正常**：积压清理后，恢复新词学习

---
## 十、高级技巧

### 1. 使用筛选牌组（Filtered Decks）

筛选牌组可以创建临时的学习集合，不影响原牌组。

**应用场景**：

**场景1：考前冲刺复习**
```
创建筛选牌组：考前冲刺
筛选条件：deck:"IELTS Vocabulary" tag:#high-frequency
卡片数量：200
排序：随机
```

**场景2：攻克难词**
```
创建筛选牌组：困难词汇
筛选条件：deck:"IELTS Vocabulary" (tag:#difficult OR tag:leech)
卡片数量：50
排序：按间隔（最久未复习优先）
```

**场景3：主题专项复习**
```
创建筛选牌组：自然地理专项
筛选条件：deck:"IELTS Vocabulary" tag:#自然地理
卡片数量：100
排序：按添加顺序
```

**操作步骤**：
1. 点击底部 **创建牌组**
2. 选择 **筛选牌组**
3. 输入筛选条件
4. 设置卡片数量和排序方式
5. 点击 **构建**

### 2. 批量编辑技巧

**安装插件**：Advanced Browser

**常用批量操作**：

**批量添加标签**：
1. 在浏览器中筛选卡片（如：`deck:"IELTS Vocabulary" added:7`）
2. 全选（Ctrl+A）
3. 右键 → **批量添加标签** → 输入 `#week1`

**批量修改字段**：
1. 筛选需要修改的卡片
2. 选中卡片
3. 右键 → **批量编辑**
4. 选择字段和修改方式（替换、追加、删除）

**批量重置进度**：
1. 筛选卡片（如：`tag:leech`）
2. 选中卡片
3. 右键 → **重新安排** → **放入学习队列**

### 3. 使用子牌组分类

将词汇按主题分成子牌组，便于分类学习。

**结构示例**：
```
IELTS Vocabulary
├── 01_自然地理
├── 02_学校教育
├── 03_社会经济
├── 04_科学技术
└── ...
```

**优点**：
- 可以单独学习某个主题
- 统计数据更清晰
- 便于调整不同主题的学习节奏

**创建方法**：
1. 在浏览器中筛选某个分类：`Category:自然地理`
2. 全选卡片
3. 右键 → **更改牌组** → 选择 `IELTS Vocabulary::01_自然地理`

### 4. 自定义快捷键

提高复习效率的快捷键设置。

**推荐设置**：
- **再来一次**：1
- **困难**：2
- **一般**：3（空格）
- **简单**：4
- **暂停卡片**：@
- **标记**：*
- **编辑**：E

**修改方法**：
1. 工具 → 首选项 → 快捷键
2. 找到对应操作
3. 点击修改

### 5. 利用统计数据优化学习

**关键指标**：

**保留率（Retention）**：
- 目标：85-90%
- 查看：牌组 → 统计 → 答案按钮
- 低于80%：说明学习节奏太快，需要减少新词或增加复习

**成熟度（Maturity）**：
- 年轻卡片：间隔<21天
- 成熟卡片：间隔≥21天
- 目标：逐步提高成熟卡片比例

**每日学习时间**：
- 查看：统计 → 今日学习
- 目标：40-60分钟
- 超过90分钟：需要调整学习量

**预测功能**：
- 安装 **Anki Simulator** 插件
- 预测未来30/60/90天的复习负担
- 根据预测调整每天新词数量

### 6. 使用标记系统

标记（Mark）可以临时标注需要特别关注的卡片。

**应用场景**：
- 复习时遇到的疑难卡片
- 需要补充内容的卡片
- 发音特别容易错的卡片

**使用方法**：
- 复习时按 `*` 键标记
- 浏览器中筛选：`tag:marked`
- 处理完后取消标记

### 7. 导出和备份

**定期备份**：

**方法1：导出牌组**
```
文件 → 导出
格式：Anki牌组包（.apkg）
包含：✓ 包含媒体文件
✓ 包含学习进度
```

**方法2：备份整个配置文件**
```
找到Anki数据文件夹：
Windows: C:\Users\[用户名]\AppData\Roaming\Anki2\
Mac: ~/Library/Application Support/Anki2/

复制整个文件夹到云盘或移动硬盘
```

**建议**：
- 每周备份一次
- 重要节点（如考前）额外备份
- 使用云同步（AnkiWeb）作为辅助

---

## 十一、学习资源推荐

### 1. Anki官方资源

**官方网站**：
- Anki官网：https://apps.ankiweb.net
- AnkiWeb（在线同步）：https://ankiweb.net
- 官方文档：https://docs.ankiweb.net

**官方论坛**：
- https://forums.ankiweb.net
- 可以找到大量插件和使用技巧

### 2. 推荐书籍

**《Fluent Forever》** - Gabriel Wyner
- 介绍如何使用SRS系统高效学习语言
- 包含大量记忆技巧和Anki使用方法

**《Make It Stick》** - Peter C. Brown
- 科学的学习方法
- 解释间隔重复的认知科学原理

### 3. 在线教程

**YouTube频道**：
- **The AnKing**：医学生Anki使用，但技巧通用
- **Matt vs Japan**：语言学习和Anki技巧
- **Zach Highley**：Anki进阶教程

**中文资源**：
- 知乎专栏：搜索"Anki"
- B站UP主：搜索"Anki教程"
- 少数派：有多篇Anki使用文章

### 4. 推荐插件

**必装插件**：
1. **Review Heatmap** - 学习进度可视化
2. **Advanced Browser** - 增强搜索功能
3. **AwesomeTTS** - 自动生成发音
4. **Image Occlusion Enhanced** - 图片遮挡记忆

**进阶插件**：
5. **Anki Simulator** - 预测复习负担
6. **Batch Editing** - 批量编辑卡片
7. **Frozen Fields** - 冻结字段
8. **Speed Focus Mode** - 限时答题模式
9. **Customize Keyboard Shortcuts** - 自定义快捷键
10. **Hierarchical Tags** - 层级标签管理

**插件安装**：
1. 工具 → 插件 → 获取插件
2. 输入插件代码（在AnkiWeb插件页面找到）
3. 重启Anki

### 5. 雅思学习资源

**词汇书籍**：
- 《剑桥雅思词汇精典》
- 《雅思词汇词根+联想记忆法》
- 《Word Power Made Easy》（英文原版）

**在线词典**：
- Cambridge Dictionary：https://dictionary.cambridge.org
- Oxford Learner's Dictionary：https://www.oxfordlearnersdictionaries.com
- Merriam-Webster：https://www.merriam-webster.com

**语料库**：
- COCA（美国当代英语语料库）：https://www.english-corpora.org/coca/
- 可以查看单词的真实使用场景

### 6. 社区和交流

**Reddit社区**：
- r/Anki：Anki使用技巧交流
- r/IELTS：雅思备考交流

**Discord服务器**：
- The AnKing Discord：活跃的Anki社区
- 可以获得实时帮助

**微信/QQ群**：
- 搜索"Anki学习群"或"雅思备考群"
- 可以交流经验、分享资源

### 7. 移动端App

**iOS**：
- **AnkiMobile**（付费，$24.99）
  - 官方应用，功能完整
  - 支持所有桌面端功能
  - 购买支持Anki开发

**Android**：
- **AnkiDroid**（免费）
  - 开源应用
  - 功能与桌面端基本一致
  - 支持插件

**使用建议**：
- 利用碎片时间（通勤、排队）复习
- 桌面端学习新词，移动端复习
- 及时同步，保持进度一致

---

## 十二、总结与建议

### 核心要点回顾

1. **卡片设计**：
   - 14个字段涵盖单词学习的所有维度
   - 正向和反向卡片结合，全面掌握
   - 图片、音频、词根词缀多维度辅助记忆

2. **数据处理**：
   - 自动化脚本处理词汇数据
   - API获取音标、同义词、反义词
   - AI翻译例句并高亮关键词
   - 音频切割脚本处理现有音频资源

3. **学习算法**：
   - 针对一年学习计划优化参数
   - 每天10-12个新词，可持续学习
   - 三阶段学习策略，循序渐进
   - 关注保留率、复习负担等关键指标

4. **学习技巧**：
   - 利用标签系统分类管理
   - 使用筛选牌组针对性复习
   - 定期复盘，调整学习策略
   - 结合移动端，充分利用碎片时间

### 成功的关键因素

**1. 坚持每天学习**
- 固定学习时间（如每天早上8点）
- 即使很忙，也要完成最低限度的复习
- 使用Review Heatmap插件激励自己

**2. 及时复习**
- 不要积压到期卡片
- 复习优先于学习新词
- 积压超过50张时暂停新词

**3. 主动调整**
- 根据保留率调整学习节奏
- 关注水蛭卡片，改进学习方法
- 定期回顾统计数据

**4. 多维度记忆**
- 不要只看单词和释义
- 利用词根词缀理解构词
- 在例句场景中记忆单词
- 使用图片建立视觉联想

**5. 实战应用**
- 在阅读中遇到学过的单词时，回忆其用法
- 在写作中主动使用学过的单词
- 参加雅思模拟考试，检验学习效果

### 常见陷阱与避免方法

**陷阱1：贪多求快**
- 问题：每天学习太多新词，导致复习负担过重
- 避免：严格控制每天新词数量（10-12个）

**陷阱2：只学不复习**
- 问题：只关注学习新词，忽视复习
- 避免：复习优先，确保保留率>85%

**陷阱3：机械记忆**
- 问题：只记单词和释义，不理解用法
- 避免：重视例句、词根词缀、同义词辨析

**陷阱4：中断学习**
- 问题：学习几天后中断，积压大量卡片
- 避免：养成习惯，使用提醒功能

**陷阱5：过度依赖Anki**
- 问题：只在Anki中学习，不在实际场景中应用
- 避免：结合阅读、写作、听力练习

### 一年学习路线图

**第1-3个月：建立基础**
- 目标：学习900-1080个单词
- 重点：高频词汇、基础分类
- 策略：专注正向卡片，建立学习习惯
- 里程碑：完成前5个主题分类

**第4-6个月：稳步推进**
- 目标：累计学习1800-2160个单词
- 重点：中频词汇、专业分类
- 策略：引入反向卡片，强化记忆
- 里程碑：完成前10个主题分类

**第7-9个月：全面覆盖**
- 目标：累计学习2700-3240个单词
- 重点：低频词汇、剩余分类
- 策略：保持学习节奏，关注水蛭卡片
- 里程碑：完成所有主题分类

**第10-12个月：冲刺巩固**
- 目标：完成所有单词，全面复习
- 重点：查漏补缺，实战应用
- 策略：减少新词，增加复习，模拟考试
- 里程碑：保留率>90%，准备考试

### 最后的话

学习雅思词汇是一个长期的过程，需要耐心和坚持。Anki是一个强大的工具，但工具本身不能保证成功，关键在于：

1. **科学的方法**：遵循记忆规律，使用间隔重复
2. **持续的努力**：每天坚持，积少成多
3. **灵活的调整**：根据实际情况优化学习策略
4. **实战的应用**：在真实场景中使用学过的单词

记住：**学习不是冲刺，而是马拉松**。保持稳定的节奏，享受学习的过程，一年后你会看到显著的进步。

祝你学习顺利，雅思考试取得好成绩！🎉

---

**文档版本**：v1.0  
**最后更新**：2026-05-19  
**作者**：Claude Opus 4.7  
**许可**：本文档可自由使用和分享

---
