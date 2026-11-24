// One helper for every call to the backend: adds the token, sends/parses JSON,
// and turns error responses into an ApiError with the server's message.

import { currentToken, serverUrl } from "./config.ts";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function api<T = any>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  const token = currentToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";

  let res: Response;
  try {
    res = await fetch(serverUrl() + path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, `Can't reach the server at ${serverUrl()}. Is it running?`);
  }

  const text = await res.text();
  const data = text ? safeJson(text) : null;
  if (!res.ok) {
    const detail = data?.detail;
    const message =
      typeof detail === "string" ? detail : detail ? JSON.stringify(detail) : `${res.status} ${res.statusText}`;
    throw new ApiError(res.status, message);
  }
  return data as T;
}

function safeJson(text: string): any {
  try {
    return JSON.parse(text);
  } catch {
    return { detail: text };
  }
}

// Shapes returned by the backend (see server/app/routes_*.py).
export interface Grant {
  principal: string; // "user:bob" | "team:backend" | "org"
  permission: "read" | "write";
}
export interface SecretSummary {
  key: string;
  access: "read" | "write";
  grants: Grant[];
  created_by: string | null;
  updated_by: string | null;
  updated_at: string;
}
export interface SecretWithValue extends SecretSummary {
  value: string;
}
export interface Me {
  login: string;
  is_admin: boolean;
  teams: string[];
  org: string;
  session: { kind: string; name: string; read_only: boolean; allowed_keys: string[] | null; expires_at: string };
}
export interface UserInfo {
  login: string;
  is_admin: boolean;
  teams: string[];
}
export interface TeamInfo {
  name: string;
  members: string[];
}
