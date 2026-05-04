---
title: Notifications
description: Slack and Microsoft Teams webhook notifications for pod failures and critical security findings.
---

Kure can push alerts to Slack and Microsoft Teams via incoming webhooks.

## Triggers

A notification is sent when:

- A new pod failure is detected
- A critical security finding is created

## Slack

1. Create an [incoming webhook](https://api.slack.com/messaging/webhooks) in your Slack workspace
2. Copy the webhook URL
3. **Admin Panel → Notification Settings**
4. Pick **Slack**, paste the webhook URL
5. Click **Test** — should drop a test message into your channel
6. Click **Save**

## Microsoft Teams

1. Add an **Incoming Webhook** connector to the channel
2. Copy the webhook URL
3. **Admin Panel → Notification Settings → Teams**
4. Paste the webhook URL → **Test** → **Save**

## Disabling notifications

Toggle the **Enabled** switch off in the Admin panel — settings are preserved so you can re-enable without re-pasting the webhook URL.

## API

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/admin/notifications` | List configured providers |
| `POST` | `/api/admin/notifications` | Create or update a provider |
| `PUT` | `/api/admin/notifications/{provider}` | Update an existing provider |
| `DELETE` | `/api/admin/notifications/{provider}` | Delete a provider |
| `POST` | `/api/admin/notifications/{provider}/test` | Send a test notification |

See the [API Reference](/kure-monitor/reference/api/#admin---notifications) for request bodies.
