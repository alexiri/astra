from pathlib import Path
import os

import environ
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
)

# Optional local env file support (docker-compose already sets env vars).
environ.Env.read_env(os.path.join(BASE_DIR, ".env"))

DEBUG = env.bool("DEBUG", default=False)

SECRET_KEY = env(
    "SECRET_KEY",
    default="django-insecure-dev-only-change-me",
)
if not DEBUG and SECRET_KEY.startswith("django-insecure-dev-only"):
    raise ImproperlyConfigured("SECRET_KEY must be set in production.")

_dev_allowed_hosts = ["localhost", "127.0.0.1", "[::1]"]
ALLOWED_HOSTS = env.list(
    "ALLOWED_HOSTS",
    default=_dev_allowed_hosts if DEBUG else [],
)
if not DEBUG and not ALLOWED_HOSTS:
    raise ImproperlyConfigured("ALLOWED_HOSTS must be set in production.")

INSTALLED_APPS = [
    'jazzmin',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'core',
]

# Disable migrations for Django's built-in 'auth' app to silence
# warnings caused by unmanaged models that share the 'auth' label. Enable via
# env var DISABLE_AUTH_MIGRATIONS=1 in container/env when running without a DB.
if os.environ.get('DISABLE_AUTH_MIGRATIONS') == '1':
    MIGRATION_MODULES = {
        'auth': None,
    }

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'core.middleware.FreeIPAAuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# Database
# https://docs.djangoproject.com/en/5.0/ref/settings/#databases
DATABASES = {
    'default': {
        **env.db(
            'DATABASE_URL',
            default='postgres://postgres:postgres@db:5432/almalinux_members',
        ),
    }
}

# Password validation
# https://docs.djangoproject.com/en/5.0/ref/settings/#auth-password-validators
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
# https://docs.djangoproject.com/en/5.0/topics/i18n/
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Security
# Keep these production-oriented but configurable; many deployments sit behind
# a TLS-terminating proxy/load balancer.
if not DEBUG:
    # If you're behind a reverse proxy that sets X-Forwarded-Proto.
    if env.bool("SECURE_PROXY_SSL", default=True):
        SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

    SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=False)
    SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", default=True)
    CSRF_COOKIE_SECURE = env.bool("CSRF_COOKIE_SECURE", default=True)
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = env("SECURE_REFERRER_POLICY", default="same-origin")

    # HSTS is opt-in by default because it can brick HTTP-only deployments.
    SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=0)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", default=False)
    SECURE_HSTS_PRELOAD = env.bool("SECURE_HSTS_PRELOAD", default=False)

    CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.0/howto/static-files/
STATIC_URL = 'static/'

# Production collectstatic target.
STATIC_ROOT = BASE_DIR / "staticfiles"

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/login/'

FREEIPA_CACHE_TIMEOUT = env.int("FREEIPA_CACHE_TIMEOUT", default=300)

# Default primary key field type
# https://docs.djangoproject.com/en/5.0/ref/settings/#default-auto-field
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Authentication Backends
AUTHENTICATION_BACKENDS = [
    'core.backends.FreeIPAAuthBackend',
]

# FreeIPA Configuration
FREEIPA_HOST = env("FREEIPA_HOST", default="ipa.demo1.freeipa.org")
FREEIPA_VERIFY_SSL = env.bool("FREEIPA_VERIFY_SSL", default=True)
FREEIPA_SERVICE_USER = env("FREEIPA_SERVICE_USER", default="admin")
FREEIPA_SERVICE_PASSWORD = env("FREEIPA_SERVICE_PASSWORD", default="")
if not FREEIPA_SERVICE_PASSWORD:
    raise ImproperlyConfigured("FREEIPA_SERVICE_PASSWORD must be set.")
FREEIPA_ADMIN_GROUP = env("FREEIPA_ADMIN_GROUP", default="admins")

# Map FreeIPA groups to Django permissions
# Format: {'freeipa_group_name': {'app_label.permission_codename', ...}}
FREEIPA_GROUP_PERMISSIONS = {
    'content_editors': {'core.add_article', 'core.change_article'},
    'moderators': {'core.delete_article'},
}

# Caching
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'unique-snowflake',
        'TIMEOUT': 300,
    }
}

# Logging
# Ensure app logs (including FreeIPA integration) are visible in container stdout.
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'console': {
            'format': '[{asctime}] {levelname} {name}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'console',
        },
    },
    'loggers': {
        # Our app
        'core': {
            'handlers': ['console'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        # FreeIPA client libs can be noisy; keep them at INFO by default.
        'python_freeipa': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        # Django request errors still visible
        'django.request': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
    },
}
