#!/bin/bash

echo "🚀 Deploying Kure to Kubernetes..."

echo "🔧 Applying Kubernetes manifests..."
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/rbac.yaml
kubectl apply -f k8s/backend.yaml
kubectl apply -f k8s/agent.yaml
kubectl apply -f k8s/frontend.yaml
kubectl apply -f k8s/postgresql.yaml

echo "⏳ Waiting for pods to be ready..."
kubectl wait --for=condition=ready pod -l app=kure-backend -n kure-system --timeout=300s
kubectl wait --for=condition=ready pod -l app=kure-agent -n kure-system --timeout=300s
kubectl wait --for=condition=ready pod -l app=kure-frontend -n kure-system --timeout=300s

echo "✅ Deployment complete!"
echo "🌐 Access the dashboard at: http://kure.local (or your configured domain)"
echo "📊 Check status: kubectl get pods -n kure-system"
