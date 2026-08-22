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

func getConversationTool() mcp.Tool {
	return mcp.NewTool("get_conversation",
		mcp.WithDescription("Get messages in a specific conversation by ID. Default limit is 50; 200 is the soft cap for routine queries — pass a higher limit when the user explicitly asks for more."),
		mcp.WithString("conversation_id", mcp.Required(), mcp.Description("The conversation ID")),
		mcp.WithNumber("limit", mcp.Description("Maximum messages to return (default 50). 200 is a soft cap for routine use; higher values are allowed when explicitly requested.")),
		mcp.WithReadOnlyHintAnnotation(true),
		mcp.WithDestructiveHintAnnotation(false),
	)
}

func getConversationHandler(a *app.App) server.ToolHandlerFunc {
	return func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		args := req.GetArguments()
		convID := strArg(args, "conversation_id")
		if convID == "" {
			return errorResult("conversation_id is required"), nil
		}
		limit, exceedsSoftCap, limitErr := messageLimitArg(args, "limit", 50)
		if limitErr != "" {
			return errorResult(limitErr), nil
		}

		msgs, err := a.Store.GetMessagesByConversation(convID, limit)
		if err != nil {
			return errorResult(fmt.Sprintf("query failed: %v", err)), nil
		}

		if len(msgs) == 0 {
			return textResult("No messages found in this conversation."), nil
		}

		var sb strings.Builder
		// Show conversation info
		conv, err := a.Store.GetConversation(convID)
		if err == nil && conv != nil {
			fmt.Fprintf(&sb, "Conversation: %s (ID: %s)\n", conv.Name, conv.ConversationID)
			if conv.IsGroup {
				sb.WriteString("Type: Group\n")
			}
			sb.WriteString("---\n")
		}

		sb.WriteString(messagePreamble)
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
			fmt.Fprintf(&sb, "[%s] %s %s: «%s»\n", ts, direction, sender, display)
		}
		appendMessageLimitNotes(&sb, limit, len(msgs), exceedsSoftCap)
		return textResult(sb.String()), nil
	}
}
