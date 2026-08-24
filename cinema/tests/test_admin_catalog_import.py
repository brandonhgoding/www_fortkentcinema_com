"""The "Import catalog" uploader on the StudioTitle changelist."""

import datetime
from io import BytesIO

import openpyxl
from cinema.models import Studio, StudioTitle
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

HEADER = (
    "TITLE,U.S. RELEASE (YYYY-MM-DD),ASPECT RATIO,AUDIO,"
    "MPA RATING,RUN TIME (MINUTES),ADDITIONAL INFORMATION"
)
URL = "/admin/cinema/studiotitle/import-catalog/"


def csv_upload(*lines: str, name: str = "catalog.csv") -> SimpleUploadedFile:
    body = ("\r\n".join((HEADER, *lines)) + "\r\n").encode()
    return SimpleUploadedFile(name, body, content_type="text/csv")


def xlsx_upload(rows, sheet_name="by TITLE") -> SimpleUploadedFile:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_name
    ws.append(HEADER.split(","))
    for row in rows:
        ws.append(row)
    buffer = BytesIO()
    wb.save(buffer)
    return SimpleUploadedFile(
        "catalog.xlsx",
        buffer.getvalue(),
        content_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
    )


class CatalogImportViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            "projectionist", "booth@fortkentcinema.com", "reel-change-1"
        )
        self.client.force_login(self.user)

    def post(self, **data):
        payload = {"studio": "universal", "sheet": "by TITLE"}
        payload.update(data)
        return self.client.post(URL, payload, follow=True)

    def messages(self, response):
        return [str(m) for m in response.context["messages"]]

    def test_the_changelist_offers_the_uploader(self):
        response = self.client.get(reverse("admin:cinema_studiotitle_changelist"))

        self.assertContains(response, URL)

    def test_the_form_is_reachable(self):
        response = self.client.get(URL)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Import catalog")

    def test_imports_a_csv_and_says_what_it_did(self):
        response = self.post(file=csv_upload(
            "NOBODY 2,2025-08-15,Scope,5.1,R,89,",
            "DRACULA,1931-02-13,Flat,1,,75,",
        ))

        title = StudioTitle.objects.get(original_title="NOBODY 2")
        self.assertEqual(title.title, "Nobody 2")
        self.assertEqual(title.release_date, datetime.date(2025, 8, 15))
        self.assertEqual(StudioTitle.objects.count(), 2)
        self.assertIn("2 created", " ".join(self.messages(response)))

    def test_imports_a_workbook(self):
        self.post(file=xlsx_upload([
            ["BAD GUYS 2, THE", datetime.datetime(2025, 8, 1),
             "Scope", "5.1, 7.1, Atmos", "PG", 104, "2D & 3D"],
        ]))

        self.assertEqual(StudioTitle.objects.get().title, "The Bad Guys 2")

    def test_creates_the_studio_on_first_import(self):
        self.post(file=csv_upload("NOBODY 2,2025-08-15,,,,,"))

        studio = Studio.objects.get(slug="universal")
        self.assertEqual(studio.name, "Universal Pictures")

    def test_redirects_back_to_the_changelist(self):
        response = self.post(file=csv_upload("NOBODY 2,2025-08-15,,,,,"))

        self.assertRedirects(
            response, reverse("admin:cinema_studiotitle_changelist")
        )

    def test_preview_writes_nothing(self):
        response = self.post(
            file=csv_upload("NOBODY 2,2025-08-15,,,,,"), dry_run="on"
        )

        self.assertEqual(StudioTitle.objects.count(), 0)
        self.assertFalse(Studio.objects.exists())
        joined = " ".join(self.messages(response))
        self.assertIn("1 title", joined)
        self.assertIn("Nothing was written", joined)

    def test_a_reimport_does_not_resurrect_a_hidden_title(self):
        studio = Studio.objects.create(slug="universal", name="Universal Pictures")
        StudioTitle.objects.create(
            studio=studio, original_title="NOBODY 2", title="Nobody 2",
            release_date=datetime.date(2025, 8, 15),
            is_available=False, hidden_reason="Played it in 2025.",
        )

        self.post(file=csv_upload("NOBODY 2,2025-08-15,Scope,5.1,R,89,"))

        title = StudioTitle.objects.get()
        self.assertFalse(title.is_available)
        self.assertEqual(title.hidden_reason, "Played it in 2025.")
        self.assertEqual(title.runtime_minutes, 89)

    def test_an_unreadable_file_is_reported_on_the_form(self):
        response = self.client.post(URL, {
            "studio": "universal",
            "sheet": "by TITLE",
            "file": SimpleUploadedFile("catalog.pdf", b"%PDF-"),
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "xlsx")
        self.assertEqual(StudioTitle.objects.count(), 0)

    def test_a_missing_sheet_is_reported_on_the_form(self):
        response = self.client.post(URL, {
            "studio": "universal",
            "sheet": "by TITLE",
            "file": xlsx_upload([["NOBODY 2", None]], sheet_name="by DATE"),
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "by DATE")
        self.assertEqual(StudioTitle.objects.count(), 0)

    def test_a_file_is_required(self):
        response = self.client.post(URL, {"studio": "universal", "sheet": ""})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(StudioTitle.objects.count(), 0)

    def test_an_unknown_studio_is_rejected(self):
        response = self.client.post(URL, {
            "studio": "univrsal",
            "sheet": "by TITLE",
            "file": csv_upload("NOBODY 2,2025-08-15,,,,,"),
        })

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Studio.objects.exists())

    def test_an_existing_studio_can_be_imported_into(self):
        Studio.objects.create(slug="a24", name="A24")

        self.post(studio="a24", file=csv_upload("MATERIALISTS,2025-06-13,,,,,"))

        self.assertEqual(
            StudioTitle.objects.get().studio.slug, "a24"
        )


class CatalogImportPermissionTests(TestCase):
    def test_a_staff_user_without_the_permission_is_turned_away(self):
        user = get_user_model().objects.create_user(
            "usher", "usher@fortkentcinema.com", "torn-ticket-2", is_staff=True
        )
        user.user_permissions.add(
            Permission.objects.get(codename="view_studiotitle")
        )
        self.client.force_login(user)

        response = self.client.post(URL, {
            "studio": "universal",
            "sheet": "by TITLE",
            "file": csv_upload("NOBODY 2,2025-08-15,,,,,"),
        })

        self.assertEqual(response.status_code, 403)
        self.assertEqual(StudioTitle.objects.count(), 0)

    def test_an_anonymous_visitor_is_sent_to_the_login_page(self):
        response = self.client.get(URL)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])
