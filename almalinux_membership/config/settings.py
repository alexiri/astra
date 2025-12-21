from pathlib import Path
import os

import environ
import datetime
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
)

# Optional local env file support (docker-compose already sets env vars).
environ.Env.read_env(os.path.join(BASE_DIR, ".env"))

DEBUG = env.bool("DEBUG", default=False)

# Development convenience: silence urllib3's InsecureRequestWarning spam when
# intentionally running with verify_ssl disabled (e.g. local FreeIPA with self-signed cert).
if DEBUG:
    try:
        import urllib3
        from urllib3.exceptions import InsecureRequestWarning

        urllib3.disable_warnings(InsecureRequestWarning)
    except Exception:
        # Best-effort; if urllib3 isn't available/changes, don't break startup.
        pass

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
    'logentry_admin',
    'post_office',
    'django_ses',
    'avatar',
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
    'core.middleware.FreeIPAServiceClientReuseMiddleware',
    'core.middleware.FreeIPAAuthenticationMiddleware',
    'core.middleware_admin_log.AdminShadowUserLogEntryMiddleware',
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

JAZZMIN_SETTINGS = {
    "site_title": "AlmaLinux Astra",
    "custom_css": "core/css/admin.css",
}

# Email
# In DEBUG, docker-compose provides EMAIL_URL pointing to Mailhog.
EMAIL_CONFIG = env.email_url('EMAIL_URL', default=None)
if EMAIL_CONFIG:
    globals().update(EMAIL_CONFIG)

DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default='webmaster@localhost')

# Queue all Django mail through django-post_office.
EMAIL_BACKEND = 'post_office.EmailBackend'

# Configure post_office delivery backends.
# - DEBUG: deliver immediately via SMTP to Mailhog.
# - non-DEBUG: default delivery backend is AWS SES (django-ses); delivery still
#   requires running `python manage.py send_queued_mail` (or enabling Celery).
POST_OFFICE = {
    'DEFAULT_PRIORITY': 'now' if DEBUG else 'medium',
    'MESSAGE_ID_ENABLED': True,
    'MAX_RETRIES': 4,
    'RETRY_INTERVAL': datetime.timedelta(minutes=5),
    'BACKENDS': {
        'default': 'django.core.mail.backends.smtp.EmailBackend' if DEBUG else 'django_ses.SESBackend',
        'smtp': 'django.core.mail.backends.smtp.EmailBackend',
        'ses': 'django_ses.SESBackend',
    },
}

# django-ses (AWS SES)
# Used as the production delivery backend (see POST_OFFICE['BACKENDS']).
# Also provides a stats dashboard and an SNS event webhook (bounces, complaints,
# deliveries, opens, clicks).
AWS_SES_REGION_NAME = env('AWS_SES_REGION_NAME', default='us-east-1')

# Signature verification is recommended for production SNS webhooks. For local
# dev, allowing unsigned test payloads is convenient.
AWS_SES_VERIFY_EVENT_SIGNATURES = env.bool('AWS_SES_VERIFY_EVENT_SIGNATURES', default=not DEBUG)

# Restrict certificate download domains for SNS signature verification.
# Prefer the full SNS domain for your region.
AWS_SNS_EVENT_CERT_TRUSTED_DOMAINS = env.list(
    'AWS_SNS_EVENT_CERT_TRUSTED_DOMAINS',
    default=[f'sns.{AWS_SES_REGION_NAME}.amazonaws.com'],
)

# Optional blacklisting behavior: when enabled, bounce/complaint signals will
# add recipients to django_ses.BlacklistedEmail and the SES backend will avoid
# sending to them.
AWS_SES_USE_BLACKLIST = env.bool('AWS_SES_USE_BLACKLIST', default=not DEBUG)
AWS_SES_ADD_BOUNCE_TO_BLACKLIST = env.bool('AWS_SES_ADD_BOUNCE_TO_BLACKLIST', default=not DEBUG)
AWS_SES_ADD_COMPLAINT_TO_BLACKLIST = env.bool('AWS_SES_ADD_COMPLAINT_TO_BLACKLIST', default=not DEBUG)

# Optional: tag outgoing mail with a configuration set for event publishing.
AWS_SES_CONFIGURATION_SET = env('AWS_SES_CONFIGURATION_SET', default='') or None

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
STATIC_URL = '/static/'

# Production collectstatic target.
STATIC_ROOT = BASE_DIR / "staticfiles"

# Profile chat link formatting (Noggin-style).
CHAT_NETWORKS = {
    "irc": {"default_server": env("CHAT_IRC_DEFAULT_SERVER", default="irc.libera.chat")},
    "matrix": {"default_server": env("CHAT_MATRIX_DEFAULT_SERVER", default="matrix.org")},
}

# Optional query string appended to matrix.to links (Element web instance).
CHAT_MATRIX_TO_ARGS = env("CHAT_MATRIX_TO_ARGS", default="web-instance[element.io]=app.element.io")

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/login/'

# django-avatar configuration
# Avoid the PrimaryAvatarProvider (DB-backed Avatar records) to prevent ORM
# lookups against AUTH_USER_MODEL for request.user objects.
AVATAR_PROVIDERS = (
    'avatar.providers.LibRAvatarProvider',
    'avatar.providers.GravatarAvatarProvider',
    'avatar.providers.DefaultAvatarProvider',
)
AVATAR_GRAVATAR_DEFAULT = env('AVATAR_GRAVATAR_DEFAULT', default='identicon')
# Only used if Gravatar provider cannot produce a URL (e.g. missing email).
AVATAR_DEFAULT_URL = env('AVATAR_DEFAULT_URL', default='')

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

# Reuse the FreeIPA service-account client across requests (per worker thread).
# This avoids repeated logins for admin/selfservice pages that trigger multiple
# FreeIPA reads, and retries automatically if the session expires.
FREEIPA_SERVICE_CLIENT_REUSE_ACROSS_REQUESTS = env.bool(
    "FREEIPA_SERVICE_CLIENT_REUSE_ACROSS_REQUESTS",
    default=True,
)

# Registration
# Inspired by Noggin's stage-user registration flow.
REGISTRATION_OPEN = env.bool("REGISTRATION_OPEN", default=True)
# Email validation token TTL.
EMAIL_VALIDATION_TOKEN_TTL_SECONDS = env.int('EMAIL_VALIDATION_TOKEN_TTL_SECONDS', default=60 * 60 * 24)
REGISTRATION_EMAIL_TEMPLATE_NAME = "registration-email-validation"
EMAIL_VALIDATION_EMAIL_TEMPLATE_NAME = "settings-email-validation"

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
    'filters': {
        'skip_healthz': {
            '()': 'core.logging_filters.SkipHealthzFilter',
        },
    },
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
            'filters': ['skip_healthz'],
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
        # Access logs from `runserver`.
        'django.server': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}
