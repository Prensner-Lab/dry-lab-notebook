"""
URL configuration for dry_lab_notebook project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include

import globus_portal_framework.urls  # Allows index converter usage
from globus_portal_framework.views import index_selection

from dry_lab_notebook import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path("<index:index>/", views.SearchView.as_view(), name="search"),
    path("<index:index>/detail/<subject>/", views.DetailView.as_view(), name="subject-detail"),
    path('browse-files/', views.FileBrowserView.as_view(), name='browse-files'),
    path('file-detail/', views.FileDetailView.as_view(), name='file-detail'),
    path('stomp-logs/', views.StompLogsView.as_view(), name='stomp-logs'),
    path('slurm-jobs/', views.SlurmJobsView.as_view(), name='slurm-jobs'),
    path('select-collection/', views.CollectionSelectionView.as_view(), name='select-collection'),
    path('select-index/', index_selection, name='select-index'),
    path('', views.ActivitiesView.as_view(), name='select-activity'),
    # Provides the basic search portal
    path('', include('globus_portal_framework.urls')),
    # Provides Login urls for Globus Auth
    path('', include('social_django.urls', namespace='social')),
]
