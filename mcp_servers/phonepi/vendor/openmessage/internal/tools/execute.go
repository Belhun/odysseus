package tools

import (
	"context"
	"fmt"

	"github.com/mark3labs/mcp-go/mcp"

	"github.com/maxghenis/openmessage/internal/app"
)

// ToolNames lists MCP tools exposed by openmessage (for HTTP bridge discovery).
var ToolNames = []string{
	"get_messages",
	"get_conversation",
	"search_messages",
	"send_message",
	"list_conversations",
	"list_contacts",
	"get_status",
	"draft_message",
	"download_media",
	"react_to_message",
}

// Execute runs a named MCP tool handler against the openmessage app.
func Execute(ctx context.Context, a *app.App, toolName string, args map[string]any) (*mcp.CallToolResult, error) {
	if args == nil {
		args = map[string]any{}
	}
	req := mcp.CallToolRequest{
		Params: mcp.CallToolParams{
			Name:      toolName,
			Arguments: args,
		},
	}

	var handler func(context.Context, mcp.CallToolRequest) (*mcp.CallToolResult, error)
	switch toolName {
	case "get_messages":
		handler = getMessagesHandler(a)
	case "get_conversation":
		handler = getConversationHandler(a)
	case "search_messages":
		handler = searchMessagesHandler(a)
	case "send_message":
		handler = sendMessageHandler(a)
	case "list_conversations":
		handler = listConversationsHandler(a)
	case "list_contacts":
		handler = listContactsHandler(a)
	case "get_status":
		handler = getStatusHandler(a)
	case "draft_message":
		handler = draftMessageHandler(a)
	case "download_media":
		handler = downloadMediaHandler(a)
	case "react_to_message":
		handler = reactToMessageHandler(a)
	default:
		return errorResult(fmt.Sprintf("unknown tool: %s", toolName)), nil
	}
	return handler(ctx, req)
}

// ResultText extracts plain text from a tool result for JSON HTTP responses.
func ResultText(result *mcp.CallToolResult) string {
	if result == nil || len(result.Content) == 0 {
		return ""
	}
	if t, ok := mcp.AsTextContent(result.Content[0]); ok {
		return t.Text
	}
	return fmt.Sprint(result.Content[0])
}
