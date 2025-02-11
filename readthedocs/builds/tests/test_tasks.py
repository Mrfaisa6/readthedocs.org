from datetime import datetime, timedelta
from unittest import mock

from django.test import TestCase
from django.utils import timezone
from django_dynamic_fixture import get

from readthedocs.builds.constants import BRANCH, EXTERNAL, TAG
from readthedocs.builds.models import Build, BuildCommandResult, Version
from readthedocs.builds.tasks import (
    archive_builds_task,
    delete_inactive_external_versions,
)
from readthedocs.projects.models import Project


class TestTasks(TestCase):

    def test_delete_inactive_external_versions(self):
        project = get(Project)
        project.versions.all().delete()
        get(
            Version,
            project=project,
            slug='branch',
            type=BRANCH,
            active=False,
            modified=datetime.now() - timedelta(days=7),
        )
        get(
            Version,
            project=project,
            slug='tag',
            type=TAG,
            active=True,
            modified=datetime.now() - timedelta(days=7),
        )
        get(
            Version,
            project=project,
            slug='external-active',
            type=EXTERNAL,
            active=True,
            modified=datetime.now() - timedelta(days=7),
        )
        get(
            Version,
            project=project,
            slug='external-inactive',
            type=EXTERNAL,
            active=False,
            modified=datetime.now() - timedelta(days=3),
        )
        get(
            Version,
            project=project,
            slug='external-inactive-old',
            type=EXTERNAL,
            active=False,
            modified=datetime.now() - timedelta(days=7),
        )

        self.assertEqual(Version.objects.all().count(), 5)
        self.assertEqual(Version.external.all().count(), 3)

        # We don't have inactive external versions from 9 days ago.
        delete_inactive_external_versions(days=9)
        self.assertEqual(Version.objects.all().count(), 5)
        self.assertEqual(Version.external.all().count(), 3)

        # We have one inactive external versions from 6 days ago.
        delete_inactive_external_versions(days=6)
        self.assertEqual(Version.objects.all().count(), 4)
        self.assertEqual(Version.external.all().count(), 2)
        self.assertFalse(Version.objects.filter(slug='external-inactive-old').exists())

    @mock.patch('readthedocs.builds.tasks.build_commands_storage')
    def test_archive_builds(self, build_commands_storage):
        project = get(Project)
        version = get(Version, project=project)
        for i in range(10):
            date = timezone.now() - timezone.timedelta(days=i)
            build = get(
                Build,
                project=project,
                version=version,
                date=date,
                cold_storage=False,
            )
            for _ in range(10):
                get(
                    BuildCommandResult,
                    build=build,
                    command='ls',
                    output='docs',
                )

        self.assertEqual(Build.objects.count(), 10)
        self.assertEqual(BuildCommandResult.objects.count(), 100)

        archive_builds_task(days=5, delete=True)

        self.assertEqual(len(build_commands_storage.save.mock_calls), 5)
        self.assertEqual(Build.objects.count(), 10)
        self.assertEqual(Build.objects.filter(cold_storage=True).count(), 5)
        self.assertEqual(BuildCommandResult.objects.count(), 50)
