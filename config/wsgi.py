"""
WSGI config for dry_lab_notebook project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application
from dry_lab_notebook.globus import initialize_globus

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
initialize_globus()

application = get_wsgi_application()
