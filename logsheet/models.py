from django.db import models
from members.models import Member

class Logsheet(models.Model):
    log_date = models.DateField()
    location = models.CharField(max_length=100)
    created_by = models.ForeignKey(Member, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("log_date", "location")

    def __str__(self):
        return f"{self.log_date} @ {self.location}"
