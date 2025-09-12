from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional
from urllib.parse import urlencode

import aiohttp
import backoff

logger = logging.getLogger(__name__)


class AdLinkFlyClient:
	def __init__(self, base_url: str, api_key: str, api_path: str = "/api") -> None:
		self._base_url = base_url.rstrip('/')
		self._default_api_key = api_key
		self._api_path = api_path if api_path.startswith('/') else f"/{api_path}"
		self._session: Optional[aiohttp.ClientSession] = None

	async def __aenter__(self) -> "AdLinkFlyClient":
		await self.ensure_session()
		return self

	async def __aexit__(self, exc_type, exc, tb) -> None:
		await self.close()

	async def ensure_session(self) -> aiohttp.ClientSession:
		if self._session is None or self._session.closed:
			self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20))
		return self._session

	async def close(self) -> None:
		if self._session and not self._session.closed:
			await self._session.close()

	@backoff.on_exception(backoff.expo, (aiohttp.ClientError, asyncio.TimeoutError), max_time=30)
	async def shorten(self, long_url: str, alias: Optional[str] = None, api_key_override: Optional[str] = None) -> str:
		session = await self.ensure_session()
		api_key = api_key_override or self._default_api_key
		query = {"api": api_key, "url": long_url}
		if alias:
			query["alias"] = alias
		endpoint = f"{self._base_url}{self._api_path}"
		url = f"{endpoint}?{urlencode(query)}"

		logger.debug("AdLinkFly request: %s", url)
		async with session.get(url, headers={"Accept": "application/json"}) as resp:
			text = await resp.text()
			logger.debug("AdLinkFly response status=%s body=%s", resp.status, text)
			if resp.status >= 500:
				raise aiohttp.ClientError(f"Server error {resp.status}")
			if resp.status >= 400:
				raise ValueError(f"AdLinkFly returned {resp.status}: {text}")

			try:
				data = json.loads(text)
			except json.JSONDecodeError:
				if text.strip().startswith("http"):
					return text.strip()
				raise ValueError("Unexpected response format from AdLinkFly")

			for key in ("shortenedUrl", "short", "short_url", "url"):
				if key in data and isinstance(data[key], str) and data[key].startswith("http"):
					return data[key]

			raise ValueError(f"Unable to parse short URL from response: {data}")
