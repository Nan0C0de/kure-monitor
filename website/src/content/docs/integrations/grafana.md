---
title: Grafana App Installation
description: How to install the Kure Monitor Grafana plugin to get the AI troubleshooting dashboard directly inside Grafana.
---

Kure Monitor ships with a dedicated Grafana App plugin (`kuremonitor-kure-app`) that brings the proactive AI troubleshooting chat and failure feed directly into your existing observability stack.

Because Kure Monitor is a specialized tool, the plugin is distributed independently rather than through the built-in Grafana catalog.

## Installation

You can install the plugin into your Grafana instance using the `grafana-cli` command and pointing it to the official `.zip` release hosted on this website.

Run the following command on your Grafana server (or add it to your Grafana Docker entrypoint/init scripts):

```bash
grafana-cli --pluginUrl https://kuremonitor.com/downloads/kuremonitor-kure-app-1.0.2.zip plugins install kuremonitor-kure-app
```

### Allowing Unsigned Plugins

Because the plugin is distributed outside the official catalog, Grafana requires you to explicitly allow it to load. Add the following to your `grafana.ini` configuration file:

```ini
[plugins]
allow_loading_unsigned_plugins = kuremonitor-kure-app
```

If you are running Grafana in Docker or Kubernetes, you can set this via an environment variable instead:

```yaml
env:
  - name: GF_PLUGINS_ALLOW_LOADING_UNSIGNED_PLUGINS
    value: "kuremonitor-kure-app"
```

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
