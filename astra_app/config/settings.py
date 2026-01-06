import datetime
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

import environ
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

print(f"[settings.py] os.environ len {len(os.environ['SECRET_KEY']) if 'SECRET_KEY' in os.environ else 'MISSING'}")
env = environ.Env(
    DEBUG=(bool, False),
)
try:
    if 'SECRET_KEY' in env:
        k = env("SECRET_KEY")
    else:
        k = 'MISSING'
    print(f"[settings.py] env len {len(k) if k != 'MISSING' else 'MISSING'}")
except Exception as e:
    print(f"[settings.py] env SECRET_KEY access error: {e}")


DEBUG = env.bool("DEBUG", default=False)

# Optional local env file support.
#
# IMPORTANT: this must never override runtime secrets injected by the platform
# (ECS secrets -> environment variables). Make it opt-in and non-overriding.
if os.environ.get("DJANGO_READ_DOTENV") == "1":
    print(f"[settings.py] Reading .env file for local development")
    environ.Env.read_env(os.path.join(BASE_DIR, ".env"), overwrite=False)

# Django management commands (e.g. `migrate`) still import settings, but they don't
# need certain web-runtime-only secrets. This makes one-off tasks safer and easier
# to run without granting access to unrelated secrets.
_DJANGO_SUBCOMMAND = sys.argv[1] if len(sys.argv) > 1 else ""
_ALLOW_MISSING_RUNTIME_SECRETS = _DJANGO_SUBCOMMAND in {
    "migrate",
    "makemigrations",
    "showmigrations",
    "sqlmigrate",
}

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

_DEFAULT_SECRET_KEY_PLACEHOLDER = "django-insecure-dev-only-change-me"
SECRET_KEY = env(
    "SECRET_KEY",
    default=_DEFAULT_SECRET_KEY_PLACEHOLDER,
)

print(f"[settings.py] len(SECRET_KEY)={len(SECRET_KEY)}, is placeholder={SECRET_KEY == _DEFAULT_SECRET_KEY_PLACEHOLDER}")
if not DEBUG and not _ALLOW_MISSING_RUNTIME_SECRETS:
    if "SECRET_KEY" not in os.environ:
        raise ImproperlyConfigured(
            "SECRET_KEY must be set in production (SECRET_KEY env var is missing)."
        )
    # Avoid the default placeholder and overly-short values.
    if SECRET_KEY == _DEFAULT_SECRET_KEY_PLACEHOLDER:
        raise ImproperlyConfigured(
            "SECRET_KEY must be set in production (value is the insecure placeholder)."
        )
    if len(SECRET_KEY) <= 32:
        raise ImproperlyConfigured(
            "SECRET_KEY value is too weak."
        )

_dev_allowed_hosts = ["localhost", "127.0.0.1", "[::1]"]
ALLOWED_HOSTS = env.list(
    "ALLOWED_HOSTS",
    default=_dev_allowed_hosts if DEBUG else [],
)
if not DEBUG and not _ALLOW_MISSING_RUNTIME_SECRETS and not ALLOWED_HOSTS:
    raise ImproperlyConfigured("ALLOWED_HOSTS must be set in production.")

INSTALLED_APPS = [
    'jazzmin',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'import_export',
    'storages',
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
    'core.middleware.LoginRequiredMiddleware',
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
                'core.context_processors.membership_review',
                'core.context_processors.organization_nav',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# Database
# https://docs.djangoproject.com/en/5.0/ref/settings/#databases

_database_url = env("DATABASE_URL", default=None)
if not _database_url:
    # In containerized environments (ECS), it's common to inject the database password
    # as a dedicated secret env var rather than embedding it in DATABASE_URL.
    db_host = env("DATABASE_HOST", default=None)
    if db_host:
        from urllib.parse import quote

        db_port = env("DATABASE_PORT", default="5432")
        db_name = env("DATABASE_NAME", default="")
        db_user = env("DATABASE_USER", default="")
        db_password = env("DATABASE_PASSWORD", default="")
        if not db_name or not db_user:
            raise ImproperlyConfigured(
                "DATABASE_NAME and DATABASE_USER must be set when using DATABASE_HOST/DATABASE_PASSWORD."
            )

        user_enc = quote(db_user, safe="")
        pass_enc = quote(db_password, safe="")
        name_enc = quote(db_name, safe="")
        _database_url = f"postgres://{user_enc}:{pass_enc}@{db_host}:{db_port}/{name_enc}"

DATABASES = {
    'default': {
        **env.db(
            'DATABASE_URL',
            default=_database_url or 'postgres://postgres:postgres@db:5432/almalinux_members',
        ),
    }
}

JAZZMIN_SETTINGS = {
    "site_title": "AlmaLinux Astra",
    "custom_css": "core/css/admin.css",
}

# Email
# In DEBUG, docker-compose provides EMAIL_URL pointing to Mailhog.
_email_url_raw = os.environ.get("EMAIL_URL", "").strip()
EMAIL_CONFIG = env.email_url("EMAIL_URL") if _email_url_raw else None
if EMAIL_CONFIG:
    globals().update(EMAIL_CONFIG)

DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default='webmaster@localhost')

# Public base URL used for absolute links in email (cron jobs don't have a request
# context). Example: https://accounts.almalinux.org
PUBLIC_BASE_URL = env("PUBLIC_BASE_URL", default="http://localhost:8000")

# Elections
ELECTION_ELIGIBILITY_MIN_MEMBERSHIP_AGE_DAYS = env.int(
    "ELECTION_ELIGIBILITY_MIN_MEMBERSHIP_AGE_DAYS",
    default=0 if DEBUG else 90,
)

# Membership workflow
MEMBERSHIP_EXPIRING_SOON_DAYS = env.int("MEMBERSHIP_EXPIRING_SOON_DAYS", default=60)
MEMBERSHIP_VALIDITY_DAYS = env.int("MEMBERSHIP_VALIDITY_DAYS", default=365)
MEMBERSHIP_EXPIRING_SOON_EMAIL_TEMPLATE_NAME = env(
    "MEMBERSHIP_EXPIRING_SOON_EMAIL_TEMPLATE_NAME",
    default="membership-expiring-soon",
)
MEMBERSHIP_EXPIRED_EMAIL_TEMPLATE_NAME = env(
    "MEMBERSHIP_EXPIRED_EMAIL_TEMPLATE_NAME",
    default="membership-expired",
)
MEMBERSHIP_REQUEST_SUBMITTED_EMAIL_TEMPLATE_NAME = env(
    "MEMBERSHIP_REQUEST_SUBMITTED_EMAIL_TEMPLATE_NAME",
    default="membership-request-submitted",
)
MEMBERSHIP_REQUEST_APPROVED_EMAIL_TEMPLATE_NAME = env(
    "MEMBERSHIP_REQUEST_APPROVED_EMAIL_TEMPLATE_NAME",
    default="membership-request-approved-individual",
)
MEMBERSHIP_REQUEST_REJECTED_EMAIL_TEMPLATE_NAME = env(
    "MEMBERSHIP_REQUEST_REJECTED_EMAIL_TEMPLATE_NAME",
    default="membership-request-rejected",
)

MEMBERSHIP_COMMITTEE_PENDING_REQUESTS_EMAIL_TEMPLATE_NAME = env(
    "MEMBERSHIP_COMMITTEE_PENDING_REQUESTS_EMAIL_TEMPLATE_NAME",
    default="membership-committee-pending-requests",
)

PASSWORD_RESET_TOKEN_TTL_SECONDS = env.int("PASSWORD_RESET_TOKEN_TTL_SECONDS", default=60 * 60)
PASSWORD_RESET_EMAIL_TEMPLATE_NAME = env(
    "PASSWORD_RESET_EMAIL_TEMPLATE_NAME",
    default="password-reset",
)
PASSWORD_RESET_SUCCESS_EMAIL_TEMPLATE_NAME = env(
    "PASSWORD_RESET_SUCCESS_EMAIL_TEMPLATE_NAME",
    default="password-reset-success",
)

ELECTION_VOTING_CREDENTIAL_EMAIL_TEMPLATE_NAME = env(
    "ELECTION_VOTING_CREDENTIAL_EMAIL_TEMPLATE_NAME",
    default="election-voting-credential",
)

ELECTION_VOTE_RECEIPT_EMAIL_TEMPLATE_NAME = env(
    "ELECTION_VOTE_RECEIPT_EMAIL_TEMPLATE_NAME",
    default="election-vote-receipt",
)

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

# Uploaded media (e.g. Organization.logo)
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# S3-backed storage for uploaded media.
STORAGES = {
    "default": {"BACKEND": "storages.backends.s3boto3.S3Boto3Storage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

AWS_STORAGE_BUCKET_NAME = env("AWS_STORAGE_BUCKET_NAME", default="")
AWS_S3_REGION_NAME = env("AWS_S3_REGION_NAME", default="us-east-1")
AWS_S3_ENDPOINT_URL = env("AWS_S3_ENDPOINT_URL", default="") or None

# Optional: separate the URL used in rendered pages from the internal API endpoint.
# This is useful in docker-compose where Django must reach MinIO via the service
# name (e.g. http://minio:9000) but browsers reach it via localhost port mapping.
#
# Historically we used AWS_S3_URL_PROTOCOL + AWS_S3_CUSTOM_DOMAIN for this, but
# those settings have been replaced by PUBLIC_BASE_URL + AWS_STORAGE_BUCKET_NAME.
_public_base_url_raw = str(PUBLIC_BASE_URL or "").strip()
if "://" not in _public_base_url_raw:
    _public_base_url_raw = f"https://{_public_base_url_raw}"

_aws_s3_domain_raw = env("AWS_S3_DOMAIN", default="")
if not _ALLOW_MISSING_RUNTIME_SECRETS:
    if not AWS_STORAGE_BUCKET_NAME:
        raise ImproperlyConfigured("AWS_STORAGE_BUCKET_NAME must be set.")
    if not _aws_s3_domain_raw:
        raise ImproperlyConfigured("AWS_S3_DOMAIN must be set.")
else:
    if not AWS_STORAGE_BUCKET_NAME:
        AWS_STORAGE_BUCKET_NAME = "migrations-placeholder"
    if not _aws_s3_domain_raw:
        _aws_s3_domain_raw = "http://localhost"

_aws_s3_domain = urlsplit(_aws_s3_domain_raw)
AWS_S3_URL_PROTOCOL = f"{_aws_s3_domain.scheme}:"
_aws_s3_base_domain = (_aws_s3_domain.netloc + _aws_s3_domain.path.rstrip("/")).strip("/")
AWS_S3_CUSTOM_DOMAIN = f"{_aws_s3_base_domain}/{AWS_STORAGE_BUCKET_NAME}" 

# MinIO compatibility and predictable URLs.
AWS_S3_ADDRESSING_STYLE = env("AWS_S3_ADDRESSING_STYLE", default="path")
AWS_QUERYSTRING_AUTH = env.bool("AWS_QUERYSTRING_AUTH", default=False)
AWS_DEFAULT_ACL = None

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
    'avatar.providers.GravatarAvatarProvider',
    'avatar.providers.LibRAvatarProvider',
    'avatar.providers.DefaultAvatarProvider',
)
AVATAR_GRAVATAR_DEFAULT = env('AVATAR_GRAVATAR_DEFAULT', default='identicon')

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
if not _ALLOW_MISSING_RUNTIME_SECRETS and not FREEIPA_SERVICE_PASSWORD:
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
