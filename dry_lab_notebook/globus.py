import globus_sdk
from django.conf import settings

from config.settings import CLIENT_ID, CLIENT_SECRET


_INITIALIZED = False
_GLOBUS_APP: globus_sdk.ClientApp | None = None
_SEARCH_CLIENT: globus_sdk.SearchClient | None = None
_TRANSFER_CLIENT: globus_sdk.TransferClient | None = None


def _extract_endpoint_id(raw: object) -> str | None:
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        return (
            raw.get("id")
            or raw.get("uuid")
            or raw.get("collection")
            or raw.get("collection_id")
            or raw.get("endpoint")
            or raw.get("endpoint_id")
        )
    return None

def _validate_configured_endpoints(
    transfer_client: globus_sdk.TransferClient,
) -> None:
    """
    Make sure configured endpoints are Guest collections and accessible
    """
    configured = getattr(settings, "GLOBUS_COLLECTION_ENDPOINTS", {}) or {}
    
    if isinstance(configured, dict):
        configured_items = configured.items()
    else:
        configured_items = [(None, item) for item in configured]

    for configured_slug, raw in configured_items:
        endpoint_id = _extract_endpoint_id(raw)

        if not endpoint_id:
            continue

        try:
            doc = transfer_client.get_endpoint(endpoint_id)
            transfer_client.operation_ls(endpoint_id, "/")
        except Exception as e:
            raise Exception(f"Endpoint {endpoint_id} is not accessible with the provided credentials: {e}") # TODO: log and remove endpoint instead

        if doc["entity_type"] == "GCSv5_guest_collection":
            continue
        elif doc["entity_type"] == "GCP_guest_collection":
            continue
        else:
            raise Exception(f"Endpoint {endpoint_id} is not a guest collection") # TODO: log and remove endpoint instead

def initialize_globus() -> None:
    global _INITIALIZED, _GLOBUS_APP, _SEARCH_CLIENT, _TRANSFER_CLIENT

    if _INITIALIZED:
        return

    app = globus_sdk.ClientApp(
        app_name="Dry Lab Notebook",
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        config=globus_sdk.GlobusAppConfig(token_storage="memory"),
    )

    search_client = globus_sdk.SearchClient(app=app)
    search_client.add_app_scope(globus_sdk.SearchClient.scopes.search)

    transfer_client = globus_sdk.TransferClient(app=app)
    _validate_configured_endpoints(transfer_client)

    _GLOBUS_APP = app
    _SEARCH_CLIENT = search_client
    _TRANSFER_CLIENT = transfer_client
    _INITIALIZED = True


def get_search_client() -> globus_sdk.SearchClient:
    initialize_globus()
    if _SEARCH_CLIENT is None:
        raise RuntimeError("Globus Search client failed to initialize")
    return _SEARCH_CLIENT


def get_transfer_client() -> globus_sdk.TransferClient:
    initialize_globus()
    if _TRANSFER_CLIENT is None:
        raise RuntimeError("Globus Transfer client failed to initialize")
    return _TRANSFER_CLIENT
