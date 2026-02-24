import typing as t
import django
from django.views.generic import View
from django.shortcuts import render
from urllib.parse import quote_plus, unquote_plus

from globus_portal_framework.gsearch import (
    get_template,
    get_index,
    process_search_data,

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

class SearchView(DGPFSearchView):

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
        return process_search_data(idata.get('fields', {}), [result.data])[0]
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
        return get_subject(index, subject)

    def get(self, request: django.http.HttpRequest, index: str, subject: str):
        """Get context data, and return a rendered search view, selecting the template with
        globus_portal_framework.gsearch.get_template."""
        context = self.get_context_data(index, subject)
        return render(request, get_template(index, self.template), context)
