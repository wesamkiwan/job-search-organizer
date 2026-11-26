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
from organizer.applications.models import (
    Application,
    ApplicationEvent,
    EventKind,
    PipelineStage,
    Task,
)
from organizer.companies.models import Company, Contact
from organizer.jobs.models import JobPosting, Tag
from organizer.sources.models import Source

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


# --- sources and jobs ------------------------------------------------------------------


class SourceFactory(DjangoModelFactory[Source]):
    class Meta:
        model = Source
        # SourceFactory.create(name="Manual") returns the default source that the data
        # migration already created, instead of failing on the unique name.
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Source {n}")


class TagFactory(DjangoModelFactory[Tag]):
    class Meta:
        model = Tag
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"tag{n}")


class JobPostingFactory(DjangoModelFactory[JobPosting]):
    class Meta:
        model = JobPosting
        # Tags are added after saving (see below); don't save a second time for that.
        skip_postgeneration_save = True

    title = factory.Sequence(lambda n: f"Python Developer {n}")
    company = factory.SubFactory(CompanyFactory)
    source = factory.SubFactory(SourceFactory, name="Manual")

    # Many-to-many values can only be added once the posting has an id (is saved), so
    # factory-boy runs this AFTER saving:  JobPostingFactory.create(tags=[tag1, tag2])
    @factory.post_generation
    def tags(self, create: bool, extracted: list[Tag] | None, **kwargs: object) -> None:
        if create and extracted:
            self.tags.add(*extracted)


# --- applications ----------------------------------------------------------------------


def stage(name: str) -> PipelineStage:
    """One of the default stages created by the data migration, e.g. stage("Applied")."""
    return PipelineStage.objects.get(name=name)


class PipelineStageFactory(DjangoModelFactory[PipelineStage]):
    """For tests that need an extra stage; most tests use the defaults via stage()."""

    class Meta:
        model = PipelineStage

    name = factory.Sequence(lambda n: f"Stage {n}")
    order = factory.Sequence(lambda n: 100 + n)
    category = "in_progress"


class ApplicationFactory(DjangoModelFactory[Application]):
    """Saves the row directly, WITHOUT the services (no timeline event). Good for tests of
    reading data; tests of the workflow call services.create_application() instead."""

    class Meta:
        model = Application
        skip_postgeneration_save = True

    posting = factory.SubFactory(JobPostingFactory)
    # LazyFunction: called when each application is built (the database is ready then).
    stage = factory.LazyFunction(lambda: PipelineStage.objects.get(name="Applied"))

    @factory.post_generation
    def tags(self, create: bool, extracted: list[Tag] | None, **kwargs: object) -> None:
        if create and extracted:
            self.tags.add(*extracted)


class ApplicationEventFactory(DjangoModelFactory[ApplicationEvent]):
    class Meta:
        model = ApplicationEvent

    application = factory.SubFactory(ApplicationFactory)
    kind = EventKind.NOTE
    summary = factory.Sequence(lambda n: f"Note {n}")


class TaskFactory(DjangoModelFactory[Task]):
    class Meta:
        model = Task

    title = factory.Sequence(lambda n: f"Task {n}")
