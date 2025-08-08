#!/bin/bash

echo "🚀 Deploying Kure to Kubernetes..."

# Build and push Docker images (modify registry as needed)
REGISTRY="your-registry"  # Change this to your Docker registry

echo "📦 Building Docker images..."
docker build -t ${REGISTRY}/kure/backend:latest ./backend/
docker build -t ${REGISTRY}/kure/agent:latest ./agent/
docker build -t ${REGISTRY}/kure/frontend:latest ./frontend/

echo "🚢 Pushing Docker images..."

docker push ${REGISTRY}/kure/backend:latest
docker push ${REGISTRY}/kure/agent:latest  
docker push ${REGISTRY}/kure/frontend:latest

echo "🔧 Applying Kubernetes manifests..."
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/rbac.yaml
kubectl apply -f k8s/backend.yaml
kubectl apply -f k8s/agent.yaml
kubectl apply -f k8s/frontend.yaml

echo "⏳ Waiting for pods to be ready..."
kubectl wait --for=condition=ready pod -l app=kure-backend -n kure-system --timeout=300s
kubectl wait --for=condition=ready pod -l app=kure-agent -n kure-system --timeout=300s
kubectl wait --for=condition=ready pod -l app=kure-frontend -n kure-system --timeout=300s

echo "✅ Deployment complete!"
echo "🌐 Access the dashboard at: http://kure.local (or your configured domain)"
echo "📊 Check status: kubectl get pods -n kure-system"