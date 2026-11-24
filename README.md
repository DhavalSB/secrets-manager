<!-- Improved compatibility of back to top link: See: https://github.com/othneildrew/Best-README-Template/pull/73 -->
<a id="readme-top"></a>

<div align="center">
<h3 align="center">Secrets Manager</h3>
A team secrets manager with GitHub login, per-secret read/write sharing, and safe access for coding agents.
</div>


<!-- GETTING STARTED -->
## Getting Started

The backend (FastAPI) and the CLI (Bun + OpenTUI) both run on your machine. The CLI talks to the backend at `http://localhost:8000`.

### Prerequisites

* **Python 3.11+** (developed on 3.15)
  ```sh
  python3 --version
  ```
* **Bun 1.x** (runs the TypeScript CLI)
  ```sh
  curl -fsSL https://bun.sh/install | bash
  ```
* **A GitHub account.** Login uses GitHub OAuth, and you'll register a small OAuth app in step 2.

### Installation

1. Clone the repo
   ```sh
   git clone https://github.com/dhavalsb/secrets-manager.git
   cd secrets-manager
   ```
2. Create a GitHub OAuth app at [github.com/settings/developers](https://github.com/settings/developers) → **New OAuth App**:
   * Homepage URL: `http://localhost:8000`
   * Authorization callback URL: `http://localhost:8000/auth/callback`

   Copy the **Client ID**, then click **Generate a new client secret** and copy that too.
3. Install the backend's Python packages
   ```sh
   python3 -m venv .venv
   ./.venv/bin/pip install -r server/requirements.txt
   ```
4. Create your config from the example
   ```sh
   cp .env.example .env
   ```
   Fill in `.env`:
   * `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET`: from step 2
   * `SM_ENCRYPTION_KEY`: the key that encrypts secret values in the database. Generate one with:
     ```sh
     ./.venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
     ```
   * `SEED_ADMIN_GITHUB_LOGIN`: **your** GitHub username, which becomes the first admin
   * `SEED_ORG_NAME`: your organization's name
5. Create the database, org and admin (run from `server/`)
   ```sh
   cd server
   ../.venv/bin/python -m app.seed          # add --demo for sample users, teams and secrets
   ```
6. Start the backend (leave it running)
   ```sh
   ../.venv/bin/uvicorn app.main:app --reload
   ```
   API docs: [http://localhost:8000/docs](http://localhost:8000/docs)
7. In a second terminal, install the CLI and put `sm` on your PATH
   ```sh
   cd cli
   bun install
   bun link
   ```
8. Log in. Your browser opens to GitHub and the CLI picks up the session automatically.
   ```sh
   sm login
   sm whoami
   ```
   Run `sm` with no arguments for the interactive screen, or `sm help` for all commands.

#### Optional: try it without GitHub

To click around as the demo users, seed with `--demo`, set `SM_DEV_LOGIN=1` in `.env`, and restart the server. Then:
```sh
sm login --dev carol
```
`--dev` skips GitHub entirely, so only turn it on for local demos.

#### Running the tests
```sh
cd server
../.venv/bin/pytest
```

<p align="right">(<a href="#readme-top">back to top</a>)</p>



## Design Priorities

### Agentic Safety

Secrets Manager allows several routes for safely handling agentic access. You can create an agent token using `sm token create NAME [--keys A,B] [--allow-write] [--days 7] [--for-agents]`, where the `--for-agents` flag will alert agents to automatically use the agent token.

Agent tokens are strictly limited by the user's own permissions, and can be further limited in scope upon creation of the token.

Using `sm run [--keys A,B] -- COMMAND..`, agents can run a given command with permitted secrets loaded as environment variables, keeping secrets out of the terminal or context.

Accessing the audit log via `sm audit` can also help to diagnose issues with agentic or human misuse.

### Common Sense Permissions Logic

For ease of understanding, Secrets Manager implements common sense permissions logic such as:
- Write access implies read access
- The creator of a secret automatically has write access
- Members of a team cannot be denied access to team-granted secrets
- Administrators may add other administrators

### Lightweight Implementation

- SQLite stores everything in `secrets.db`
- Few dependencies: six Python packages for the backend, and a single library (OpenTUI) for the CLI.
- No build step, as Bun runs the TypeScript CLI directly
- Opaque session tokens instead of JWTs. They're random strings stored as hashes, so there's no signing-key management, and logout or revoke takes effect immediately.
- Permissions are computed when checked, from the grants table, by two small pure functions. There are no cached access lists to keep in sync.
- One encryption key (Fernet) in .env instead of a key-management service. This is a deliberate trade-off for a single-server deployment.

## Architectural Decisions

### Data Model (SQLite using SQLModel)

| Table | Columns | Notes |
| --- | --- | --- |
| **Organization** | `id`, `name` | One per deployment |
| **User** | `id`, `github_login`, `org_id`, `is_admin`, `created_at` | Identified by GitHub login |
| **Team** | `id`, `name`, `org_id` | |
| **TeamMember** | `team_id`, `user_id` | Links users to teams (many-to-many) |
| **Secret** | `id`, `key`, `encrypted_value`, `org_id`, `created_by`, `updated_by`, `created_at`, `updated_at` | |
| **SecretGrant** | `id`, `secret_id`, `principal_type`, `principal_id`, `permission` | `principal_type`: `user` / `team` / `org`<br>`permission`: `read` / `write` |
| **Session** | `id`, `token_hash`, `user_id`, `kind`, `name`, `read_only`, `allowed_keys`, `created_at`, `expires_at`, `last_used_at` | `kind`: `cli` / `agent`<br>Only the token's hash is stored |
| **AuditLog** | `id`, `at`, `user_id`, `actor`, `action`, `target`, `detail` | Append-only |

### Bun + OpenTUI CLI, FastAPI backend

Bun handles the local login server, and the `sm` command is directly routed to `bun run src/index.ts`.

OpenTUI provides the terminal UI for the interactive secrets manager `sm` with no arguments.

FastAPI has interactive API docs at `/docs` when the server is running.

## Deliberately Cut Features

1. Deny Grants: a user cannot be explicitly denied from a certain secret if their team/org already enables them access to it.
   - Can cause conflicts with priority of permissions, and secret-by-secret permission can still be granted with the current implementation.

2. Multi-Organization Setup: managing secrets for multiple organizations would require running multiple server instances.
   - The effect of multiple organizations can be achieved with the teams feature already. Implementing multi-organizational access would require reshaping the database structure and verifying users do not have access to secrets from a different organization.

3. Secrets Versioning: there is no tracked history of secret K/V pairs.
   - This would likely be the highest value addition to Secrets Manager to fix mistakenly changed secrets, but the implementation would be non-trivial.

4. Sophisticated Admin Seeding: the first admin must be directly seeded into the database using their GitHub username.
   - More sophisticated admin seeding could use GitHub organizations or server-side setup codes, but a practical solution would depend on the organizations needs.

<p align="right">(<a href="#readme-top">back to top</a>)</p>


