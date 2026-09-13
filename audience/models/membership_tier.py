from django.db import models
from .membership_benefit import MembershipBenefit


class MembershipTier(models.Model):
    name = models.CharField(max_length=45)
    description = models.TextField()
    benefits = models.ManyToManyField(to=MembershipBenefit)
    hidden = models.BooleanField(default=False)

    def __str__(self):
        return self.name