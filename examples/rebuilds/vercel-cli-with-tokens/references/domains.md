# Managing domains

```bash
# List domains
vercel domains ls --scope <team-slug>

# Add a domain to the project: linked or env-linked directory (1 arg)
vercel domains add <domain> --scope <team-slug>

# Add a domain: unlinked directory (requires <project> positional)
vercel domains add <domain> <project> --scope <team-slug>
```
