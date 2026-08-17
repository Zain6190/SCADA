# infrastructure/notifications/email_notifier.py
# Email notification channel using SMTP.
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

from infrastructure.notifications.base import BaseNotifier, AlertNotification

logger = logging.getLogger("aquavision.notifications.email")


class EmailNotifier(BaseNotifier):
    """Email notification channel using SMTP."""
    
    def __init__(
        self,
        smtp_host: str,
        smtp_port: int = 587,
        username: Optional[str] = None,
        password: Optional[str] = None,
        from_addr: Optional[str] = None,
        use_tls: bool = True,
    ):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.from_addr = from_addr or username
        self.use_tls = use_tls
    
    def is_available(self) -> bool:
        """Check if SMTP is configured."""
        return bool(self.smtp_host and self.username and self.password)
    
    def send(self, notification: AlertNotification, recipient: str) -> bool:
        """Send email notification."""
        if not self.is_available():
            logger.warning("Email notifier not configured, skipping")
            return False
        
        try:
            # Build email
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"[{notification.severity}] {notification.title}"
            msg["From"] = self.from_addr
            msg["To"] = recipient
            
            # Plain text body
            body = self._build_body(notification)
            msg.attach(MIMEText(body, "plain"))
            
            # HTML body
            html_body = self._build_html(notification)
            msg.attach(MIMEText(html_body, "html"))
            
            # Send via SMTP
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                if self.use_tls:
                    server.starttls()
                if self.username and self.password:
                    server.login(self.username, self.password)
                server.sendmail(self.from_addr, [recipient], msg.as_string())
            
            logger.info(f"Email sent to {recipient}: {notification.title}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email to {recipient}: {e}")
            return False
    
    def _build_body(self, notification: AlertNotification) -> str:
        """Build plain text email body."""
        lines = [
            f"Alert: {notification.title}",
            f"Severity: {notification.severity}",
            f"Source: {notification.source}",
            f"Type: {notification.alert_type}",
        ]
        if notification.asset_name:
            lines.append(f"Asset: {notification.asset_name}")
        lines.append("")
        lines.append(notification.message)
        if notification.details:
            lines.append("")
            lines.append("Details:")
            for k, v in notification.details.items():
                lines.append(f"  {k}: {v}")
        return "\n".join(lines)
    
    def _build_html(self, notification: AlertNotification) -> str:
        """Build HTML email body."""
        severity_colors = {
            "WATCH": "#3b82f6",
            "ADVISORY": "#f59e0b",
            "WARNING": "#f97316",
            "CRITICAL": "#ef4444",
        }
        color = severity_colors.get(notification.severity, "#6b7280")
        
        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <div style="border-left: 4px solid {color}; padding-left: 16px;">
                <h2 style="color: {color}; margin: 0;">[{notification.severity}] {notification.title}</h2>
                <p style="color: #6b7280; margin: 8px 0;">Source: {notification.source} | Type: {notification.alert_type}</p>
                {"<p><strong>Asset:</strong> " + notification.asset_name + "</p>" if notification.asset_name else ""}
                <p>{notification.message}</p>
            </div>
        </body>
        </html>
        """
        return html
