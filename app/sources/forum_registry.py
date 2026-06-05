"""Hosting forum channels: LowEndTalk, WebHostingTalk."""

from __future__ import annotations

from dataclasses import dataclass

from app.settings_store import get_setting


@dataclass(frozen=True)
class ForumSpec:
    key: str
    label: str
    domain: str
    enabled_setting: str
    search_url: str
    requires_unlocker: bool


LOWENDTALK = ForumSpec(
    key="lowendtalk",
    label="LowEndTalk",
    domain="lowendtalk.com",
    enabled_setting="lowendtalk_enabled",
    search_url="https://lowendtalk.com/search/search?keywords={query}&order=relevance",
    requires_unlocker=False,
)

WEBHOSTINGTALK = ForumSpec(
    key="webhostingtalk",
    label="WebHostingTalk",
    domain="webhostingtalk.com",
    enabled_setting="webhostingtalk_enabled",
    search_url="https://www.webhostingtalk.com/search/1/?q={query}&o=relevance",
    requires_unlocker=True,
)

FORUM_CHANNELS: tuple[ForumSpec, ...] = (LOWENDTALK, WEBHOSTINGTALK)


def is_channel_enabled(spec: ForumSpec) -> bool:
    return get_setting(spec.enabled_setting, "1").strip() != "0"


def is_channel_configured(spec: ForumSpec) -> bool:
    return is_channel_enabled(spec)


def configured_channels() -> list[ForumSpec]:
    return [spec for spec in FORUM_CHANNELS if is_channel_configured(spec)]


def channel_config(spec: ForumSpec) -> dict:
    from app.sources import web_unlocker

    return {
        "key": spec.key,
        "label": spec.label,
        "domain": spec.domain,
        "enabled": is_channel_enabled(spec),
        "configured": is_channel_configured(spec),
        "requires_unlocker": spec.requires_unlocker,
        "unlocker_configured": web_unlocker.is_configured(),
        "search_url_template": spec.search_url,
    }


def get_all_configs() -> dict[str, dict]:
    return {spec.key: channel_config(spec) for spec in FORUM_CHANNELS}
