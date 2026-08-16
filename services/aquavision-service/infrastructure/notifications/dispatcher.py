# infrastructure/notifications/dispatcher.py
# Notification dispatcher with persistent deduplication.
# Uses database-backed dedup to survive restarts and support multiple instances.
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from infrastructure.db.models import NotificationDelivery
from infrastructure.notifications.base import BaseNotifier, AlertNotification

logger = logging.getLogger("aquavision.notifications.dispatcher")

# Cooldown periods by severity (in hours)
SEVERITY_COOLDOWNS = {
    "WATCH": 6,        # Digest every 6 hours
    "ADVISORY": 2,     # Every 2 hours while unacknowledged
    "WARNING": 0.5,    # Repeat after 30 minutes if unresolved
    "CRITICAL": 0.17,  # Repeat after 10 minutes if unacknowledged
}


class NotificationDispatcher:
    """Dispatches notifications with persistent deduplication."""
    
    def __init__(self, session: Session, notifiers: List[BaseNotifier]):
        self.session = session
        self.notifiers = notifiers
    
    def dispatch(self, notification: AlertNotification, recipients: List[str]) -> dict:
        """Dispatch notification to all recipients with dedup.
        
        Returns:
            Dict with sent, suppressed, failed counts.
        """
        result = {"sent": 0, "suppressed": 0, "failed": 0}
        
        for recipient in recipients:
            dedup_key = self._build_dedup_key(notification, recipient)
            
            # Check cooldown
            if self._is_in_cooldown(dedup_key, notification.severity):
                result["suppressed"] += 1
                logger.debug(f"Notification suppressed (cooldown): {dedup_key}")
                continue
            
            # Send via all notifiers
            sent = False
            for notifier in self.notifiers:
                if notifier.is_available():
                    try:
                        success = notifier.send(notification, recipient)
                        if success:
                            sent = True
                    except Exception as e:
                        logger.error(f"Notifier failed: {e}")
            
            # Record delivery
            status = "SENT" if sent else "FAILED"
            self._record_delivery(dedup_key, notification, recipient, status)
            
            if sent:
                result["sent"] += 1
            else:
                result["failed"] += 1
        
        return result
    
    def _build_dedup_key(self, notification: AlertNotification, recipient: str) -> str:
        """Build dedup key for persistent tracking."""
        return f"{notification.source}:{notification.alert_type}:{notification.asset_id or 0}:{notification.severity}"
    
    def _is_in_cooldown(self, dedup_key: str, severity: str) -> bool:
        """Check if notification is in cooldown period."""
        cooldown_hours = SEVERITY_COOLDOWNS.get(severity, 1)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=cooldown_hours)
        
        existing = self.session.execute(
            select(NotificationDelivery).where(
                NotificationDelivery.dedup_key == dedup_key,
                NotificationDelivery.status == "SENT",
                NotificationDelivery.sent_at >= cutoff,
            ).order_by(NotificationDelivery.sent_at.desc())
        ).scalar_one_or_none()
        
        return existing is not None
    
    def _record_delivery(
        self,
        dedup_key: str,
        notification: AlertNotification,
        recipient: str,
        status: str,
    ):
        """Record notification delivery for audit and dedup."""
        delivery = NotificationDelivery(
            alert_key=notification.alert_key,
            recipient=recipient,
            channel="EMAIL",
            dedup_key=dedup_key,
            sent_at=datetime.now(timezone.utc) if status == "SENT" else None,
            status=status,
        )
        self.session.add(delivery)
        self.session.commit()
