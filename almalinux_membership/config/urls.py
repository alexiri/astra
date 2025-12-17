from django.conf import settings
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from core.debug_views import cache_debug_view
from core.views_auth import FreeIPALoginView, password_expired

urlpatterns = [
    path('login/', FreeIPALoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('password-expired/', password_expired, name='password-expired'),
    path('admin/', admin.site.urls),
    path('', include('core.urls')),
]

if settings.DEBUG:
    urlpatterns += [
        path('__debug__/cache/', cache_debug_view, name='cache-debug'),
    ]
