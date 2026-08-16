# infrastructure/notifications/base.py
# Abstract notifier interface for alert notifications.
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class AlertNotification:
    """Notification to be sent for an alert."""
    alert_key: str  # source:type:asset_id:episode_id
    alert_type: str  # PIPELINE_FAILURE, DATA_QUALITY, THRESHOLD, etc.
    severity: str  # WATCH, ADVISORY, WARNING, CRITICAL
    asset_id: Optional[int]
    asset_name: Optional[str]
    title: str
    message: str
    source: str  # IRSA, FFD, ML, etc.
    details: Optional[dict] = None


class BaseNotifier(ABC):
    """Abstract base class for notification channels."""
    
    @abstractmethod
    def send(self, notification: AlertNotification, recipient: str) -> bool:
        """Send a notification to a recipient.
        
        Returns True if sent successfully, False otherwise.
        """
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if this notifier is configured and available."""
        pass
