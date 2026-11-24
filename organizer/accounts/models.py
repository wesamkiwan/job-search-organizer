"""User accounts."""

from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """The person using the app.

    Identical to Django's built-in user for now. It exists so fields can be added later
    without a painful migration: Django recommends a custom user model for every new
    project, because switching AUTH_USER_MODEL after the first migration is very hard.
    """
