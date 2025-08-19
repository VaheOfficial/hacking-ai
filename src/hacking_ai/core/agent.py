import os
import json
from typing import Optional, Dict, Any
from rich.console import Console
from rich.panel import Panel
from ..tools.shell import ShellTool
from ..tools.docs import DocsTool
from ..tools.web import WebTool

console = Console()


class Agent:
	def __init__(self, shell: ShellTool, docs: DocsTool, web: WebTool):
		self.shell = shell
		self.docs = docs
		self.web = web

	def run(self, prompt: str, max_steps: int = 8):
		state: Dict[str, Any] = {"goal": prompt, "notes": []}
		console.print(Panel.fit(f"Goal: {prompt}", title="Agent"))
		for step in range(1, max_steps + 1):
			thought = self._think(state)
			console.print(f"[bold]Thought {step}:[/bold] {thought}")
			action, args = self._choose_action(thought)
			obs = self._act(action, args)
			state["notes"].append({"step": step, "thought": thought, "action": action, "args": args, "observation": obs[:800]})
			console.print(Panel.fit(obs[:1200], title=f"Observation {step}"))
			if self._is_done(state):
				console.print("[bold green]Done.[/bold green]")
				break

	def _think(self, state: Dict[str, Any]) -> str:
		# Lightweight heuristic planner; optionally use OpenAI if configured
		goal = state["goal"].lower()
		if any(k in goal for k in ["privilege", "privesc", "escalation", "gtfobins", "hacktricks"]):
			return "Check docs (HackTricks/GTFOBins), enumerate system info (id, sudo -l, env), then test candidate vectors."
		if any(k in goal for k in ["enumerate", "recon", "scan"]):
			return "Enumerate OS/network/services; consult docs; run safe scans (ip a, ss -tulnp)."
		return "Gather context, consult docs/web, and run minimal safe commands to progress."

	def _choose_action(self, thought: str):
		text = thought.lower()
		if "docs" in text or "hacktricks" in text or "gtfobins" in text:
			return "docs", {"source": "hacktricks", "query": text}
		if "web" in text or "search" in text:
			return "web", {"query": text}
		return "shell", {"command": "whoami && id && uname -a"}

	def _act(self, action: str, args: Dict[str, Any]) -> str:
		if action == "shell":
			res = self.shell.run(args["command"])
			return res.output
		if action == "docs":
			return self.docs.search_and_summarize(args.get("source", "hacktricks"), args.get("query", ""))
		if action == "web":
			return self.web.search_and_summarize(args.get("query", ""))
		return "Unknown action"

	def _is_done(self, state: Dict[str, Any]) -> bool:
		obs = state.get("notes", [])
		# Stop if we have observed at least one shell output and one info source, or 3 steps completed
		has_shell = any(n["action"] == "shell" for n in obs)
		has_info = any(n["action"] in {"docs", "web"} for n in obs)
		return (has_shell and has_info) or len(obs) >= 3