// `sm run [--keys A,B] -- <command> [args...]`
//
// Fetch the secrets you (or your agent token) can read, add them to the environment,
// and run the command. The values reach the program but never get printed, so they
// don't end up in an agent's chat log or your shell history.

import { api } from "./api.ts";
import { list, UsageError, type Args } from "./util.ts";

export async function run(args: Args): Promise<void> {
  if (args.rest.length === 0) throw new UsageError("Usage: sm run [--keys A,B] -- <command> [args...]");
  const keys = list(args, "keys");
  const query = keys.length ? `?keys=${encodeURIComponent(keys.join(","))}` : "";
  const secrets = await api<Record<string, string>>("GET", `/env${query}`);

  console.error(`sm: injecting ${Object.keys(secrets).length} secret(s): ${Object.keys(secrets).join(", ")}`);
  const child = Bun.spawn(args.rest, {
    env: { ...process.env, ...secrets },
    stdin: "inherit",
    stdout: "inherit",
    stderr: "inherit",
  });
  process.exit(await child.exited);
}
