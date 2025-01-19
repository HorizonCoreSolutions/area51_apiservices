from django.contrib.gis.measure import Distance
from rest_framework.renderers import (
    JSONRenderer as DefaultJSONRenderer,
    BaseRenderer as DefaultBaseRenderer,
)
from rest_framework.utils.encoders import JSONEncoder as DefaultJSONEncoder


class JSONEncoder(DefaultJSONEncoder):
    def default(self, obj):
        if isinstance(obj, Distance):
            return obj.km
        return super().default(obj)


class BaseRenderer(DefaultBaseRenderer):
    def render(self, data, media_type=None, renderer_context={}, writer_opts=None):

        if type(data) is dict and "results" not in data:
            return PermissionError(
                data.get("detail", "There are some problems, try again.")
            )


class JSONRenderer(DefaultJSONRenderer):
    encoder_class = JSONEncoder

    def render(self, data, accepted_media_type=None, renderer_context=None):

        # if 'results' not in data and type(data) is dict:
        #     return PermissionError(data.get('detail', 'There are some problems, try again.'))

        return super().render(data, accepted_media_type, renderer_context)
