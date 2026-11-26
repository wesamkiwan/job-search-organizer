"""Test data factories (factory-boy).

A factory is a recipe for a model object with sensible default values. A test only
spells out the values it actually cares about:

    user = UserFactory.create()                    # random but valid username
    user = UserFactory.create(username="maria")    # override what matters for this test

.create() saves the object to the test database; .build() makes it WITHOUT saving.
(UserFactory() is a shortcut for .create(), but mypy can't tell that it returns a User,
so we always write .create() / .build().) Each app's models get a factory here.
"""

import factory
from factory.django import DjangoModelFactory, Password

from organizer.accounts.models import User
from organizer.companies.models import Company, Contact

# The password every factory user has, so tests can log in with it.
DEFAULT_PASSWORD = "correct-horse-battery-staple"


class UserFactory(DjangoModelFactory[User]):
    class Meta:
        model = User
        # get_or_create on username: calling UserFactory(username="maria") twice
        # returns the same user instead of failing on the unique username.
        django_get_or_create = ("username",)

    # Sequence: user1, user2, user3, ... so usernames are always unique.
    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda obj: f"{obj.username}@example.com")
    # Password() hashes the text the same way Django does, so login works.
    password = Password(DEFAULT_PASSWORD)


# --- companies -------------------------------------------------------------------------


class CompanyFactory(DjangoModelFactory[Company]):
    class Meta:
        model = Company

    name = factory.Sequence(lambda n: f"Company {n}")
    industry = "Software"


class ContactFactory(DjangoModelFactory[Contact]):
    class Meta:
        model = Contact

    # Faker generates realistic fake data ("Lena", "Schmidt"). locale de_DE: German names.
    first_name = factory.Faker("first_name", locale="de_DE")
    last_name = factory.Faker("last_name", locale="de_DE")
    # SubFactory: also creates a company for the contact (pass company=None to skip).
    company = factory.SubFactory(CompanyFactory)
