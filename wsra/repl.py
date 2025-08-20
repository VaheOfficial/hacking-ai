from __future__ import annotations
import asyncio
from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table
from .core.session import SessionManager
from .core.guardrails import enforce
from .core.executor import run_command, make_observation

console = Console()

def _print_status(ses: SessionManager):
    cfg = ses.config
    console.rule("[bold]STATUS[/bold]")
    console.print(f"[bold]Mode:[/bold] {cfg.mode}")
    console.print(f"[bold]Output:[/bold] {cfg.output_dir}")
    console.print(f"[bold]Kill switch:[/bold] {cfg.kill_switch}")
    console.print(f"[bold]Domains:[/bold] {cfg.scope.domains}  [bold]Hosts:[/bold] {cfg.scope.hosts}")
    console.print(f"[bold]Paths:[/bold] {cfg.scope.paths}")

async def _exec_single(ses: SessionManager, cmd: str, block_id: str = "ADHOC"):
    allow, needs_approval, reason = enforce(ses.config, cmd)
    if not allow:
        console.print(f"[yellow]Not executed[/yellow] ({'needs approval' if needs_approval else 'blocked'}): {reason}")
        return
    console.print(f"[green]Executing[/green]: {cmd}   [dim]{reason}[/dim]")
    rc, out, err, o_path, e_path = await run_command(ses.config, block_id, 0, cmd)
    obs = make_observation(block_id, [(rc, out, err, o_path, e_path)])
    table = Table(title=f"Observation {obs.block_id} (exit {obs.exit_code})")
    table.add_column("Key lines", justify="left")
    table.add_row("\n".join(obs.key_lines[:30]))
    console.print(table)
    (ses.root / "assessment_log.jsonl").open("a", encoding="utf-8").write(
        f'{{"ts":"{obs.ts.isoformat()}","type":"observation","block_id":"{obs.block_id}","exit_code":{obs.exit_code},"bytes_out":{obs.bytes_out},"summary":"{obs.summary}"}}\n'
    )

def start_repl(ses: SessionManager):
    console.print("[bold cyan]WSRA REPL[/bold cyan] — type HELP for commands; STOP to exit.")
    while True:
        try:
            line = Prompt.ask("[wsra]")
        except (KeyboardInterrupt, EOFError):
            console.print("\n[red]Exiting.[/red]")
            break

        if not line.strip():
            continue
        if line.strip().upper() in {"STOP", ses.config.kill_switch.upper()}:
            console.print("[red]Stopped.[/red]")
            break
        if line.strip().upper() == "HELP":
            console.print("Commands: STATUS | RUN <cmd> | LIST BLOCKS | APPROVE <id> | EXEC <id> | STOP")
            continue
        if line.strip().upper() == "STATUS":
            _print_status(ses); continue
        if line.strip().upper().startswith("RUN "):
            cmd = line.strip()[4:]
            asyncio.run(_exec_single(ses, cmd))
            continue
        # Minimal stubs for future:
        if line.strip().upper() == "LIST BLOCKS":
            console.print("Use `wsra propose` to generate blocks, then `approve/exec` via CLI.")
            continue
        if line.strip().upper().startswith("APPROVE ") or line.strip().upper().startswith("EXEC "):
            console.print("Use CLI subcommands `wsra approve/exec` in this MVP.")
            continue

        console.print("[yellow]Unknown command.[/yellow] Try HELP.")
