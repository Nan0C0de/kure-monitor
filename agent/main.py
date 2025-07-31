import os
import time
import requests
from kubernetes import client, config, watch

BACKEND_URL = os.getenv("BACKEND_API_URL", "http://localhost:8000/api/events")


def send_event(event_data):
    try:
        response = requests.post(BACKEND_URL, json=event_data)
        response.raise_for_status()
        print(f"Sent event for pod {event_data['name']}")
    except Exception as e:
        print(f"Failed to send event: {e}")


def main():
    # Load in-cluster config or kubeconfig
    try:
        config.load_incluster_config()
        print("Loaded in-cluster config")
    except:
        config.load_kube_config()
        print("Loaded local kubeconfig")

    v1 = client.CoreV1Api()
    w = watch.Watch()

    for event in w.stream(v1.list_pod_for_all_namespaces):
        obj = event['object']
        pod_name = obj.metadata.name
        namespace = obj.metadata.namespace
        status = obj.status.phase
        conditions = obj.status.container_statuses or []

        # Check for problematic states (CrashLoopBackOff, ImagePullBackOff, Pending)
        for cs in conditions:
            state = cs.state
            waiting = state.waiting
            if waiting:
                reason = waiting.reason
                if reason in ["CrashLoopBackOff", "ImagePullBackOff", "ErrImagePull"]:
                    event_data = {
                        "type": "PodError",
                        "name": pod_name,
                        "namespace": namespace,
                        "status": reason,
                        "reason": waiting.message or reason,
                        "timestamp": obj.metadata.creation_timestamp.isoformat()
                    }
                    send_event(event_data)
        time.sleep(0.1)


if __name__ == "__main__":
    main()
