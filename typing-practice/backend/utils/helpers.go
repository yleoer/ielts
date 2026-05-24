package utils

func ClampLimit(value, defaultValue, maxValue int) int {
	// 防止用户通过 query 参数一次拉取过多单词。
	if value <= 0 {
		return defaultValue
	}
	if maxValue > 0 && value > maxValue {
		return maxValue
	}
	return value
}
