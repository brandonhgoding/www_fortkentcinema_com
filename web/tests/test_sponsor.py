import datetime

from cinema.models import SponsorshipInquiry, Studio, StudioTitle
from django.test import TestCase
from django.urls import reverse


class SponsorPageTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.studio = Studio.objects.create(
            name="Universal Pictures", slug="universal"
        )
        cls.wild = StudioTitle.objects.create(
            studio=cls.studio, original_title="WILD ROBOT, THE",
            title="The Wild Robot", release_date=datetime.date(2024, 9, 27),
            mpa_rating="PG", runtime_minutes=102, aspect_ratio="Scope",
        )
        cls.jaws = StudioTitle.objects.create(
            studio=cls.studio, original_title="JAWS", title="Jaws",
            release_date=datetime.date(1975, 6, 20),
            mpa_rating="PG", runtime_minutes=124,
        )
        cls.hidden = StudioTitle.objects.create(
            studio=cls.studio, original_title="HIDDEN ONE", title="Hidden One",
            release_date=datetime.date(2020, 1, 1), is_available=False,
        )

    def test_page_returns_200_and_uses_templates(self):
        response = self.client.get(reverse("sponsor"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "base.html")
        self.assertTemplateUsed(response, "web/sponsor.html")

    def test_no_template_comment_leaks_into_page(self):
        html = self.client.get(reverse("sponsor")).content.decode()
        self.assertNotIn("{#", html)
        self.assertNotIn("{% comment %}", html)

    def test_lists_available_titles_only(self):
        # "The Wild Robot" cannot be checked via raw HTML: the page's static
        # worked example names it unconditionally (see
        # test_inactive_studio_titles_are_hidden below), so that assertion
        # would pass even if the table rendered empty. Checked via context
        # instead; "Jaws" and "Hidden One" have no such collision, so those
        # stay as real HTML assertions proving the table actually renders.
        response = self.client.get(reverse("sponsor"))
        titles = [t.title for t in response.context["titles"]]
        self.assertIn("The Wild Robot", titles)

        html = response.content.decode()
        self.assertIn("Jaws", html)
        self.assertNotIn("Hidden One", html)

    def test_inactive_studio_titles_are_hidden(self):
        # Checked against context, not raw HTML: the page's static worked
        # example also names "The Wild Robot" (a real, approved sponsorship),
        # so a whole-page substring scan would false-fail regardless of
        # whether the queryset actually excludes the inactive studio.
        self.studio.is_active = False
        self.studio.save()
        response = self.client.get(reverse("sponsor"))
        titles = [t.title for t in response.context["titles"]]
        self.assertNotIn("The Wild Robot", titles)

    def test_search_filters_by_title(self):
        response = self.client.get(reverse("sponsor"), {"q": "wild"})
        titles = [t.title for t in response.context["titles"]]
        self.assertEqual(titles, ["The Wild Robot"])

    def test_search_is_case_insensitive(self):
        response = self.client.get(reverse("sponsor"), {"q": "JAWS"})
        self.assertEqual([t.title for t in response.context["titles"]], ["Jaws"])

    def test_decade_filter(self):
        response = self.client.get(reverse("sponsor"), {"decade": "1970"})
        self.assertEqual([t.title for t in response.context["titles"]], ["Jaws"])

    def test_decade_never_500s_across_a_swept_input_space(self):
        # Regression sweep. str.isdigit() is True for Unicode digits that
        # int() can't always turn into a safe year ('²', '१९७०'), and even a
        # plain ASCII digit string can be zero, negative-looking, absurdly
        # long, or simply out of any calendar's range — all of which must
        # be *ignored*, not 500. Every one of these must return 200.
        inputs = [
            "²", "0", "1", "999", "1800", "1970", "2100", "2101", "9999",
            "10000", "12000", "99999", "9999999999999",
            "000000000000000000001", "-5", "abc", "", "1970.5",
            "१९७०",  # Devanagari digits: isdigit() True, isascii() False
            "9" * 500,
        ]
        for decade in inputs:
            with self.subTest(decade=decade):
                response = self.client.get(reverse("sponsor"), {"decade": decade})
                self.assertEqual(response.status_code, 200)

    def test_decade_upper_bound_is_inclusive_and_still_filters(self):
        # The accepted bound must do more than "not crash" — it must still
        # filter, so a title sitting right on the upper edge is included.
        future = StudioTitle.objects.create(
            studio=self.studio, original_title="FUTURE FILM",
            title="Future Film", release_date=datetime.date(2105, 1, 1),
        )
        response = self.client.get(reverse("sponsor"), {"decade": "2100"})
        self.assertEqual(response.status_code, 200)
        titles = [t.title for t in response.context["titles"]]
        self.assertEqual(titles, [future.title])

    def test_decade_one_past_the_upper_bound_is_ignored_not_filtered(self):
        future = StudioTitle.objects.create(
            studio=self.studio, original_title="FUTURE FILM",
            title="Future Film", release_date=datetime.date(2105, 1, 1),
        )
        response = self.client.get(reverse("sponsor"), {"decade": "2101"})
        self.assertEqual(response.status_code, 200)
        titles = [t.title for t in response.context["titles"]]
        # Out of range means the param is dropped entirely, not applied —
        # every available title shows, including the one from 2105.
        self.assertIn(future.title, titles)
        self.assertIn("Jaws", titles)

    def test_rating_filter(self):
        response = self.client.get(reverse("sponsor"), {"rating": "PG"})
        self.assertEqual(len(response.context["titles"]), 2)

    def test_sort_by_year_descending(self):
        response = self.client.get(reverse("sponsor"), {"sort": "-year"})
        titles = [t.title for t in response.context["titles"]]
        self.assertEqual(titles, ["The Wild Robot", "Jaws"])

    def test_unknown_sort_falls_back_to_title(self):
        # Never interpolate raw querystring into order_by.
        response = self.client.get(reverse("sponsor"), {"sort": "runtime; DROP TABLE"})
        self.assertEqual(response.status_code, 200)
        titles = [t.title for t in response.context["titles"]]
        self.assertEqual(titles, ["Jaws", "The Wild Robot"])

    def test_pagination_is_twenty_five_per_page(self):
        response = self.client.get(reverse("sponsor"))
        self.assertEqual(response.context["paginator"].per_page, 25)

    def test_tiers_are_in_context_with_the_agreed_prices(self):
        tiers = self.client.get(reverse("sponsor")).context["tiers"]
        self.assertEqual([t["price"] for t in tiers], [299, 499, 799])

    def test_page_names_the_real_sponsor_example(self):
        html = self.client.get(reverse("sponsor")).content.decode()
        self.assertIn("A.H. Custom Carpentry", html)
        self.assertIn("The Wild Robot", html)

    def test_full_house_tier_states_the_guest_cap_and_size(self):
        html = self.client.get(reverse("sponsor")).content.decode()
        self.assertIn("first 100 guests", html)
        self.assertIn("Medium", html)

    def test_filter_choices_come_from_available_titles(self):
        context = self.client.get(reverse("sponsor")).context
        self.assertIn("PG", context["ratings"])
        self.assertIn(1970, context["decades"])
        self.assertIn(2020, context["decades"])


class SponsorSitemapTests(TestCase):
    def test_sponsor_is_in_the_sitemap(self):
        html = self.client.get("/sitemap.xml").content.decode()
        self.assertIn("/sponsor/", html)

    def test_sponsor_is_in_the_site_navigation(self):
        # nav.html loops SITE_CONFIG["navigation"]; the trailing slash matters
        # because a bare /sponsor would 301 on every click.
        html = self.client.get("/").content.decode()
        self.assertIn('href="/sponsor/"', html)


class SponsorCatalogAnchorTests(TestCase):
    """Every catalog control must come back to #catalog.

    Searching, sorting, and paging are full page loads. Without the fragment
    the browser lands at the top of the page — above the hero, the worked
    example, and the tier cards — and the reader has to scroll back down to
    the table they were already reading.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.studio = Studio.objects.create(
            name="Universal Pictures", slug="universal"
        )
        # 26 titles: one more than the page size, so pagination renders.
        for n in range(26):
            StudioTitle.objects.create(
                studio=cls.studio,
                original_title=f"TITLE {n:03d}",
                title=f"Title {n:03d}",
                release_date=datetime.date(1990, 1, 1),
                mpa_rating="PG",
                runtime_minutes=100,
            )

    def test_filter_form_submits_back_to_the_catalog(self):
        html = self.client.get(reverse("sponsor")).content.decode()
        self.assertIn('action="/sponsor/#catalog"', html)

    def test_column_sort_links_carry_the_anchor(self):
        html = self.client.get(reverse("sponsor")).content.decode()
        for sort in ("sort=title", "sort=-year", "sort=runtime"):
            self.assertIn(f"{sort}#catalog", html)

    def test_pagination_links_carry_the_anchor(self):
        html = self.client.get(reverse("sponsor")).content.decode()
        self.assertIn("page=2#catalog", html)

        second = self.client.get(reverse("sponsor"), {"page": 2})
        self.assertIn("page=1#catalog", second.content.decode())

    def test_clear_links_carry_the_anchor(self):
        html = self.client.get(reverse("sponsor"), {"q": "Title"}).content.decode()
        self.assertIn('href="/sponsor/#catalog"', html)

    def test_empty_state_clear_link_carries_the_anchor(self):
        html = self.client.get(
            reverse("sponsor"), {"q": "nothing will ever match this"}
        ).content.decode()
        self.assertIn("Nothing matched that.", html)
        self.assertIn('href="/sponsor/#catalog"', html)

    def test_no_bare_sponsor_link_is_left_inside_the_catalog(self):
        # A bare href="/sponsor/" anywhere in the catalog section is the exact
        # regression this guards: it reloads to the top of the page.
        html = self.client.get(reverse("sponsor")).content.decode()
        catalog = html.split('id="catalog"', 1)[1].split('id="inquire"', 1)[0]
        self.assertNotIn('href="/sponsor/"', catalog)
        self.assertNotIn('action="/sponsor/"', catalog)


class SponsorCatalogFragmentTests(TestCase):
    """The htmx endpoint behind the no-reload catalog.

    It must stay a bare fragment, stay out of the index, and answer the same
    query the full page does — if the two ever disagree, the table you get
    while typing differs from the one you get on refresh.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.studio = Studio.objects.create(
            name="Universal Pictures", slug="universal"
        )
        cls.wild = StudioTitle.objects.create(
            studio=cls.studio, original_title="WILD ROBOT, THE",
            title="The Wild Robot", release_date=datetime.date(2024, 9, 27),
            mpa_rating="PG", runtime_minutes=102,
        )
        cls.jaws = StudioTitle.objects.create(
            studio=cls.studio, original_title="JAWS", title="Jaws",
            release_date=datetime.date(1975, 6, 20),
            mpa_rating="R", runtime_minutes=124,
        )
        cls.hidden = StudioTitle.objects.create(
            studio=cls.studio, original_title="HIDDEN ONE", title="Hidden One",
            release_date=datetime.date(2020, 1, 1), is_available=False,
        )

    def test_url_name_resolves_to_the_catalog_path(self):
        self.assertEqual(reverse("sponsor_catalog"), "/sponsor/catalog")

    def test_returns_a_bare_fragment_not_a_whole_page(self):
        html = self.client.get("/sponsor/catalog").content.decode()
        self.assertNotIn("<html", html)
        self.assertNotIn("<head", html)
        self.assertNotIn("SPONSOR A FILM", html)  # the page header
        self.assertIn("sponsor-table", html)      # but the table itself

    def test_fragment_is_noindex_and_nofollow(self):
        response = self.client.get("/sponsor/catalog")
        self.assertEqual(
            response["X-Robots-Tag"], "noindex, nofollow"
        )

    def test_fragment_renders_the_same_rows_as_the_full_page(self):
        # Drift between these two is the whole risk of having two entry
        # points: type a filter and get one table, refresh and get another.
        for params in (
            {},
            {"q": "wild"},
            {"rating": "R"},
            {"decade": "1970"},
            {"sort": "-year"},
            {"sort": "runtime"},
            {"q": "a", "rating": "PG"},
        ):
            with self.subTest(params=params):
                page = self.client.get(reverse("sponsor"), params)
                fragment = self.client.get("/sponsor/catalog", params)
                self.assertEqual(
                    [t.pk for t in page.context["titles"]],
                    [t.pk for t in fragment.context["titles"]],
                )

    def test_fragment_paginates_like_the_full_page(self):
        for n in range(30):
            StudioTitle.objects.create(
                studio=self.studio, original_title=f"FILLER {n:03d}",
                title=f"Filler {n:03d}", release_date=datetime.date(1990, 1, 1),
            )
        fragment = self.client.get("/sponsor/catalog", {"page": 2})
        self.assertEqual(fragment.context["paginator"].per_page, 25)
        self.assertEqual(fragment.context["page_obj"].number, 2)

    def test_fragment_renders_the_empty_state(self):
        html = self.client.get(
            "/sponsor/catalog", {"q": "nothing will ever match this"}
        ).content.decode()
        self.assertIn("Nothing matched that.", html)

    def test_bad_decade_is_ignored_in_the_fragment_too(self):
        # The full page hardened this against OverflowError; the fragment
        # shares get_queryset, and this proves it wasn't reimplemented.
        for decade in ("9999999999999", "0", "12000", "not-a-decade"):
            with self.subTest(decade=decade):
                response = self.client.get("/sponsor/catalog", {"decade": decade})
                self.assertEqual(response.status_code, 200)

    def test_fragment_is_not_in_the_sitemap(self):
        xml = self.client.get("/sitemap.xml").content.decode()
        self.assertNotIn("/sponsor/catalog", xml)


class SponsorLiveFilteringTests(TestCase):
    """The full page's HTMX wiring: filter without a reload."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.studio = Studio.objects.create(
            name="Universal Pictures", slug="universal"
        )
        StudioTitle.objects.create(
            studio=cls.studio, original_title="JAWS", title="Jaws",
            release_date=datetime.date(1975, 6, 20),
            mpa_rating="PG", runtime_minutes=124,
        )

    def _page(self, params=None):
        return self.client.get(reverse("sponsor"), params or {}).content.decode()

    def test_results_region_exists_as_the_swap_target(self):
        html = self._page()
        self.assertIn('id="sponsor-results"', html)
        self.assertIn('hx-target="#sponsor-results"', html)

    def test_filter_form_sits_outside_the_swapped_region(self):
        # The invariant that makes as-you-type usable. If the form were
        # inside #sponsor-results, HTMX would destroy and recreate the search
        # input on every swap and you would lose focus and caret position
        # mid-word. Keep the form out of the target.
        html = self._page()
        results = html.split('id="sponsor-results"', 1)[1]
        results = results.split('id="inquire"', 1)[0]
        self.assertNotIn("<form", results)
        self.assertNotIn('name="q"', results)
        self.assertNotIn('name="rating"', results)
        self.assertNotIn('name="decade"', results)

    def test_form_filters_live_with_a_debounce(self):
        html = self._page()
        self.assertIn('hx-get="/sponsor/catalog"', html)
        # Typing waits for a pause; the dropdowns fire at once.
        self.assertIn("delay:300ms", html)

    def test_form_still_submits_the_old_way_without_javascript(self):
        html = self._page()
        self.assertIn('action="/sponsor/#catalog"', html)
        self.assertIn('method="get"', html)

    def test_sort_and_page_links_keep_working_links_and_gain_hx_get(self):
        html = self._page()
        # Real href for no-JS...
        self.assertIn("sort=-year#catalog", html)
        # ...and an HTMX request that hits the fragment instead.
        self.assertIn('hx-get="/sponsor/catalog?sort=-year"', html)

    def test_pushed_url_is_the_page_never_the_fragment(self):
        # A reader who bookmarks or shares what they are looking at must get
        # /sponsor/?sort=-year, not the bare fragment.
        html = self._page()
        self.assertIn('hx-push-url="?sort=-year"', html)
        self.assertNotIn('hx-push-url="/sponsor/catalog', html)

    def test_page_renders_rows_server_side_for_crawlers_and_no_js(self):
        # First paint must contain the catalog, not an empty shell HTMX
        # fills in later.
        self.assertIn("Jaws", self._page())

    def test_page_and_fragment_render_the_same_table(self):
        # Both include partials/sponsor_catalog.html. Byte-identical output
        # is what proves the full page isn't carrying a stale second copy of
        # the table that someone edits one of and not the other.
        page = self._page({"sort": "-year"})
        fragment = self.client.get(
            "/sponsor/catalog", {"sort": "-year"}
        ).content.decode()
        table = page.split('id="sponsor-results"', 1)[1].split("</div>", 1)[0]
        self.assertIn(fragment.strip().split("\n", 1)[0].strip(), table)
        self.assertIn("sponsor-table__scroll", fragment)


class SponsorSortSurvivesFilteringTests(TestCase):
    """Sorting a column, then typing, must keep the sort you picked.

    The filter form is never re-rendered (that is what keeps focus in the
    search box), so a hidden sort field rendered once with the page goes
    stale the moment you sort a column. It has to live inside the swapped
    region and be tied back to the form with the HTML `form` attribute.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.studio = Studio.objects.create(
            name="Universal Pictures", slug="universal"
        )
        StudioTitle.objects.create(
            studio=cls.studio, original_title="JAWS", title="Jaws",
            release_date=datetime.date(1975, 6, 20), mpa_rating="PG",
        )

    def test_sort_field_lives_inside_the_swapped_region(self):
        html = self.client.get(reverse("sponsor")).content.decode()
        results = html.split('id="sponsor-results"', 1)[1]
        self.assertIn('name="sort"', results)

    def test_sort_field_is_tied_back_to_the_filter_form(self):
        # Outside the <form> in the DOM, so it needs form="..." to still be
        # submitted — both by a no-JS submit and by HTMX's FormData.
        html = self.client.get(reverse("sponsor")).content.decode()
        self.assertIn('id="sponsor-filters"', html)
        self.assertIn('form="sponsor-filters"', html)

    def test_fragment_carries_the_active_sort_back_to_the_form(self):
        html = self.client.get(
            "/sponsor/catalog", {"sort": "-year"}
        ).content.decode()
        self.assertIn('name="sort"', html)
        self.assertIn('value="-year"', html)

    def test_sorting_then_searching_keeps_the_sort(self):
        # The regression itself: the sort field the browser would submit
        # after sorting by year must say -year, not title.
        html = self.client.get(
            "/sponsor/catalog", {"sort": "-year"}
        ).content.decode()
        self.assertNotIn('value="title"', html)

    def test_no_duplicate_sort_field_on_the_full_page(self):
        # Two inputs named sort would submit sort twice and the server would
        # take the first, which may not be the one the reader just clicked.
        html = self.client.get(reverse("sponsor")).content.decode()
        self.assertEqual(html.count('name="sort"'), 1)


class SponsorFilterButtonsTests(TestCase):
    """Live filtering made the Search and Clear controls redundant.

    They are gone from the interface everyone with JavaScript sees. They
    survive only inside <noscript>, which the browser renders exclusively
    when scripting is off — the one case where the dropdowns cannot filter
    anything on their own.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        studio = Studio.objects.create(name="Universal", slug="universal")
        StudioTitle.objects.create(
            studio=studio, original_title="JAWS", title="Jaws",
            release_date=datetime.date(1975, 6, 20), mpa_rating="PG",
        )

    def _split(self):
        html = self.client.get(reverse("sponsor")).content.decode()
        form = html.split('<form class="sponsor-filters"', 1)[1]
        form = form.split("</form>", 1)[0]
        fallback = form.split("<noscript>", 1)[1].split("</noscript>", 1)[0]
        visible = form.replace(fallback, "")
        return visible, fallback

    def test_search_button_is_gone_from_the_normal_interface(self):
        visible, _ = self._split()
        self.assertNotIn("Search</button>", visible)
        self.assertNotIn('type="submit"', visible)

    def test_clear_link_is_gone_from_the_normal_interface(self):
        visible, _ = self._split()
        self.assertNotIn("sponsor-filters__reset", visible)
        self.assertNotIn(">Clear<", visible)

    def test_no_javascript_visitors_keep_both_controls(self):
        _, fallback = self._split()
        self.assertIn('type="submit"', fallback)
        self.assertIn("sponsor-filters__reset", fallback)
        self.assertIn("/sponsor/#catalog", fallback)

    def test_the_filter_fields_themselves_are_untouched(self):
        visible, _ = self._split()
        for field in ('name="q"', 'name="rating"', 'name="decade"'):
            self.assertIn(field, visible)


class SponsorDrawerTests(TestCase):
    """Pick a film in the table, get the form with that film already chosen.

    Finding a title in a 1,140-row table and then hunting for it again in a
    1,140-option <select> throws away the work the search just did.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.studio = Studio.objects.create(name="Universal", slug="universal")
        cls.jaws = StudioTitle.objects.create(
            studio=cls.studio, original_title="JAWS", title="Jaws",
            release_date=datetime.date(1975, 6, 20), mpa_rating="PG",
            runtime_minutes=124,
        )
        cls.hidden = StudioTitle.objects.create(
            studio=cls.studio, original_title="HIDDEN", title="Hidden One",
            release_date=datetime.date(2020, 1, 1), is_available=False,
        )

    def _page(self):
        return self.client.get(reverse("sponsor")).content.decode()

    def test_each_row_offers_a_way_to_sponsor_that_film(self):
        html = self._page()
        self.assertIn('data-title-id="%d"' % self.jaws.pk, html)
        self.assertIn('data-title-name="Jaws"', html)

    def test_the_trigger_is_a_real_link_for_visitors_without_javascript(self):
        # With no JS there is no drawer, so the trigger has to fall back to
        # jumping at the form the way the tier buttons already do.
        html = self._page()
        row = html.split('data-title-id="%d"' % self.jaws.pk, 1)[0]
        self.assertIn('href="#inquire"', row.rsplit("<a ", 1)[1])

    def test_the_form_is_rendered_exactly_once(self):
        # Two copies would mean two <form>s posting to the same endpoint and
        # duplicate ids on every field.
        html = self._page()
        self.assertEqual(html.count("sponsor-inquire__form"), 1)
        self.assertEqual(html.count('id="id_business_name"'), 1)

    def test_the_drawer_is_not_hidden_from_visitors_without_javascript(self):
        # The drawer is only a drawer once the js class lands on <html>.
        # Nothing here may hide it on its own, or a no-JS visitor loses the
        # form altogether.
        html = self._page()
        # Just the section's own opening tag — the form inside legitimately
        # contains a type="hidden" honeypot — and only its plain HTML
        # attributes. Alpine bindings (:aria-hidden and friends) do nothing
        # until Alpine runs, which is the very case this is about.
        opening = html.split('id="inquire"', 1)[1].split(">", 1)[0]
        plain = " ".join(
            attr for attr in opening.split()
            if not attr.startswith((":", "@", "x-"))
        )
        self.assertNotIn("x-cloak", plain)
        self.assertNotIn("hidden", plain)
        self.assertNotIn("display:none", plain.replace(" ", ""))

    def test_the_real_select_is_still_in_the_form(self):
        # Alpine sets its value; the server keeps validating it. Dropping it
        # for a bare hidden input would mean no-JS visitors could not pick a
        # film at all.
        #
        # This used to assert that every option was rendered too. It no
        # longer is: the list was ~1,140 options and more than half the
        # page's HTML, so it is fetched on demand now (see
        # SponsorshipInquiryForm._defer_film_choices). The intent above is
        # unchanged and still tested — by the ?films=all assertion below and
        # by SponsorDeferredFilmListTests in test_sponsor_seo.py, which
        # checks that an un-rendered film is still accepted on POST.
        html = self._page()
        self.assertIn('name="studio_title"', html)
        self.assertIn(reverse("sponsor_films"), html)

    def test_visitors_without_javascript_can_still_reach_every_film(self):
        # The <noscript> escape hatch for the deferred list. Without this,
        # trimming the options would have quietly removed the only way a
        # no-JS reader can name a film.
        html = self._page()
        self.assertIn("<noscript>", html)
        self.assertIn("films=all", html)

        full = self.client.get(
            reverse("sponsor"), {"films": "all"}
        ).content.decode()
        self.assertIn('value="%d"' % self.jaws.pk, full)

    def test_tier_buttons_carry_their_tier(self):
        html = self._page()
        for key in ("presenting", "community", "full_house"):
            self.assertIn('data-tier="%s"' % key, html)

    def test_an_unavailable_film_is_still_rejected(self):
        # The chosen film reaches the server through a form control the
        # reader can edit, so the queryset check has to keep doing its job.
        response = self.client.post(reverse("sponsor_inquire"), {
            "business_name": "A.H. Custom Carpentry",
            "contact_name": "Andrew",
            "email": "andrew@example.com",
            "phone": "", "tier": "", "message": "", "website": "",
            "studio_title": self.hidden.pk,
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors.get("studio_title"))

    def test_choosing_a_film_from_the_table_still_saves_it(self):
        response = self.client.post(reverse("sponsor_inquire"), {
            "business_name": "A.H. Custom Carpentry",
            "contact_name": "Andrew",
            "email": "andrew@example.com",
            "phone": "", "tier": "full_house", "message": "", "website": "",
            "studio_title": self.jaws.pk,
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(SponsorshipInquiry.objects.get().studio_title, self.jaws)
