"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
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
from django.conf import settings
from django.contrib import admin
from django.http import FileResponse, Http404
from django.urls import include, path, re_path
from django.views.static import serve

from portal.analytics import analytics_dashboard


def react_app(request):
    """Return the built React page; React Router then shows the right screen."""
    index = settings.FRONTEND_DIST / 'index.html'
    if not index.exists():
        raise Http404('Run "npm run build" in frontend/ first.')
    return FileResponse(index.open('rb'), content_type='text/html')


urlpatterns = [
    # Before admin/, which would otherwise treat this path as an unknown page.
    path('admin/analytics/', analytics_dashboard, name='analytics'),
    path('admin/', admin.site.urls),
    path('api/', include('portal.urls')),
    # Uploaded files (article banners, avatars). Fine for a small demo site;
    # a busy site would put these on a file host instead.
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
    # Every other URL is a page of the React app, e.g. /documents/some-slug.
    re_path(r'^(?!(?:api|admin|static|media)(?:/|$)).*$', react_app),
]
