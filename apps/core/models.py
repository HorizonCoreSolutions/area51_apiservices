from django.db import models
from django.utils import timezone


class BaseManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset()


class AbstractBaseModel(models.Model):
    """
    An abstract base class for all models
    Add created and modified fields for all models
    """

    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False, blank=False)
    objects = BaseManager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        self.modified = timezone.now()
        return super().save(*args, **kwargs)
