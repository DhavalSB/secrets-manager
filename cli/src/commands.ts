// Plain (non-interactive) commands. Each prints short text, or JSON with --json,
// so both people and agents/scripts can use them.

import { api, ApiError, type Grant, type SecretSummary, type TeamInfo, type UserInfo } from "./api.ts";
import { credentialsPath, deleteCredentials, readCredentials } from "./config.ts";
import { browserLogin, devLogin } from "./login.ts";
import { flag, grantText, has, list, need, printJson, readStdin, table, UsageError, type Args } from "./util.ts";

const enc = encodeURIComponent;

// ---------------------------------------------------------------------------
// Session
// ---------------------------------------------------------------------------

export async function login(args: Args): Promise<void> {
  const dev = flag(args, "dev");
  if (readCredentials() && !process.env.SM_TOKEN) {
    await api("POST", "/auth/logout").catch(() => {}); // don't leave the previous session alive
  }
  const who = dev ? await devLogin(dev) : await browserLogin();
  console.log(`Logged in as ${who}. Credentials saved to ${credentialsPath}`);
  process.exit(0); // make sure nothing (browser keep-alive connections, timers) keeps us running
}

export async function logout(_args: Args): Promise<void> {
  if (process.env.SM_TOKEN) throw new UsageError("SM_TOKEN is set; unset it (or revoke the token) instead.");
  if (!readCredentials()) return console.log("Not logged in.");
  try {
    await api("POST", "/auth/logout"); // revoke on the server too, not just locally
  } catch (e) {
    if (!(e instanceof ApiError) || e.status !== 401) throw e;
  }
  deleteCredentials();
  console.log("Logged out.");
}

// ---------------------------------------------------------------------------
// Secrets
// ---------------------------------------------------------------------------

export async function ls(args: Args): Promise<void> {
  const secrets = await api<SecretSummary[]>("GET", "/secrets");
  if (has(args, "json")) return printJson(secrets);
  table(
    ["KEY", "ACCESS", "SHARED WITH", "UPDATED"],
    secrets.map((s) => [s.key, s.access, grantText(s.grants), `${s.updated_at.slice(0, 10)} by ${s.updated_by ?? "?"}`]),
  );
}

/** "--read team:backend --write user:bob --read org" -> grants */
function grantsFromFlags(args: Args): Grant[] {
  const out: Grant[] = [];
  for (const permission of ["read", "write"] as const) {
    for (const p of list(args, permission)) out.push({ principal: normalize(p), permission });
  }
  return out;
}

function normalize(p: string): string {
  if (p === "org" || p.startsWith("user:") || p.startsWith("team:")) return p;
  if (p.startsWith("@")) return `user:${p.slice(1)}`;
  throw new UsageError(`'${p}' should be user:<login>, team:<name>, @<login>, or org`);
}

async function findSummary(key: string): Promise<SecretSummary | undefined> {
  const all = await api<SecretSummary[]>("GET", "/secrets");
  return all.find((s) => s.key === key);
}

export async function set(args: Args): Promise<void> {
  const key = need(args, 0, "KEY");
  let value = args.positional[1];
  if (value === undefined) {
    if (process.stdin.isTTY) throw new UsageError("Give a VALUE, or pipe it in: echo -n 'v' | sm set KEY");
    value = await readStdin(); // keeps the value out of shell history
  }
  const grants = grantsFromFlags(args);
  const existing = await findSummary(key);
  if (!existing) {
    const s = await api<SecretSummary>("PUT", `/secrets/${enc(key)}`, { value, grants });
    return has(args, "json") ? printJson(s) : console.log(`Created ${key}. Shared with: ${grantText(s.grants)}`);
  }
  await api("PUT", `/secrets/${enc(key)}`, { value });
  if (grants.length) await applyShare(key, existing.grants, grants, []);
  console.log(`Updated ${key}.`);
}

export async function share(args: Args): Promise<void> {
  const key = need(args, 0, "KEY");
  const add = grantsFromFlags(args);
  const remove = list(args, "remove").map(normalize);
  if (!add.length && !remove.length) {
    throw new UsageError("Usage: sm share KEY [--read P]... [--write P]... [--remove P]...   (P = user:x, team:y, @x, org)");
  }
  const existing = await findSummary(key);
  if (!existing) throw new UsageError(`No secret '${key}' that you can read`);
  const s = await applyShare(key, has(args, "replace") ? [] : existing.grants, add, remove);
  console.log(`${key} is now shared with: ${grantText(s.grants)}`);
}

/** Merge grant changes and send the full new list (the API replaces all grants at once). */
async function applyShare(key: string, current: Grant[], add: Grant[], remove: string[]): Promise<SecretSummary> {
  const byPrincipal = new Map(current.map((g) => [g.principal, g.permission]));
  for (const p of remove) byPrincipal.delete(p);
  for (const g of add) {
    // Never downgrade: adding read for someone who already has write keeps write.
    if (byPrincipal.get(g.principal) !== "write") byPrincipal.set(g.principal, g.permission);
  }
  const grants = [...byPrincipal].map(([principal, permission]) => ({ principal, permission }));
  return api<SecretSummary>("PUT", `/secrets/${enc(key)}`, { grants });
}

export async function rm(args: Args): Promise<void> {
  const key = need(args, 0, "KEY");
  await api("DELETE", `/secrets/${enc(key)}`);
  console.log(`Deleted ${key}.`);
}

// ---------------------------------------------------------------------------
// People and teams
// ---------------------------------------------------------------------------

export async function users(args: Args): Promise<void> {
  const rows = await api<UserInfo[]>("GET", "/users");
  if (has(args, "json")) return printJson(rows);
  table(["LOGIN", "ROLE", "TEAMS"], rows.map((u) => [u.login, u.is_admin ? "admin" : "member", u.teams.join(", ")]));
}

export async function teams(args: Args): Promise<void> {
  const rows = await api<TeamInfo[]>("GET", "/teams");
  if (has(args, "json")) return printJson(rows);
  table(["TEAM", "MEMBERS"], rows.map((t) => [t.name, t.members.join(", ")]));
}

export async function user(args: Args): Promise<void> {
  const [sub, login] = [args.positional[0], args.positional[1]];
  const need1 = () => {
    if (!login) throw new UsageError(`Usage: sm user ${sub} LOGIN`);
    return enc(login);
  };
  switch (sub) {
    case "add": {
      const u = await api<UserInfo>("POST", "/users", { github_login: decodeURIComponent(need1()), is_admin: has(args, "admin"), teams: list(args, "team") });
      return console.log(`Added ${u.login}${u.is_admin ? " (admin)" : ""}${u.teams.length ? ` to ${u.teams.join(", ")}` : ""}.`);
    }
    case "rm":
      await api("DELETE", `/users/${need1()}`);
      return console.log(`Removed ${login}. Their sessions and agent tokens are revoked.`);
    case "promote":
      await api("POST", `/users/${need1()}/promote`);
      return console.log(`${login} is now an admin.`);
    case "demote":
      await api("POST", `/users/${need1()}/demote`);
      return console.log(`${login} is no longer an admin.`);
    case "teams": {
      const u = await api<UserInfo>("PUT", `/users/${need1()}/teams`, { teams: args.positional.slice(2).flatMap((t) => t.split(",")).filter(Boolean) });
      return console.log(`${u.login} is now in: ${u.teams.join(", ") || "(no teams)"}`);
    }
    default:
      throw new UsageError("Usage: sm user add LOGIN [--admin] [--team T]... | rm LOGIN | promote LOGIN | demote LOGIN | teams LOGIN [TEAM...]");
  }
}

export async function team(args: Args): Promise<void> {
  const [sub, name, login] = [args.positional[0], args.positional[1], args.positional[2]];
  if (!name) throw new UsageError("Usage: sm team create NAME [--member U]... | add NAME LOGIN | remove NAME LOGIN | rm NAME");
  let t: TeamInfo;
  switch (sub) {
    case "create":
      t = await api("POST", "/teams", { name, members: list(args, "member") });
      break;
    case "add":
      if (!login) throw new UsageError("Usage: sm team add NAME LOGIN");
      t = await api("POST", `/teams/${enc(name)}/members/${enc(login)}`);
      break;
    case "remove":
      if (!login) throw new UsageError("Usage: sm team remove NAME LOGIN");
      t = await api("DELETE", `/teams/${enc(name)}/members/${enc(login)}`);
      break;
    case "rm":
      await api("DELETE", `/teams/${enc(name)}`);
      return console.log(`Deleted team ${name}. Secrets shared with it are no longer shared with its members.`);
    default:
      throw new UsageError("Usage: sm team create NAME [--member U]... | add NAME LOGIN | remove NAME LOGIN | rm NAME");
  }
  console.log(`${t.name}: ${t.members.join(", ") || "(no members)"}`);
}

// ---------------------------------------------------------------------------
// Agent tokens and audit
// ---------------------------------------------------------------------------

interface TokenInfo {
  id: number;
  kind: string;
  name: string;
  read_only: boolean;
  allowed_keys: string[] | null;
  expires_at: string;
  last_used_at: string | null;
  current: boolean;
  token?: string;
}

export async function token(args: Args): Promise<void> {
  const sub = args.positional[0];
  if (sub === "create") {
    const name = need(args, 1, "NAME");
    const keys = list(args, "keys");
    const t = await api<TokenInfo>("POST", "/tokens", {
      name,
      read_only: !has(args, "allow-write"),
      keys: keys.length ? keys : null,
      expires_days: Number(flag(args, "days") ?? 7),
    });
    if (has(args, "json")) return printJson(t);
    console.error(
      `Agent token "${t.name}": ${t.read_only ? "read-only" : "read/write"}, keys: ${t.allowed_keys?.join(", ") ?? "all you can read"}, expires ${t.expires_at.slice(0, 10)}.`,
    );
    console.error("Give it to the agent as SM_TOKEN. It is shown only once:\n");
    console.log(t.token);
    return;
  }
  if (sub === "ls" || sub === undefined) {
    const rows = await api<TokenInfo[]>("GET", "/tokens");
    if (has(args, "json")) return printJson(rows);
    return table(
      ["ID", "KIND", "NAME", "SCOPE", "EXPIRES", "LAST USED"],
      rows.map((t) => [
        String(t.id) + (t.current ? "*" : ""),
        t.kind,
        t.name,
        t.kind === "agent" ? `${t.read_only ? "read" : "read/write"} ${t.allowed_keys?.join(",") ?? "*"}` : "full",
        t.expires_at.slice(0, 10),
        t.last_used_at?.slice(0, 16).replace("T", " ") ?? "never",
      ]),
    );
  }
  if (sub === "revoke") {
    await api("DELETE", `/tokens/${enc(need(args, 1, "ID"))}`);
    return console.log("Revoked.");
  }
  throw new UsageError("Usage: sm token create NAME [--keys A,B] [--allow-write] [--days N] | ls | revoke ID");
}

export async function audit(args: Args): Promise<void> {
  const q = new URLSearchParams({ limit: flag(args, "limit") ?? "50" });
  const secret = flag(args, "secret");
  if (secret) q.set("secret", secret);
  const rows = await api<{ at: string; actor: string; action: string; target: string; detail: string }[]>("GET", `/audit?${q}`);
  if (has(args, "json")) return printJson(rows);
  table(["WHEN", "WHO", "ACTION", "TARGET", "DETAIL"], rows.map((r) => [r.at.slice(0, 19).replace("T", " "), r.actor, r.action, r.target, r.detail]));
}
