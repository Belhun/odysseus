package tools

import (
	"context"
	"fmt"
	"strings"

	"github.com/mark3labs/mcp-go/mcp"
	"github.com/mark3labs/mcp-go/server"
	"go.mau.fi/mautrix-gmessages/pkg/libgm/gmproto"

	"github.com/maxghenis/openmessage/internal/app"
)

func reactToMessageTool() mcp.Tool {
	return mcp.NewTool("react_to_message",
		mcp.WithDescription("Add, remove, or switch an emoji reaction on a message"),
		mcp.WithString("message_id", mcp.Required(), mcp.Description("Message ID to react to")),
		mcp.WithString("emoji", mcp.Required(), mcp.Description("Emoji character (e.g. 👍)")),
		mcp.WithString("conversation_id", mcp.Description("Conversation ID (helps pick the correct SIM)")),
		mcp.WithString("action", mcp.Description("add, remove, or switch (default add)")),
		mcp.WithDestructiveHintAnnotation(false),
	)
}

func reactToMessageHandler(a *app.App) server.ToolHandlerFunc {
	return func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		args := req.GetArguments()
		messageID := strArg(args, "message_id")
		emoji := strArg(args, "emoji")
		conversationID := strArg(args, "conversation_id")
		action := strArg(args, "action")

		if messageID == "" {
			return errorResult("message_id is required"), nil
		}
		if emoji == "" {
			return errorResult("emoji is required"), nil
		}
		if a.Client == nil {
			return errorResult("not connected to Google Messages"), nil
		}

		var sim *gmproto.SIMPayload
		if conversationID != "" {
			if conv, err := a.Client.GM.GetConversation(conversationID); err == nil {
				if sc := conv.GetSimCard(); sc != nil {
					sim = sc.GetSIMData().GetSIMPayload()
				}
			}
		}

		payload := buildReactionPayload(messageID, emoji, action, sim)
		resp, err := a.Client.GM.SendReaction(payload)
		if err != nil {
			return errorResult(fmt.Sprintf("send reaction: %v", err)), nil
		}
		if !resp.GetSuccess() {
			return errorResult("reaction was not accepted by Google Messages"), nil
		}
		return textResult(fmt.Sprintf("Reaction %s on message %s", emoji, messageID)), nil
	}
}

func buildReactionPayload(messageID, emoji, action string, sim *gmproto.SIMPayload) *gmproto.SendReactionRequest {
	var a gmproto.SendReactionRequest_Action
	switch strings.ToLower(action) {
	case "remove":
		a = gmproto.SendReactionRequest_REMOVE
	case "switch":
		a = gmproto.SendReactionRequest_SWITCH
	default:
		a = gmproto.SendReactionRequest_ADD
	}
	return &gmproto.SendReactionRequest{
		MessageID:    messageID,
		ReactionData: gmproto.MakeReactionData(emoji),
		Action:       a,
		SIMPayload:   sim,
	}
}
