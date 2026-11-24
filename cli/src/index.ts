#!/usr/bin/env bun
// sm: the SecretsManager CLI. `sm` alone opens the interactive screen; subcommands
// print plain text (or JSON with --json) for scripts and coding agents.

import { ApiError } from "./api.ts";
import * as cmd from "./commands.ts";
import { run } from "./run.ts";
import { parseArgs, UsageError, type Args } from "./util.ts";
import { get, whoami } from "./yours.ts";

const HELP = `sm: share secrets with your team and your coding agents

Usage:
  sm                                   open the interactive screen
  sm login [--dev LOGIN]               log in with GitHub in your browser
  sm logout
  sm whoami [--json]

Secrets:
  sm ls [--json]                       secrets you can read
  sm get KEY [--json]                  print a value (just the value, for scripts)
  sm set KEY [VALUE] [--read P]... [--write P]...
                                       create or update; VALUE can be piped on stdin
  sm share KEY [--read P]... [--write P]... [--remove P]... [--replace]
  sm rm KEY
      P is user:<login>, @<login>, team:<name>, or org

Agents:
  sm token create NAME [--keys A,B] [--allow-write] [--days 7]
                                       scoped token; give it to an agent as SM_TOKEN
  sm token ls | sm token revoke ID
  sm run [--keys A,B] -- COMMAND...    run COMMAND with your secrets as env vars

People (everyone can list; admins can change):
  sm users | sm teams
  sm user add LOGIN [--admin] [--team T]... | rm LOGIN | promote LOGIN | demote LOGIN
  sm user teams LOGIN TEAM...          reassign a user to exactly these teams
  sm team create NAME [--member U]... | add NAME LOGIN | remove NAME LOGIN | rm NAME
  sm audit [--secret KEY] [--limit N]  (admins)

Environment:
  SM_SERVER   backend URL (default http://localhost:8000)
  SM_TOKEN    use this token instead of the saved login (agents, CI)
`;

const COMMANDS: Record<string, (a: Args) => Promise<void>> = {
  login: cmd.login,
  logout: cmd.logout,
  whoami,
  ls: cmd.ls,
  list: cmd.ls,
  get,
  set: cmd.set,
  share: cmd.share,
  rm: cmd.rm,
  users: cmd.users,
  teams: cmd.teams,
  user: cmd.user,
  team: cmd.team,
  token: cmd.token,
  tokens: cmd.token,
  run,
  audit: cmd.audit,
};

async function main(): Promise<void> {
  const [name, ...rest] = process.argv.slice(2);
  if (name === undefined) {
    if (!process.stdout.isTTY) return void console.log(HELP);
    const { startTui } = await import("./tui.ts");
    await startTui();
    return;
  }
  if (name === "help" || name === "--help" || name === "-h") return void console.log(HELP);
  const handler = COMMANDS[name];
  if (!handler) throw new UsageError(`Unknown command '${name}'. Run \`sm help\`.`);
  await handler(parseArgs(rest));
}

main().catch((e) => {
  if (e instanceof UsageError) console.error(e.message);
  else if (e instanceof ApiError) console.error(`Error: ${e.message}`);
  else console.error(e);
  process.exit(1);
});
