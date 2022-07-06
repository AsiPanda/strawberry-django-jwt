from django.db import models


class MyTestModel(models.Model):
    id = models.AutoField(primary_key=True)  # noqa A003
    test = models.CharField(max_length=100)

    class Meta:
        app_label = "tests"
