from __future__ import annotations
import json
from pathlib import Path
from typing import Optional, List
import typer
from rich import print as rprint
from rich.table import Table
from .core.session import SessionManager
from .repl import start_repl
from .models import CommandBlock, SessionConfig
from .core.guardrails import enforce
from .core.executor import run_command, make_observation
import asyncio
from datetime import datetime

app = typer.Typer(help="WSRA - White-Hat Security Research Assistant")

@app.callback(invoke_without_command=True)
def _default(ctx: typer.Context, output_dir: Optional[Path] = typer.Option(None, "--output-dir", "-o")):
    if ctx.invoked_subcommand:
        return
    # No command -> load or init then REPL
    ses = SessionManager.load_or_init(output_dir=output_dir)
    start_repl(ses)

@app.command()
def init(output_dir: Optional[Path] = typer.Option(None, "--output-dir", "-o")):
    """Run the setup wizard (or load existing)."""
    ses = SessionManager.load_or_init(output_dir=output_dir)
    rprint(f"[green]Session ready:[/green] {ses.root}")

def _blocks_file(cfg: SessionConfig) -> Path:
    return cfg.output_dir / "proposed_blocks.json"

@app.command()
def propose():
    """Propose safe read-only DNS + HTTP HEAD blocks for in-scope domains/hosts."""
    ses = SessionManager.load_or_init()
    blocks: List[CommandBlock] = []
    i = 1
    ts = datetime.utcnow().strftime("%Y%m%d")
    for d in ses.config.scope.domains:
        bid = f"CB-{ts}-{i:03d}"; i += 1
        blocks.append(CommandBlock(
            id=bid, intent=f"DNS/WHOIS/HEAD for {d}",
            scope_check=f"{d} in scope domains",
            commands=[
                f"dig +short {d}",
                f"whois {d} | head -n 30",
                f"curl -I --max-time 10 https://{d}",
            ],
            expected_observation="Resolve A/AAAA; basic WHOIS metadata; HTTP server headers",
            risk="low"
        ))
    for h in ses.config.scope.hosts:
        bid = f"CB-{ts}-{i:03d}"; i += 1
        blocks.append(CommandBlock(
            id=bid, intent=f"HEAD for host {h}",
            scope_check=f"{h} in scope hosts",
            commands=[
                f"curl -I --max-time 10 http://{h}",
                f"curl -I --max-time 10 https://{h}",
            ],
            expected_observation="HTTP status and headers",
            risk="low"
        ))
    (ses.config.output_dir / "proposed_blocks.json").write_text(
        json.dumps([b.model_dump(mode="json") for b in blocks], indent=2)
    )
    table = Table(title="Proposed Command Blocks")
    table.add_column("ID"); table.add_column("Intent"); table.add_column("Commands")
    for b in blocks:
        table.add_row(b.id, b.intent, "\n".join(b.commands))
    rprint(table)
    rprint(f"[green]Saved:[/green] {_blocks_file(ses.config)}")

@app.command()
def approve(block_id: str):
    """Mark a block as approved (writes a simple approval file)."""
    ses = SessionManager.load_or_init()
    (ses.config.output_dir / f"{block_id}.approved").write_text("approved")
    rprint(f"[green]Approved:[/green] {block_id}")

def _load_blocks(cfg: SessionConfig) -> List[CommandBlock]:
    f = _blocks_file(cfg)
    if not f.exists():
        raise SystemExit("No proposed_blocks.json found. Run `wsra propose` first.")
    data = json.loads(f.read_text())
    return [CommandBlock(**x) for x in data]

@app.command()
def exec(block_id: str):
    """Execute an approved block with guardrails + scope checks."""
    ses = SessionManager.load_or_init()
    approved = (ses.config.output_dir / f"{block_id}.approved").exists()
    if not approved:
        raise SystemExit("Block not approved. Run `wsra approve <id>` first.")

    blocks = _load_blocks(ses.config)
    block = next((b for b in blocks if b.id == block_id), None)
    if not block:
        raise SystemExit("Block ID not found.")

    # Check every command before running any
    for c in block.commands:
        allow, needs, reason = enforce(ses.config, c)
        if not allow:
            raise SystemExit(f"Blocked/Needs approval: {c}\nReason: {reason}")

    async def run_all():
        results = []
        for idx, c in enumerate(block.commands):
            rc, out, err, o, e = await run_command(ses.config, block.id, idx, c, timeout=20)
            results.append((rc, out, err, o, e))
        return results

    rprint(f"[cyan]Executing block[/cyan] {block.id}: {block.intent}")
    results = asyncio.run(run_all())
    obs = make_observation(block.id, results)
    # Print a short observation
    rprint(f"[bold]Observation[/bold] {obs.block_id} exit={obs.exit_code} bytes={obs.bytes_out}")
    for line in obs.key_lines[:40]:
        rprint(line)

    # Log
    (ses.root / "assessment_log.jsonl").open("a", encoding="utf-8").write(
        f'{{"ts":"{obs.ts.isoformat()}","type":"observation","block_id":"{obs.block_id}","exit_code":{obs.exit_code},"bytes_out":{obs.bytes_out},"summary":"{obs.summary}"}}\n'
    )
    rprint(f"[green]Logs saved under[/green] {ses.root / 'logs'}")

@app.command()
def repl():
    """Interactive REPL (RUN <cmd>, STATUS, LIST BLOCKS, STOP)."""
    ses = SessionManager.load_or_init()
    start_repl(ses)

@app.command()
def status():
    """Show session at a glance."""
    ses = SessionManager.load_or_init()
    rprint({
        "mode": ses.config.mode,
        "output_dir": str(ses.config.output_dir),
        "domains": ses.config.scope.domains,
        "hosts": ses.config.scope.hosts,
        "paths": ses.config.scope.paths,
        "kill_switch": ses.config.kill_switch
    })

@app.command()
def index_logs():
    """Index current session logs/evidence into the vector store."""
    # Lazy import heavy deps
    from .vector.store import VectorStore  # type: ignore
    ses = SessionManager.load_or_init()
    vs = VectorStore.for_session(ses)
    count = vs.index_session_artifacts()
    rprint(f"[green]Indexed[/green] {count} documents for session {ses.root.name}")

@app.command()
def search(query: str, top_k: int = 5):
    """Semantic search over current session corpus."""
    from .vector.store import VectorStore  # type: ignore
    ses = SessionManager.load_or_init()
    vs = VectorStore.for_session(ses)
    results = vs.search(query, top_k=top_k)
    table = Table(title=f"Search results for: {query}")
    table.add_column("score"); table.add_column("source"); table.add_column("snippet")
    for r in results:
        table.add_row(f"{r['score']:.4f}", r["source"], r["text"][:200].replace("\n"," ") + ("…" if len(r["text"])>200 else ""))
    rprint(table)

@app.command()
def kb_add(title: str, note: str):
    """Add a note/finding to the centralized knowledge bank and index it."""
    from .vector.knowledge import KnowledgeBank  # type: ignore
    ses = SessionManager.load_or_init()
    kb = KnowledgeBank()
    kb_id = kb.add_entry(session_root=ses.root, title=title, note=note)
    rprint(f"[green]KB entry added[/green]: {kb_id}")

@app.command()
def kb_search(query: str, top_k: int = 5):
    """Search the centralized knowledge bank."""
    from .vector.knowledge import KnowledgeBank  # type: ignore
    kb = KnowledgeBank()
    rows = kb.search(query, top_k=top_k)
    table = Table(title=f"KB results for: {query}")
    table.add_column("score"); table.add_column("title"); table.add_column("session"); table.add_column("snippet")
    for r in rows:
        table.add_row(f"{r['score']:.4f}", r["title"], r["session"], r["text"][:200].replace("\n"," ") + ("…" if len(r["text"])>200 else ""))
    rprint(table)

@app.command()
def ai_init(api_key: str = typer.Option(None, "--api-key", help="OpenAI API key (will be stored securely)")):
    """Securely store the OpenAI API key for AI mode."""
    from .core.ai import SecureKeys
    if not api_key:
        api_key = typer.prompt("Enter OpenAI API key", hide_input=True)
    backend = SecureKeys.set_openai_key(api_key)
    rprint(f"[green]API key saved securely via {backend} backend.[/green]")

@app.command()
def ai_run(objective: str = typer.Option(..., "--objective", "-g", help="Goal to achieve (e.g., assess host 10.0.0.1)"), model: str = typer.Option("gpt-5", "--model", help="OpenAI model name")):
    """Run AI-guided research loop: propose -> approve -> execute -> iterate."""
    from .core.ai import SecureKeys
    from .core.ai_loop import run_ai_loop
    ses = SessionManager.load_or_init()
    api_key = SecureKeys.get_openai_key()
    if not api_key:
        raise SystemExit("API key not found. Run `wsra ai_init` first.")
    run_ai_loop(ses, api_key=api_key, model=model, objective=objective)
