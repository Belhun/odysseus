/**
 * Google Messages (openmessage) MCP tool schemas.
 * Prefixed with gm_ to avoid clashing with phone WebSocket tools.
 */

export const GM_TOOL_PREFIX = "gm_";

/** openmessage tool name → PhonePi MCP tool name */
export const GM_TOOL_MAP: Record<string, string> = {
  get_messages: "gm_get_messages",
  get_conversation: "gm_get_conversation",
  search_messages: "gm_search_messages",
  send_message: "gm_send_message",
  list_conversations: "gm_list_conversations",
  list_contacts: "gm_list_contacts",
  get_status: "gm_get_status",
  draft_message: "gm_draft_message",
  download_media: "gm_download_media",
  react_to_message: "gm_react_to_message",
};

export const GM_MCP_TO_OPENMESSAGE: Record<string, string> = Object.fromEntries(
  Object.entries(GM_TOOL_MAP).map(([openmessage, mcp]) => [mcp, openmessage])
);

export const GM_TOOL_NAMES = new Set(Object.values(GM_TOOL_MAP));

export function isGmTool(name: string): boolean {
  return GM_TOOL_NAMES.has(name);
}

export const GM_TOOL_SCHEMAS = [
  {
    name: "gm_get_messages",
    description:
      "Get recent Google Messages (SMS + RCS) with optional phone/date filters. Default limit is 20; 200 is the soft cap for routine queries — pass a higher limit when the user explicitly asks for more. Requires phonepi-gmessages serve.",
    inputSchema: {
      type: "object",
      properties: {
        phone_number: { type: "string", description: "Filter by sender phone number" },
        after: { type: "string", description: "ISO date YYYY-MM-DD — messages after this day" },
        before: { type: "string", description: "ISO date YYYY-MM-DD — messages before this day" },
        limit: {
          type: "number",
          description:
            "Max messages (default 20). 200 is a soft cap for routine use; higher values are allowed when explicitly requested.",
        },
      },
      required: [],
    },
  },
  {
    name: "gm_get_conversation",
    description:
      "Get messages in a Google Messages conversation by ID (full SMS/RCS thread). Default limit is 50; 200 is the soft cap for routine queries — pass a higher limit when the user explicitly asks for more.",
    inputSchema: {
      type: "object",
      properties: {
        conversation_id: { type: "string", description: "Conversation ID from gm_list_conversations" },
        limit: {
          type: "number",
          description:
            "Max messages (default 50). 200 is a soft cap for routine use; higher values are allowed when explicitly requested.",
        },
      },
      required: ["conversation_id"],
    },
  },
  {
    name: "gm_search_messages",
    description:
      "Full-text search across all Google Messages (SMS + RCS). Default limit is 20; 200 is the soft cap for routine queries — pass a higher limit when the user explicitly asks for more.",
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string", description: "Search text" },
        phone_number: { type: "string", description: "Optional phone filter" },
        limit: {
          type: "number",
          description:
            "Max results (default 20). 200 is a soft cap for routine use; higher values are allowed when explicitly requested.",
        },
      },
      required: ["query"],
    },
  },
  {
    name: "gm_send_message",
    description:
      "Send SMS/RCS via Google Messages. Response starts with DELIVERED or NOT DELIVERED — do not claim success unless the tool output says DELIVERED.",
    inputSchema: {
      type: "object",
      properties: {
        phone_number: { type: "string", description: "Recipient in E.164 form e.g. +17605868615" },
        message: { type: "string", description: "Message text" },
        conversation_id: {
          type: "string",
          description: "Optional thread ID from gm_list_conversations (recommended for dual-SIM)",
        },
      },
      required: ["phone_number", "message"],
    },
  },
  {
    name: "gm_list_conversations",
    description: "List recent Google Messages conversations (SMS + RCS), newest first.",
    inputSchema: {
      type: "object",
      properties: {
        limit: { type: "number", description: "Max conversations (default 20)" },
      },
      required: [],
    },
  },
  {
    name: "gm_list_contacts",
    description: "List or search contacts from Google Messages sync.",
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string", description: "Search by name or number" },
        limit: { type: "number", description: "Max contacts (default 50)" },
      },
      required: [],
    },
  },
  {
    name: "gm_get_status",
    description: "Google Messages bridge connection status and data directory.",
    inputSchema: { type: "object", properties: {}, required: [] },
  },
  {
    name: "gm_draft_message",
    description: "Create a draft message in a conversation for user review in the web UI.",
    inputSchema: {
      type: "object",
      properties: {
        conversation_id: { type: "string" },
        message: { type: "string" },
      },
      required: ["conversation_id", "message"],
    },
  },
  {
    name: "gm_download_media",
    description: "Download media (image, video, voice) from a message to a local temp file.",
    inputSchema: {
      type: "object",
      properties: {
        message_id: { type: "string", description: "Message ID containing media" },
      },
      required: ["message_id"],
    },
  },
  {
    name: "gm_react_to_message",
    description: "Add, remove, or switch an emoji reaction on a Google Messages message.",
    inputSchema: {
      type: "object",
      properties: {
        message_id: { type: "string" },
        emoji: { type: "string", description: "Emoji e.g. 👍" },
        conversation_id: { type: "string", description: "Optional, helps SIM selection" },
        action: { type: "string", enum: ["add", "remove", "switch"], description: "Default add" },
      },
      required: ["message_id", "emoji"],
    },
  },
] as const;
