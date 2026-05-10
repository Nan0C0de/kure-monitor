---
title: LLM Providers
description: Supported LLM providers, default models, and recommendations for Kure Monitor's AI-powered troubleshooting.
---

Kure Monitor uses an LLM to generate contextual fixes for pod failures and security findings. The provider is configured **after install** from the **Admin Panel → AI Configuration** — no API keys at install time.

> **2.3.4** — the AI Configuration panel now defaults to **Groq** for new installations (was Ollama). Existing installs are unaffected; this only changes the initial pre-selection. Model catalogs across all six providers were also refreshed to current (May 2026) latest models.

## Supported providers

| Provider | Alias | Default Model | Pricing |
|----------|-------|---------------|---------|
| **Groq** (default) | `groq`, `groq_cloud` | `meta-llama/llama-4-scout-17b-16e-instruct` | [groq.com/pricing](https://groq.com/pricing/) |
| **OpenAI** | `openai` | `gpt-5.5-mini` | [openai.com/pricing](https://openai.com/pricing) |
| **Anthropic** | `anthropic`, `claude` | `claude-sonnet-4-6` | [anthropic.com/pricing](https://www.anthropic.com/pricing) |
| **Google Gemini** | `gemini`, `google` | `gemini-3-flash` | [ai.google.dev/pricing](https://ai.google.dev/pricing) |
| **GitHub Copilot** (GitHub Models) | `copilot`, `github`, `github_models` | `openai/gpt-5.5-mini` | [GitHub Models](https://github.com/marketplace/models) |
| **Ollama** (local) | `ollama` | `llama4:scout` | Free / self-hosted |

### Model catalogs (dropdown options)

| Provider | Models in the dropdown (default in **bold**) |
|----------|----------------------------------------------|
| OpenAI | `gpt-5.5`, **`gpt-5.5-mini`**, `gpt-5.4-mini` |
| Anthropic | `claude-opus-4-7`, **`claude-sonnet-4-6`**, `claude-haiku-4-5` |
| Google Gemini | `gemini-3.1-pro`, **`gemini-3-flash`**, `gemini-3.1-flash-lite` |
| Groq | `openai/gpt-oss-120b`, **`meta-llama/llama-4-scout-17b-16e-instruct`**, `llama-3.3-70b-versatile`, `openai/gpt-oss-20b` |
| Ollama | **`llama4:scout`**, `llama3.3`, `qwen3` |
| GitHub Copilot | `openai/gpt-5.5`, **`openai/gpt-5.5-mini`**, `anthropic/claude-sonnet-4-6` |

### GitHub Copilot (GitHub Models)

- **Display name**: GitHub Copilot (GitHub Models)
- **Auth**: GitHub Personal Access Token (fine-grained, with the `Models` permission)
- **Base URL**: `https://models.github.ai/inference`
- **API**: OpenAI-compatible
- **Example models**: `openai/gpt-5.5`, `openai/gpt-5.5-mini`, `anthropic/claude-sonnet-4-6`

### Ollama

For air-gapped clusters. Run Ollama in your cluster, point Kure at it, and your cluster data never leaves your network. Default model: `llama4:scout`. Other models in the dropdown: `llama3.3`, `qwen3`.

## Recommendations

| Use case | Provider | Model |
|----------|----------|-------|
| Best quality | Anthropic | `claude-opus-4-7` |
| Best value | OpenAI | `gpt-5.5-mini` |
| Fastest | Groq | `meta-llama/llama-4-scout-17b-16e-instruct` |
| Free tier | Groq | `meta-llama/llama-4-scout-17b-16e-instruct` |
| Google ecosystem | Google | `gemini-3-flash` |
| GitHub ecosystem | GitHub Copilot | `openai/gpt-5.5-mini` |
| Local / air-gapped | Ollama | `llama4:scout` |

## Configuring a provider

1. Open the dashboard
2. **Admin Panel → AI Configuration**
3. Pick a provider
4. Paste your API key (or PAT for GitHub Copilot)
5. Pick a model from the dropdown
6. Click **Test Connection** — verifies the key works
7. Click **Save Configuration**

If the LLM call fails at runtime, Kure falls back to rule-based solutions so the dashboard stays useful.

## Rotating an API key

1. Generate a new key with your provider
2. **Admin Panel → AI Configuration**
3. Replace the existing key
4. **Test Connection** → **Save**

LLM API keys are encrypted at rest using a Fernet key (`security.encryptionKey` in Helm values). If left empty at install time the chart auto-generates one.

## Removing a provider

```http
DELETE /api/admin/llm/config
```

…or click **Delete** in the Admin panel. Kure reverts to rule-based solutions.
