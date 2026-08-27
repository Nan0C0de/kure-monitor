// @ts-check
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

import react from '@astrojs/react';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  site: 'https://kuremonitor.com',

  integrations: [starlight({
			title: 'Kure Monitor',
			description: 'Kubernetes AI monitoring — detect pod failures in seconds and get AI-powered fixes. Open source, air-gapped ready.',
			social: [],
			editLink: {
          baseUrl:
              'https://github.com/igor-koricanac/kure-monitor/edit/main/website/',
			},
			head: [
          {
              tag: 'script',
              content: 'document.documentElement.dataset.theme = "light"; localStorage.setItem("starlight-theme", "light");',
          },
          {
              tag: 'meta',
              attrs: {
                  name: 'keywords',
                  content: 'kubernetes monitoring, kubernetes troubleshooting, kubernetes security scan, AI observability, LLM kubernetes, kubernetes ai agent, kure monitor'
              }
          },
          {
              tag: 'meta',
              attrs: {
                  name: 'author',
                  content: 'Kure Monitor'
              }
          },
          {
              tag: 'script',
              attrs: {
                  src: 'https://static.cloudflareinsights.com/beacon.min.js',
                  'data-cf-beacon': '{"token": "07ebc19e670d45c7abcfe4c5a8148325"}',
                  defer: true,
              },
          },
			],
			lastUpdated: true,
			logo: {
          src: './src/assets/kure_monitor_logo.svg',
          replacesTitle: true,
			},
			customCss: ['./src/styles/custom.css'],
			components: {
          Footer: './src/components/Footer.astro',
			},
			sidebar: [
          {
              label: 'Getting Started',
              items: [
                  { label: 'Introduction', slug: 'getting-started/introduction' },
                  { label: 'Installation', slug: 'getting-started/installation' },
                  { label: 'Quick Start', slug: 'getting-started/quick-start' },
              ],
          },
          {
              label: 'Showcase',
              slug: 'showcase',
          },
          {
              label: 'Integrations',
              items: [
                  { label: 'Grafana App', slug: 'integrations/grafana' },
              ],
          },
          {
              label: 'Configuration',
              items: [
                  { label: 'Overview', slug: 'configuration/overview' },
                  { label: 'Helm Values', slug: 'configuration/helm-values' },
                  { label: 'LLM Providers', slug: 'configuration/llm-providers' },
                  { label: 'Authentication', slug: 'configuration/authentication' },
              ],
          },
          {
              label: 'Features',
              items: [
                  { label: 'Overview', slug: 'features/overview' },
                  { label: 'Pod Monitoring', slug: 'features/pod-monitoring' },
                  { label: 'Security Scanner', slug: 'features/security-scanner' },
                  { label: 'Topology Diagram', slug: 'features/diagram' },
                  { label: 'AI Advice', slug: 'features/advice' },
                  { label: 'Mirror Pod Testing', slug: 'features/mirror-pod' },
                  { label: 'Notifications', slug: 'features/notifications' },
                  { label: 'Suppressions', slug: 'features/suppressions' },
              ],
          },
          {
              label: 'Error Guides',
              items: [
                  { label: 'CrashLoopBackOff', slug: 'errors/crashloopbackoff' },
                  { label: 'OOMKilled', slug: 'errors/oomkilled' },
                  { label: 'ImagePullBackOff', slug: 'errors/imagepullbackoff' },
              ],
          },
          {
              label: 'Comparisons',
              items: [
                  { label: 'Prometheus vs Kure', slug: 'comparisons/prometheus-vs-kure' },
              ],
          },
          {
              label: 'Reference',
              items: [
                  { label: 'Architecture', slug: 'reference/architecture' },
                  { label: 'API Reference', slug: 'reference/api' },
                  { label: 'Troubleshooting', slug: 'reference/troubleshooting' },
              ],
          },
          {
              label: 'Release Notes',
              autogenerate: { directory: 'release-notes' },
              collapsed: true,
          },
			],
  }), react()],

  vite: {
    plugins: [tailwindcss()],
  },
});