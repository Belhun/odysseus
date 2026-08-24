// PhonePi Google Messages bridge — thin wrapper around vendored openmessage.
//
// Build:  go build -o phonepi-gmessages.exe .
// Pair:   .\phonepi-gmessages.exe pair
// Serve:  .\phonepi-gmessages.exe serve
package main

import (
	"fmt"
	"os"
	"path/filepath"

	"github.com/rs/zerolog"

	"github.com/maxghenis/openmessage/cmd"
)

func init() {
	if os.Getenv("OPENMESSAGES_DATA_DIR") == "" {
		if dir := os.Getenv("PHONEPI_GMESSAGES_DATA_DIR"); dir != "" {
			os.Setenv("OPENMESSAGES_DATA_DIR", dir)
		} else {
			home, err := os.UserHomeDir()
			if err == nil {
				os.Setenv(
					"OPENMESSAGES_DATA_DIR",
					filepath.Join(home, ".local", "share", "phonepi-gmessages"),
				)
			}
		}
	}
	if os.Getenv("OPENMESSAGES_PORT") == "" {
		os.Setenv("OPENMESSAGES_PORT", "11042")
	}
	if os.Getenv("OPENMESSAGES_SERVE_HINT") == "" {
		os.Setenv("OPENMESSAGES_SERVE_HINT",
			"You can now run:\n"+
				"  From repo root: .\\serve-gmessages.ps1\n"+
				"  Or: .\\messages-bridge\\phonepi-gmessages.exe serve",
		)
	}
}

func main() {
	level := cmd.LogLevel()
	logger := zerolog.New(zerolog.ConsoleWriter{Out: os.Stderr}).
		With().Timestamp().Logger().Level(level)

	if len(os.Args) < 2 {
		printUsage()
		os.Exit(1)
	}

	var err error
	switch os.Args[1] {
	case "pair":
		err = cmd.RunPair(logger)
	case "pair-google":
		err = cmd.RunPairGoogle(logger)
	case "serve":
		err = cmd.RunServe(logger)
	case "send":
		if len(os.Args) < 4 {
			fmt.Fprintln(os.Stderr, "Usage: phonepi-gmessages send <conversation_id> <message>")
			os.Exit(1)
		}
		err = cmd.RunSend(logger, os.Args[2], os.Args[3])
	default:
		fmt.Fprintf(os.Stderr, "Unknown command: %s\n", os.Args[1])
		printUsage()
		os.Exit(1)
	}

	if err != nil {
		logger.Fatal().Err(err).Msg("Fatal error")
	}
}

func printUsage() {
	fmt.Fprintln(os.Stderr, "PhonePi Google Messages bridge (openmessage)")
	fmt.Fprintln(os.Stderr, "")
	fmt.Fprintln(os.Stderr, "Usage: phonepi-gmessages <command>")
	fmt.Fprintln(os.Stderr, "  pair         - Pair via QR code (legacy, US accounts)")
	fmt.Fprintln(os.Stderr, "  pair-google  - Pair via Google account cookies + phone emoji")
	fmt.Fprintln(os.Stderr, "  serve        - Start sync server + web UI + HTTP tool bridge")
	fmt.Fprintln(os.Stderr, "")
	fmt.Fprintln(os.Stderr, "Environment:")
	fmt.Fprintln(os.Stderr, "  PHONEPI_GMESSAGES_DATA_DIR  Session + SQLite (default %USERPROFILE%\\.local\\share\\phonepi-gmessages)")
	fmt.Fprintln(os.Stderr, "  OPENMESSAGES_PORT           HTTP port (default 11042)")
}
