'''
DO NOT PUT
from apps.casino.models import Xaosmdof, .....
We do not want circular imports
'''
import os
import uuid


# It is here to prevent circular imports
def rename_image(instance, filename):
    # Get extension
    ext = filename.split('.')[-1]
    # Generate new unique name
    new_filename = f"{uuid.uuid4().hex}.{ext}"
    return os.path.join('uploads/images/', new_filename)
    