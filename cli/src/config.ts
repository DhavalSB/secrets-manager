// Where the CLI keeps its logins, and which server it talks to.
//
// Two saved logins, in ~/.config/sm/:
//   credentials.json   your own login, written by `sm login` (full access)
//   agent.json         the agent token, written by `sm token create NAME --for-agents`
//
// Which one a command uses:
//   1. SM_TOKEN env var, if set (CI, or handing a token to one specific process)
//   2. agent mode (an AI agent is running sm): agent.json, and NEVER your own login
//   3. otherwise: credentials.json
//
// Agent mode is detected from environment variables coding agents set in every
// command they run: CLAUDECODE (Claude Code), AI_AGENT, or SM_AGENT=1 for any
// other agent. SM_AGENT=0 forces human mode.

import { chmodSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

const CONFIG_DIR = process.env.SM_CONFIG_DIR ?? join(homedir(), ".config", "sm");
const CREDENTIALS = join(CONFIG_DIR, "credentials.json");
const AGENT_CREDENTIALS = join(CONFIG_DIR, "agent.json");

export interface Credentials {
  server: string;
  token: string;
  login: string;
}

export function isAgentMode(): boolean {
  const forced = process.env.SM_AGENT;
  if (forced === "0") return false;
  if (forced === "1") return true;
  return Boolean(process.env.CLAUDECODE || process.env.AI_AGENT);
}

function readJson(path: string): Credentials | null {
  if (!existsSync(path)) return null;
  try {
    return JSON.parse(readFileSync(path, "utf8")) as Credentials;
  } catch {
    return null;
  }
}

function writeJson(path: string, creds: Credentials): void {
  mkdirSync(CONFIG_DIR, { recursive: true, mode: 0o700 });
  writeFileSync(path, JSON.stringify(creds, null, 2), { mode: 0o600 });
  chmodSync(path, 0o600); // only your user can read it
}

export const readCredentials = () => readJson(CREDENTIALS);
export const saveCredentials = (c: Credentials) => writeJson(CREDENTIALS, c);
export const deleteCredentials = () => rmSync(CREDENTIALS, { force: true });

export const readAgentCredentials = () => readJson(AGENT_CREDENTIALS);
export const saveAgentCredentials = (c: Credentials) => writeJson(AGENT_CREDENTIALS, c);
export const deleteAgentCredentials = () => rmSync(AGENT_CREDENTIALS, { force: true });

/** The saved login this process should use (ignoring SM_TOKEN). */
function savedLogin(): Credentials | null {
  return isAgentMode() ? readAgentCredentials() : readCredentials();
}

export function serverUrl(): string {
  return (process.env.SM_SERVER ?? savedLogin()?.server ?? "http://localhost:8000").replace(/\/$/, "");
}

export function currentToken(): string | null {
  return process.env.SM_TOKEN ?? savedLogin()?.token ?? null;
}

export const credentialsPath = CREDENTIALS;
export const agentCredentialsPath = AGENT_CREDENTIALS;
