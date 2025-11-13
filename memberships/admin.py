from django.contrib import admin
from memberships.models import MembershipType, MembershipBenefit

admin.site.register(MembershipType)
admin.site.register(MembershipBenefit)