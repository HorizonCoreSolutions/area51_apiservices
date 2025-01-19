"""
ASGI entrypoint. Configures Django and then runs the application
defined in the ASGI_APPLICATION setting.
"""

import os
import django
from channels.routing import get_default_application

settings_file = 'local' if os.environ.get('IS_LOCAL_ENV') else 'production'


os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api_services.settings.' + settings_file)

django.setup()
application = get_default_application()

