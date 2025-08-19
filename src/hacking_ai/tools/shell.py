import os
import re
import shlex
import subprocess
import platform
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class RunResult:
	return_code: int
	output: str


class ShellTool:
	SAFE_PREFIXES = (
		"whoami",
		"id",
		"uname",
		"ls",
		"dir",
		"pwd",
		"cat ",
		"type ",
		"echo ",
		"env",
		"printenv",
		"ifconfig",
		"ip ",
		"ss ",
		"netstat ",
		"ps ",
		"tasklist",
		"sudo -l",
	)

	DANGEROUS_PATTERNS = [
		r"\brm\b.*\-rf",
		r"\bdd\b.*\bof=|\bto=",
		r"\bmkfs\b",
		r"\bmount\b.*\-o remount,rw",
		r"\bchmod\b.* 777\b",
		r"\bchown\b.* root:\w+",
		r"\bshutdown\b|\breboot\b|\bhalt\b",
		r"\bpoweroff\b",
		r"\b:.*\(\)\{.*:.*\|:.*;\}\s*;?\s*:\s*\|:\s*&\s*\}",  # fork bomb
		r"curl\b.*\|\s*sh\b|wget\b.*\|\s*sh\b",
		r"\bformat\-volume\b|\bremove\-item\b.*\-recurse\s*\-force",
	]

	def __init__(self, auto_confirm: bool = False, working_dir: Optional[str] = None):
		self.auto_confirm = auto_confirm
		self.working_dir = working_dir or os.getcwd()
		self.system = platform.system().lower()

	def run(self, command: str) -> RunResult:
		command = command.strip()
		if not command:
			return RunResult(return_code=1, output="Empty command")

		if self._looks_dangerous(command) and not self._confirm(command):
			return RunResult(return_code=2, output="Command rejected by safety policy")

		return self._execute(command)

	def _execute(self, command: str) -> RunResult:
		if self.system.startswith("windows"):
			# Prefer PowerShell if available
			shell_exe = os.environ.get("COMSPEC", "powershell")
			if "powershell" in shell_exe.lower() or shell_exe.endswith("pwsh.exe"):
				args = ["powershell", "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command]
			else:
				args = [shell_exe, "/c", command]
		else:
			args = ["/bin/bash", "-lc", command]

		try:
			proc = subprocess.run(
				args,
				cwd=self.working_dir,
				env=os.environ.copy(),
				stdout=subprocess.PIPE,
				stderr=subprocess.STDOUT,
				text=True,
				timeout=300,
			)
			return RunResult(return_code=proc.returncode, output=proc.stdout)
		except subprocess.TimeoutExpired:
			return RunResult(return_code=124, output="Command timed out")
		except Exception as exc:
			return RunResult(return_code=1, output=f"Execution error: {exc}")

	def _looks_dangerous(self, command: str) -> bool:
		# Allow safe prefixes quickly
		if any(command.startswith(pref) for pref in self.SAFE_PREFIXES):
			return False
		joined = command.lower()
		for pattern in self.DANGEROUS_PATTERNS:
			if re.search(pattern, joined):
				return True
		return False

	def _confirm(self, command: str) -> bool:
		if self.auto_confirm:
			return True
		try:
			resp = input(f"Approve command?\n{command}\n[y/N]: ").strip().lower()
			return resp in {"y", "yes"}
		except EOFError:
			return False