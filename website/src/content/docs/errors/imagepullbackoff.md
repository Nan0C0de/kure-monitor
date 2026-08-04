---
title: How to Debug ImagePullBackOff
description: Learn how to troubleshoot Kubernetes ImagePullBackOff and ErrImagePull errors, fix registry authentication, and use Kure Monitor to automate the diagnosis.
---

`ImagePullBackOff` and `ErrImagePull` are Kubernetes errors indicating that the kubelet on a worker node cannot pull the Docker container image required to start your pod.

When a pod is stuck in `ImagePullBackOff`, the container will never start.

## What causes ImagePullBackOff?

The kubelet failed to retrieve the image for one of these common reasons:
1. **Typo in the image name or tag**: The image repository, name, or tag (`v1.0.0`) is misspelled in the pod manifest.
2. **Missing Registry Authentication**: The image is hosted in a private registry (like AWS ECR, GCP GCR, or Docker Hub private repos), but the pod does not have the correct `imagePullSecrets` configured.
3. **Network Issues**: The Kubernetes worker node cannot reach the image registry due to firewall rules, egress network policies, or DNS resolution failures.
4. **Image Does Not Exist**: The CI/CD pipeline failed to build and push the image, or the image tag was deleted from the registry.

## How to debug manually

When a pod is stuck in `ImagePullBackOff`, the application has not even started yet, so **there are no container logs**. You must rely entirely on Kubernetes events.

**1. Inspect the Pod Events**
Run a describe command to see exactly why the kubelet failed to pull the image:
```bash
kubectl describe pod <pod-name> -n <namespace>
```
Scroll to the bottom `Events:` section. You will typically see an event like:
* `Failed to pull image "my-repo/my-app:v1": rpc error: code = NotFound desc = failed to pull and unpack image...` (Indicates a typo or missing image).
* `pull access denied for my-repo/my-app, repository does not exist or may require 'docker login'` (Indicates missing or invalid `imagePullSecrets`).

**2. Verify ImagePullSecrets**
If it's an authentication issue, ensure your `Secret` exists in the same namespace as the pod:
```bash
kubectl get secret <secret-name> -n <namespace> -o yaml
```
Then verify that your deployment manifest actually references this secret in the `spec.template.spec.imagePullSecrets` array.

## How to debug instantly with Kure Monitor

Instead of manually digging through Kubernetes events and cross-referencing secret names, let AI do it for you.

When a pod enters `ImagePullBackOff`, Kure Monitor:
1. Detects the stuck pod instantly.
2. Automatically extracts the exact error message from the kubelet events.
3. Uses its AI engine (OpenAI, Anthropic, Gemini, or a private local LLM) to analyze the failure.
4. Tells you exactly what is wrong. If it's an authentication issue, the AI will instruct you on how to create the missing `imagePullSecret` and provide the exact YAML snippet needed to attach it to your deployment.

[Install Kure Monitor](/getting-started/installation/) today and let AI solve your deployment errors in seconds.
