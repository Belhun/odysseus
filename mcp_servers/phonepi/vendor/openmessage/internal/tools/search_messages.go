package tools

import (
	"context"
	"fmt"
	"strings"
	"time"

	"github.com/mark3labs/mcp-go/mcp"
	"github.com/mark3labs/mcp-go/server"

	"github.com/maxghenis/openmessage/internal/app"
)

func searchMessagesTool() mcp.Tool {
	return mcp.NewTool("search_messages",
		mcp.WithDescription("Search messages by text content across all conversations. Default limit is 20; 200 is the soft cap for routine queries — pass a higher limit when the user explicitly asks for more."),
		mcp.WithString("query", mcp.Required(), mcp.Description("Search text")),
		mcp.WithString("phone_number", mcp.Description("Filter by phone number")),
		mcp.WithNumber("limit", mcp.Description("Maximum results (default 20). 200 is a soft cap for routine use; higher values are allowed when explicitly requested.")),
		mcp.WithReadOnlyHintAnnotation(true),
		mcp.WithDestructiveHintAnnotation(false),
	)
}

func searchMessagesHandler(a *app.App) server.ToolHandlerFunc {
	return func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		args := req.GetArguments()
		query := strArg(args, "query")
		if query == "" {
			return errorResult("query is required"), nil
		}
		phone := strArg(args, "phone_number")
		limit, exceedsSoftCap, limitErr := messageLimitArg(args, "limit", 20)
		if limitErr != "" {
			return errorResult(limitErr), nil
		}

		msgs, err := a.Store.SearchMessages(query, phone, limit)
		if err != nil {
			return errorResult(fmt.Sprintf("search failed: %v", err)), nil
		}

		if len(msgs) == 0 {
			return textResult(fmt.Sprintf("No messages found matching '%s'.", query)), nil
		}

		var sb strings.Builder
		sb.WriteString(messagePreamble)
		fmt.Fprintf(&sb, "Found %d messages matching '%s':\n\n", len(msgs), query)
		for _, m := range msgs {
			ts := time.UnixMilli(m.TimestampMS).Format(time.RFC3339)
			direction := "←"
			if m.IsFromMe {
				direction = "→"
			}
			sender := m.SenderName
			if sender == "" {
				sender = m.SenderNumber
			}
			if sender == "" {
				sender = "Unknown"
			}
			display := formatMessageBody(m.Body, m.MediaID, m.MimeType, m.MessageID)
			fmt.Fprintf(&sb, "[%s] %s %s (conv: %s): «%s»\n", ts, direction, sender, m.ConversationID, display)
		}
		appendMessageLimitNotes(&sb, limit, len(msgs), exceedsSoftCap)
		return textResult(sb.String()), nil
	}
}
