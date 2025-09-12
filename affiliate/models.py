from django.db import models


class Product(models.Model):
    name = models.CharField(max_length=100)
    link = models.URLField(max_length=200)
    description = models.TextField()
    image = models.ImageField(upload_to="product/")

