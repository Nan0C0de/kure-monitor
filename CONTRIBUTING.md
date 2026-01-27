# Contributing to Kure Monitor

Thank you for your interest in contributing to Kure Monitor! This document provides guidelines and instructions for contributing.

## Code of Conduct

Please be respectful and constructive in all interactions. We welcome contributors of all experience levels.

## Getting Started

### Prerequisites

- Python 3.9+
- Node.js 18+
- Docker
- kubectl configured with a Kubernetes cluster
- (Optional) Kind or Minikube for local development

### Local Development Setup

```bash
# Clone the repository
git clone https://github.com/Nan0C0de/kure-monitor.git
cd kure-monitor

# Backend
cd backend
pip install -r requirements.txt
pip install -r requirements-dev.txt
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Frontend (in another terminal)
cd frontend
npm install
npm start

# Agent (requires kubectl configured)
cd agent
pip install -r requirements.txt
python main.py
```

## How to Contribute

### Reporting Bugs

1. Check existing issues to avoid duplicates
2. Use the bug report template
3. Include:
   - Kubernetes version
   - Kure Monitor version
   - Steps to reproduce
   - Expected vs actual behavior
   - Relevant logs

### Suggesting Features

1. Check existing issues and discussions
2. Use the feature request template
3. Describe the use case and expected behavior

### Submitting Pull Requests

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Make your changes
4. Run tests:
   ```bash
   cd backend && python -m pytest -v
   cd frontend && npm test
   cd agent && python -m pytest -v
   ```
5. Commit with clear messages: `git commit -m 'Add feature: description'`
6. Push to your fork: `git push origin feature/your-feature`
7. Open a Pull Request

### PR Guidelines

- Keep changes focused and atomic
- Update tests for new functionality
- Update documentation if needed
- Ensure all tests pass
- Follow existing code style

## Project Structure

```
kure-monitor/
├── agent/           # Kubernetes pod monitoring agent
├── backend/         # FastAPI backend server
├── frontend/        # React web dashboard
├── security-scanner/# Security auditing agent
├── helm/            # Helm chart
├── k8s/             # Kubernetes manifests
└── examples/        # Test pod examples
```

## Development Guidelines

### Backend (Python/FastAPI)

- Follow PEP 8 style guidelines
- Use type hints
- Write async functions for I/O operations
- Add tests for new functionality

### Frontend (React)

- Use functional components with hooks
- Follow existing component patterns
- Use Tailwind CSS for styling
- Add tests for new components

### Agent

- Handle Kubernetes API errors gracefully
- Implement proper retry logic
- Log at appropriate levels

## Testing

### Running Tests

```bash
# Backend
cd backend && python -m pytest -v

# Frontend
cd frontend && npm test

# Agent
cd agent && python -m pytest -v
```

### Test Pod Examples

Use the examples in `examples/` directory to test failure detection:

```bash
kubectl apply -f examples/01-image-pull-backoff.yaml
```

## Questions?

- Open a GitHub issue for bugs and feature requests
- Check existing documentation in README.md and CLAUDE.md

## License

By contributing, you agree that your contributions will be licensed under the project's Custom Non-Commercial License.
