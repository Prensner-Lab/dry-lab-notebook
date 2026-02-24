from globus_portal_framework.views.generic import SearchView as DGPFSearchView
import globus_sdk

from config.settings import CLIENT_ID, CLIENT_SECRET

class SearchView(DGPFSearchView):

    def get_search_client(self) -> globus_sdk.SearchClient:
        '''
        Override default and use [client credentials](https://globus-sdk-python.readthedocs.io/en/stable/examples/client_credentials.html)
        to provide auth'ed client for Globus Search.
        
        :rtype: SearchClient
        '''
        confidential_client = globus_sdk.ConfidentialAppAuthClient(
            client_id=CLIENT_ID, client_secret=CLIENT_SECRET
        )
        cc_authorizer = globus_sdk.ClientCredentialsAuthorizer(
            confidential_client, globus_sdk.SearchClient.scopes.search
        )
        client = globus_sdk.SearchClient(authorizer=cc_authorizer)
        return client
    
    def post_search(self, client, index_uuid, search_client_data):
        search_client_data['q_settings'] = {
            'mode': 'text_match',
            'fuzziness': 2
        }
        return super().post_search(client, index_uuid, search_client_data)
