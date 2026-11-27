"""manage.py seed_demo_data: fill the local database with made-up example data.

Useful to try the pages (lists, sorting, paging, later the kanban board and dashboard)
and for screenshots. All companies, people and jobs are invented.

    uv run python manage.py seed_demo_data          # add the demo data
    uv run python manage.py seed_demo_data --reset  # remove it (and add it again)

Every demo row is marked with {"demo": true} in its custom_data, so --reset removes
exactly the demo data and never touches your own entries.
"""

import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction
from django.utils import timezone

from organizer.applications import services
from organizer.applications.models import Application, PipelineStage, RejectionReason, Task
from organizer.companies.models import Company, CompanySize, Contact, ContactKind
from organizer.core.models import Tone
from organizer.jobs.models import (
    ContractType,
    EmploymentType,
    JobPosting,
    RemoteType,
    Seniority,
    Tag,
)
from organizer.sources.models import Source

DEMO = {"demo": True}

# (name, industry, size, city, is_recruiting_agency) — all invented.
COMPANIES = [
    ("Nordlicht Software GmbH", "Software", CompanySize.S51_200, "Hamburg", False),
    ("Elbkante Digital GmbH", "E-commerce", CompanySize.S201_1000, "Hamburg", False),
    ("Alpenblick Systems AG", "Industrial software", CompanySize.S1001_5000, "München", False),
    ("Spreeufer Labs GmbH", "Software", CompanySize.S11_50, "Berlin", False),
    ("Mainbrücke Fintech GmbH", "Finance", CompanySize.S201_1000, "Frankfurt am Main", False),
    ("Isartal Data GmbH", "Data & analytics", CompanySize.S51_200, "München", False),
    ("Neckarbogen Mobility GmbH", "Automotive", CompanySize.S5000_PLUS, "Stuttgart", False),
    ("Domblick Health IT GmbH", "Healthcare", CompanySize.S201_1000, "Köln", False),
    ("Lindenhof Energy GmbH", "Energy", CompanySize.S1001_5000, "Leipzig", False),
    ("Talentbrücke Recruiting GmbH", "Recruiting", CompanySize.S11_50, "Berlin", True),
]  # fmt: skip

TAGS = [("remote", Tone.INFO), ("python", Tone.ACCENT), ("django", Tone.SUCCESS),
        ("dream job", Tone.WARNING), ("english team", Tone.NEUTRAL)]  # fmt: skip

TITLES = [
    "Python Developer", "Backend Engineer (Django)", "Data Engineer", "Junior Software Engineer",
    "DevOps Engineer", "Full-Stack Developer (Python/Vue)", "Data Analyst",
    "Software Engineer Python",
    "Machine Learning Engineer", "Platform Engineer", "Backend Developer (Python)",
    "Werkstudent Softwareentwicklung", "Analytics Engineer", "Python Developer (Automation)",
    "Cloud Engineer", "Senior Backend Developer", "QA Automation Engineer (Python)",
    "Data Scientist", "Software Developer Django", "Site Reliability Engineer",
    "API Developer (Python)", "Junior Data Engineer",
]  # fmt: skip


@dataclass(frozen=True)
class Scenario:
    """The story of one demo application: stage names with "days ago" for each step."""

    steps: tuple[tuple[str, int], ...]
    close_as: str = ""  # final stage name, if the story ends with close_application
    close_days_ago: int = 0
    reason: str = ""


SCENARIOS = [
    Scenario((("Saved", 2),)),
    Scenario((("Saved", 6),)),
    Scenario((("Applied", 1),)),
    Scenario((("Applied", 4),)),
    Scenario((("Applied", 9),)),
    Scenario((("Applied", 12), ("Screening", 6))),
    Scenario((("Applied", 18), ("Screening", 11), ("Interviewing", 4))),
    Scenario((("Applied", 25), ("Screening", 19), ("Interviewing", 12))),
    Scenario((("Applied", 30), ("Screening", 22), ("Interviewing", 15), ("Offer", 2))),
    Scenario(
        (("Applied", 45), ("Screening", 38), ("Interviewing", 30), ("Offer", 20), ("Accepted", 16))
    ),
    Scenario((("Applied", 20),), "Rejected", 14, RejectionReason.NO_REASON_GIVEN),
    Scenario((("Applied", 28), ("Screening", 21)), "Rejected", 17, RejectionReason.SKILLS_MISMATCH),
    Scenario(
        (("Applied", 35), ("Screening", 30), ("Interviewing", 23)),
        "Rejected",
        8,
        RejectionReason.OTHER_CANDIDATE,
    ),
    Scenario((("Applied", 40), ("Screening", 33)), "Rejected", 26, RejectionReason.SALARY),
    Scenario((("Applied", 50),), "Ghosted", 15),
    Scenario((("Applied", 60),), "Ghosted", 25),
    Scenario((("Applied", 16), ("Screening", 10)), "Withdrawn", 5),
    Scenario((("Applied", 7),)),
    Scenario((("Applied", 3),)),
    Scenario((("Saved", 1),)),
]


class Command(BaseCommand):
    help = "Fill the local database with made-up demo data (use --reset to remove it)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--reset", action="store_true", help="Remove existing demo data first.")
        parser.add_argument(
            "--force", action="store_true", help="Run even when DEBUG is off (not recommended)."
        )

    def handle(self, *args: Any, **options: Any) -> None:
        if not settings.DEBUG and not options["force"]:
            raise CommandError("Demo data is for local development only (DEBUG is off).")

        with transaction.atomic():  # all or nothing
            if options["reset"]:
                removed = remove_demo_data()
                self.stdout.write(f"Removed {removed} demo applications.")
            elif Company.objects.filter(custom_data__demo=True).exists():
                raise CommandError("Demo data already exists. Use --reset to recreate it.")
            # Fixed seed: the same demo data every time. (S311 warns that `random` is not
            # safe for secrets; here it only picks fake salaries and dates.)
            created = create_demo_data(random.Random(42))  # noqa: S311

        self.stdout.write(self.style.SUCCESS(f"Created {created} demo applications."))


def remove_demo_data() -> int:
    """Delete everything marked as demo. Order matters: PROTECT relations come first."""
    applications = Application.objects.filter(custom_data__demo=True)
    count = applications.count()
    applications.delete()  # also deletes their events and tasks (CASCADE)
    JobPosting.objects.filter(custom_data__demo=True).delete()
    Contact.objects.filter(custom_data__demo=True).delete()
    Company.objects.filter(custom_data__demo=True).delete()
    return count


def create_demo_data(rng: random.Random) -> int:
    now = timezone.now()
    tags = [
        Tag.objects.get_or_create(name=name, defaults={"color": color})[0] for name, color in TAGS
    ]
    sources = list(Source.objects.filter(name__in=["StepStone", "LinkedIn", "Manual"]))
    companies = [
        Company.objects.create(
            name=name,
            industry=industry,
            size=size,
            headquarters=city,
            is_recruiting_agency=agency,
            rating=rng.choice([None, 3, 4, 5]),
            custom_data=DEMO,
        )
        for name, industry, size, city, agency in COMPANIES
    ]
    recruiter = Contact.objects.create(
        first_name="Jana",
        last_name="Wendt",
        job_title="Senior Recruiter",
        company=companies[-1],
        kind=ContactKind.EXTERNAL_RECRUITER,
        email="jana.wendt@example.com",
        custom_data=DEMO,
    )

    for number, (title, scenario) in enumerate(zip(TITLES, SCENARIOS, strict=False)):
        company = companies[number % len(companies)]
        first_day = scenario.steps[0][1]
        posting = JobPosting.objects.create(
            title=title,
            company=company,
            company_name_raw=company.name,
            source=rng.choice(sources),
            url=f"https://jobs.example.com/{number + 1}",
            city=company.headquarters,
            location_text=company.headquarters,
            remote_type=rng.choice(RemoteType.values),
            employment_type=EmploymentType.FULL_TIME,
            contract_type=ContractType.PERMANENT,
            seniority=rng.choice(
                [Seniority.JUNIOR, Seniority.MID, Seniority.MID, Seniority.SENIOR]
            ),
            salary_min=(low := rng.randrange(48, 70) * 1000),
            salary_max=low + rng.randrange(5, 20) * 1000,
            found_at=now - timedelta(days=first_day + rng.randrange(0, 3)),
            custom_data=DEMO,
        )
        posting.tags.set(rng.sample(tags, k=rng.randrange(0, 3)))
        # Your salary expectation: somewhere in or a bit above the ad's range, in whole
        # thousands. Only when you actually applied (a saved job has no expectation yet).
        expectation = None
        if scenario.steps[0][0] != "Saved":
            middle = (posting.salary_min + posting.salary_max) // 2  # type: ignore[operator]
            expectation = round(middle + rng.randrange(-3, 8) * 1000, -3)
        application = _play(scenario, posting, rng, now, expectation)
        if number == 6:
            application.referred_by = recruiter
            application.save()
        if application.stage.name in {"Applied", "Screening"} and number % 3 == 0:
            Task.objects.create(
                title="Follow up by email",
                application=application,
                due_on=timezone.localdate(now) + timedelta(days=rng.randrange(1, 7)),
            )

    # Two postings without an application yet (they will show up in the inbox later).
    for title in TITLES[len(SCENARIOS) :]:
        JobPosting.objects.create(
            title=title,
            company=rng.choice(companies),
            source=rng.choice(sources),
            custom_data=DEMO,
        )
    return len(SCENARIOS)


def _play(
    scenario: Scenario,
    posting: JobPosting,
    rng: random.Random,
    now: datetime,
    salary_expectation: int | None,
) -> Application:
    """Create the application and replay its story through the services (backdated)."""

    def days_ago(days: int) -> datetime:
        return now - timedelta(days=days, hours=rng.randrange(0, 8))

    first_stage, first_day = scenario.steps[0]
    application = Application(
        posting=posting,
        stage=PipelineStage.objects.get(name=first_stage),
        priority=rng.choice(["low", "medium", "medium", "high"]),
        interest=rng.choice([None, 3, 4, 5]),
        salary_expectation=salary_expectation,
        custom_data=DEMO,
    )
    services.create_application(application, occurred_at=days_ago(first_day))
    for stage_name, day in scenario.steps[1:]:
        services.change_stage(
            application, PipelineStage.objects.get(name=stage_name), occurred_at=days_ago(day)
        )
    if scenario.close_as:
        services.close_application(
            application,
            stage=PipelineStage.objects.get(name=scenario.close_as),
            reason=scenario.reason,
            occurred_at=days_ago(scenario.close_days_ago),
        )
    application.tags.set(posting.tags.all())

    # updated_at would be "now" for every row (auto_now). For realistic sorting, set it to
    # the time of the last event. QuerySet.update() writes directly, bypassing auto_now.
    # (There is always at least one event: create_application writes it.)
    last_event = application.events.latest("occurred_at")
    Application.objects.filter(pk=application.pk).update(updated_at=last_event.occurred_at)
    return application
