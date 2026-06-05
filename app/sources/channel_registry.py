"""Registry of data channels available to lead discovery and Pi tools."""

from __future__ import annotations

from typing import Any

from app.sources import forum_registry
from app.sources import peeringdb, shodan, web_search, web_unlocker
from app.sources.social_registry import SOCIAL_CHANNELS, configured_channels, get_all_configs
from app.sources import brightdata_social as bs


def list_channels() -> dict[str, Any]:
    """Summary flags/channels for UI and discover_leads plan."""
    social = {spec.key: bs.is_channel_configured(spec) for spec in SOCIAL_CHANNELS}
    hosting_forums = {
        spec.key: forum_registry.is_channel_configured(spec)
        for spec in forum_registry.FORUM_CHANNELS
    }
    return {
        "web_search": web_search.available_backends(),
        "peeringdb": True,
        "shodan": shodan.is_configured(),
        "web_unlocker": web_unlocker.is_configured(),
        "arin_rdap": True,
        **hosting_forums,
        **social,
        "llm_extract": True,
        "llm_scoring": True,
    }


def get_channel_config() -> dict[str, Any]:
    """Detailed configuration snapshot for settings / get_search_config."""
    web = web_search.get_search_config()
    social_configs = get_all_configs()
    return {
        **web,
        "data_channels": list_channels(),
        "social_profiles": social_configs,
        "linkedin_profiles": social_configs.get("linkedin"),
        "x_profiles": social_configs.get("x"),
        "facebook_profiles": social_configs.get("facebook"),
        "social_configured": [spec.key for spec in configured_channels()],
        "shodan": shodan.get_config(),
        "web_unlocker": web_unlocker.get_config(),
        "hosting_forums": forum_registry.get_all_configs(),
    }
