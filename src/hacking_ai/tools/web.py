import time
import requests
from bs4 import BeautifulSoup
from typing import List, Tuple
from urllib.parse import urlparse, parse_qs, unquote, urljoin

DEFAULT_HEADERS = {
	"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
}


class WebTool:
	def __init__(self, timeout: int = 15):
		self.timeout = timeout

	def _normalize_url(self, href: str, base: str) -> str:
		if not href:
			return href
		# Resolve relative URLs
		abs_url = urljoin(base, href)
		# Fix schema-less //example.com
		if abs_url.startswith("//"):
			abs_url = "https:" + abs_url
		# Unwrap DuckDuckGo redirector /l/?uddg=
		parsed = urlparse(abs_url)
		if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
			params = parse_qs(parsed.query)
			uddg = params.get("uddg", [None])[0]
			if uddg:
				try:
					return unquote(uddg)
				except Exception:
					return abs_url
		return abs_url

	def search_duckduckgo(self, query: str, max_results: int = 5) -> List[Tuple[str, str]]:
		url = "https://duckduckgo.com/html/"
		params = {"q": query}
		resp = requests.get(url, params=params, headers=DEFAULT_HEADERS, timeout=self.timeout)
		soup = BeautifulSoup(resp.text, "html.parser")
		results = []
		for a in soup.select("a.result__a"):
			title = a.get_text(" ", strip=True)
			href_raw = a.get("href")
			href = self._normalize_url(href_raw, url)
			if href and title:
				results.append((title, href))
				if len(results) >= max_results:
					break
		return results

	def fetch_text(self, url: str, max_chars: int = 4000) -> str:
		if url.startswith("//"):
			url = "https:" + url
		resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=self.timeout)
		soup = BeautifulSoup(resp.text, "html.parser")
		# Remove script/style/nav
		for tag in soup(["script", "style", "nav", "footer", "header"]):
			tag.decompose()
		text = " ".join(t.strip() for t in soup.stripped_strings)
		return text[:max_chars]

	def summarize(self, text: str, max_chars: int = 1000) -> str:
		if not text:
			return "No content"
		# Simple heuristic summary: first N chars with sentence boundary if possible
		cut = text[:max_chars]
		last_dot = cut.rfind(".")
		if last_dot > max_chars * 0.5:
			return cut[: last_dot + 1]
		return cut

	def search_and_summarize(self, query: str) -> str:
		results = self.search_duckduckgo(query, max_results=3)
		chunks: List[str] = []
		for title, href in results:
			try:
				text = self.fetch_text(href)
				chunks.append(f"[Source] {title} - {href}\n{self.summarize(text)}")
			except Exception as exc:
				chunks.append(f"[Source] {title} - {href}\nError fetching: {exc}")
			# be polite
			time.sleep(1.0)
		return "\n\n".join(chunks) if chunks else "No results"