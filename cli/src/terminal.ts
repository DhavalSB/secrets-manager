// Terminal compatibility for the OpenTUI screen.
//
// On startup OpenTUI asks the terminal what it supports by writing "query" escape
// sequences. Modern terminals (iTerm2, Ghostty, WezTerm, kitty, VS Code) answer them
// silently. Some terminals (macOS Terminal.app, the Claude desktop app terminal) print some of
// them as text instead, e.g. "+q4d73pppppp Gi=31337,s=1,v=1,a=q,t=d,f=24;AAAA".
//
// The queries are built into OpenTUI's native engine and can't be switched off, so
// on those terminals we give the renderer an output stream that removes them.

import tty from "node:tty";
import type { CliRenderer, CliRendererConfig } from "@opentui/core";

// The query kinds those terminals print. Their answers to the remaining ones (like the
// "device attributes" query) still tells OpenTUI what's supported.
const UNSUPPORTED_QUERIES = [
  /\x1bP\+q[0-9A-Fa-f;]*\x1b\\/g, // XTGETTCAP: "do you have capability X?"
  /\x1b_G[^\x1b]*\x1b\\/g, // kitty graphics: "can you show images?"
  /\x1b\[\?\d+\$p/g, // DECRQM: "is mode N on?"
];

function strip(chunk: unknown): unknown {
  if (typeof chunk !== "string" && !(chunk instanceof Uint8Array)) return chunk;
  let text = typeof chunk === "string" ? chunk : Buffer.from(chunk).toString("latin1");
  const before = text.length;
  for (const re of UNSUPPORTED_QUERIES) text = text.replace(re, "");
  if (text.length === before) return chunk;
  return typeof chunk === "string" ? text : Buffer.from(text, "latin1");
}

// Terminals known to print these queries as text (TERM_PROGRAM values).
const TERMINALS_THAT_PRINT_QUERIES = new Set(["Apple_Terminal", "claude-desktop"]);

/** SM_FILTER_QUERIES=1 forces the filter on (=0 forces it off) for any other terminal. */
function needsQueryFilter(): boolean {
  const force = process.env.SM_FILTER_QUERIES;
  if (force === "1") return true;
  if (force === "0") return false;
  return TERMINALS_THAT_PRINT_QUERIES.has(process.env.TERM_PROGRAM ?? "");
}

let filteredStdout: tty.WriteStream | null = null;

/**
 * With a custom output stream OpenTUI doesn't watch for window resizes itself,
 * so on Terminal.app we catch the resize signal and pass the new size along.
 */
export function watchResize(renderer: CliRenderer): void {
  const out = filteredStdout;
  if (!out) return;
  process.on("SIGWINCH", () => {
    // Our extra stream's own size goes stale in Bun; process.stdout has the real one.
    out.columns = process.stdout.columns;
    out.rows = process.stdout.rows;
    (renderer as unknown as { sigwinchHandler: () => void }).sigwinchHandler();
  });
}

/** Options to pass to createCliRenderer for the current terminal. */
export function rendererOptions(): Partial<CliRendererConfig> {
  // We never show images, so don't ask about image support anywhere.
  const options: Partial<CliRendererConfig> = { environment: { OPENTUI_GRAPHICS: "0" } };
  if (!needsQueryFilter() || !process.stdout.isTTY) return options;

  const out = new tty.WriteStream(1);
  const write = out.write.bind(out) as (...a: unknown[]) => boolean;
  out.write = ((chunk: unknown, ...rest: unknown[]) => write(strip(chunk), ...rest)) as typeof out.write;
  filteredStdout = out;

  // Pass the terminal details OpenTUI normally reads from the environment.
  const env: Record<string, string> = { OPENTUI_GRAPHICS: "0" };
  for (const key of ["TERM", "TERM_PROGRAM", "TERM_PROGRAM_VERSION", "COLORTERM", "LANG", "LC_ALL"]) {
    const v = process.env[key];
    if (v) env[key] = v;
  }
  return { stdout: out as unknown as NodeJS.WriteStream, remote: false, environment: env };
}
