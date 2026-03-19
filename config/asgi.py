"""
ASGI config for dry_lab_notebook project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application
from dry_lab_notebook.globus import initialize_globus

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
initialize_globus()

application = get_asgi_application()
