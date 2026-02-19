import logging
import yaml
from typing import Optional

logger = logging.getLogger(__name__)

# Dangerous capabilities that should never be added
DANGEROUS_CAPABILITIES = [
    'SYS_ADMIN', 'NET_RAW', 'SYS_PTRACE', 'SYS_MODULE',
    'DAC_READ_SEARCH', 'NET_ADMIN', 'SYS_RAWIO', 'SYS_BOOT',
    'SYS_TIME', 'MKNOD', 'SETUID', 'SETGID',
]

# Capabilities allowed by Pod Security Standards Restricted policy
ALLOWED_CAPABILITIES = ['NET_BIND_SERVICE']

# System namespaces to skip
SYSTEM_NAMESPACES = ['kube-system', 'kube-public', 'kube-node-lease', 'kube-flannel', 'kure-system', 'kyverno']

# Trusted container registries (can be customized via config)
TRUSTED_REGISTRIES = [
    'docker.io', 'gcr.io', 'ghcr.io', 'quay.io',
    'registry.k8s.io', 'mcr.microsoft.com', 'public.ecr.aws',
]

# Large emptyDir size limit threshold (in bytes) - 10GB
LARGE_EMPTYDIR_THRESHOLD = 10 * 1024 * 1024 * 1024


def clean_dict(obj):
    """Recursively remove None values and empty collections from a dictionary"""
    if isinstance(obj, dict):
        cleaned = {}
        for key, value in obj.items():
            if value is None:
                continue
            cleaned_value = clean_dict(value)
            if isinstance(cleaned_value, (list, dict)) and len(cleaned_value) == 0:
                continue
            cleaned[key] = cleaned_value
        return cleaned
    elif isinstance(obj, list):
        return [clean_dict(item) for item in obj if item is not None]
    else:
        return obj


def get_resource_manifest(resource_obj, api_version: str, kind: str) -> str:
    """Serialize a Kubernetes resource object to clean YAML manifest"""
    try:
        resource_dict = resource_obj.to_dict()
        resource_dict['apiVersion'] = api_version
        resource_dict['kind'] = kind

        if 'metadata' in resource_dict:
            metadata = resource_dict['metadata']
            for key in ['managed_fields', 'resource_version', 'uid',
                        'creation_timestamp', 'generation', 'self_link']:
                metadata.pop(key, None)

        resource_dict.pop('status', None)
        return yaml.safe_dump(clean_dict(resource_dict), default_flow_style=False, sort_keys=False)
    except Exception as e:
        logger.debug(f"Could not generate manifest for {kind}/{resource_obj.metadata.name}: {e}")
        return ""


def get_image_registry(image: str) -> Optional[str]:
    """Extract registry from container image string"""
    if not image:
        return None
    parts = image.split('/')
    if len(parts) == 1:
        return 'docker.io'
    elif len(parts) == 2:
        first_part = parts[0]
        if '.' in first_part or ':' in first_part or first_part == 'localhost':
            return first_part.split(':')[0]
        else:
            return 'docker.io'
    else:
        return parts[0].split(':')[0]


def parse_size_to_bytes(size_str: str) -> Optional[int]:
    """Parse Kubernetes size string to bytes"""
    if not size_str:
        return None
    try:
        size_str = size_str.strip()
        units = {
            'Ki': 1024, 'Mi': 1024 ** 2, 'Gi': 1024 ** 3, 'Ti': 1024 ** 4,
            'K': 1000, 'M': 1000 ** 2, 'G': 1000 ** 3, 'T': 1000 ** 4,
        }
        for suffix, multiplier in units.items():
            if size_str.endswith(suffix):
                return int(float(size_str[:-len(suffix)]) * multiplier)
        return int(size_str)
    except (ValueError, TypeError):
        return None
