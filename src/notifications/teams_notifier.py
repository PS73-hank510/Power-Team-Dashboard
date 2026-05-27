"""Microsoft Teams notification via Workflow webhook.

Sends Adaptive Card messages to a Teams channel using a Power Automate
Workflow webhook URL. This replaces the deprecated Office 365 Connector.

Setup instructions for the user:
  1. Open the target Teams channel → click "..." → Workflows
  2. Search for "Post to a channel when a webhook request is received"
  3. Complete the setup wizard and copy the webhook URL
  4. Paste the URL into the dashboard Settings panel

The notifier is synchronous — it blocks until the POST completes.
Call from a background thread if latency is a concern.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# Secondary rate-limit guard (primary is in LimitChecker)
_RATE_LIMIT_SECONDS: float = 60.0


class TeamsNotifier:
    """Send alert messages to a Microsoft Teams channel via Workflow webhook.

    Args:
        webhook_url: The Power Automate Workflow webhook URL. If empty or None,
                     all send() calls are silent no-ops.

    Example:
        notifier = TeamsNotifier(webhook_url="https://...")
        notifier.send("UPPER LIMIT BREACH: PSU voltage = 15.32 V (> 15.00 V)")
    """

    def __init__(self, webhook_url: Optional[str] = None) -> None:
        self._webhook_url: str = (webhook_url or "").strip()
        self._last_sent: dict[str, float] = {}

    def update_webhook_url(self, url: str) -> None:
        """Update the webhook URL (e.g. after the user changes it in Settings)."""
        self._webhook_url = (url or "").strip()

    def send(self, message: str, color: str = "Attention") -> bool:
        """Send a message to Teams.

        Args:
            message: Plain-text alert string to display in the Teams card.
            color:   Adaptive Card color — "Attention" (red/orange), "Good" (green),
                     "Warning" (yellow), or "Default".

        Returns:
            True if the message was sent successfully, False otherwise.
        """
        if not self._webhook_url:
            return False

        # Refuse to transmit the webhook bearer token over plain HTTP
        if not self._webhook_url.lower().startswith("https://"):
            logger.warning(
                "Teams webhook URL does not start with https:// — refusing to send. "
                "Update the URL in Settings."
            )
            return False

        # Secondary rate-limit guard (primary enforcement is in LimitChecker)
        now = time.time()
        last = self._last_sent.get(message, 0.0)
        if now - last < _RATE_LIMIT_SECONDS:
            return False
        self._last_sent[message] = now

        payload = self._build_payload(message, color)
        try:
            response = httpx.post(
                self._webhook_url,
                content=json.dumps(payload),
                headers={"Content-Type": "application/json"},
                timeout=10.0,
            )
            response.raise_for_status()
            return True
        except httpx.TimeoutException:
            logger.warning("Teams webhook timed out sending: %s", message)
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Teams webhook HTTP error %s sending: %s",
                exc.response.status_code,
                message,
            )
        except httpx.RequestError as exc:
            logger.warning("Teams webhook request error: %s", exc)
        return False

    def send_alert(self, message: str) -> bool:
        """Send a breach/error alert (red Attention card)."""
        return self.send(message, color="Attention")

    def send_resolved(self, message: str) -> bool:
        """Send a resolution notice (green Good card)."""
        return self.send(message, color="Good")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_payload(message: str, color: str) -> dict:
        """Build the Adaptive Card JSON payload for the Teams Workflow webhook."""
        return {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "body": [
                            {
                                "type": "TextBlock",
                                "text": "⚡ Power Systems Dashboard",
                                "weight": "Bolder",
                                "size": "Medium",
                            },
                            {
                                "type": "TextBlock",
                                "text": message,
                                "wrap": True,
                                "color": color,
                            },
                        ],
                    },
                }
            ],
        }
