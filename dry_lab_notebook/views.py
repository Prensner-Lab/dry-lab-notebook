from pathlib import Path
import typing as t
import os
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

from config.settings import CLIENT_ID, CLIENT_SECRET

def get_client_from_client_credentials() -> globus_sdk.SearchClient:
    confidential_client = globus_sdk.ConfidentialAppAuthClient(
        client_id=CLIENT_ID, client_secret=CLIENT_SECRET
    )
    cc_authorizer = globus_sdk.ClientCredentialsAuthorizer(
        confidential_client, globus_sdk.SearchClient.scopes.search
    )
    client = globus_sdk.SearchClient(authorizer=cc_authorizer)
    return client

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
        return get_client_from_client_credentials()
    
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
    client = get_client_from_client_credentials()
    try:
        idata = get_index(index)
        result = client.get_subject(idata['uuid'], unquote_plus(subject))
        return process_search_data([result.data])[0]
    except globus_sdk.SearchAPIError:
        return {'subject': subject, 'error': 'No data was found for subject'}

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
        data["dirs"] = {name: "/" + "/".join(parts[:i+1]) for parts in [[pt for pt in str(path.parent).split('/') if pt]] for i, name in enumerate(parts)}
        return data

    def get(self, request: django.http.HttpRequest, index: str, subject: str):
        """Get context data, and return a rendered search view, selecting the template with
        globus_portal_framework.gsearch.get_template."""
        context = self.get_context_data(index, subject)
        return render(request, get_template(index, self.template), context)

class FileBrowserView(View):
    """File browser integrated with Globus Portal Framework"""
    DEFAULT_TEMPLATE = "select_browser.html"
    
    def __init__(self, template=None):
        super().__init__()
        self.template = template or self.DEFAULT_TEMPLATE
    
    def get_context_data(self, request, path='') -> dict:
        """Get directory and file listings for the given path"""
        root = settings.LOCAL_FS_BASE
        full_path = os.path.join(root, path)
        
        items = os.listdir(full_path)
        dirs = sorted([i for i in items if os.path.isdir(os.path.join(full_path, i))])
        files = sorted([i for i in items if os.path.isfile(os.path.join(full_path, i))])
        
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
        }
    
    def get(self, request):
        """Display file browser"""
        path = request.GET.get('path', '')
        context = self.get_context_data(request, path)
        return render(request, self.template, context)
    
    def post(self, request):
        """Process selected files"""
        selected_files = request.POST.getlist('files')
        # Logic for processing selected files goes here
        return render(request, 'task_success.html', {'files': selected_files})