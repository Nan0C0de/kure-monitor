---
title: LLM Providers
description: Supported LLM providers, default models, and recommendations for Kure Monitor's AI-powered troubleshooting.
---

Kure Monitor uses an LLM to generate contextual fixes for pod failures and security findings. The provider is configured **after install** from the **Admin Panel → AI Configuration** — no API keys at install time.

## Supported providers

| Provider | Alias | Default Model | Pricing |
|----------|-------|---------------|---------|
| **Ollama** (local) | `ollama` | `llama3.2` | Free / self-hosted |
| **OpenAI** | `openai` | `gpt-5-mini` | [openai.com/pricing](https://openai.com/pricing) |
| **Anthropic** | `anthropic`, `claude` | `claude-sonnet-4-5` | [anthropic.com/pricing](https://www.anthropic.com/pricing) |
| **Groq** | `groq`, `groq_cloud` | `meta-llama/llama-4-scout-17b-16e-instruct` | [groq.com/pricing](https://groq.com/pricing/) |
| **Google Gemini** | `gemini`, `google` | `gemini-2.5-flash` | [ai.google.dev/pricing](https://ai.google.dev/pricing) |
| **GitHub Copilot** (GitHub Models) | `copilot`, `github`, `github_models` | `openai/gpt-5-mini` | [GitHub Models](https://github.com/marketplace/models) |

### GitHub Copilot (GitHub Models)

- **Display name**: GitHub Copilot (GitHub Models)
- **Auth**: GitHub Personal Access Token (fine-grained, with the `Models` permission)
- **Base URL**: `https://models.github.ai/inference`
- **API**: OpenAI-compatible
- **Example models**: `openai/gpt-5`, `openai/gpt-5-mini`, `anthropic/claude-sonnet-4`

### Ollama

For air-gapped clusters. Run Ollama in your cluster, point Kure at it, and your cluster data never leaves your network. Default model: `llama3.2`. Other models in the dropdown: `llama3.3`, `qwen2.5`.

## Recommendations

| Use case | Provider | Model |
|----------|----------|-------|
| Best quality | Anthropic | `claude-sonnet-4-5` |
| Best value | OpenAI | `gpt-5-mini` |
| Fastest | Groq | `meta-llama/llama-4-scout-17b-16e-instruct` |
| Free tier | Groq | `meta-llama/llama-4-scout-17b-16e-instruct` |
| Google ecosystem | Google | `gemini-2.5-flash` |
| GitHub ecosystem | GitHub Copilot | `openai/gpt-5-mini` |
| Local / air-gapped | Ollama | `llama3.2` |

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
