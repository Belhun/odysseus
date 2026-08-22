import { spawn, type ChildProcess } from "child_process";
import fs from "fs";
import net from "net";
import os from "os";
import path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

/** Spawned sidecar; left running after MCP shutdown for stability. */
let sidecarProcess: ChildProcess | null = null;

function gmessagesDataDir(): string {
  return (
    process.env.PHONEPI_GMESSAGES_DATA_DIR ||
    path.join(os.homedir(), ".local", "share", "phonepi-gmessages")
  );
}

function sessionFilePath(): string {
  return path.join(gmessagesDataDir(), "session.json");
}

function gmessagesPort(): number {
  const port = parseInt(process.env.OPENMESSAGES_PORT || "11042", 10);
  return Number.isFinite(port) ? port : 11042;
}

function resolveGmessagesExe(): string {
  const envBin = process.env.PHONEPI_GMESSAGES_BIN;
  if (envBin) {
    return envBin;
  }
  const names =
    process.platform === "win32"
      ? ["phonepi-gmessages.exe", "phonepi-gmessages"]
      : ["phonepi-gmessages", "phonepi-gmessages.exe"];
  const roots = [
    // Odysseus: dist/gmessages → mcp_servers/phonepi/messages-bridge
    path.resolve(__dirname, "..", ".."),
    // Standalone phonepi-mcp repo: server/dist/gmessages → repo/messages-bridge
    path.resolve(__dirname, "..", "..", ".."),
  ];
  for (const root of roots) {
    for (const name of names) {
      const candidate = path.join(root, "messages-bridge", name);
      if (fs.existsSync(candidate)) {
        return candidate;
      }
    }
  }
  return path.join(roots[0], "messages-bridge", names[0]);
}

function isPortInUse(port: number, host = "127.0.0.1"): Promise<boolean> {
  return new Promise((resolve) => {
    const socket = net.connect({ port, host }, () => {
      socket.destroy();
      resolve(true);
    });
    socket.setTimeout(2000, () => {
      socket.destroy();
      resolve(false);
    });
    socket.on("error", () => resolve(false));
  });
}

/**
 * Start phonepi-gmessages serve when paired and not already listening.
 *
 * On MCP shutdown the sidecar is intentionally left running (detached spawn)
 * so Google Messages sync survives Cursor/MCP restarts.
 */
export async function ensureGmessagesSidecar(): Promise<void> {
  const sessionPath = sessionFilePath();
  if (!fs.existsSync(sessionPath)) {
    console.error(
      "[gmessages] No pairing session; skipping sidecar start.",
      `Pair with: phonepi-gmessages pair (${sessionPath})`
    );
    return;
  }

  const port = gmessagesPort();
  if (await isPortInUse(port)) {
    console.error(
      `[gmessages] Port ${port} already in use; bridge assumed running.`
    );
    return;
  }

  const exePath = resolveGmessagesExe();
  if (!fs.existsSync(exePath)) {
    console.error(
      `[gmessages] Executable not found at ${exePath}; skipping sidecar start.`,
      "Build with messages-bridge\\build.ps1"
    );
    return;
  }

  console.error(`[gmessages] Starting sidecar: ${exePath} serve (port ${port})`);

  sidecarProcess = spawn(exePath, ["serve"], {
    cwd: path.dirname(exePath),
    detached: true,
    stdio: "ignore",
    windowsHide: true,
    env: { ...process.env },
  });

  sidecarProcess.on("error", (err) => {
    console.error("[gmessages] Sidecar spawn error:", err.message);
  });

  sidecarProcess.unref();
}

/** Intentionally no-op: sidecar stays up after MCP exits. */
export function stopGmessagesSidecar(): void {
  if (sidecarProcess) {
    console.error(
      "[gmessages] Leaving sidecar running after MCP shutdown (detached process)."
    );
    sidecarProcess = null;
  }
}
