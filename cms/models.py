from django.db import models
from utils.upload_entropy import upload_homepage_gallery
from tinymce.models import HTMLField

# Create your models here.


class HomePageContent(models.Model):
    AUDIENCE_CHOICES = [
        ("public", "Public (not logged in)"),
        ("member", "Member (logged in)")
    ]
    title = models.CharField(
        max_length=200, default="Welcome to the Skyline Soaring Members Site 🛫")
    slug = models.SlugField(
        max_length=100, unique=True, help_text="URL path for this page, e.g. 'home', 'about', 'contact'")
    audience = models.CharField(
        max_length=10, choices=AUDIENCE_CHOICES, default="public",
        help_text="Who should see this page content?")
    content = HTMLField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "CMS Page Content"
        verbose_name_plural = "CMS Page Content"

    def __str__(self):
        return f"{self.title} [{self.audience}]"


class HomePageImage(models.Model):
    page = models.ForeignKey(
        HomePageContent, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to=upload_homepage_gallery)
    caption = models.CharField(max_length=255, blank=True)
    order = models.PositiveIntegerField(
        default=0, help_text="Order for display")

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "CMS Page Image"
        verbose_name_plural = "CMS Page Images"

    def __str__(self):
        return self.caption or f"Image {self.pk}"
