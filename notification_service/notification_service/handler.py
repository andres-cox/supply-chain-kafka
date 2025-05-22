"""Notification handlers for different delivery channels."""

import os
import smtplib
from email.message import EmailMessage
from typing import Protocol

import requests
from logging_utils.config import get_kafka_logger

from .schemas import Notification, NotificationPreferences

logger = get_kafka_logger("notification-service")

# Default configuration constants
DEFAULT_SMTP_CONFIG = {
    "host": "smtp.gmail.com",
    "port": "587",
    "from_email": "notifications@supply-chain.com",
}

DEFAULT_SMS_CONFIG = {"api_url": "https://api.sms-service.com/send"}

# Error messages
ERROR_MESSAGES = {
    "no_email": "No email address for customer {customer_id}",
    "no_phone": "No phone number for customer {customer_id}",
    "no_preferences": "No preferences found for customer {customer_id}",
    "type_disabled": "Customer {customer_id} has disabled {notification_type} notifications",
    "send_failed": "Failed to send notification {notification_id} through any channel",
    "email_failed": "Failed to send email: {error}",
    "sms_failed": "Failed to send SMS: {error}",
}


class NotificationChannel(Protocol):
    """Protocol defining the interface for notification channels."""

    def send(self, notification: Notification, preferences: NotificationPreferences) -> bool:
        """Send a notification through this channel.

        Args:
            notification: The notification to send
            preferences: Recipient's notification preferences

        Returns:
            bool: True if sent successfully, False otherwise
        """
        ...


class EmailNotificationChannel:
    """Email notification channel implementation."""

    def __init__(self):
        """Initialize the email channel with SMTP configuration."""
        self.smtp_host = os.getenv("SMTP_HOST", DEFAULT_SMTP_CONFIG["host"])
        self.smtp_port = int(os.getenv("SMTP_PORT", DEFAULT_SMTP_CONFIG["port"]))
        self.smtp_user = os.getenv("SMTP_USER", "")
        self.smtp_pass = os.getenv("SMTP_PASS", "")
        self.from_email = os.getenv("FROM_EMAIL", DEFAULT_SMTP_CONFIG["from_email"])

    def send(self, notification: Notification, preferences: NotificationPreferences) -> bool:
        """Send an email notification.

        Args:
            notification: The notification to send
            preferences: Recipient's notification preferences

        Returns:
            bool: True if sent successfully, False otherwise
        """
        if not preferences.email:
            logger.warning(ERROR_MESSAGES["no_email"].format(customer_id=preferences.customer_id))
            return False

        try:
            msg = EmailMessage()
            msg.set_content(notification.message)

            msg["Subject"] = notification.subject
            msg["From"] = self.from_email
            msg["To"] = preferences.email

            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_pass)
                server.send_message(msg)

            logger.info(f"Email sent successfully: {notification.notification_id}")
            return True

        except Exception as e:
            logger.error(ERROR_MESSAGES["email_failed"].format(error=str(e)))
            return False


class SMSNotificationChannel:
    """SMS notification channel implementation."""

    def __init__(self):
        """Initialize the SMS channel with API configuration."""
        self.sms_api_key = os.getenv("SMS_API_KEY", "")
        self.sms_api_url = os.getenv("SMS_API_URL", DEFAULT_SMS_CONFIG["api_url"])

    def send(self, notification: Notification, preferences: NotificationPreferences) -> bool:
        """Send an SMS notification.

        Args:
            notification: The notification to send
            preferences: Recipient's notification preferences

        Returns:
            bool: True if sent successfully, False otherwise
        """
        if not preferences.sms:
            logger.warning(ERROR_MESSAGES["no_phone"].format(customer_id=preferences.customer_id))
            return False

        try:
            response = requests.post(
                self.sms_api_url,
                headers={"Authorization": f"Bearer {self.sms_api_key}"},
                json={"to": preferences.sms, "message": f"{notification.subject}: {notification.message}"},
                timeout=10,  # Add timeout for safety
            )
            response.raise_for_status()

            logger.info(f"SMS sent successfully: {notification.notification_id}")
            return True

        except Exception as e:
            logger.error(ERROR_MESSAGES["sms_failed"].format(error=str(e)))
            return False


class NotificationHandler:
    """Manages sending notifications through configured channels."""

    def __init__(self):
        """Initialize notification channels."""
        self.channels = {"email": EmailNotificationChannel(), "sms": SMSNotificationChannel()}

    def send_notification(self, notification: Notification, preferences: NotificationPreferences) -> bool:
        """Send a notification through all enabled channels.

        Args:
            notification: The notification to send
            preferences: Recipient's notification preferences

        Returns:
            bool: True if the notification was sent successfully through at least one channel
        """
        if not preferences:
            logger.warning(ERROR_MESSAGES["no_preferences"].format(customer_id=notification.customer_id))
            return False

        # Only send if the notification type is enabled
        if notification.type not in preferences.types:
            logger.info(
                ERROR_MESSAGES["type_disabled"].format(
                    customer_id=preferences.customer_id, notification_type=notification.type
                )
            )
            return False

        # Try each enabled channel
        success = False
        for channel_name in preferences.channels:
            try:
                channel = self.channels.get(channel_name)
                if channel and channel.send(notification, preferences):
                    success = True
            except Exception as e:
                logger.error(f"Unexpected error in {channel_name} channel: {e}")
                continue

        if not success:
            logger.error(ERROR_MESSAGES["send_failed"].format(notification_id=notification.notification_id))

        return success
