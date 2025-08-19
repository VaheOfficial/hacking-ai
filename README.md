# Hacking AI (Ethical Security Research Assistant)

Hacking AI is a CLI agent for ethical security research on Kali Linux and other OSes. It can:

- Run OS-aware shell commands with safety checks (bash on Linux/macOS, PowerShell on Windows)
- Search the web and summarize content
- Pull and summarize docs from HackTricks and GTFOBins
- Follow an agentic loop (plan → act → observe) with optional LLM integration

## Quickstart

```bash
# Create and activate a venv (recommended)
python3 -m venv .venv && source .venv/bin/activate

# Install
pip install -e .

# Run
hacking-ai agent "enumerate linux privilege escalation vectors"
```

Interactive mode:
```bash
hacking-ai agent
```

## Safety and Ethics
- This tool is for authorized testing, learning, and defensive research only.
- Commands are allowlisted by default. Potentially dangerous commands require explicit confirmation.
- You can bypass confirmations with `--no-confirm` (not recommended).

## Agent Usage
```bash
hacking-ai agent "find potential privesc techniques on ubuntu 22.04"

# Options
hacking-ai agent --max-steps 5 --no-confirm
```

## Docs and Web
```bash
# HackTricks search
hacking-ai docs hacktricks "linux privilege escalation"

# GTFOBins search
hacking-ai docs gtfobins "awk privesc"

# General web search
hacking-ai web "CVE-2023-XYZ PoC"
```

## Single Command Runner
```bash
hacking-ai cmd "whoami && id"
```

## Build a Single Binary
```bash
pip install .[dev]
./scripts/build.sh

# Output binary: dist/hacking-ai
./dist/hacking-ai agent "linux post-exploitation checklist"
```

## Configuration
- Environment variables:
  - `OPENAI_API_KEY` (optional): If set, the agent uses an OpenAI-compatible Chat Completions endpoint for reasoning/summarization.
  - `OPENAI_BASE_URL` (optional): Defaults to `https://api.openai.com/v1`.
  - `OPENAI_MODEL` (optional): Defaults to `gpt-4o-mini`.

## Legal
Use only on systems you own or are explicitly authorized to test. The authors assume no liability for misuse.