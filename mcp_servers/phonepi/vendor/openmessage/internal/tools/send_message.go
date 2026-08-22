package tools

import (
	"context"
	"fmt"
	"strings"
	"time"

	"github.com/mark3labs/mcp-go/mcp"
	"github.com/mark3labs/mcp-go/server"
	"go.mau.fi/mautrix-gmessages/pkg/libgm/gmproto"

	"github.com/maxghenis/openmessage/internal/app"
	"github.com/maxghenis/openmessage/internal/db"
)

func sendMessageTool() mcp.Tool {
	return mcp.NewTool("send_message",
		mcp.WithDescription("Send a text message (SMS/RCS) to a phone number. Returns delivery status from Google Messages; success means the bridge accepted the send, not merely that the RPC completed."),
		mcp.WithString("phone_number", mcp.Required(), mcp.Description("Recipient phone number with country code (e.g., +17605868615)")),
		mcp.WithString("message", mcp.Required(), mcp.Description("Message text to send")),
		mcp.WithString("conversation_id", mcp.Description("Optional existing conversation ID (helps dual-SIM routing; from list_conversations)")),
		mcp.WithDestructiveHintAnnotation(false),
		mcp.WithIdempotentHintAnnotation(false),
	)
}

func sendMessageHandler(a *app.App) server.ToolHandlerFunc {
	return func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		args := req.GetArguments()
		phone := normalizePhoneNumber(strArg(args, "phone_number"))
		message := strArg(args, "message")
		conversationID := strArg(args, "conversation_id")

		if phone == "" {
			return errorResult("phone_number is required"), nil
		}
		if message == "" {
			return errorResult("message is required"), nil
		}
		if a.Client == nil {
			return errorResult("not connected to Google Messages"), nil
		}

		var conv *gmproto.Conversation
		var err error

		if conversationID != "" {
			conv, err = a.Client.GM.GetConversation(conversationID)
			if err != nil {
				return errorResult(fmt.Sprintf("failed to load conversation %s: %v", conversationID, err)), nil
			}
		} else {
			convResp, convErr := a.Client.GM.GetOrCreateConversation(&gmproto.GetOrCreateConversationRequest{
				Numbers: []*gmproto.ContactNumber{{
					MysteriousInt: 7,
					Number:        phone,
					Number2:       phone,
				}},
			})
			if convErr != nil {
				return errorResult(fmt.Sprintf("failed to get/create conversation: %v", convErr)), nil
			}
			conv = convResp.GetConversation()
			if conv == nil {
				return errorResult("no conversation returned"), nil
			}
			conversationID = conv.GetConversationID()
			// Refresh full conversation for participant + SIM metadata.
			if full, fullErr := a.Client.GM.GetConversation(conversationID); fullErr == nil && full != nil {
				conv = full
			}
		}

		participantID, sim := participantAndSIM(conv)
		payload := buildSendPayload(conversationID, message, participantID, sim)

		resp, err := a.Client.GM.SendMessage(payload)
		if err != nil {
			return errorResult(fmt.Sprintf("send failed (transport error): %v", err)), nil
		}

		status := resp.GetStatus()
		statusName := status.String()
		if status != gmproto.SendMessageResponse_SUCCESS {
			hint := sendFailureHint(sim == nil)
			return errorResult(fmt.Sprintf(
				"NOT DELIVERED: Google Messages rejected the send (status=%s). conversation_id=%s phone=%s. %s",
				statusName, conversationID, phone, hint,
			)), nil
		}

		now := time.Now().UnixMilli()
		if a.Store != nil {
			_ = a.Store.UpsertMessage(&db.Message{
				MessageID:      payload.TmpID,
				ConversationID: conversationID,
				Body:           message,
				IsFromMe:       true,
				TimestampMS:    now,
				Status:         "OUTGOING_SENDING",
			})
			_ = a.Store.UpdateConversationTimestamp(conversationID, now)
		}

		return textResult(fmt.Sprintf(
			"DELIVERED: Google Messages accepted the send (status=%s).\nconversation_id: %s\nphone: %s\nmessage_id: %s\n\nThe message should appear in the thread on your phone shortly. If it does not, open http://localhost:11042 and check the conversation.",
			statusName, conversationID, phone, payload.TmpID,
		)), nil
	}
}

func sendFailureHint(missingSIM bool) string {
	parts := []string{
		"The message was not sent.",
	}
	if missingSIM {
		parts = append(parts, "No active SIM was resolved for this conversation (common on dual-SIM phones).")
	}
	parts = append(parts,
		"Try gm_draft_message with conversation_id so the user can send from the web UI, or send manually at http://localhost:11042.",
	)
	return strings.Join(parts, " ")
}
