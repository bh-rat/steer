# Troubleshooting

## Token not found

Check steer, the environment, and any `.env` files present (variable
names only; never print values):

```bash
steer secrets check VERCEL_TOKEN --skill vercel-cli-with-tokens
printenv | grep -io '^[a-z_]*vercel[a-z_]*' 
grep -o '^[A-Za-z_]*VERCEL[A-Za-z_]*=' .env 2>/dev/null
```

## Authentication error

If the CLI fails with `Authentication required`:

- The token may be expired or invalid.
- Verify: `vercel whoami` (uses `VERCEL_TOKEN` from the environment).
- Ask the user for a fresh token, stored via
  `steer secrets set VERCEL_TOKEN --skill vercel-cli-with-tokens`.

## Wrong team

Verify the scope is correct:

```bash
vercel whoami --scope <team-slug>
```

Also check the remembered binding; it may be stale after a project
moved teams:

```bash
steer store get vercel_binding --skill vercel-cli-with-tokens --scope workspace
```

## Build failure

Check the build logs:

```bash
vercel inspect <deployment-url> --logs
```

Common causes:

- Missing dependencies: ensure `package.json` is complete and committed.
- Missing environment variables: add with `vercel env add`.
- Framework misconfiguration: check `vercel.json`. Vercel auto-detects
  frameworks (Next.js, Remix, Vite, etc.) from `package.json`; override
  with `vercel.json` if detection is wrong.

## Inspecting deployments

```bash
vercel ls --format json --scope <team-slug>    # recent deployments
vercel inspect <deployment-url>                # one deployment
vercel inspect <deployment-url> --logs         # build logs (CLI v35+)
vercel logs <deployment-url>                   # runtime logs (add --no-follow for one-shot)
```

## CLI not installed

```bash
npm install -g vercel
```
