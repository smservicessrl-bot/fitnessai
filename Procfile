web: python manage.py migrate --noinput && python manage.py create_default_superuser && gunicorn fitness.wsgi:application --bind 0.0.0.0:$PORT
