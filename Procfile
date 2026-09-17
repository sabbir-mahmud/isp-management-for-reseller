release: python manage.py migrate --noinput
web: gunicorn isp_management.wsgi:application --config gunicorn.conf.py
