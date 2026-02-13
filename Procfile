web: uv run manage.py runserver 0.0.0.0:8000
worker: celery -A proj worker -l INFO
beat: celery -A conf.celery beat -l INFO --scheduler django_celery_beat.schedulers:DatabaseScheduler