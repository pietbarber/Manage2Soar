from django.conf import settings
from django.db import models
from django.utils.text import slugify
from tinymce.models import HTMLField

from utils.upload_document_obfuscated import upload_document_obfuscated
from utils.upload_entropy import upload_homepage_gallery

# --- CMS Arbitrary Page and Document Models ---


# --- CMS Arbitrary Page and Document Models ---


class Page(models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(
        max_length=100,
        unique=True,
        help_text="URL path for this page, e.g. 'club-documents', 'bylaws', etc.",
    )
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        related_name="children",
        on_delete=models.CASCADE,
        help_text="Parent directory (for subdirectories)",
    )
    content = HTMLField(blank=True)
    is_public = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "CMS Page"
        verbose_name_plural = "CMS Pages"
        unique_together = ("parent", "slug")

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        if self.parent:
            return f"/cms/{self.parent.slug}/{self.slug}/"
        return f"/cms/{self.slug}/"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)


def upload_document_to(instance, filename):
    # Store files under cms/<page-slug>/<filename> for public, obfuscated for private
    page_slug = instance.page.slug if instance.page else "uncategorized"
    if instance.page and not instance.page.is_public:
        # Use obfuscated filename for restricted/private documents
        return upload_document_obfuscated(instance, filename)
    return f"cms/{page_slug}/{filename}"


class Document(models.Model):
    page = models.ForeignKey(Page, related_name="documents", on_delete=models.CASCADE)
    file = models.FileField(upload_to=upload_document_to)
    title = models.CharField(max_length=255, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "CMS Document"
        verbose_name_plural = "CMS Documents"

    def __str__(self):
        return self.title or self.file.name

    @property
    def is_pdf(self):
        return self.file.name.lower().endswith(".pdf")

    @property
    def extension(self):
        return self.file.name.split(".")[-1].lower()


# Create your models here.


class HomePageContent(models.Model):
    AUDIENCE_CHOICES = [
        ("public", "Public (not logged in)"),
        ("member", "Member (logged in)"),
    ]
    title = models.CharField(
        max_length=200, default="Welcome to the Skyline Soaring Members Site 🛫"
    )
    slug = models.SlugField(
        max_length=100,
        unique=True,
        help_text="URL path for this page, e.g. 'home', 'about', 'contact'",
    )
    audience = models.CharField(
        max_length=10,
        choices=AUDIENCE_CHOICES,
        default="public",
        help_text="Who should see this page content?",
    )
    content = HTMLField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "CMS Page Content"
        verbose_name_plural = "CMS Page Content"

    def __str__(self):
        return f"{self.title} [{self.audience}]"


class HomePageImage(models.Model):
    page = models.ForeignKey(
        HomePageContent, on_delete=models.CASCADE, related_name="images"
    )
    image = models.ImageField(upload_to=upload_homepage_gallery)
    caption = models.CharField(max_length=255, blank=True)
    order = models.PositiveIntegerField(default=0, help_text="Order for display")

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "CMS Page Image"
        verbose_name_plural = "CMS Page Images"

    def __str__(self):
        return self.caption or f"Image {self.pk}"
