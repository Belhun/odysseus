package cmd

import (
	"strings"
	"testing"
)

func TestParseGoogleCookiesJSON(t *testing.T) {
	raw := `{"SID":"a","HSID":"b","SSID":"c","OSID":"d","APISID":"e","SAPISID":"f"}`
	got, err := ParseGoogleCookiesInput(raw)
	if err != nil {
		t.Fatal(err)
	}
	if got["SID"] != "a" || got["OSID"] != "d" {
		t.Fatalf("unexpected cookies: %#v", got)
	}
}

func TestParseGoogleCookiesFromWindowsCurl(t *testing.T) {
	raw := `curl.exe ^"https://messages.google.com/web/config?pli=1^" ^
  -H ^"Cookie: SID=sidval; HSID=hsidval; SSID=ssidval; OSID=osidval; APISID=apisidval; SAPISID=sapisidval^" ^
  -H ^"User-Agent: Mozilla/5.0^"`
	got, err := ParseGoogleCookiesInput(raw)
	if err != nil {
		t.Fatal(err)
	}
	for _, name := range requiredGoogleCookies {
		if got[name] == "" {
			t.Fatalf("missing %s in %#v", name, got)
		}
	}
	if got["SID"] != "sidval" {
		t.Fatalf("SID=%q", got["SID"])
	}
}

func TestParseGoogleCookiesMissingRequired(t *testing.T) {
	_, err := ParseGoogleCookiesInput(`{"SID":"only"}`)
	if err == nil || !strings.Contains(err.Error(), "missing required cookies") {
		t.Fatalf("expected missing cookie error, got %v", err)
	}
}
