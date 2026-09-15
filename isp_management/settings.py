"""
Django settings for the isp_management project.

Configuration is environment-driven (12-factor): copy `.env.example` to `.env`
and override per environment. Nothing in this file should need editing to move
between local, staging and production.

Docs: https://docs.djangoproject.com/en/6.1/ref/settings/
"""

from pathlib import Path

import dj_database_url
from decouple import Csv, config

BASE_DIR = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------#
# Core
# ---------------------------------------------------------------------------#

# SECURITY WARNING: keep the secret key used in production secret.
SECRET_KEY = config("SECRET_KEY")

# SECURITY WARNING: never run with debug turned on in production.
DEBUG = config("DEBUG", default=False, cast=bool)

ALLOWED_HOSTS = config(
    "ALLOWED_HOSTS",
    default="localhost,127.0.0.1,[::1]",
    cast=Csv(),
)

# Hosts allowed to submit cross-origin POSTs (must include the scheme).
CSRF_TRUSTED_ORIGINS = config("CSRF_TRUSTED_ORIGINS", default="", cast=Csv())


# ---------------------------------------------------------------------------#
# Applications
# ---------------------------------------------------------------------------#

INSTALLED_APPS = [
    # third party admin theme (must precede django.contrib.admin)
    "jazzmin",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # third party apps
    "crispy_forms",
    "crispy_bootstrap5",
    "django_filters",
    # local apps
    "apps.warehouse",
    "apps.accounts",
    "apps.accountants",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise serves static files; it must sit directly below SecurityMiddleware.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "isp_management.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "isp_management.wsgi.application"
ASGI_APPLICATION = "isp_management.asgi.application"


# ---------------------------------------------------------------------------#
# Database
# ---------------------------------------------------------------------------#

DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=config("DB_CONN_MAX_AGE", default=600, cast=int),
        conn_health_checks=True,
        ssl_require=config("DB_SSL_REQUIRE", default=False, cast=bool),
    )
}


# ---------------------------------------------------------------------------#
# Authentication
# ---------------------------------------------------------------------------#

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "clients"
LOGOUT_REDIRECT_URL = "login"


# ---------------------------------------------------------------------------#
# Internationalization
# ---------------------------------------------------------------------------#

LANGUAGE_CODE = "en-us"
TIME_ZONE = config("TIME_ZONE", default="UTC")
USE_I18N = True
USE_TZ = True


# ---------------------------------------------------------------------------#
# Static & media files
# ---------------------------------------------------------------------------#

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        # Hashed + compressed in production; plain (no manifest) under DEBUG so
        # `runserver` does not require a `collectstatic` run first.
        "BACKEND": (
            "whitenoise.storage.CompressedManifestStaticFilesStorage"
            if not DEBUG
            else "django.contrib.staticfiles.storage.StaticFilesStorage"
        ),
    },
}


# ---------------------------------------------------------------------------#
# Third party
# ---------------------------------------------------------------------------#

CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"
CRISPY_TEMPLATE_PACK = "bootstrap5"

JAZZMIN_SETTINGS = {
    "site_title": "internet service provider dashboard",
    "site_header": "service provider dashboard",
    "site_brand": "service provider dashboard",
}


# ---------------------------------------------------------------------------#
# Security (production hardening — inert while DEBUG is on)
# ---------------------------------------------------------------------------#

if not DEBUG:
    SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=True, cast=bool)
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_HSTS_SECONDS = config("SECURE_HSTS_SECONDS", default=31536000, cast=int)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    X_FRAME_OPTIONS = "DENY"


# ---------------------------------------------------------------------------#
# Logging
# ---------------------------------------------------------------------------#

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": config("LOG_LEVEL", default="INFO"),
    },
}


DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
