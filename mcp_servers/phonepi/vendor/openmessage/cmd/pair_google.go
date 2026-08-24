package cmd

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"

	"github.com/rs/zerolog"
	"go.mau.fi/mautrix-gmessages/pkg/libgm/events"

	"github.com/maxghenis/openmessage/internal/app"
	"github.com/maxghenis/openmessage/internal/client"
)

const cookiesInputFile = "cookies-input.txt"

func RunPairGoogle(logger zerolog.Logger) error {
	dataDir := app.DefaultDataDir()
	if err := os.MkdirAll(dataDir, 0700); err != nil {
		return fmt.Errorf("create data dir: %w", err)
	}

	inputPath := filepath.Join(dataDir, cookiesInputFile)
	raw, err := os.ReadFile(inputPath)
	if err != nil {
		return fmt.Errorf("read %s: %w (paste cookies in Settings first)", cookiesInputFile, err)
	}
	defer os.Remove(inputPath)

	cookies, err := ParseGoogleCookiesInput(string(raw))
	if err != nil {
		writePairState(PairState{State: "error", Mode: "google", Error: err.Error()})
		return err
	}

	sessionPath := filepath.Join(dataDir, "session.json")
	writePairState(PairState{State: "starting", Mode: "google"})

	cli := client.NewForPairing(logger)
	cli.GM.AuthData.SetCookies(cookies)

	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go func() {
		<-sigCh
		cancel()
		cli.GM.Disconnect()
	}()

	if err := cli.GM.FetchConfig(ctx); err != nil {
		msg := fmt.Sprintf("Google config fetch failed: %v", err)
		writePairState(PairState{State: "error", Mode: "google", Error: msg})
		return fmt.Errorf("%s", msg)
	}

	cli.GM.SetEventHandler(func(evt any) {
		switch evt := evt.(type) {
		case *events.ListenFatalError:
			logger.Error().Err(evt.Error).Msg("Fatal error during Google pairing")
		default:
			logger.Debug().Type("type", evt).Msg("Event during Google pairing")
		}
	})

	err = cli.GM.DoGaiaPairing(ctx, func(emoji string) {
		logger.Info().Str("emoji", emoji).Msg("Tap this emoji on your phone")
		writePairState(PairState{State: "emoji_wait", Mode: "google", Emoji: emoji})
		fmt.Println("EMOJI:", emoji)
	})
	cli.GM.Disconnect()
	if err != nil {
		msg := gaiaPairingError(err)
		writePairState(PairState{State: "error", Mode: "google", Error: msg})
		return fmt.Errorf("%s", msg)
	}

	sessionData, err := cli.SessionData()
	if err != nil {
		writePairState(PairState{State: "error", Mode: "google", Error: err.Error()})
		return fmt.Errorf("get session data: %w", err)
	}
	if err := client.SaveSession(sessionPath, sessionData); err != nil {
		writePairState(PairState{State: "error", Mode: "google", Error: err.Error()})
		return fmt.Errorf("save session: %w", err)
	}

	writePairState(PairState{State: "paired", Mode: "google"})
	fmt.Println("Session saved to", sessionPath)
	if hint := os.Getenv("OPENMESSAGES_SERVE_HINT"); hint != "" {
		fmt.Println(hint)
	} else {
		fmt.Println("You can now run: openmessage serve")
	}
	return nil
}

func gaiaPairingError(err error) string {
	switch {
	case err == nil:
		return ""
	case err.Error() == "gaia pairing requires cookies":
		return "Google cookies missing or expired. Paste a fresh cURL from a Firefox private window."
	default:
		return err.Error()
	}
}

// WriteCookiesInput stores raw cookie input for pair-google.
func WriteCookiesInput(dataDir, raw string) error {
	if err := os.MkdirAll(dataDir, 0700); err != nil {
		return err
	}
	return os.WriteFile(filepath.Join(dataDir, cookiesInputFile), []byte(raw), 0o600)
}

// ReadPairStateJSON returns the current pair-status.json contents for tests.
func ReadPairStateJSON(dataDir string) (PairState, error) {
	b, err := os.ReadFile(filepath.Join(dataDir, "pair-status.json"))
	if err != nil {
		return PairState{}, err
	}
	var state PairState
	if err := json.Unmarshal(b, &state); err != nil {
		return PairState{}, err
	}
	return state, nil
}
