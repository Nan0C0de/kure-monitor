---
title: LLM Providers
description: Supported LLM providers and configuration for Kure Monitor's AI-powered troubleshooting.
---

Kure Monitor uses an LLM to generate contextual fixes for pod failures and security findings. The provider is configured **after install** from the **Admin Panel → AI Configuration** — no API keys at install time.

## Supported Providers

Kure Monitor **supports almost any LLM provider**! 

Whether you are using a managed cloud service or running an air-gapped local model, Kure has you covered:

- **Local AI Auto-Detect**: Kure automatically scans your Kubernetes cluster's services for local LLMs (like Ollama, vLLM, LocalAI, TGI, or NVIDIA NIM). With a single click in the Admin panel, it automatically retrieves the service URL and lists the available models you have loaded.
- **Predefined Providers**: For convenience, we offer quick-select options for **Anthropic**, **Google Gemini**, and **GitHub Copilot**.
- **Custom Provider**: For everything else (OpenAI, Groq, DeepSeek, or any other API), use the **Custom** option.

### The "Custom" Provider

The Custom provider allows you to connect to absolutely any OpenAI-compatible API. 

When you select Custom, you need to provide:
1. **Base URL**: The API endpoint (e.g., `https://api.openai.com/v1`, `https://api.groq.com/openai/v1`)
2. **API Key**: Your secret token.
3. **Model Name**: Type in the exact name of the model you want to use (e.g., `gpt-5.5-mini`, `llama-3.3-70b-versatile`, `qwen2.5:72b`).

## Configuring a provider

1. Open the dashboard.
2. Go to **Admin Panel → AI Configuration**.
3. Select either a **Predefined Provider** (like Anthropic), **Auto-Detect** (for cluster models), or **Custom**.
4. Fill in your Base URL, API Key, and Model name (or select them from the auto-detected dropdown).
5. Click **Test Connection** — this verifies that your key and URL work.
6. Click **Save Configuration**.

If the LLM call ever fails at runtime (e.g., due to rate limits), Kure falls back to rule-based solutions so the dashboard always stays useful.

## Rotating an API key

1. Generate a new key with your provider.
2. Go to **Admin Panel → AI Configuration**.
3. Replace the existing key.
4. Click **Test Connection** → **Save**.

LLM API keys are encrypted at rest using a Fernet key (`security.encryptionKey` in Helm values). If left empty at install time, the chart auto-generates one.

## Removing a provider

```http
DELETE /api/admin/llm/config
```

…or click **Delete** in the Admin panel. Kure will revert to rule-based solutions.
