import asyncio
import aiohttp
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# Try to import kubernetes. If it's not available, discovery will just return empty.
try:
    from kubernetes import client, config
    K8S_AVAILABLE = True
except ImportError:
    K8S_AVAILABLE = False


class LLMDiscoveryService:
    """Discovers LLM services running in the Kubernetes cluster."""

    def __init__(self):
        self.k8s_client = None
        if K8S_AVAILABLE:
            try:
                # In cluster
                config.load_incluster_config()
                self.k8s_client = client.CoreV1Api()
            except config.ConfigException:
                try:
                    # Out of cluster
                    config.load_kube_config()
                    self.k8s_client = client.CoreV1Api()
                except Exception as e:
                    logger.warning(f"Could not load kubernetes config for discovery: {e}")

    async def discover_local_llms(self) -> List[Dict]:
        """Scans the cluster for known LLM services and queries their available models."""
        if not self.k8s_client:
            return []

        endpoints = []
        try:
            # We run this in a thread because kubernetes python client is blocking
            def fetch_services():
                return self.k8s_client.list_service_for_all_namespaces().items

            services = await asyncio.to_thread(fetch_services)
            
            # Filter services that look like LLMs
            llm_keywords = ["ollama", "vllm", "localai", "tgi", "nim", "llm", "llama", "deepseek", "qwen", "mistral"]
            
            for svc in services:
                name = svc.metadata.name.lower()
                is_candidate = any(keyword in name for keyword in llm_keywords)
                
                # Check ports
                if not svc.spec.ports:
                    continue
                    
                for port_obj in svc.spec.ports:
                    port = port_obj.port
                    
                    # If port is 11434, it's almost certainly Ollama
                    if port == 11434:
                        endpoints.append({
                            "type": "ollama",
                            "name": svc.metadata.name,
                            "namespace": svc.metadata.namespace,
                            "url": f"http://{svc.metadata.name}.{svc.metadata.namespace}.svc.cluster.local:{port}"
                        })
                    # If it matches a keyword but isn't 11434, assume OpenAI compatible on whatever port it uses
                    elif is_candidate:
                        endpoints.append({
                            "type": "openai",
                            "name": svc.metadata.name,
                            "namespace": svc.metadata.namespace,
                            "url": f"http://{svc.metadata.name}.{svc.metadata.namespace}.svc.cluster.local:{port}/v1"
                        })
                        
        except Exception as e:
            logger.error(f"Error during Kubernetes service discovery: {e}")
            return []

        # Now concurrently probe the endpoints
        discovered = []
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=2)) as session:
            tasks = []
            for ep in endpoints:
                if ep["type"] == "ollama":
                    tasks.append(self._probe_ollama(session, ep))
                else:
                    tasks.append(self._probe_openai(session, ep))
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for res in results:
                if isinstance(res, dict) and res:
                    discovered.append(res)
                    
        return discovered

    async def _probe_ollama(self, session: aiohttp.ClientSession, ep: Dict) -> Optional[Dict]:
        """Probe an Ollama endpoint"""
        try:
            async with session.get(f"{ep['url']}/api/tags") as response:
                if response.status == 200:
                    data = await response.json()
                    models = [m["name"] for m in data.get("models", [])]
                    return {
                        "provider": "custom_local",
                        "name": ep["name"],
                        "namespace": ep["namespace"],
                        "base_url": f"{ep['url']}/v1",
                        "models": models,
                        "description": f"Ollama on {ep['namespace']}/{ep['name']}"
                    }
        except Exception as e:
            logger.error(f"Error probing ollama {ep['url']}: {e}")
            pass
        return None

    async def _probe_openai(self, session: aiohttp.ClientSession, ep: Dict) -> Optional[Dict]:
        """Probe an OpenAI-compatible endpoint"""
        try:
            async with session.get(f"{ep['url']}/models") as response:
                if response.status == 200:
                    data = await response.json()
                    models = [m["id"] for m in data.get("data", []) if "id" in m]
                    if models:
                        return {
                            "provider": "custom_local",
                            "name": ep["name"],
                            "namespace": ep["namespace"],
                            "base_url": ep["url"],
                            "models": models,
                            "description": f"Custom LLM on {ep['namespace']}/{ep['name']}"
                        }
        except Exception:
            pass
        return None
