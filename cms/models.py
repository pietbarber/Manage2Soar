from django.db import models
from utils.upload_entropy import upload_with_entropy
from tinymce.models import HTMLField

# Create your models here.


class HomePageContent(models.Model):
    title = models.CharField(
        max_length=200, default="Welcome to the Skyline Soaring Members Site 🛫")
    content = HTMLField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Homepage Content"
        verbose_name_plural = "Homepage Content"

    def __str__(self):
        return self.title


class HomePageImage(models.Model):
    homepage_content = models.ForeignKey(
        HomePageContent, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to=upload_with_entropy('homepage/gallery'))
    caption = models.CharField(max_length=255, blank=True)
    order = models.PositiveIntegerField(
        default=0, help_text="Order for display")

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "Homepage Image"
        verbose_name_plural = "Homepage Images"

    def __str__(self):
        return self.caption or f"Image {self.pk}"
