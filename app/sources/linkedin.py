"""Bright Data LinkedIn — re-exports from social_registry."""

from __future__ import annotations

from typing import Any

from app.sources import brightdata_social as bs
from app.sources.social_registry import LINKEDIN

DEFAULT_LINKEDIN_DATASET_ID = LINKEDIN.default_dataset_id
MAX_LINKEDIN_URLS = bs.DEFAULT_MAX_URLS


def is_configured() -> bool:
    return bs.is_channel_configured(LINKEDIN)


def get_config() -> dict[str, Any]:
    return bs.channel_config(LINKEDIN)


def normalize_profile_url(url: str) -> str:
    return bs.normalize_url(LINKEDIN, url)


def extract_profile_urls(*blobs: str) -> list[str]:
    return bs.extract_urls(LINKEDIN, *blobs)


def extract_profile_urls_from_web_results(results: list[dict[str, Any]]) -> list[str]:
    return bs.extract_urls_from_web_results(LINKEDIN, results)


def collect_profiles_by_url(urls: list[str], *, max_urls: int = MAX_LINKEDIN_URLS) -> list[dict[str, Any]]:
    return bs.collect_profiles_by_url(LINKEDIN, urls, max_urls=max_urls)


def profile_to_web_result(profile: dict[str, Any]) -> dict[str, str]:
    return LINKEDIN.to_web_result(profile)


def profiles_to_lead_previews(profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return bs.profiles_to_lead_previews(LINKEDIN, profiles)
