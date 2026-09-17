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
    "apps.core",
    "apps.users",
    "apps.warehouse",
    "apps.accounts",
    "apps.accountants",
    "apps.reports",
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
    "apps.core.middleware.HtmxMiddleware",
]

ROOT_URLCONF = "isp_management.urls"

# Moving the admin off the default path removes it from the most common
# scanner wordlist. Not a security control on its own, just less noise.
ADMIN_URL = config("ADMIN_URL", default="admin/")

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
                "apps.core.context_processors.site",
                "apps.core.context_processors.nav_badges",
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
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"

# Sessions expire after a day of inactivity and never outlive the browser.
SESSION_COOKIE_AGE = config("SESSION_COOKIE_AGE", default=60 * 60 * 24, cast=int)
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

# Login brute-force throttle (see apps/users/throttle.py).
LOGIN_FAILURE_LIMIT = config("LOGIN_FAILURE_LIMIT", default=6, cast=int)
LOGIN_FAILURE_TIMEOUT = config("LOGIN_FAILURE_TIMEOUT", default=900, cast=int)
# Only honour X-Forwarded-For when something trustworthy sets it.
TRUST_PROXY_HEADERS = config("TRUST_PROXY_HEADERS", default=False, cast=bool)


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
# Caches
# ---------------------------------------------------------------------------#

# The login throttle and dashboard fragments need a shared cache in production;
# locmem is per-process and would let each gunicorn worker count separately.
CACHES = {
    "default": (
        {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": config("REDIS_URL", default=""),
        }
        if config("REDIS_URL", default="")
        else {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "isp-management",
        }
    )
}


# ---------------------------------------------------------------------------#
# Business defaults
# ---------------------------------------------------------------------------#

SITE_NAME = config("SITE_NAME", default="ISP Manager")
CURRENCY_SYMBOL = config("CURRENCY_SYMBOL", default="৳")


# ---------------------------------------------------------------------------#
# Third party
# ---------------------------------------------------------------------------#

CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"
CRISPY_TEMPLATE_PACK = "bootstrap5"

JAZZMIN_SETTINGS = {
    "site_title": f"{SITE_NAME} admin",
    "site_header": SITE_NAME,
    "site_brand": SITE_NAME,
    "welcome_sign": f"{SITE_NAME} back office",
    "show_ui_builder": False,
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
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "same-origin"
    SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

# Cap request bodies; nothing here legitimately uploads megabytes.
DATA_UPLOAD_MAX_MEMORY_SIZE = config(
    "DATA_UPLOAD_MAX_MEMORY_SIZE", default=5 * 1024 * 1024, cast=int
)
DATA_UPLOAD_MAX_NUMBER_FIELDS = 2000
FILE_UPLOAD_MAX_MEMORY_SIZE = DATA_UPLOAD_MAX_MEMORY_SIZE


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
    "loggers": {
        "django.security": {"handlers": ["console"], "level": "INFO", "propagate": False},
        # Auth events (logins, lockouts, role changes) are worth keeping even
        # when the root logger is turned down.
        "apps.users": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "apps.accountants": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
    "root": {
        "handlers": ["console"],
        "level": config("LOG_LEVEL", default="INFO"),
    },
}


DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
