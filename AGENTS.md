## Secrets
- Secrets come from SecretsManager. Never ask for secret values or put them in files.
- To run anything that needs secrets: `sm run -- <command>` (e.g. `sm run -- npm test`).
- `sm ls` lists the keys you have access to; `sm whoami` shows your token's limits.
- Don't use `sm get`; it prints the value into your context.
