from django.conf import settings
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from core.views_auth import FreeIPALoginView, otp_sync, password_expired
from core.views_health import healthz, readyz

urlpatterns = [
    path('healthz/', healthz, name='healthz'),
    path('readyz/', readyz, name='readyz'),
    path('login/', FreeIPALoginView.as_view(), name='login'),
    path('otp/sync/', otp_sync, name='otp-sync'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('password-expired/', password_expired, name='password-expired'),
    path('admin/', admin.site.urls),
    path('', include('core.urls')),
]

if settings.DEBUG:
    from core.debug_views import cache_debug_view

    urlpatterns += [
        path('__debug__/cache/', cache_debug_view, name='cache-debug'),
    ]
