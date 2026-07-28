---
title: Notifications
description: Slack and Microsoft Teams notifications for pod failures and critical security findings.
---

Kure can push alerts to Slack and Microsoft Teams. For Slack, Kure supports a full ChatOps experience (App Mode) or simple Webhooks.

## Triggers

A notification is sent when:

- A new pod failure is detected
- A pod failure is resolved (Slack App Mode only)
- A critical security finding is created

## Slack

### Option 1: App Mode (Recommended)
App Mode enables advanced features: **Interactive AI Troubleshooting**, **Threaded Chat**, and **Resolution Notifications**.

1. In the Kure Monitor repo, copy the contents of `docs/configuration/slack_manifest.json`.
2. Go to [api.slack.com/apps](https://api.slack.com/apps) and click **Create New App** → **From an app manifest**.
3. Select your workspace and paste the JSON.
4. Go to **Install App** in the sidebar and install it to your workspace.
5. Copy the **Bot User OAuth Token** (starts with `xoxb-`).
6. Go to **Basic Information** and copy the **Signing Secret**.
7. In the Kure Monitor **Admin Panel → Notification Settings**, select **Slack**.
8. Set the Mode to **App**.
9. Paste your Token, Signing Secret, and target Channel ID (e.g., `C12345678`).
10. Click **Test** and **Save**.
11. Finally, **invite the bot** to your Slack channel (e.g., type `/invite @Kure Monitor` in the channel).

### Option 2: Webhook Mode (Basic)
If you only need one-way alerts without AI ChatOps:

1. Create an [incoming webhook](https://api.slack.com/messaging/webhooks) in your Slack workspace.
2. Copy the webhook URL.
3. In the Kure Monitor **Admin Panel → Notification Settings**, pick **Slack**.
4. Set the Mode to **Webhook** and paste the URL.
5. Click **Test** and **Save**.

## Microsoft Teams

For Microsoft Teams, you must use a Microsoft 365 Work or School account to create Webhooks or Workflows.

### Option 1: Interactive Mode (ChatOps)
This mode adds a **🔍 Troubleshoot** button to your Teams alerts. When clicked, Kure generates an AI analysis and posts the solution back to the channel.

1. In Microsoft Teams, go to your channel.
2. Click the `...` menu and select **Workflows** (or Connectors).
3. Search for "Post to a channel when a webhook request is received" (or "Incoming Webhook").
4. Follow the prompts to create the workflow and copy the **Webhook URL**.
5. In the Kure Monitor **Admin Panel → Notification Settings**, pick **Microsoft Teams**.
6. Set the Mode to **Interactive (ChatOps)**.
7. Paste the **Webhook URL**.
8. In the **Kure Public URL** field, paste your public-facing Kure URL (e.g., your `ngrok` tunnel URL) so Teams can send the button click back to Kure.
9. Click **Test** and **Save**.

### Option 2: Webhook Mode (Alerts Only)
If you only want basic alerts without the interactive Troubleshoot button:

1. Generate a **Webhook URL** in Teams (using Workflows or Connectors).
2. In the Kure Monitor **Admin Panel**, pick **Microsoft Teams**.
3. Set the Mode to **Webhook (alerts only)** and paste the URL.
4. Click **Test** and **Save**.

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
