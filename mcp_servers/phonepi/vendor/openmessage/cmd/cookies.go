package cmd

import (
	"encoding/json"
	"fmt"
	"net/http"
	"regexp"
	"strings"
)

var requiredGoogleCookies = []string{"SID", "HSID", "SSID", "OSID", "APISID", "SAPISID"}

// ParseGoogleCookiesInput accepts a JSON object or a browser cURL command.
func ParseGoogleCookiesInput(raw string) (map[string]string, error) {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return nil, fmt.Errorf("empty cookie input")
	}
	if strings.HasPrefix(raw, "{") {
		return parseCookiesJSON(raw)
	}
	if strings.Contains(strings.ToLower(raw), "curl") || strings.Contains(strings.ToLower(raw), "cookie:") {
		return parseCookiesFromCurl(raw)
	}
	return nil, fmt.Errorf("paste JSON cookies or a cURL command copied from Firefox devtools")
}

func parseCookiesJSON(raw string) (map[string]string, error) {
	var cookies map[string]string
	if err := json.Unmarshal([]byte(raw), &cookies); err != nil {
		return nil, fmt.Errorf("invalid JSON cookies: %w", err)
	}
	return validateGoogleCookies(cookies)
}

func parseCookiesFromCurl(raw string) (map[string]string, error) {
	normalized := normalizeCurl(raw)
	cookieLine, ok := extractCookieHeader(normalized)
	if !ok {
		return nil, fmt.Errorf("no Cookie header found in cURL command")
	}
	parsed, err := http.ParseCookie(cookieLine)
	if err != nil {
		return nil, fmt.Errorf("parse Cookie header: %w", err)
	}
	cookies := make(map[string]string, len(parsed))
	for _, c := range parsed {
		cookies[c.Name] = c.Value
	}
	return validateGoogleCookies(cookies)
}

func normalizeCurl(raw string) string {
	raw = strings.ReplaceAll(raw, "^\r\n", " ")
	raw = strings.ReplaceAll(raw, "^\n", " ")
	raw = strings.ReplaceAll(raw, "^", "")
	raw = strings.ReplaceAll(raw, "\\\r\n", " ")
	raw = strings.ReplaceAll(raw, "\\\n", " ")
	return raw
}

var cookieHeaderRE = regexp.MustCompile(`(?i)(?:-H|--header)\s+"([^"]*cookie:\s*[^"]+)"`)

func extractCookieHeader(normalized string) (string, bool) {
	if m := cookieHeaderRE.FindStringSubmatch(normalized); len(m) == 2 {
		line := strings.TrimSpace(m[1])
		if idx := strings.Index(strings.ToLower(line), "cookie:"); idx >= 0 {
			line = strings.TrimSpace(line[idx+len("cookie:"):])
		}
		return line, line != ""
	}
	lower := strings.ToLower(normalized)
	idx := strings.Index(lower, "cookie:")
	if idx < 0 {
		return "", false
	}
	rest := normalized[idx+len("cookie:"):]
	rest = strings.TrimSpace(rest)
	if end := strings.Index(rest, `"`); end >= 0 {
		rest = rest[:end]
	}
	return strings.TrimSpace(rest), rest != ""
}

func validateGoogleCookies(cookies map[string]string) (map[string]string, error) {
	if len(cookies) == 0 {
		return nil, fmt.Errorf("no cookies found")
	}
	var missing []string
	for _, name := range requiredGoogleCookies {
		if strings.TrimSpace(cookies[name]) == "" {
			missing = append(missing, name)
		}
	}
	if len(missing) > 0 {
		return nil, fmt.Errorf("missing required cookies: %s", strings.Join(missing, ", "))
	}
	return cookies, nil
}
