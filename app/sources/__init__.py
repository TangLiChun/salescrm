"""Multi-channel search source registry."""

from app.sources import peeringdb, web_search

__all__ = ["peeringdb", "web_search"]


def list_channels() -> dict:
    web_backends = web_search.available_backends()
    return {
        "web_search": web_backends,
        "peeringdb": True,
        "arin_rdap": True,
        "llm_extract": True,
    }
