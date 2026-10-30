"""Read-only vocabulary grouping shared by progress and detail queries."""

CEFR_LEVELS = {"A1": "入门", "A2": "基础", "B1": "进阶", "B2": "中高级", "C1": "高级", "C2": "熟练"}
UNKNOWN_CEFR = "未分级"
UNKNOWN_TOPIC = "未分类"


def group_value(word, dimension):
    if dimension == "cefr":
        value = word.get("cefr", "").strip().upper()
        return value if value in CEFR_LEVELS else UNKNOWN_CEFR
    if dimension == "topic":
        return word.get("category", "").strip() or UNKNOWN_TOPIC
    raise ValueError("无效的词库分组")


def empty_group(value, label=None):
    return {"value": value, "label": label or value, "total": 0, "learned": 0,
            "new": 0, "learning": 0, "mastered": 0}


def progress(entries):
    levels = {value: empty_group(value, label) for value, label in CEFR_LEVELS.items()}
    topics = {}
    overall = empty_group("all")
    for word in entries:
        level, topic = group_value(word, "cefr"), group_value(word, "topic")
        for group in (overall, levels.setdefault(level, empty_group(level)),
                      topics.setdefault(topic, empty_group(topic))):
            group["total"] += 1
            group[word["status"]] += 1
            group["learned"] += word["status"] != "new"
    return {"overall": overall, "levels": list(levels.values()), "topics": list(topics.values())}


def word_sort_key(word):
    """Put practiced words first, prioritizing a smoothed lifetime error rate."""
    total = word.get("total_attempts", 0)
    errors = total - word.get("correct_attempts", 0)
    return (total == 0, -(errors + 1) / (total + 2), -errors,
            word["word"].casefold(), word["source_id"])


def word_page(entries, dimension, value, status, offset, limit):
    if dimension not in {"cefr", "topic"}:
        raise ValueError("无效的词库分组")
    if not value or status not in {"all", "new", "learning", "mastered"}:
        raise ValueError("无效的词库筛选")
    matches = [word for word in entries if group_value(word, dimension) == value
               and (status == "all" or word["status"] == status)]
    matches.sort(key=word_sort_key)
    items = matches[offset:offset + limit]
    return {"items": items, "total": len(matches),
            "next_offset": offset + len(items) if offset + len(items) < len(matches) else None}
