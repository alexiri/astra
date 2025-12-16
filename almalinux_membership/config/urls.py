from django.contrib import admin
from django.conf import settings
from django.urls import path

from core.debug_views import cache_debug_view

urlpatterns = [
    path('admin/', admin.site.urls),
]

if settings.DEBUG:
    urlpatterns += [
        path('__debug__/cache/', cache_debug_view, name='cache-debug'),
    ]
