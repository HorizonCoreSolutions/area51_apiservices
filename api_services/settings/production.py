import sys

from .base import *

# import rollbar

DEBUG = False

INSTALLED_APPS = DEFAULT_APPS + THIRD_PARTY_APPS + PROJECT_APPS

#  Rollbar
MIDDLEWARE.append('rollbar.contrib.django.middleware.RollbarNotifierMiddleware')

# ROLLBAR = {
#     'access_token': get_env_var('ROLLBAR_ACCESS_TOKEN'),
#     'environment': get_env_var('ENV', 'production'),
#     'enabled': True,
#     'class': 'rollbar.logger.RollbarHandler',
#     'level': 'WARNING',
#     'root': BASE_DIR
# }

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'file': {
            'level': 'DEBUG',
            'class': 'logging.FileHandler',
            'filename': os.path.join(BASE_DIR, 'logs', 'errors.log'),
        },
        'console': {
            'class': 'logging.StreamHandler',
            'stream': sys.stdout,
            'level': 'DEBUG',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG',
            'propagate': True,
        },
    },
}
# rollbar.init(**ROLLBAR)