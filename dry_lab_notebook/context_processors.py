import typing as t

from django.conf import settings


def _normalize_endpoint_config(value: t.Any) -> t.Optional[dict]:
    if isinstance(value, str):
        return {"id": value}
    if isinstance(value, dict):
        endpoint_id = (
            value.get("id")
            or value.get("uuid")
            or value.get("collection")
            or value.get("collection_id")
            or value.get("endpoint")
            or value.get("endpoint_id")
        )
        if endpoint_id:
            normalized = dict(value)
            normalized["id"] = endpoint_id
            return normalized
    return None


def globus_collections(_request):
    """
    Provide collection endpoints to templates.

    Sources (in priority order):
    1. settings.GLOBUS_COLLECTION_ENDPOINTS (list[str|dict])
    2. settings.SEARCH_INDEXES[*]['collection'|'collection_id'|'endpoint'|'endpoint_id']

    Returned context key:
      globus_collection_endpoints: list[dict]
    """
    seen = set()
    collection_endpoints = []

    configured = getattr(settings, "GLOBUS_COLLECTION_ENDPOINTS", {}) or {}

    if isinstance(configured, dict):
        configured_items = configured.items()
    else:
        configured_items = [(None, item) for item in configured]

    for configured_slug, raw in configured_items:
        normalized = _normalize_endpoint_config(raw)
        if not normalized:
            continue
        endpoint_id = normalized["id"]
        if endpoint_id in seen:
            continue
        if configured_slug and "slug" not in normalized:
            normalized["slug"] = configured_slug
        seen.add(endpoint_id)
        collection_endpoints.append(normalized)

    search_indexes = getattr(settings, "SEARCH_INDEXES", {}) or {}
    for slug, index_data in search_indexes.items():
        if not isinstance(index_data, dict):
            continue
        endpoint_id = (
            index_data.get("collection")
            or index_data.get("collection_id")
            or index_data.get("endpoint")
            or index_data.get("endpoint_id")
        )
        if not endpoint_id or endpoint_id in seen:
            continue
        seen.add(endpoint_id)
        collection_endpoints.append(
            {
                "id": endpoint_id,
                "slug": slug,
                "name": index_data.get("name"),
            }
        )

    return {"globus_collection_endpoints": collection_endpoints}
