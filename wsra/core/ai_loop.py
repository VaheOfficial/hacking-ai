from __future__ import annotations
from typing import List
from rich import print as rprint
from .session import SessionManager
from ..models import CommandBlock
from .executor import run_command, make_observation
from ..core.guardrails import enforce
from .ai import AIClient, MemoryStore, MemoryPaths, propose_blocks_from_ai, AIMessage


async def execute_block_with_approval(ses: SessionManager, block: CommandBlock) -> None:
    rprint(f"[cyan]Proposed[/cyan] {block.id}: {block.intent}")
    rprint("Commands:\n" + "\n".join([f"  - {c}" for c in block.commands]))
    ans = input("Approve this block? [y/N]: ").strip().lower()
    if ans not in {"y", "yes"}:
        rprint("[yellow]Skipped.[/yellow]")
        # Record decision in memory
        mem = MemoryStore(MemoryPaths.for_session(ses))
        mem.append(AIMessage(role="user", content=f"Approval for {block.id}: no", meta={"block_id": block.id}))
        return
    # Record approval in memory
    mem = MemoryStore(MemoryPaths.for_session(ses))
    mem.append(AIMessage(role="user", content=f"Approval for {block.id}: yes", meta={"block_id": block.id}))

    async def run_all():
        results = []
        for idx, c in enumerate(block.commands):
            allow, needs, reason = enforce(ses.config, c)
            if not allow and needs:
                # In EXECUTE_WITH_APPROVAL mode, the user approved the block, so we proceed unless out-of-scope or denied pattern.
                if "Out of scope" in reason or "Denied pattern" in reason or "forbids execution" in reason:
                    rprint(f"[red]Blocked by guardrails[/red]: {c} — {reason}")
                    continue
            rc, out, err, o, e = await run_command(ses.config, block.id, idx, c, timeout=30)
            results.append((rc, out, err, o, e))
        return results

    results = await run_all()
    obs = make_observation(block.id, results)
    # Brief output
    rprint(f"[bold]Observation[/bold] {obs.block_id} exit={obs.exit_code} bytes={obs.bytes_out}")
    for line in obs.key_lines[:20]:
        rprint(line)
    # Persist a short summary and key lines into memory
    mem = MemoryStore(MemoryPaths.for_session(ses))
    snippet = "\n".join(obs.key_lines[:30])
    mem.append(AIMessage(role="user", content=f"Executed block {block.id}. Summary: {obs.summary}\nKey lines:\n{snippet}", meta={"block_id": block.id}))


def run_ai_loop(ses: SessionManager, api_key: str, model: str, objective: str) -> None:
    ai = AIClient(api_key=api_key, model=model)
    mem = MemoryStore(MemoryPaths.for_session(ses))

    # Seed conversation
    # Note: vector search can be incorporated by preloading context snippets if needed
    # For now, we keep conversation history manageable and rely on the AI to request next steps.
    # The memory log is persisted under <session>/memory/messages.jsonl
    # so the loop can be resumed later.
    # We don't store secrets in memory files.
    mem.append(AIMessage(role="user", content=f"Objective: {objective}", meta={}))

    while True:
        blocks: List[CommandBlock] = propose_blocks_from_ai(ai, mem, ses, user_goal=objective)
        if not blocks:
            rprint("[red]AI did not return valid blocks. Ask the user for guidance or try again.[/red]")
            ans = input("Continue? [y/N]: ").strip().lower()
            if ans not in {"y", "yes"}:
                break
            continue

        for b in blocks:
            import asyncio
            asyncio.run(execute_block_with_approval(ses, b))

        # Re-index artifacts for better next-step proposals
        try:
            from ..vector.store import VectorStore  # type: ignore
            VectorStore.for_session(ses).index_session_artifacts()
        except Exception:
            pass

        # After executing a batch, ask AI if done, providing conversation memory
        history = MemoryStore(MemoryPaths.for_session(ses)).load(last_n=500)
        ack_messages = [{"role": "system", "content": "You are evaluating progress. Consider the conversation so far and answer with a single word: DONE or CONTINUE."}]
        for m in history:
            ack_messages.append({"role": m.role, "content": m.content})
        ack_messages.append({"role": "user", "content": "Are we done? Reply: DONE or CONTINUE."})
        ack = ai.chat(ack_messages)
        mem.append(AIMessage(role="assistant", content=ack, meta={}))
        if "DONE" in ack.upper():
            rprint("[green]AI indicated the objective is complete.[/green]")
            break


