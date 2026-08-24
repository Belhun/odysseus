package cmd

import (
	"encoding/json"
	"os"
	"path/filepath"

	"github.com/maxghenis/openmessage/internal/app"
)

// PairState is written to pair-status.json for Odysseus Settings → Phone.
type PairState struct {
	State string `json:"state"`
	URL   string `json:"url,omitempty"`
	Emoji string `json:"emoji,omitempty"`
	Mode  string `json:"mode,omitempty"`
	Error string `json:"error,omitempty"`
}

func writePairState(state PairState) {
	dataDir := app.DefaultDataDir()
	_ = os.MkdirAll(dataDir, 0700)
	if state.URL != "" {
		_ = os.WriteFile(filepath.Join(dataDir, "qr-url.txt"), []byte(state.URL+"\n"), 0o600)
	}
	payload, err := json.Marshal(state)
	if err != nil {
		return
	}
	_ = os.WriteFile(filepath.Join(dataDir, "pair-status.json"), payload, 0o600)
}
