# WSRA (MVP)

White-Hat Security Research Assistant. Safe-by-design: **read-only** by default, scope/ROE enforced.

## Quickstart (pipx)

```bash
# Install via pipx
pipx install .

# Or from a checkout for development
pipx install --editable .

# Use the CLI
wsra init
wsra propose
wsra repl

#Inside the REPL, try:
STATUS
LIST BLOCKS
APPROVE CB-...
EXEC CB-...
RUN echo hello
STOP

#Logs/evidence are saved under your chosen OUTPUT_DIR.

### AI mode

1) Configure your API key securely:
```bash
wsra ai_init --api-key sk-...
```

2) Run the loop:
```bash
wsra ai_run --objective "Assess host 10.129.16.197 for non-destructive recon"
```

The AI will propose safe command blocks for approval, execute approved steps, store results, and iterate. Session artifacts are indexed for semantic search.
