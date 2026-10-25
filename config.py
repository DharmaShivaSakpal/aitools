"""Application configuration loaded from the project's `.env` file."""

import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from dotenv import load_dotenv
from rich.console import Console

PROJECT_ROOT = Path(__file__).resolve().parent


class PipelineError(Exception):
	"""Base exception raised when a pipeline stage fails."""


def mask_value(name: str, value: str) -> str:
	"""Redact secrets and remove sensitive URL components from config values.

	Args:
		name: Configuration field name.
		value: String representation of the configuration value.

	Returns:
		A masked secret, URL hostname, or the unchanged value.
	"""
	field_name = name.upper()
	if any(secret_marker in field_name for secret_marker in ("KEY", "TOKEN", "SECRET", "PASSWORD")):
		return "********"
	if field_name.endswith("_URL"):
		return urlparse(value).hostname or ""
	return value


def _normalize_base_url(value: str, *, strip_suffixes: tuple[str, ...] = ("/prompt", "/generate")) -> str:
	"""Drop API path suffixes that are meant to be appended later by the client."""
	trimmed = value.strip()
	if not trimmed:
		return ""
	without_slash = trimmed.rstrip("/")
	for suffix in strip_suffixes:
		if without_slash.lower().endswith(suffix.lower()):
			without_slash = without_slash[: -len(suffix)]
			break
	return without_slash


@dataclass(frozen=True)
class Config:
	"""Typed, immutable values for all supported environment variables."""

	pollinations_text_url: str
	pollinations_image_url: str
	video_api_provider: Literal["mock", "replicate", "fal", "kling"]
	video_api_key: str
	video_api_base_url: str
	output_dir: Path
	cache_dir: Path
	target_resolution: str
	clips_per_scene: int
	pollinations_api_key: str = ""
	ffmpeg_timeout_seconds: int = 600
	tts_voice: str = "en-IN-NeerjaNeural"

	@classmethod
	def load(cls) -> "Config":
		"""Load, validate, and prepare configuration from `.env`.

		Returns:
			A frozen configuration instance with output/cache directories ready.

		Raises:
			ValueError: If required values are missing or invalid.
		"""
		load_dotenv(PROJECT_ROOT / ".env")

		required_urls = {
			"POLLINATIONS_TEXT_URL": _normalize_base_url(os.getenv("POLLINATIONS_TEXT_URL", "")),
			"POLLINATIONS_IMAGE_URL": _normalize_base_url(os.getenv("POLLINATIONS_IMAGE_URL", "")),
		}
		missing = [key for key, value in required_urls.items() if not value or not value.strip()]
		if missing:
			keys = ", ".join(missing)
			raise ValueError(f"Missing required configuration: {keys}. Copy .env.example to .env and set these values.")

		provider_value = os.getenv("VIDEO_API_PROVIDER", "mock").strip().lower()
		supported_providers = ("mock", "replicate", "fal", "kling")
		if provider_value not in supported_providers:
			options = ", ".join(supported_providers)
			raise ValueError(f"VIDEO_API_PROVIDER must be one of: {options}.")

		video_api_key = os.getenv("VIDEO_API_KEY", "").strip()
		video_api_base_url = os.getenv("VIDEO_API_BASE_URL", "").strip()
		if provider_value != "mock":
			missing_video_settings = [
				key
				for key, value in (
					("VIDEO_API_KEY", video_api_key),
					("VIDEO_API_BASE_URL", video_api_base_url),
				)
				if not value or value == "your_video_api_key_here"
			]
			if missing_video_settings:
				keys = ", ".join(missing_video_settings)
				raise ValueError(f"{provider_value} requires valid {keys} values in .env.")

		resolution = os.getenv("TARGET_RESOLUTION", "1920x1080").strip()
		if not re.fullmatch(r"\d+x\d+", resolution):
			raise ValueError("TARGET_RESOLUTION must use WIDTHxHEIGHT format, for example 1920x1080.")

		try:
			clips_per_scene = int(os.getenv("CLIPS_PER_SCENE", "1"))
		except ValueError as error:
			raise ValueError("CLIPS_PER_SCENE must be a positive integer.") from error
		if clips_per_scene < 1:
			raise ValueError("CLIPS_PER_SCENE must be a positive integer.")
		try:
			ffmpeg_timeout_seconds = int(os.getenv("FFMPEG_TIMEOUT_SECONDS", "600"))
		except ValueError as error:
			raise ValueError("FFMPEG_TIMEOUT_SECONDS must be a positive integer.") from error
		if ffmpeg_timeout_seconds <= 0:
			raise ValueError("FFMPEG_TIMEOUT_SECONDS must be a positive integer.")

		def resolve_directory(variable: str, default: str) -> Path:
			directory = Path(os.getenv(variable, default)).expanduser()
			return directory if directory.is_absolute() else PROJECT_ROOT / directory

		output_dir = resolve_directory("OUTPUT_DIR", "./output")
		cache_dir = resolve_directory("CACHE_DIR", "./.cache")
		output_dir.mkdir(parents=True, exist_ok=True)
		cache_dir.mkdir(parents=True, exist_ok=True)

		return cls(
			pollinations_text_url=required_urls["POLLINATIONS_TEXT_URL"].strip(),
			pollinations_image_url=required_urls["POLLINATIONS_IMAGE_URL"].strip(),
			video_api_provider=provider_value,  # type: ignore[arg-type]
			video_api_key=video_api_key,
			video_api_base_url=video_api_base_url,
			output_dir=output_dir,
			cache_dir=cache_dir,
			target_resolution=resolution,
			clips_per_scene=clips_per_scene,
			pollinations_api_key=os.getenv("POLLINATIONS_API_KEY", "").strip(),
			ffmpeg_timeout_seconds=ffmpeg_timeout_seconds,
			tts_voice=os.getenv("TTS_VOICE", "en-IN-NeerjaNeural").strip() or "en-IN-NeerjaNeural",
		)


if __name__ == "__main__":
	config = Config.load()
	assert mask_value(
		"POLLINATIONS_TEXT_URL",
		"https://user:tok@api.example.com/v1?key=abc",
	) == "api.example.com"
	printable_config = {
		key: mask_value(key, str(value))
		for key, value in asdict(config).items()
	}
	Console().print(printable_config)