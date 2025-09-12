import os
from dataclasses import dataclass
from typing import List, Optional

from dotenv import load_dotenv


def _parse_int_list(raw: str) -> Optional[List[int]]:
	values = [v.strip() for v in raw.split(',') if v.strip()]
	if not values:
		return None
	ids: List[int] = []
	for v in values:
		try:
			ids.append(int(v))
		except ValueError:
			continue
	return ids or None


def _parse_str_list(raw: str) -> Optional[List[str]]:
	values = [v.strip().lower() for v in raw.split(',') if v.strip()]
	return values or None


@dataclass
class Settings:
	telegram_bot_token: str
	adlinkfly_base_url: str
	adlinkfly_api_key: str
	adlinkfly_api_path: str
	allowed_user_ids: Optional[List[int]]
	admin_user_ids: Optional[List[int]]
	rate_limit_per_min: int
	max_batch: int
	blacklist_domains: Optional[List[str]]
	whitelist_domains: Optional[List[str]]
	inline_mode: bool
	log_level: str

	@staticmethod
	def load() -> "Settings":
		dotenv_path = os.getenv("DOTENV_CONFIG_PATH")
		load_dotenv(dotenv_path if dotenv_path else None)

		telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
		adlinkfly_base_url = os.getenv("ADLINKFLY_BASE_URL", "").strip().rstrip('/')
		adlinkfly_api_key = os.getenv("ADLINKFLY_API_KEY", "").strip()
		adlinkfly_api_path = os.getenv("ADLINKFLY_API_PATH", "/api").strip()
		allowed_user_ids = _parse_int_list(os.getenv("ALLOWED_USER_IDS", ""))
		admin_user_ids = _parse_int_list(os.getenv("ADMIN_USER_IDS", ""))
		rate_limit_per_min = int(os.getenv("RATE_LIMIT_PER_MIN", "20"))
		max_batch = int(os.getenv("MAX_BATCH", "5"))
		blacklist_domains = _parse_str_list(os.getenv("BLACKLIST_DOMAINS", ""))
		whitelist_domains = _parse_str_list(os.getenv("WHITELIST_DOMAINS", ""))
		inline_mode = os.getenv("INLINE_MODE", "true").lower() == "true"
		log_level = os.getenv("LOG_LEVEL", "INFO").upper()

		if not telegram_bot_token:
			raise RuntimeError("TELEGRAM_BOT_TOKEN is required")
		if not adlinkfly_base_url:
			raise RuntimeError("ADLINKFLY_BASE_URL is required")
		if not adlinkfly_api_key:
			raise RuntimeError("ADLINKFLY_API_KEY is required")

		return Settings(
			telegram_bot_token=telegram_bot_token,
			adlinkfly_base_url=adlinkfly_base_url,
			adlinkfly_api_key=adlinkfly_api_key,
			adlinkfly_api_path=adlinkfly_api_path,
			allowed_user_ids=allowed_user_ids,
			admin_user_ids=admin_user_ids,
			rate_limit_per_min=rate_limit_per_min,
			max_batch=max_batch,
			blacklist_domains=blacklist_domains,
			whitelist_domains=whitelist_domains,
			inline_mode=inline_mode,
			log_level=log_level,
		)
