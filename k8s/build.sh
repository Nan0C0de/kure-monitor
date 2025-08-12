#!/bin/bash

echo "🚀 Build docker images..."

REGISTRY="ghcr.io/igor-koricanac"
BACKEND_VERSION="0.0.16"
AGENT_VERSION="0.0.15"
FRONTEND_VERSION="0.0.14"

echo "📦 Building Docker images..."
docker build -t ${REGISTRY}/kure/backend:${BACKEND_VERSION} ./backend/
docker build -t ${REGISTRY}/kure/agent:${AGENT_VERSION} ./agent/
docker build -t ${REGISTRY}/kure/frontend:${FRONTEND_VERSION} ./frontend/

echo "🚢 Pushing Docker images..."

docker push ${REGISTRY}/kure/backend:${BACKEND_VERSION}
docker push ${REGISTRY}/kure/agent:${AGENT_VERSION}
docker push ${REGISTRY}/kure/frontend:${FRONTEND_VERSION}

echo "🔒 Applying network policies..."
kubectl apply -f k8s/network-policies.yaml
