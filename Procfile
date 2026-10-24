web: gunicorn agridep.config.wsgi:application --bind 0.0.0.0:$PORT --workers 3 --timeout 120
worker: python -m celery -A agridep.config worker -l info --concurrency 2
beat: python -m celery -A agridep.config beat -l info
