// @ts-check
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

export default defineConfig({
	site: 'https://nan0c0de.github.io',
	base: '/kure-monitor',
	integrations: [
		starlight({
			title: 'Kure Monitor',
			description:
				'Real-time Kubernetes failure detection and security scanning with AI-powered troubleshooting.',
			social: [
				{
					icon: 'github',
					label: 'GitHub',
					href: 'https://github.com/Nan0C0de/kure-monitor',
				},
			],
			editLink: {
				baseUrl:
					'https://github.com/Nan0C0de/kure-monitor/edit/main/website/',
			},
			lastUpdated: true,
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
						{ label: 'Mirror Pod Testing', slug: 'features/mirror-pod' },
						{ label: 'Notifications', slug: 'features/notifications' },
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
					label: 'Migration Guides',
					items: [
						{ label: '2.2 → 2.3', slug: 'migration/2-2-to-2-3' },
					],
				},
				{
					label: 'Release Notes',
					autogenerate: { directory: 'release-notes' },
					collapsed: true,
				},
			],
		}),
	],
});
