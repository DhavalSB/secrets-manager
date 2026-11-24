// Commands you write: `sm whoami` and `sm get`.
//
// The pattern every command follows:
//   1. read what you need from `args` (helpers in util.ts)
//   2. call the backend with `api(METHOD, PATH)`; it adds your token and throws ApiError on failure
//   3. print: JSON if --json was given, otherwise something short and readable
//
// Try it:   bun run src/index.ts whoami         bun run src/index.ts get STRIPE_KEY

import { api, type Me, type SecretWithValue } from "./api.ts";
import { isAgentMode } from "./config.ts";
import { has, need, printJson, type Args } from "./util.ts";

export async function whoami(args: Args): Promise<void> {
  const me = await api<Me>("GET", "/me");
  if (has(args, "json")) return printJson(me);
  const role = me.is_admin ? "admin" : "member";
  console.log(`${me.login} (${role}) in ${me.org}`);
  console.log(`teams: ${me.teams.join(", ") || "(none)"}`);
  if (isAgentMode() && !process.env.SM_TOKEN) console.log("mode: agent (using the saved agent token, not your personal login)");
  if (me.session.kind === "agent") {
    const keys = me.session.allowed_keys?.join(", ") ?? "all readable keys";
    console.log(`agent token "${me.session.name}": ${me.session.read_only ? "read-only" : "read/write"}, ${keys}`);
  }
}

export async function get(args: Args): Promise<void> {
  const key = need(args, 0, "KEY");
  const secret = await api<SecretWithValue>("GET", `/secrets/${encodeURIComponent(key)}`);
  if (has(args, "json")) return printJson(secret);
  // Print only the value, with no extra text, so `$(sm get KEY)` works in scripts.
  process.stdout.write(secret.value + (process.stdout.isTTY ? "\n" : ""));
}
