package tools

import (
	"fmt"
	"math/rand"
	"strings"

	"go.mau.fi/mautrix-gmessages/pkg/libgm/gmproto"
)

// normalizePhoneNumber formats US numbers as E.164 (+1...) when possible.
func normalizePhoneNumber(phone string) string {
	phone = strings.TrimSpace(phone)
	if phone == "" {
		return phone
	}
	if strings.HasPrefix(phone, "+") {
		return phone
	}
	digits := make([]byte, 0, len(phone))
	for i := 0; i < len(phone); i++ {
		if phone[i] >= '0' && phone[i] <= '9' {
			digits = append(digits, phone[i])
		}
	}
	switch len(digits) {
	case 10:
		return "+1" + string(digits)
	case 11:
		if digits[0] == '1' {
			return "+" + string(digits)
		}
	}
	return phone
}

func participantAndSIM(conv *gmproto.Conversation) (participantID string, sim *gmproto.SIMPayload) {
	if conv == nil {
		return "", nil
	}
	for _, p := range conv.GetParticipants() {
		if p.GetIsMe() {
			if id := p.GetID(); id != nil {
				participantID = id.GetNumber()
			}
			sim = p.GetSimPayload()
			break
		}
	}
	if sc := conv.GetSimCard(); sc != nil {
		if convSim := sc.GetSIMData().GetSIMPayload(); sim == nil {
			sim = convSim
		}
	}
	return participantID, sim
}

// buildSendPayload matches the web UI send path (MessageInfo array, TmpID, SIM).
func buildSendPayload(conversationID, message, participantID string, sim *gmproto.SIMPayload) *gmproto.SendMessageRequest {
	tmpID := fmt.Sprintf("tmp_%012d", rand.Int63n(1e12))
	return &gmproto.SendMessageRequest{
		ConversationID: conversationID,
		MessagePayload: &gmproto.MessagePayload{
			TmpID: tmpID,
			MessageInfo: []*gmproto.MessageInfo{{
				Data: &gmproto.MessageInfo_MessageContent{
					MessageContent: &gmproto.MessageContent{
						Content: message,
					},
				},
			}},
			ConversationID: conversationID,
			ParticipantID:  participantID,
			TmpID2:         tmpID,
		},
		SIMPayload: sim,
		TmpID:      tmpID,
	}
}
