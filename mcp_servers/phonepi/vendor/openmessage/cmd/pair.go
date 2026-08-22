package cmd

import (
	"encoding/json"
	"fmt"
	"os"
	"os/signal"
	"path/filepath"
	"sync"
	"syscall"
	"time"

	"github.com/mdp/qrterminal/v3"
	"github.com/rs/zerolog"
	"go.mau.fi/mautrix-gmessages/pkg/libgm"
	"go.mau.fi/mautrix-gmessages/pkg/libgm/events"
	"go.mau.fi/mautrix-gmessages/pkg/libgm/gmproto"

	"github.com/maxghenis/openmessage/internal/app"
	"github.com/maxghenis/openmessage/internal/client"
)

const maxQRRefreshes = 5

func RunPair(logger zerolog.Logger) error {
	dataDir := app.DefaultDataDir()
	if err := os.MkdirAll(dataDir, 0700); err != nil {
		return fmt.Errorf("create data dir: %w", err)
	}

	sessionPath := dataDir + "/session.json"
	writePairState("waiting", "")

	cli := client.NewForPairing(logger)

	var pairDone sync.WaitGroup
	pairDone.Add(1)
	var pairErr error

	pairCB := func(data *gmproto.PairedData) {
		defer pairDone.Done()

		logger.Info().
			Str("phone_id", data.GetMobile().GetSourceID()).
			Msg("Pairing successful!")

		sessionData, err := cli.SessionData()
		if err != nil {
			pairErr = fmt.Errorf("get session data: %w", err)
			return
		}
		if err := client.SaveSession(sessionPath, sessionData); err != nil {
			pairErr = fmt.Errorf("save session: %w", err)
			return
		}
		fmt.Println("\nSession saved to", sessionPath)
		writePairState("paired", "")
		if hint := os.Getenv("OPENMESSAGES_SERVE_HINT"); hint != "" {
			fmt.Println(hint)
		} else {
			fmt.Println("You can now run: openmessage serve")
		}
	}
	cli.GM.PairCallback.Store(&pairCB)

	// Handle Ctrl+C
	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
	go func() {
		<-sigCh
		fmt.Println("\nAborted.")
		cli.GM.Disconnect()
		os.Exit(1)
	}()

	// Start login - shows first QR code
	qrURL, err := cli.GM.StartLogin()
	if err != nil {
		return fmt.Errorf("start login: %w", err)
	}
	displayQR(qrURL)

	// Auto-refresh QR codes
	go func() {
		for i := 0; i < maxQRRefreshes; i++ {
			time.Sleep(30 * time.Second)
			newURL, err := cli.GM.RefreshPhoneRelay()
			if err != nil {
				logger.Warn().Err(err).Msg("Failed to refresh QR code")
				return
			}
			fmt.Println("\n--- QR code refreshed ---")
			displayQR(newURL)
		}
	}()

	// Also set event handler for non-pair events during pairing
	cli.GM.SetEventHandler(func(evt any) {
		switch evt := evt.(type) {
		case *events.ListenFatalError:
			logger.Error().Err(evt.Error).Msg("Fatal error during pairing")
		case *events.PairSuccessful:
			// Handled by PairCallback
		default:
			logger.Debug().Type("type", evt).Msg("Event during pairing")
		}
	})

	pairDone.Wait()
	cli.GM.Disconnect()
	return pairErr
}

func displayQR(url string) {
	fmt.Println("\nScan this QR code with Google Messages:")
	fmt.Println("(Settings > Device pairing > Pair a device)")
	fmt.Println()
	qrterminal.GenerateHalfBlock(url, qrterminal.L, os.Stdout)
	fmt.Println()
	fmt.Println("URL:", url)
	writePairState("waiting", url)
}

func writePairState(state string, url string) {
	// Odysseus Settings → Phone reads these files. Pair stdout is often
	// block-buffered when the process is not a TTY, so the UI cannot
	// scrape the QR art from stdout.
	dataDir := app.DefaultDataDir()
	_ = os.MkdirAll(dataDir, 0700)
	if url != "" {
		_ = os.WriteFile(filepath.Join(dataDir, "qr-url.txt"), []byte(url+"\n"), 0o600)
	}
	payload, err := json.Marshal(map[string]string{"state": state, "url": url})
	if err != nil {
		return
	}
	_ = os.WriteFile(filepath.Join(dataDir, "pair-status.json"), payload, 0o600)
}

// Ensure PairCallback type matches what libgm expects
var _ = (*libgm.Client)(nil)
