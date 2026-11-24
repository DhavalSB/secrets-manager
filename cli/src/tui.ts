// `sm` with no arguments: an interactive browser for humans, built with OpenTUI.
//
//   ┌ Secrets ──────────┐┌ Details ─────────────────────────┐
//   │▶ STRIPE_KEY       ││ STRIPE_KEY        (you can write) │
//   │  DB_PASSWORD      ││ value: ••••••  (v to reveal)      │
//   │  SENTRY_DSN       ││ shared with: user:bob write, ...  │
//   └───────────────────┘└───────────────────────────────────┘
//    tab view · v reveal · c copy · n new · e edit · s share · d delete · q quit
//
// Layout is flexbox: a column (header, body, prompt, footer); the body is a row (list, details).

import {
  BoxRenderable,
  createCliRenderer,
  InputRenderable,
  SelectRenderable,
  TextRenderable,
  type CliRenderer,
  type KeyEvent,
  type SelectOption,
} from "@opentui/core";
import { rendererOptions, watchResize } from "./terminal.ts";
import { api, ApiError, type Me, type SecretSummary, type SecretWithValue, type TeamInfo, type UserInfo } from "./api.ts";

const C = {
  accent: "#7aa2f7",
  dim: "#7f849c",
  text: "#cdd6f4",
  ok: "#a6e3a1",
  warn: "#f9e2af",
  err: "#f38ba8",
  bg: "#1e1e2e",
  panel: "#181825",
};

type View = "secrets" | "teams" | "users";
const VIEWS: View[] = ["secrets", "teams", "users"];

export async function startTui(renderer?: CliRenderer): Promise<{ renderer: CliRenderer; ready: Promise<void> }> {
  // We handle Ctrl+C ourselves so it goes through quit() below, like q does.
  if (!renderer) {
    renderer = await createCliRenderer({ exitOnCtrlC: false, backgroundColor: C.bg, ...rendererOptions() });
    watchResize(renderer);
  }

  // ---- layout -------------------------------------------------------------
  const root = new BoxRenderable(renderer, { flexDirection: "column", width: "100%", height: "100%", padding: 0 });
  const header = new TextRenderable(renderer, { content: "SecretsManager", fg: C.accent, height: 1, paddingX: 1 });
  const body = new BoxRenderable(renderer, { flexDirection: "row", flexGrow: 1 });
  const listBox = new BoxRenderable(renderer, { border: true, title: " Secrets ", borderColor: C.accent, width: "40%", flexDirection: "column" });
  const list = new SelectRenderable(renderer, {
    flexGrow: 1,
    options: [],
    backgroundColor: C.panel,
    focusedBackgroundColor: C.panel,
    selectedBackgroundColor: "#313244",
    selectedTextColor: C.accent,
    textColor: C.text,
    descriptionColor: C.dim,
    selectedDescriptionColor: C.dim,
    showDescription: true,
    wrapSelection: true,
  });
  const detailBox = new BoxRenderable(renderer, { border: true, title: " Details ", borderColor: C.dim, flexGrow: 1, paddingX: 1 });
  const detail = new TextRenderable(renderer, { content: "", fg: C.text });
  const promptBox = new BoxRenderable(renderer, { border: true, borderColor: C.warn, height: 3, visible: false, flexDirection: "row", paddingX: 1 });
  const promptLabel = new TextRenderable(renderer, { content: "", fg: C.warn });
  const input = new InputRenderable(renderer, { flexGrow: 1, textColor: C.text, backgroundColor: C.bg, focusedBackgroundColor: C.bg });
  const footer = new TextRenderable(renderer, { content: "", fg: C.dim, height: 1, paddingX: 1 });

  listBox.add(list);
  detailBox.add(detail);
  body.add(listBox);
  body.add(detailBox);
  promptBox.add(promptLabel);
  promptBox.add(input);
  root.add(header);
  root.add(body);
  root.add(promptBox);
  root.add(footer);
  renderer.root.add(root);

  // ---- state --------------------------------------------------------------
  let view: View = "secrets";
  let me: Me | null = null;
  let secrets: SecretSummary[] = [];
  let teams: TeamInfo[] = [];
  let users: UserInfo[] = [];
  const revealed = new Map<string, string>(); // key -> value, only after you press v
  let prompting: ((v: string | null) => void) | null = null;

  const HELP: Record<View, string> = {
    secrets: "tab view · ↑↓ move · v reveal · c copy · n new · e edit · s share · d delete · r refresh · q quit",
    teams: "tab view · ↑↓ move · r refresh · q quit   (admins: use `sm team ...` to change teams)",
    users: "tab view · ↑↓ move · r refresh · q quit   (admins: use `sm user ...` to change users)",
  };

  function status(msg: string, color = C.dim): void {
    footer.content = msg;
    footer.fg = color;
  }

  function selectedSecret(): SecretSummary | undefined {
    return view === "secrets" ? secrets[list.getSelectedIndex()] : undefined;
  }

  function renderList(): void {
    listBox.title = ` ${view[0]!.toUpperCase()}${view.slice(1)} `;
    let options: SelectOption[];
    if (view === "secrets") {
      options = secrets.map((s) => ({ name: s.key, description: s.access === "write" ? "read/write" : "read only" }));
    } else if (view === "teams") {
      options = teams.map((t) => ({ name: t.name, description: `${t.members.length} member(s)` }));
    } else {
      options = users.map((u) => ({ name: u.login, description: u.is_admin ? "admin" : "member" }));
    }
    const idx = Math.min(list.getSelectedIndex(), Math.max(0, options.length - 1));
    list.options = options;
    if (options.length) list.setSelectedIndex(idx);
    renderDetail();
  }

  function renderDetail(): void {
    const i = list.getSelectedIndex();
    if (view === "secrets") {
      const s = secrets[i];
      if (!s) return void (detail.content = "No secrets you can see yet.\n\nPress n to create one.");
      const value = revealed.has(s.key) ? revealed.get(s.key)! : "••••••••  (press v to reveal)";
      detail.content = [
        `${s.key}    (you can ${s.access === "write" ? "read and write" : "read"})`,
        "",
        `value:        ${value}`,
        "",
        "shared with:",
        ...s.grants.map((g) => `  ${g.permission === "write" ? "write" : "read "}  ${g.principal}`),
        "",
        `created by:   ${s.created_by ?? "?"}`,
        `updated:      ${s.updated_at.slice(0, 16).replace("T", " ")} by ${s.updated_by ?? "?"}`,
      ].join("\n");
    } else if (view === "teams") {
      const t = teams[i];
      detail.content = t ? [`team ${t.name}`, "", "members:", ...t.members.map((m) => `  ${m}`)].join("\n") : "No teams yet.";
    } else {
      const u = users[i];
      detail.content = u
        ? [`${u.login}${u.is_admin ? "  (admin)" : ""}`, "", "teams:", ...(u.teams.length ? u.teams.map((t) => `  ${t}`) : ["  (none)"])].join("\n")
        : "No users.";
    }
  }

  async function load(): Promise<void> {
    try {
      [me, secrets, teams, users] = await Promise.all([
        api<Me>("GET", "/me"),
        api<SecretSummary[]>("GET", "/secrets"),
        api<TeamInfo[]>("GET", "/teams").catch(() => []),
        api<UserInfo[]>("GET", "/users").catch(() => []),
      ]);
      const who = me.session.kind === "agent" ? `${me.login} via agent:${me.session.name}` : me.login;
      header.content = `SecretsManager  ·  ${who}${me.is_admin ? " (admin)" : ""}  ·  ${me.org}  ·  teams: ${me.teams.join(", ") || "none"}`;
      renderList();
      status(HELP[view]);
    } catch (e) {
      status(errorText(e), C.err);
    }
  }

  // ---- prompt (bottom input line) -----------------------------------------
  function ask(label: string, initial = ""): Promise<string | null> {
    promptLabel.content = label + " ";
    input.value = initial;
    promptBox.visible = true;
    input.focus();
    status("enter to confirm · esc to cancel", C.warn);
    return new Promise((resolve) => (prompting = resolve));
  }

  function endPrompt(value: string | null): void {
    const done = prompting;
    prompting = null;
    promptBox.visible = false;
    list.focus();
    status(HELP[view]);
    done?.(value);
  }

  input.on("enter", () => endPrompt(input.value));

  // ---- actions ------------------------------------------------------------
  async function act(fn: () => Promise<string | void>): Promise<void> {
    try {
      const msg = await fn();
      if (msg) status(msg, C.ok);
    } catch (e) {
      status(errorText(e), C.err);
    }
  }

  async function reveal(): Promise<void> {
    const s = selectedSecret();
    if (!s) return;
    if (revealed.has(s.key)) {
      revealed.delete(s.key);
      return renderDetail();
    }
    await act(async () => {
      const full = await api<SecretWithValue>("GET", `/secrets/${encodeURIComponent(s.key)}`);
      revealed.set(s.key, full.value);
      renderDetail();
      return `Revealed ${s.key} (this read is in the audit log)`;
    });
  }

  async function copy(): Promise<void> {
    const s = selectedSecret();
    if (!s) return;
    await act(async () => {
      const full = await api<SecretWithValue>("GET", `/secrets/${encodeURIComponent(s.key)}`);
      const cmd = process.platform === "darwin" ? ["pbcopy"] : ["xclip", "-selection", "clipboard"];
      const p = Bun.spawn(cmd, { stdin: "pipe" });
      p.stdin.write(full.value);
      await p.stdin.end();
      await p.exited;
      return `Copied ${s.key} to the clipboard`;
    });
  }

  async function create(): Promise<void> {
    const key = await ask("New key (e.g. STRIPE_KEY):");
    if (!key) return;
    const value = await ask(`Value for ${key}:`);
    if (value === null) return;
    const shareWith = await ask("Share with (e.g. team:backend read, @bob write, org read; empty = only you):");
    await act(async () => {
      await api("PUT", `/secrets/${encodeURIComponent(key)}`, { value, grants: parseGrantList(shareWith ?? "") });
      await load();
      list.setSelectedIndex(Math.max(0, secrets.findIndex((s) => s.key === key)));
      renderDetail();
      return `Created ${key}`;
    });
  }

  async function edit(): Promise<void> {
    const s = selectedSecret();
    if (!s) return;
    if (s.access !== "write") return status(`You can read ${s.key} but not change it`, C.err);
    const value = await ask(`New value for ${s.key}:`);
    if (value === null) return;
    await act(async () => {
      await api("PUT", `/secrets/${encodeURIComponent(s.key)}`, { value });
      revealed.delete(s.key);
      await load();
      return `Updated ${s.key}`;
    });
  }

  async function shareSecret(): Promise<void> {
    const s = selectedSecret();
    if (!s) return;
    if (s.access !== "write") return status(`You need write access to change who ${s.key} is shared with`, C.err);
    const current = s.grants.map((g) => `${g.principal} ${g.permission}`).join(", ");
    const answer = await ask("Shared with (edit the list):", current);
    if (answer === null) return;
    await act(async () => {
      await api("PUT", `/secrets/${encodeURIComponent(s.key)}`, { grants: parseGrantList(answer) });
      await load();
      return `Updated sharing for ${s.key}`;
    });
  }

  async function remove(): Promise<void> {
    const s = selectedSecret();
    if (!s) return;
    const answer = await ask(`Type ${s.key} to delete it:`);
    if (answer !== s.key) return status("Not deleted", C.dim);
    await act(async () => {
      await api("DELETE", `/secrets/${encodeURIComponent(s.key)}`);
      revealed.delete(s.key);
      await load();
      return `Deleted ${s.key}`;
    });
  }

  // ---- keys ---------------------------------------------------------------
  list.on("selectionChanged", () => renderDetail());

  renderer.keyInput.on("keypress", (key: KeyEvent) => {
    if (key.ctrl && key.name === "c") return void quit();
    if (prompting) {
      if (key.name === "escape") endPrompt(null);
      return; // everything else goes to the input box
    }
    switch (key.name) {
      case "q":
      case "escape":
        return quit();
      case "tab":
        view = VIEWS[(VIEWS.indexOf(view) + (key.shift ? VIEWS.length - 1 : 1)) % VIEWS.length]!;
        list.setSelectedIndex(0);
        renderList();
        return status(HELP[view]);
      case "r":
        return void load();
    }
    if (view !== "secrets") return;
    const actions: Record<string, () => Promise<void>> = { v: reveal, c: copy, n: create, e: edit, s: shareSecret, d: remove };
    const action = actions[key.name];
    if (!action) return;
    key.preventDefault(); // otherwise the "n" that opens a prompt also gets typed into it
    void action();
  });

  async function quit(): Promise<void> {
    renderer!.destroy();
    await renderer!.closed;
    process.exit(0);
  }

  list.focus();
  status("Loading…");
  return { renderer, ready: load() };
}

/** "team:backend read, @bob write, org" -> grants (default permission: read) */
export function parseGrantList(text: string): { principal: string; permission: string }[] {
  return text
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean)
    .map((part) => {
      const [who, perm = "read"] = part.split(/\s+/) as [string, string?];
      const principal = who.startsWith("@") ? `user:${who.slice(1)}` : who;
      return { principal, permission: perm };
    });
}

function errorText(e: unknown): string {
  if (e instanceof ApiError) return e.status === 401 ? `${e.message}` : `Error: ${e.message}`;
  return `Error: ${e instanceof Error ? e.message : String(e)}`;
}
