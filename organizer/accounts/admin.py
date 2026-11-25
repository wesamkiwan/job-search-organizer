from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User

# Django's UserAdmin gives the full user screens (password change form, permissions, ...).
admin.site.register(User, UserAdmin)
