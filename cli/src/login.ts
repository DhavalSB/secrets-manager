// `sm login`: browser-based GitHub login with no copy/paste.
//
// We start a tiny web server on 127.0.0.1:<random port>, open the browser at the
// backend's /auth/login, and wait. After GitHub, the backend redirects the browser
// to our tiny server with the session token. We check the `state` we generated
// matches (so nobody else can feed us a token), save it, and shut the server down.

import { api } from "./api.ts";
import { saveCredentials, serverUrl } from "./config.ts";

const TIMEOUT_MS = 3 * 60 * 1000;

export async function browserLogin(): Promise<string> {
  const state = crypto.randomUUID().replaceAll("-", "");
  let finish!: (r: { token?: string; login?: string; error?: string }) => void;
  const result = new Promise<{ token?: string; login?: string; error?: string }>((r) => (finish = r));

  const server = Bun.serve({
    hostname: "127.0.0.1",
    port: 0, // let the OS pick a free port
    fetch(req) {
      const url = new URL(req.url);
      if (url.pathname !== "/callback") return new Response("Not found", { status: 404 });
      if (url.searchParams.get("state") !== state) return page("Login failed: state mismatch. Run sm login again.", 400);
      const error = url.searchParams.get("error");
      if (error) {
        finish({ error });
        return page(`Login failed: ${error}`, 400);
      }
      finish({ token: url.searchParams.get("token") ?? undefined, login: url.searchParams.get("login") ?? undefined });
      return page("Logged in. You can close this tab and return to your terminal.");
    },
  });

  const loginUrl = `${serverUrl()}/auth/login?port=${server.port}&state=${state}`;
  console.log("Opening your browser to log in with GitHub...");
  console.log(`If it doesn't open, visit:\n  ${loginUrl}\n`);
  openBrowser(loginUrl);

  let timer: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<{ error: string }>((r) => {
    timer = setTimeout(() => r({ error: "Timed out waiting for login" }), TIMEOUT_MS);
  });
  const outcome = await Promise.race([result, timeout]);
  clearTimeout(timer); // a pending timer would keep the process alive for 3 minutes
  // Let the browser finish receiving the "you can close this tab" page, then stop listening.
  await Bun.sleep(300);
  server.stop(true);

  if (outcome.error || !("token" in outcome) || !outcome.token) throw new Error(outcome.error ?? "No token received");
  saveCredentials({ server: serverUrl(), token: outcome.token, login: outcome.login ?? "" });
  return outcome.login ?? "";
}

/** Log in as a seeded user without GitHub. Only works if the server has SM_DEV_LOGIN=1. */
export async function devLogin(login: string): Promise<string> {
  const r = await api<{ token: string; login: string }>("POST", "/auth/dev-login", { login });
  saveCredentials({ server: serverUrl(), token: r.token, login: r.login });
  return r.login;
}

function openBrowser(url: string): void {
  const cmd =
    process.platform === "darwin" ? ["open", url] : process.platform === "win32" ? ["cmd", "/c", "start", "", url] : ["xdg-open", url];
  try {
    Bun.spawn(cmd, { stdout: "ignore", stderr: "ignore" });
  } catch {
    // The URL is printed above; the user can open it by hand.
  }
}

function page(message: string, status = 200): Response {
  const html = `<!doctype html><meta charset="utf-8"><title>sm login</title>
<body style="font-family:system-ui;display:grid;place-items:center;height:90vh">
<h2>${message.replace(/</g, "&lt;")}</h2></body>`;
  return new Response(html, { status, headers: { "Content-Type": "text/html" } });
}
