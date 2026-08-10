---
title: Grafana App Installation
description: How to install the Kure Monitor Grafana plugin to get the AI troubleshooting dashboard directly inside Grafana.
---

Kure Monitor ships with a dedicated Grafana App plugin (`kuremonitor-kure-app`) that brings the proactive AI troubleshooting chat and failure feed directly into your existing observability stack.

Because Kure Monitor is a specialized tool, the plugin is distributed independently rather than through the built-in Grafana catalog.

## Installation

### 1. Declarative Installation (Recommended)

If you are deploying Grafana via the official Helm chart or Kubernetes manifests, you can configure Grafana to automatically install the plugin on startup using environment variables.

Add the following to your Grafana `values.yaml`:

```yaml
env:
  GF_INSTALL_PLUGINS: "https://github.com/igor-koricanac/kuremonitor-kure-app/releases/download/v1.0.2/kuremonitor-kure-app-1.0.2.zip;kuremonitor-kure-app"
  GF_PLUGINS_ALLOW_LOADING_UNSIGNED_PLUGINS: "kuremonitor-kure-app"
```

When Grafana boots, it will automatically download the plugin and allow it to load.

### 2. Manual Installation (CLI)

If you are running Grafana natively or want to test the plugin before committing to your Helm chart, you can install it manually using the `grafana cli` tool. 

Run the following command in your server terminal, or execute it inside your running container/pod:

```bash
grafana cli plugins install kuremonitor-kure-app --pluginUrl https://github.com/igor-koricanac/kuremonitor-kure-app/releases/download/v1.0.2/kuremonitor-kure-app-1.0.2.zip
```

**Allowing Unsigned Plugins**
If you install manually, you must still explicitly tell Grafana to allow the unsigned plugin. Add the following to your `grafana.ini` configuration file:

```ini
[plugins]
allow_loading_unsigned_plugins = kuremonitor-kure-app
```
*(Alternatively, you can set the `GF_PLUGINS_ALLOW_LOADING_UNSIGNED_PLUGINS="kuremonitor-kure-app"` environment variable).*

## Post-Installation

1. **Restart Grafana** to load the new unsigned plugin.
2. In the Grafana UI, navigate to **Apps → Kure Monitor** and click **Enable**.
3. Go to the plugin **Configuration** tab to connect it to your Kure backend:
   - **Backend URL:** If Grafana runs in the same cluster, use the internal service URL: `http://kure-backend.kure-system.svc.cluster.local:8000`.
   - **API Key (Service Token):** You must provide the `X-Service-Token`. You can retrieve this by reading the bootstrap secret generated during Kure installation:
     ```bash
     kubectl get secret kure-monitor-bootstrap -n kure-system -o jsonpath='{.data.service-token}' | base64 -d
     ```
4. Click **Save & Test**. You will now see the Kure Monitor dashboard, AI Advice, and Troubleshooting Feed fully integrated!
