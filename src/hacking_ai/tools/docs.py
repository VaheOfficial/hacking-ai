from typing import Literal
from .web import WebTool


class DocsTool:
	def __init__(self):
		self.web = WebTool()

	def search_and_summarize(self, source: str, query: str) -> str:
		source_l = source.lower().strip()
		if source_l in {"hacktricks", "hacktricks.xyz"}:
			q = f"site:hacktricks.xyz {query}"
			return self.web.search_and_summarize(q)
		if source_l in {"gtfobins", "gtfobins.github.io"}:
			q = f"site:gtfobins.github.io {query}"
			return self.web.search_and_summarize(q)
		return f"Unknown source: {source}. Try 'hacktricks' or 'gtfobins'."