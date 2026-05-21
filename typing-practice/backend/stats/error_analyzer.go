package stats

import "strings"

func AnalyzeErrorType(expected, input string) string {
	// 错误类型用于“错误类型分析饼图”。当前规则比较轻量：
	// 空输入算 skipped，编辑距离小的算拼写相关，距离很大算 completely_wrong。
	input = strings.ToLower(strings.TrimSpace(input))
	if input == "" {
		return "skipped"
	}

	expected = strings.ToLower(strings.TrimSpace(expected))
	if expected == input {
		return ""
	}

	distance := levenshteinDistance(expected, input)
	if distance == 1 {
		if len([]rune(input)) < len([]rune(expected)) {
			return "missing_letter"
		}
		if len([]rune(input)) > len([]rune(expected)) {
			return "extra_letter"
		}
		return "spelling"
	}
	if distance <= 3 {
		return "spelling"
	}
	return "completely_wrong"
}

func levenshteinDistance(left, right string) int {
	// 标准 Levenshtein 编辑距离。使用 rune 而不是 byte，避免非 ASCII 字符长度计算出错。
	a := []rune(left)
	b := []rune(right)
	if len(a) == 0 {
		return len(b)
	}
	if len(b) == 0 {
		return len(a)
	}

	previous := make([]int, len(b)+1)
	current := make([]int, len(b)+1)
	for j := range previous {
		previous[j] = j
	}

	for i := 1; i <= len(a); i++ {
		current[0] = i
		for j := 1; j <= len(b); j++ {
			cost := 0
			if a[i-1] != b[j-1] {
				cost = 1
			}
			current[j] = minInt(
				current[j-1]+1,
				previous[j]+1,
				previous[j-1]+cost,
			)
		}
		previous, current = current, previous
	}

	return previous[len(b)]
}

func minInt(values ...int) int {
	minimum := values[0]
	for _, value := range values[1:] {
		if value < minimum {
			minimum = value
		}
	}
	return minimum
}
