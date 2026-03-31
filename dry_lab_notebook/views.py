from pathlib import Path
import typing as t
from datetime import datetime
import django
from django.conf import settings
from django.views.generic import View
from django.shortcuts import render
from urllib.parse import quote_plus, unquote, unquote_plus, urlencode

from globus_portal_framework.gsearch import (
    get_template,
    get_index,
    get_facets, 
    get_pagination
)

from globus_portal_framework.views.generic import SearchView as DGPFSearchView
import globus_sdk

from dry_lab_notebook.globus import get_search_client, get_transfer_client


def get_collection_endpoints() -> list[dict]:
    configured = getattr(settings, "GLOBUS_COLLECTION_ENDPOINTS", {}) or {}
    endpoints = []

    if isinstance(configured, dict):
        configured_items = configured.items()
    else:
        configured_items = [(None, item) for item in configured]

    for configured_slug, raw in configured_items:
        if isinstance(raw, str):
            endpoint = {"id": raw}
        elif isinstance(raw, dict):
            endpoint_id = (
                raw.get("id")
                or raw.get("uuid")
                or raw.get("collection")
                or raw.get("collection_id")
                or raw.get("endpoint")
                or raw.get("endpoint_id")
            )
            if not endpoint_id:
                continue
            endpoint = dict(raw)
            endpoint["id"] = endpoint_id
        else:
            continue

        endpoint["slug"] = endpoint.get("slug") or configured_slug or endpoint["id"]
        endpoints.append(endpoint)

    return endpoints


def get_collection_endpoint(collection_key: str | None) -> dict | None:
    endpoints = get_collection_endpoints()
    if not endpoints:
        return None
    if collection_key:
        for endpoint in endpoints:
            if collection_key in {endpoint["id"], endpoint.get("slug")}:
                return endpoint
    return endpoints[0]

def generate_globus_url(collection_id, path="/~/"):
    base_url = "https://app.globus.org/file-manager"
    
    # Define parameters for the URL
    params = {
        "origin_id": collection_id,
        "origin_path": path
    }
    
    # URL encode the parameters to handle spaces and special characters
    query_string = urlencode(params)
    
    return f"{base_url}?{query_string}"

def process_search_data(results):
    """
    Override `globus_portal_framework.gsearch.process_search_data`.
    Remove `field_mappers` parameter and associated processing, e.g.
    flattening and other steps given structure of dry-lab-notebook index.
    May cause unforeseen issues with framework features not yet explored.
    """
    structured_results = []
    for gmeta_result in results:

        entries = gmeta_result['entries']
        content = [e['content'] for e in entries]

        content[0]["last_modified"] = datetime.fromisoformat(content[0]["last_modified"])
        content[0]["date_indexed"] = datetime.fromisoformat(content[0]["date_indexed"])
        result = {
            'subject': quote_plus(gmeta_result['subject']),
            'all': content
        }

        structured_results.append(result)
    return structured_results


class SearchView(DGPFSearchView):

    def process_result(
        self, index_info: t.Mapping[str, str], search_result: t.Mapping[str, str]
    ) -> t.Mapping[str, str]:
        """
        Override parent class implementation. Called by `self.get_context_data`, which is called by `self.get`.
        """
        return {
            "search": {
                "search_results": process_search_data(
                    search_result.data["gmeta"]
                ),
                "facets": get_facets(
                    search_result,
                    index_info.get("facets", []),
                    self.filters,
                    index_info.get("filter_match"),
                    index_info.get("facet_modifiers"),
                ),
                "pagination": get_pagination(
                    search_result.data["total"], search_result.data["offset"]
                ),
                "count": search_result.data["count"],
                "offset": search_result.data["offset"],
                "total": search_result.data["total"],
            }
        }

    def get_search_client(self) -> globus_sdk.SearchClient:
        '''
        Override default and use [client credentials](https://globus-sdk-python.readthedocs.io/en/stable/examples/client_credentials.html)
        to provide auth'ed client for Globus Search.
        
        :rtype: SearchClient
        '''
        return get_search_client()
    
    def post_search(self, client, index_uuid, search_client_data):
        search_client_data['q_settings'] = {
            'mode': 'text_match',
            'fuzziness': 2
        }
        return super().post_search(client, index_uuid, search_client_data)

def get_subject(index, subject):
    """
    Modify `globus_portal_framework.gsearch.get_subject` to use client credentials to authorize.
    """
    client = get_search_client()
    try:
        idata = get_index(index)
        result = client.get_subject(idata['uuid'], unquote_plus(subject))
        return process_search_data([result.data])[0]
    except globus_sdk.SearchAPIError:
        return {'subject': subject, 'error': 'No data was found for subject'}

def get_path_map(
    path: str,
    *,
    prefix_slash: bool = False,
    suffix_slash: bool = False,
    include_empty_root: bool = False,
) -> dict:
    """
    Convert a path into a name->path mapping for breadcrumb-style navigation.

    Examples:
    - `get_path_map('/a/b/c', prefix_slash=True)` ->
      {'a': '/a', 'b': '/a/b', 'c': '/a/b/c'}
    - `get_path_map('a/b/c/', suffix_slash=True)` ->
      {'a': 'a/', 'b': 'a/b/', 'c': 'a/b/c/'}
    """
    if include_empty_root and path == "":
        return {"(root)": "/"}

    parts = [pt for pt in path.split('/') if pt]
    mapped_paths = {}
    for i, name in enumerate(parts):
        partial = "/".join(parts[: i + 1])
        if prefix_slash:
            partial = "/" + partial
        if suffix_slash:
            partial = partial + "/"
        mapped_paths[name] = partial

    return mapped_paths

class DetailView(View):
    """
    Modify `globus_portal_framework.views.generic.DetailView`.
    """

    DEFAULT_TEMPLATE = "globus-portal-framework/v2/detail-overview.html"

    def __init__(self, template=None):
        super().__init__()
        self.template = template or self.DEFAULT_TEMPLATE

    def get_context_data(self, index: str, subject: str) -> t.Mapping[str, str]:
        """Call globus_portal_framework.gsearch.get_subject using the index, subject, and user
        and return the result."""
        data = get_subject(index, subject)
        entry = data['all'][0] # data from the index that will be rendered as a table
        data['title'] = entry['name'] # special key used by template `detail-nav.html`
        path = Path(unquote(entry["path"]))
        data['globus_app_link'] = generate_globus_url(entry['collection'], str(path.parent))
        data["dirs"] = get_path_map(
            str(path.parent),
            prefix_slash=True,
            include_empty_root=True,
        )
        return data

    def get(self, request: django.http.HttpRequest, index: str, subject: str):
        """Get context data, and return a rendered search view, selecting the template with
        globus_portal_framework.gsearch.get_template."""
        context = self.get_context_data(index, subject)
        return render(request, get_template(index, self.template), context)

class FileBrowserView(View):
    """File browser integrated with Globus Portal Framework"""
    DEFAULT_TEMPLATE = "file-browser.html"
    
    def __init__(self, template=None):
        super().__init__()
        self.template = template or self.DEFAULT_TEMPLATE
    
    def get_context_data(self, request, path='', collection_key=None) -> dict:
        """Get directory and file listings for the given path"""
        collection = get_collection_endpoint(collection_key)
        items = []
        current_dir_path = "/" + path.lstrip("/") if path else "/"
        if collection:
            transfer_client = get_transfer_client()
            res = transfer_client.operation_ls(collection['id'], path)
            items = res['DATA']

        dirs = [i['name'] for i in items if i['type'] == 'dir']
        files = [
            {
                'name': i['name'],
                'size': i.get('size'),
                'user': i.get('user'),
                'last_modified': datetime.fromisoformat(i.get('last_modified')),
            }
            for i in items if i['type'] == 'file'
        ]
        
        stripped = path.rstrip('/')
        if stripped:
            parent = '/'.join(stripped.split('/')[:-1])
            parent_path = parent + '/' if parent else ''
        else:
            parent_path = ''
        
        return {
            'dirs': dirs,
            'files': files,
            'current_path': path,
            'parent_path': parent_path,
            'browser_dirs': get_path_map(path, suffix_slash=True),
            'current_collection': collection,
            'collection_query_key': collection.get('slug') if collection else '',
            'globus_app_link': generate_globus_url(collection['id'], current_dir_path) if collection else '',
        }
    
    def get(self, request):
        """Display file browser"""
        path = request.GET.get('path', '')
        collection_key = request.GET.get('collection')
        context = self.get_context_data(request, path, collection_key)
        return render(request, self.template, context)
    
    def post(self, request):
        """Process selected files"""
        selected_files = request.POST.getlist('files')
        # Logic for processing selected files goes here
        return render(request, 'task_success.html', {'files': selected_files})


class FileDetailView(View):
    """File detail page integrated with Globus Portal Framework."""

    DEFAULT_TEMPLATE = "file-detail.html"

    def __init__(self, template=None):
        super().__init__()
        self.template = template or self.DEFAULT_TEMPLATE

    def get_context_data(self, file_path: str = '', collection_key: str | None = None) -> dict:
        collection = get_collection_endpoint(collection_key)
        stripped_path = file_path.strip('/')

        parent_path = ''
        file_name = stripped_path
        if '/' in stripped_path:
            parent_dir, file_name = stripped_path.rsplit('/', 1)
            parent_path = f"{parent_dir}/"

        file_data = None
        if collection and stripped_path:
            transfer_client = get_transfer_client()
            stat = transfer_client.operation_stat(collection['id'], stripped_path)
            file_data = {
                'name': stat.get('name', file_name),
                'size': stat.get('size'),
                'user': stat.get('user'),
                'type': stat.get('type'),
                'last_modified': datetime.fromisoformat(stat.get('last_modified')) if stat.get('last_modified') else None,
            }

        return {
            'file': file_data,
            'file_name': file_name,
            'file_path': stripped_path,
            'parent_path': parent_path,
            'browser_dirs': get_path_map(parent_path, suffix_slash=True),
            'current_collection': collection,
            'collection_query_key': collection.get('slug') if collection else '',
            'globus_app_link': generate_globus_url(collection['id'], f"/{stripped_path}") if collection and stripped_path else '',
        }

    def get(self, request):
        file_path = request.GET.get('path', '')
        collection_key = request.GET.get('collection')
        context = self.get_context_data(file_path, collection_key)
        return render(request, self.template, context)
    
class ActivitiesView(View):

    DEFAULT_TEMPLATE = "activity-selection.html"
 
    def __init__(self, template=None):
        super().__init__()
        self.template = template or self.DEFAULT_TEMPLATE

    def get(self, request: django.http.HttpRequest):
        """Return a rendered main view, selecting the template with
        globus_portal_framework.gsearch.get_template."""
        return render(request, self.template)


class CollectionSelectionView(View):

    DEFAULT_TEMPLATE = "collection-selection.html"

    def __init__(self, template=None):
        super().__init__()
        self.template = template or self.DEFAULT_TEMPLATE

    def get(self, request: django.http.HttpRequest):
        return render(request, self.template, self.get_context_data())


class StompLogsView(View):

    DEFAULT_TEMPLATE = "stomp-logs.html"

    def __init__(self, template=None):
        super().__init__()
        self.template = template or self.DEFAULT_TEMPLATE

    def get_context_data(self):
        return {
            "STOMP_STREAM_QUEUE": settings.STOMP_STREAM_QUEUE,
            "RABBITMQ_DEFAULT_USER": settings.RABBITMQ_DEFAULT_USER,
            "RABBITMQ_DEFAULT_PASS": settings.RABBITMQ_DEFAULT_PASS,
        }

    def get(self, request: django.http.HttpRequest):
        return render(request, self.template, self.get_context_data())