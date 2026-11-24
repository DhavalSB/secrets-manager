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
      if (url.searchParams.get("state") !== state) {
        return resultPage({ error: "this login didn't come from your terminal (state mismatch)." });
      }
      const error = url.searchParams.get("error");
      if (error) {
        finish({ error });
        return resultPage({ error });
      }
      const login = url.searchParams.get("login") ?? undefined;
      finish({ token: url.searchParams.get("token") ?? undefined, login });
      return resultPage({ login });
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

/**
 * Send the browser to the backend's styled result page. Only the login name or error
 * goes in the URL; the token stays here in the CLI.
 */
function resultPage(params: { login?: string; error?: string }): Response {
  const q = new URLSearchParams();
  if (params.login) q.set("login", params.login);
  if (params.error) q.set("error", params.error);
  return Response.redirect(`${serverUrl()}/auth/done?${q}`, 302);
}
