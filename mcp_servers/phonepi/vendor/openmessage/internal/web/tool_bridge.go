package web

import (
	"encoding/json"
	"net/http"

	"github.com/maxghenis/openmessage/internal/app"
	"github.com/maxghenis/openmessage/internal/tools"
)

type toolCallRequest struct {
	Tool      string         `json:"tool"`
	Arguments map[string]any `json:"arguments"`
}

type toolCallResponse struct {
	Text    string `json:"text"`
	IsError bool   `json:"isError"`
}

// RegisterToolBridge mounts POST /api/tool for PhonePi Node MCP integration.
func RegisterToolBridge(mux *http.ServeMux, a *app.App) {
	mux.HandleFunc("/api/tool", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			httpError(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		var req toolCallRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			httpError(w, "invalid JSON: "+err.Error(), http.StatusBadRequest)
			return
		}
		if req.Tool == "" {
			httpError(w, "tool is required", http.StatusBadRequest)
			return
		}

		result, err := tools.Execute(r.Context(), a, req.Tool, req.Arguments)
		if err != nil {
			httpError(w, err.Error(), http.StatusInternalServerError)
			return
		}

		writeJSON(w, toolCallResponse{
			Text:    tools.ResultText(result),
			IsError: result != nil && result.IsError,
		})
	})

	mux.HandleFunc("/api/tools", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			httpError(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		writeJSON(w, map[string]any{
			"tools": tools.ToolNames,
		})
	})
}
