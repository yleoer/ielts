package utils

import "strings"

func CheckSpelling(expected, input string) bool {
	// 基础拼写检查：忽略首尾空格和大小写。
	// 如果单词字段是 "analyse / analyze" 这种变体，任意一个变体都算正确。
	expected = strings.ToLower(strings.TrimSpace(expected))
	input = strings.ToLower(strings.TrimSpace(input))
	if expected == input {
		return true
	}

	for _, candidate := range strings.Split(expected, "/") {
		if strings.TrimSpace(candidate) == input {
			return true
		}
	}

	return false
}

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
