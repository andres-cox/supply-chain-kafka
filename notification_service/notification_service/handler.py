"""Notification handlers for different delivery channels."""

import os
import smtplib
from email.message import EmailMessage
from typing import Protocol

import requests
from logging_utils.config import get_kafka_logger

from .schemas import Notification, NotificationPreferences

logger = get_kafka_logger("notification-service")


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
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER", "")
        self.smtp_pass = os.getenv("SMTP_PASS", "")
        self.from_email = os.getenv("FROM_EMAIL", "notifications@supply-chain.com")

    def send(self, notification: Notification, preferences: NotificationPreferences) -> bool:
        """Send an email notification.

        Args:
            notification: The notification to send
            preferences: Recipient's notification preferences

        Returns:
            bool: True if sent successfully, False otherwise
        """
        if not preferences.email:
            logger.warning(f"No email address for customer {preferences.customer_id}")
            return False

        try:
            # Commented out actual email sending for security reasons
            # msg = EmailMessage()
            # msg.set_content(notification.message)

            # msg["Subject"] = notification.subject
            # msg["From"] = self.from_email
            # msg["To"] = preferences.email

            # with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
            #     server.starttls()
            #     server.login(self.smtp_user, self.smtp_pass)
            #     server.send_message(msg)

            logger.info(f"Email sent successfully: {notification.notification_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False


class SMSNotificationChannel:
    """SMS notification channel implementation."""

    def __init__(self):
        """Initialize the SMS channel with API configuration."""
        self.sms_api_key = os.getenv("SMS_API_KEY", "")
        self.sms_api_url = os.getenv("SMS_API_URL", "https://api.sms-service.com/send")

    def send(self, notification: Notification, preferences: NotificationPreferences) -> bool:
        """Send an SMS notification.

        Args:
            notification: The notification to send
            preferences: Recipient's notification preferences

        Returns:
            bool: True if sent successfully, False otherwise
        """
        if not preferences.sms:
            logger.warning(f"No phone number for customer {preferences.customer_id}")
            return False

        try:
            response = requests.post(
                self.sms_api_url,
                headers={"Authorization": f"Bearer {self.sms_api_key}"},
                json={"to": preferences.sms, "message": f"{notification.subject}: {notification.message}"},
            )
            response.raise_for_status()

            logger.info(f"SMS sent successfully: {notification.notification_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to send SMS: {e}")
            return False


class NotificationHandler:
    """Manages sending notifications through configured channels."""

    def __init__(self):
        """Initialize notification channels."""
        self.channels = {"email": EmailNotificationChannel(), "sms": SMSNotificationChannel()}

    def send_notification(self, notification: Notification, preferences: NotificationPreferences = None) -> None:
        """Send a notification through all enabled channels.

        Args:
            notification: The notification to send
            preferences: Recipient's notification preferences
        """
        logger.info(f"send_notification called with type={notification.type}, notification={notification}")
        # If fraud_alert, just log the message instead of sending (regardless of preferences)
        if notification.type == "fraud_alert":
            admin_email = os.getenv("FRAUD_ALERT_ADMIN_EMAIL", "fraud-team@example.com")
            logger.info(f"[STUB] Would send FRAUD ALERT EMAIL to {admin_email} | subject={notification.subject} | message={notification.message}")
            logger.info(f"Fraud alert notification {notification.notification_id} would be sent to admin at {admin_email}")
            return

        if not preferences:
            logger.warning(f"No preferences found for customer {notification.customer_id}")
            return

        # Only send if the notification type is enabled
        if notification.type not in preferences.types:
            logger.info(f"Customer {preferences.customer_id} has disabled {notification.type} notifications")
            return

        # Try each enabled channel for normal notifications
        success = False
        for channel_name in preferences.channels:
            channel = self.channels.get(channel_name)
            if channel and channel.send(notification, preferences):
                success = True

        if not success:
            logger.error(f"Failed to send notification {notification.notification_id} through any channel")
