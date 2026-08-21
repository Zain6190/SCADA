# infrastructure/notifications/slack_notifier.py
# Slack notification channel using incoming webhooks.
import json
import logging
from typing import Optional

import httpx

from infrastructure.notifications.base import BaseNotifier, AlertNotification

logger = logging.getLogger("aquavision.notifications.slack")


class SlackNotifier(BaseNotifier):
    """Slack notification channel using incoming webhooks."""
    
    SEVERITY_EMOJI = {
        "WATCH": "🔍",
        "ADVISORY": "⚠️",
        "WARNING": "🔶",
        "CRITICAL": "🚨",
    }
    
    SEVERITY_COLOR = {
        "WATCH": "#3b82f6",
        "ADVISORY": "#f59e0b",
        "WARNING": "#f97316",
        "CRITICAL": "#ef4444",
    }
    
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
    
    def is_available(self) -> bool:
        """Check if Slack webhook is configured."""
        return bool(self.webhook_url)
    
    def send(self, notification: AlertNotification, recipient: str) -> bool:
        """Send Slack notification via webhook."""
        if not self.is_available():
            logger.warning("Slack notifier not configured, skipping")
            return False
        
        try:
            emoji = self.SEVERITY_EMOJI.get(notification.severity, "📋")
            color = self.SEVERITY_COLOR.get(notification.severity, "#6b7280")
            
            # Build Slack Block Kit message
            blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"{emoji} [{notification.severity}] {notification.title}",
                        "emoji": True,
                    },
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Source:*\n{notification.source}"},
                        {"type": "mrkdwn", "text": f"*Type:*\n{notification.alert_type}"},
                    ],
                },
            ]
            
            if notification.asset_name:
                blocks[1]["fields"].append(
                    {"type": "mrkdwn", "text": f"*Asset:*\n{notification.asset_name}"}
                )
            
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": notification.message},
            })
            
            if notification.details:
                detail_lines = [f"• *{k}*: {v}" for k, v in notification.details.items()]
                blocks.append({
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": "\n".join(detail_lines)},
                })
            
            payload = {"blocks": blocks}
            
            resp = httpx.post(
                self.webhook_url,
                json=payload,
                timeout=10.0,
            )
            resp.raise_for_status()
            
            logger.info(f"Slack notification sent: {notification.title}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send Slack notification: {e}")
            return False
