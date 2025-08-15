#!/usr/bin/env python
import os
import sys

import dotenv

if __name__ == "__main__":
    dotenv.read_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

    settings_file = 'local' if os.environ.get('IS_LOCAL_ENV') else 'production'

    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api_services.settings.' + settings_file)
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)
