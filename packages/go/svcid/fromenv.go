// FromEnv returns the secret named name. When the environment variable
// name+"_FILE" is set (not empty), it returns the content of that file with
// trailing '\r' and '\n' characters removed. Otherwise it returns the value of
// name, which may be "". It returns an error when both variables are set or
// when the file cannot be read.
package svcid

import (
	"fmt"
	"os"
	"strings"
)

func FromEnv(name string) (string, error) {
	fileVar := name + "_FILE"
	filePath := os.Getenv(fileVar)
	if filePath == "" {
		return os.Getenv(name), nil
	}
	if os.Getenv(name) != "" {
		return "", fmt.Errorf("%s and %s are both set; set only one", name, fileVar)
	}
	data, err := os.ReadFile(filePath)
	if err != nil {
		return "", fmt.Errorf("%s: cannot read %q: %w", fileVar, filePath, err)
	}
	return strings.TrimRight(string(data), "\r\n"), nil
}
