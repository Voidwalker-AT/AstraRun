"""Safe web URL opening tool."""

from __future__ import annotations

import webbrowser
from urllib.parse import urlparse

from astrarun.core.logging import get_logger

logger = get_logger("astrarun.tools.web")

# Safe schemes allowed for URL tool
ALLOWED_SCHEMES = {"http", "https"}


def open_url(url: str) -> bool:
    """
    Open a web URL safely in the default system browser.
    
    Args:
        url: Absolute HTTP or HTTPS URL.
    """
    parsed = urlparse(url)
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        logger.error("Blocked URL opening with untrusted scheme: %s", url)
        return False

    if not parsed.netloc:
        logger.error("Blocked URL opening without valid domain: %s", url)
        return False

    logger.info("Executing open_url: %s", url)

    try:
        webbrowser.open(url, new=2)
        return True
    except Exception as err:
        logger.error("Failed to open URL '%s': %s", url, err, exc_info=True)
        return False
