import { GM_MCP_TO_OPENMESSAGE } from "./tool-schemas.js";

export interface GmessagesToolResult {
  text: string;
  isError: boolean;
}

export class GmessagesClient {
  private baseUrl: string;

  constructor(baseUrl?: string) {
    this.baseUrl = (
      baseUrl ||
      process.env.PHONEPI_GMESSAGES_URL ||
      "http://127.0.0.1:11042"
    ).replace(/\/$/, "");
  }

  async isReachable(): Promise<boolean> {
    try {
      const res = await fetch(`${this.baseUrl}/api/status`, {
        signal: AbortSignal.timeout(2000),
      });
      return res.ok;
    } catch {
      return false;
    }
  }

  async callTool(
    mcpToolName: string,
    args: Record<string, unknown> = {}
  ): Promise<GmessagesToolResult> {
    const openmessageTool = GM_MCP_TO_OPENMESSAGE[mcpToolName];
    if (!openmessageTool) {
      throw new Error(`Unknown Google Messages tool: ${mcpToolName}`);
    }

    let res: Response;
    try {
      res = await fetch(`${this.baseUrl}/api/tool`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tool: openmessageTool, arguments: args }),
        signal: AbortSignal.timeout(120_000),
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      throw new Error(
        `Google Messages bridge not reachable at ${this.baseUrl}. ` +
          `Run: messages-bridge\\phonepi-gmessages.exe serve (${msg})`
      );
    }

    const body = (await res.json()) as GmessagesToolResult & { error?: string };
    if (!res.ok) {
      throw new Error(body.error || `HTTP ${res.status}`);
    }
    return { text: body.text ?? "", isError: !!body.isError };
  }
}

export const gmessagesClient = new GmessagesClient();
