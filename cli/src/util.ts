// Small helpers: argument parsing, tables, and errors.

export class UsageError extends Error {}

export interface Args {
  positional: string[];
  flags: Record<string, string[]>; // every flag can repeat: --read a --read b
  rest: string[]; // everything after `--` (for `sm run -- cmd args`)
}

// Flags that never take a value.
const BOOLEAN_FLAGS = new Set(["json", "admin", "allow-write", "help", "replace", "yes"]);

export function parseArgs(argv: string[]): Args {
  const args: Args = { positional: [], flags: {}, rest: [] };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i]!;
    if (a === "--") {
      args.rest = argv.slice(i + 1);
      break;
    }
    if (a.startsWith("--")) {
      let [name, value] = a.slice(2).split("=", 2) as [string, string | undefined];
      if (value === undefined && !BOOLEAN_FLAGS.has(name)) {
        value = argv[++i];
        if (value === undefined) throw new UsageError(`--${name} needs a value`);
      }
      (args.flags[name] ??= []).push(value ?? "true");
    } else if (a === "-h") {
      (args.flags.help ??= []).push("true");
    } else {
      args.positional.push(a);
    }
  }
  return args;
}

export const flag = (args: Args, name: string): string | undefined => args.flags[name]?.at(-1);
export const has = (args: Args, name: string): boolean => name in args.flags;
/** Repeated and/or comma-separated: --keys A,B --keys C -> [A, B, C] */
export const list = (args: Args, name: string): string[] =>
  (args.flags[name] ?? []).flatMap((v) => v.split(",")).map((s) => s.trim()).filter(Boolean);

export function need(args: Args, index: number, what: string): string {
  const v = args.positional[index];
  if (!v) throw new UsageError(`Missing ${what}`);
  return v;
}

export function printJson(data: unknown): void {
  console.log(JSON.stringify(data, null, 2));
}

/** Plain aligned columns; no colors so output is easy to pipe and read by agents. */
export function table(headers: string[], rows: string[][]): void {
  if (rows.length === 0) {
    console.log("(none)");
    return;
  }
  const widths = headers.map((h, i) => Math.max(h.length, ...rows.map((r) => (r[i] ?? "").length)));
  const line = (cells: string[]) => cells.map((c, i) => c.padEnd(widths[i]!)).join("  ").trimEnd();
  console.log(line(headers));
  console.log(line(widths.map((w) => "-".repeat(w))));
  for (const r of rows) console.log(line(r));
}

export function grantText(grants: { principal: string; permission: string }[]): string {
  return grants.map((g) => `${g.principal} (${g.permission})`).join(", ");
}

export async function readStdin(): Promise<string> {
  return (await new Response(Bun.stdin.stream()).text()).replace(/\n$/, "");
}
