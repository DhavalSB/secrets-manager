// Where the CLI keeps its login, and which server it talks to.
//
// Token lookup order:
//   1. SM_TOKEN env var   (how agents and CI authenticate: no file, no browser)
//   2. ~/.config/sm/credentials.json   (written by `sm login`)

import { chmodSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

const CONFIG_DIR = process.env.SM_CONFIG_DIR ?? join(homedir(), ".config", "sm");
const CREDENTIALS = join(CONFIG_DIR, "credentials.json");

export interface Credentials {
  server: string;
  token: string;
  login: string;
}

export function readCredentials(): Credentials | null {
  if (!existsSync(CREDENTIALS)) return null;
  try {
    return JSON.parse(readFileSync(CREDENTIALS, "utf8")) as Credentials;
  } catch {
    return null;
  }
}

export function saveCredentials(creds: Credentials): void {
  mkdirSync(CONFIG_DIR, { recursive: true, mode: 0o700 });
  writeFileSync(CREDENTIALS, JSON.stringify(creds, null, 2), { mode: 0o600 });
  chmodSync(CREDENTIALS, 0o600); // only you can read it
}

export function deleteCredentials(): void {
  rmSync(CREDENTIALS, { force: true });
}

export function serverUrl(): string {
  return (process.env.SM_SERVER ?? readCredentials()?.server ?? "http://localhost:8000").replace(/\/$/, "");
}

export function currentToken(): string | null {
  return process.env.SM_TOKEN ?? readCredentials()?.token ?? null;
}

export const credentialsPath = CREDENTIALS;
