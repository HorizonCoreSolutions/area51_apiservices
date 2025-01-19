from django.urls import path, re_path

from .views import FileUploadView

urlpatterns = [
    path("upload/", FileUploadView.as_view(), name="upload"),
]
