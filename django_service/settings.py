"""Django settings with SQLite demo fallback and PostgreSQL production support."""
import os
import sys
from pathlib import Path
from urllib.parse import urlparse, unquote, parse_qs
from dotenv import load_dotenv
from django.core.management.utils import get_random_secret_key

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
# Set a persistent shared key in .env for multi-process/deployed environments.
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY") or get_random_secret_key()
DEBUG = os.getenv("DJANGO_DEBUG", "true").lower() == "true"
ALLOWED_HOSTS = [item.strip() for item in os.getenv("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")]

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "rest_framework",
    "raileta_api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "raileta_api.middleware.CorsMiddleware",
]

ROOT_URLCONF = "django_service.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]
WSGI_APPLICATION = "django_service.wsgi.application"
ASGI_APPLICATION = "django_service.asgi.application"

database_url = os.getenv("DATABASE_URL", "")
if database_url.startswith("postgres") or os.getenv("POSTGRES_HOST"):
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("POSTGRES_DB", "raileta"),
        "USER": os.getenv("POSTGRES_USER", "raileta"),
        "PASSWORD": os.getenv("POSTGRES_PASSWORD", "raileta"),
        "HOST": os.getenv("POSTGRES_HOST", "db"),
        "PORT": os.getenv("POSTGRES_PORT", "5432"),
    }}
    if database_url:
        parsed = urlparse(database_url)
        DATABASES["default"].update({
            "NAME": unquote(parsed.path.lstrip("/")),
            "USER": unquote(parsed.username or ""),
            "PASSWORD": unquote(parsed.password or ""),
            "HOST": parsed.hostname or "localhost",
            "PORT": str(parsed.port or 5432),
        })
        sslmode = parse_qs(parsed.query).get("sslmode", [None])[0]
        if sslmode:
            DATABASES["default"]["OPTIONS"] = {"sslmode": sslmode}
else:
    DATA_DIR = BASE_DIR / "data"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": DATA_DIR / "raileta_demo.sqlite3", "OPTIONS": {"timeout": 30}}}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "UNAUTHENTICATED_USER": None,
}

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", CELERY_BROKER_URL)
TESTING = os.getenv("TESTING", "false").lower() in {"1", "true", "yes"} or "test" in sys.argv or "pytest" in sys.modules
# Eager execution is intentionally test-only. Local/demo runtime uses Redis so
# worker and beat failures cannot be hidden by inline task execution.
CELERY_TASK_ALWAYS_EAGER = TESTING
CELERY_TASK_EAGER_PROPAGATES = TESTING
if TESTING:
    # Tests must never send tasks or results to the running demo's broker.
    CELERY_BROKER_URL = "memory://"
    CELERY_RESULT_BACKEND = "cache+memory://"
CELERY_BEAT_SCHEDULE = {
    'dated-journey-sweep': {'task': 'raileta.sweep_journeys', 'schedule': 60.0},
    # Keep the scheduled worker aligned with the local collector cadence.
    "ingest-data-sources": {"task": "raileta.ingest_data_sources", "schedule": float(os.getenv("RAILETA_COLLECTOR_INTERVAL_SECONDS", "30"))},
    "nightly-retrain": {"task": "raileta.nightly_retrain", "schedule": 86400.0},
}
RAILETA_CONFIDENCE_LEVEL = float(os.getenv("RAILETA_CONFIDENCE_LEVEL", "0.80"))
RAILETA_MODEL_VERSION = os.getenv("RAILETA_MODEL_VERSION", "demo-event-v1")
RAILETA_JOURNEY_INGEST_TOKEN = os.getenv('RAILETA_JOURNEY_INGEST_TOKEN', '')
RAILETA_JOURNEY_RETRAIN_ENABLED = os.getenv('RAILETA_JOURNEY_RETRAIN_ENABLED', 'false').lower() == 'true'
PUBLIC_NTES_URL = os.getenv("PUBLIC_NTES_URL", "")
IMD_WEATHER_URL = os.getenv("IMD_WEATHER_URL", "")
OPEN_METEO_URL = os.getenv("OPEN_METEO_URL", "https://api.open-meteo.com/v1/forecast")
OPEN_METEO_ENABLED = os.getenv("OPEN_METEO_ENABLED", "false").lower() == "true"
RAILETA_STORE_RAW_PAYLOADS = os.getenv("RAILETA_STORE_RAW_PAYLOADS", "true").lower() == "true"
RAILETA_RAW_DATA_DIR = os.getenv("RAILETA_RAW_DATA_DIR", "data/raw")
PUBLIC_RAILYATRI_URL_TEMPLATE = os.getenv(
    "PUBLIC_RAILYATRI_URL_TEMPLATE",
    "https://www.railyatri.in/live-train-status/{train_number}",
)
RAILETA_TRAIN_NUMBERS = tuple(
    value.strip() for value in os.getenv("RAILETA_TRAIN_NUMBERS", "12007,12639,12607,22625,12609").split(",") if value.strip()
)
RAILETA_COLLECTOR_INTERVAL_SECONDS = int(os.getenv("RAILETA_COLLECTOR_INTERVAL_SECONDS", "30"))
RAILETA_DATA_ADAPTER = os.getenv("RAILETA_DATA_ADAPTER", "historical_profiles").strip().lower()
if RAILETA_DATA_ADAPTER == 'corridor_simulation' and not TESTING:
    # Isolate the new demo from any queued legacy collector/reforecast work.
    CELERY_TASK_DEFAULT_QUEUE = 'raileta-synthetic'
RAILETA_HISTORICAL_MODEL_DIR = str(BASE_DIR / os.getenv("RAILETA_HISTORICAL_MODEL_DIR", "data/models/etrain-profiles-v1"))
RAILETA_REPLAY_INTERVAL_SECONDS = max(1, int(os.getenv("RAILETA_REPLAY_INTERVAL_SECONDS", "15")))
if RAILETA_DATA_ADAPTER == "historical_profiles":
    # Frozen experiment: never retrain automatically on newly replayed labels.
    CELERY_BEAT_SCHEDULE.pop("nightly-retrain", None)
RAILETA_ENABLE_PUBLIC_SCRAPING = os.getenv("RAILETA_ENABLE_PUBLIC_SCRAPING", "false").lower() in {"1", "true", "yes"}
CRIS_REST_URL = os.getenv("CRIS_REST_URL", "")
RAILETA_EVENT_STALE_SECONDS = int(os.getenv("RAILETA_EVENT_STALE_SECONDS", "180"))
RAILETA_WEATHER_INTERVAL_SECONDS = max(60, int(os.getenv("RAILETA_WEATHER_INTERVAL_SECONDS", "900")))
