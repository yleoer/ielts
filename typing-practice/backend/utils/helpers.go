package utils

import "strings"

func CheckSpelling(expected, input string) bool {
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
	if value <= 0 {
		return defaultValue
	}
	if maxValue > 0 && value > maxValue {
		return maxValue
	}
	return value
}
