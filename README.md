# Edu System (Django)

    pip install -r requirements.txt        # (mysqlclient only if using MySQL)
    export DJANGO_DEBUG=1                  # dev; in production set DJANGO_SECRET_KEY instead
    python manage.py migrate
    python manage.py createsuperuser       # asks for email, name, password (role = admin)
    python manage.py runserver
    python manage.py test                  # 27 tests: login, roles, OTP reset, admin/teacher/student flows, checking + verification, file permissions

Django admin lives at /django-admin/. Reset codes print in the terminal until EMAIL_HOST is set.
See .env.example for configuration.
