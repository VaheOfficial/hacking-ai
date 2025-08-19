import os
import platform
import typer
from rich.console import Console
from .core.agent import Agent
from .tools.shell import ShellTool
from .tools.docs import DocsTool
from .tools.web import WebTool

app = typer.Typer(add_completion=False, help="Hacking AI - Ethical security research assistant")
console = Console()


@app.command()
def agent(
	prompt: str = typer.Argument(None, help="Goal or task for the agent. If omitted, runs interactive mode."),
	max_steps: int = typer.Option(8, help="Maximum number of reasoning/act steps"),
	no_confirm: bool = typer.Option(False, help="Run commands without interactive confirmation"),
):
	"""Run the agent loop."""
	shell = ShellTool(auto_confirm=no_confirm)
	docs = DocsTool()
	web = WebTool()
	agent = Agent(shell=shell, docs=docs, web=web)
	if prompt:
		agent.run(prompt=prompt, max_steps=max_steps)
	else:
		console.print("[bold]Interactive mode. Type 'exit' to quit.[/bold]")
		while True:
			user = input("agent> ").strip()
			if user.lower() in {"exit", "quit"}:
				break
			agent.run(prompt=user, max_steps=max_steps)


@app.command()
def cmd(command: str, no_confirm: bool = typer.Option(False, help="Run without confirmation")):
	"""Run a single OS-aware command safely."""
	shell = ShellTool(auto_confirm=no_confirm)
	result = shell.run(command)
	console.print(result.output)
	if result.return_code != 0:
		typer.Exit(code=result.return_code)


@app.command()
def docs(source: str = typer.Argument(..., help="hacktricks|gtfobins"), query: str = typer.Argument(...)):
	"""Search security docs and summarize."""
	d = DocsTool()
	text = d.search_and_summarize(source=source, query=query)
	console.print(text)


@app.command()
def web(query: str = typer.Argument(..., help="Search query")):
	"""Search the web and summarize top hits."""
	w = WebTool()
	console.print(w.search_and_summarize(query))


if __name__ == "__main__":
	app()