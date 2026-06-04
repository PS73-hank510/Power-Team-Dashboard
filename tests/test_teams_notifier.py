"""Tests for TeamsNotifier — payload shape, error handling, and no-op behaviour."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.notifications.teams_notifier import TeamsNotifier


# ------------------------------------------------------------------
# Payload shape  (plain-text {"text": "..."} format)
# ------------------------------------------------------------------

def test_payload_has_text_key():
    """Payload must use the plain-text 'text' field, not Adaptive Cards."""
    notifier = TeamsNotifier("https://example.com/webhook")
    payload = notifier._build_payload("Test message", "Attention")
    assert "text" in payload
    assert isinstance(payload["text"], str)


def test_payload_has_no_attachments():
    """Plain-text format must NOT include an Adaptive Card attachments list."""
    notifier = TeamsNotifier("https://example.com/webhook")
    payload = notifier._build_payload("Test", "Attention")
    assert "attachments" not in payload


def test_payload_text_contains_header():
    """The text body must include the dashboard header line."""
    notifier = TeamsNotifier("https://example.com/webhook")
    payload = notifier._build_payload("Test", "Attention")
    assert "Power Systems Dashboard" in payload["text"]


def test_payload_text_is_single_string():
    """The entire payload must be a single-key dict with a string value."""
    notifier = TeamsNotifier("https://example.com/webhook")
    payload = notifier._build_payload("Test", "Attention")
    assert len(payload) == 1


def test_payload_body_contains_message():
    notifier = TeamsNotifier("https://example.com/webhook")
    payload = notifier._build_payload("UPPER LIMIT BREACH: voltage", "Attention")
    assert "UPPER LIMIT BREACH: voltage" in payload["text"]


def test_payload_color_applied():
    """Attention → 🔴, Good → 🟢, Warning → 🟡 in the text body."""
    notifier = TeamsNotifier("https://example.com/webhook")
    assert "🔴" in notifier._build_payload("msg", "Attention")["text"]
    assert "🟢" in notifier._build_payload("msg", "Good")["text"]
    assert "🟡" in notifier._build_payload("msg", "Warning")["text"]


# ------------------------------------------------------------------
# Successful send
# ------------------------------------------------------------------

def test_send_posts_to_correct_url():
    notifier = TeamsNotifier("https://example.com/webhook")
    with patch("httpx.post") as mock_post:
        mock_post.return_value = MagicMock(raise_for_status=lambda: None)
        result = notifier.send("test message")
    assert result is True
    mock_post.assert_called_once()
    call_url = mock_post.call_args[0][0]
    assert call_url == "https://example.com/webhook"


def test_send_uses_json_content_type():
    notifier = TeamsNotifier("https://example.com/webhook")
    with patch("httpx.post") as mock_post:
        mock_post.return_value = MagicMock(raise_for_status=lambda: None)
        notifier.send("test")
    headers = mock_post.call_args[1].get("headers", {})
    assert headers.get("Content-Type") == "application/json"


# ------------------------------------------------------------------
# Empty / None webhook URL — no-op
# ------------------------------------------------------------------

def test_empty_url_is_noop():
    notifier = TeamsNotifier("")
    with patch("httpx.post") as mock_post:
        result = notifier.send("test")
    mock_post.assert_not_called()
    assert result is False


def test_none_url_is_noop():
    notifier = TeamsNotifier(None)
    with patch("httpx.post") as mock_post:
        result = notifier.send("test")
    mock_post.assert_not_called()
    assert result is False


def test_whitespace_url_is_noop():
    notifier = TeamsNotifier("   ")
    with patch("httpx.post") as mock_post:
        result = notifier.send("test")
    mock_post.assert_not_called()
    assert result is False


# ------------------------------------------------------------------
# Error handling — must never raise
# ------------------------------------------------------------------

def test_timeout_returns_false_does_not_raise():
    notifier = TeamsNotifier("https://example.com/webhook")
    with patch("httpx.post", side_effect=httpx.TimeoutException("timeout")):
        result = notifier.send("test")
    assert result is False


def test_http_status_error_returns_false():
    notifier = TeamsNotifier("https://example.com/webhook")
    mock_response = MagicMock()
    mock_response.status_code = 500
    with patch("httpx.post") as mock_post:
        mock_post.return_value = MagicMock(
            raise_for_status=MagicMock(
                side_effect=httpx.HTTPStatusError("err", request=MagicMock(), response=mock_response)
            )
        )
        result = notifier.send("test")
    assert result is False


def test_request_error_returns_false():
    notifier = TeamsNotifier("https://example.com/webhook")
    with patch("httpx.post", side_effect=httpx.RequestError("conn error")):
        result = notifier.send("test")
    assert result is False


# ------------------------------------------------------------------
# Convenience methods
# ------------------------------------------------------------------

def test_send_alert_uses_attention_color():
    notifier = TeamsNotifier("https://example.com/webhook")
    with patch.object(notifier, "send") as mock_send:
        mock_send.return_value = True
        notifier.send_alert("breach")
    mock_send.assert_called_once_with("breach", color="Attention")


def test_send_resolved_uses_good_color():
    notifier = TeamsNotifier("https://example.com/webhook")
    with patch.object(notifier, "send") as mock_send:
        mock_send.return_value = True
        notifier.send_resolved("resolved")
    mock_send.assert_called_once_with("resolved", color="Good")


# ------------------------------------------------------------------
# update_webhook_url
# ------------------------------------------------------------------

def test_update_webhook_url():
    notifier = TeamsNotifier("")
    notifier.update_webhook_url("https://new.example.com/wh")
    with patch("httpx.post") as mock_post:
        mock_post.return_value = MagicMock(raise_for_status=lambda: None)
        result = notifier.send("test")
    assert result is True
    assert mock_post.call_args[0][0] == "https://new.example.com/wh"


# ------------------------------------------------------------------
# HTTPS enforcement
# ------------------------------------------------------------------

def test_http_url_is_refused():
    """Plain HTTP URLs must be rejected — the webhook token must not travel unencrypted."""
    notifier = TeamsNotifier("http://example.com/webhook")
    with patch("httpx.post") as mock_post:
        result = notifier.send("test")
    mock_post.assert_not_called()
    assert result is False


def test_https_url_is_accepted():
    """HTTPS URL must be allowed through."""
    notifier = TeamsNotifier("https://example.com/webhook")
    with patch("httpx.post") as mock_post:
        mock_post.return_value = MagicMock(raise_for_status=lambda: None)
        result = notifier.send("test")
    assert result is True


def test_http_url_case_insensitive():
    """Scheme check is case-insensitive — HTTP:// must also be refused."""
    notifier = TeamsNotifier("HTTP://example.com/webhook")
    with patch("httpx.post") as mock_post:
        result = notifier.send("test")
    mock_post.assert_not_called()
    assert result is False


# ------------------------------------------------------------------
# Secondary rate-limit guard
# ------------------------------------------------------------------

def test_same_message_rate_limited_within_60s():
    """Sending the same message twice within 60 s should suppress the second send."""
    notifier = TeamsNotifier("https://example.com/webhook")
    with patch("httpx.post") as mock_post:
        mock_post.return_value = MagicMock(raise_for_status=lambda: None)
        first = notifier.send("breach alert")
        second = notifier.send("breach alert")  # within the same second
    assert first is True
    assert second is False
    assert mock_post.call_count == 1


def test_different_messages_not_rate_limited():
    """Different messages must each be sent independently."""
    notifier = TeamsNotifier("https://example.com/webhook")
    with patch("httpx.post") as mock_post:
        mock_post.return_value = MagicMock(raise_for_status=lambda: None)
        notifier.send("voltage breach")
        notifier.send("current breach")  # different message
    assert mock_post.call_count == 2
