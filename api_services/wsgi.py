"""
WSGI config for api_services project.
It exposes the WSGI callable as a module-level variable named ``application``.
For more information on this file, see
https://docs.djangoproject.com/en/1.8/howto/deployment/wsgi/
"""

import os

import dotenv
from django.core.wsgi import get_wsgi_application
# import newrelic.agent

settings_file = 'local' if os.environ.get('IS_LOCAL_ENV') else 'production'

dotenv.read_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api_services.settings.' + settings_file)

application = get_wsgi_application()
# newrelic.agent.initialize(os.path.join(os.path.dirname(__file__), "newrelic.ini"))
# application = newrelic.agent.WSGIApplicationWrapper(application)
