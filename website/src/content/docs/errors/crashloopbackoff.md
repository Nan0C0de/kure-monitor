---
title: How to Debug CrashLoopBackOff
description: Learn what causes the Kubernetes CrashLoopBackOff error, how to debug it manually using kubectl, and how Kure Monitor uses AI to instantly find the root cause.
---

`CrashLoopBackOff` is one of the most common and frustrating Kubernetes errors. It means that a container is starting, crashing immediately, and Kubernetes is repeatedly trying (and failing) to restart it.

Because Kubernetes implements an exponential backoff delay (10s, 20s, 40s, up to 5 minutes) between restart attempts, your pod gets stuck in a loop.

## What causes CrashLoopBackOff?

A container crashes when its main process exits. Common reasons include:
1. **Misconfigured environment variables**: The application is missing a required config value and panics on startup.
2. **Missing dependencies**: A required database or external service is unreachable.
3. **Bad startup commands**: The `command` or `args` in your manifest are incorrect.
4. **Port binding issues**: The container is trying to bind to a port that requires root privileges, or is already in use.

## How to debug manually

When you see a pod in `CrashLoopBackOff`, you need to check two things: the pod events and the container logs.

**1. Check the Pod Events**
Events will tell you if the kubelet is killing the pod for a specific reason (like a failed readiness probe).
```bash
kubectl describe pod <pod-name> -n <namespace>
```
Look at the `Events:` section at the bottom of the output.

**2. Check the Previous Container Logs**
Because the container has crashed, running a standard `kubectl logs` might show nothing. You must use the `--previous` (or `-p`) flag to see the logs from the *last* time it crashed.
```bash
kubectl logs <pod-name> -n <namespace> --previous
```
This is usually where you will see the fatal stack trace or error message that caused the application to panic.

## How to debug instantly with Kure Monitor

Manually running `kubectl describe` and `kubectl logs --previous` across hundreds of pods is exhausting. 

**Kure Monitor automates this entire process.** 

When a pod enters `CrashLoopBackOff`, Kure Monitor:
1. Instantly detects the failure in real-time.
2. Gathers the pod manifest, the recent Kubernetes events, and the `--previous` container logs.
3. Feeds this context to the AI model of your choice (OpenAI, Anthropic, Gemini, or a fully local Ollama model).
4. Generates a plain-English explanation of exactly *why* the container crashed, along with the exact `kubectl` command or YAML snippet to fix it.

Stop guessing why your pods are crashing. [Install Kure Monitor](/getting-started/installation/) today.
