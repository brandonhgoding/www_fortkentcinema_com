from html.parser import HTMLParser

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from cinema.models import Film, Poll, PollOption, PollStatus, Vote

User = get_user_model()


class _SearchBoxAncestors(HTMLParser):
    """Collect the hx-vals values on every open element above the film
    search box (the input named "q")."""

    VOID = {"input", "img", "br", "hr", "meta", "link"}

    def __init__(self) -> None:
        super().__init__()
        self.stack: list[dict] = []
        self.found: list[str] | None = None

    def handle_starttag(self, tag, attrs) -> None:
        attrs = dict(attrs)
        if tag == "input" and attrs.get("name") == "q" and self.found is None:
            self.found = [a["hx-vals"] for a in self.stack if "hx-vals" in a]
        if tag not in self.VOID:
            self.stack.append(attrs)

    def handle_endtag(self, tag) -> None:
        if self.stack:
            self.stack.pop()


def _hx_vals_above_search_box(html: str) -> list[str]:
    parser = _SearchBoxAncestors()
    parser.feed(html)
    assert parser.found is not None, "no film search box on the page"
    return parser.found


class PollDetailTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")
        self.poll = Poll.objects.create(title="Round One")

    def test_detail_renders(self) -> None:
        response = self.client.get(
            reverse("dashboard:poll_detail", args=[self.poll.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Round One", response.content.decode())

    def test_detail_shows_the_film_picker(self) -> None:
        html = self.client.get(
            reverse("dashboard:poll_detail", args=[self.poll.pk])
        ).content.decode()
        self.assertIn("Search for a film", html)

    def test_film_picker_search_box_inherits_no_hx_vals(self) -> None:
        # The add-to-ballot hook used to be hx-post/hx-vals on the picker's
        # wrapper. htmx inherits hx-vals from ancestors, so the wrapper's
        # `js:event.detail.id` ran on the search box's own request, threw,
        # and the dropdown never showed any results.
        html = self.client.get(
            reverse("dashboard:poll_detail", args=[self.poll.pk])
        ).content.decode()
        self.assertEqual(_hx_vals_above_search_box(html), [])
        self.assertIn(
            f'data-add-url="{reverse("dashboard:poll_option_add", args=[self.poll.pk])}"',
            html,
        )

    def test_detail_lists_options_with_counts(self) -> None:
        option = PollOption.objects.create(
            poll=self.poll, film=Film.objects.create(title="Casablanca")
        )
        Vote.objects.create(poll=self.poll, option=option, voter_key="k1")

        html = self.client.get(
            reverse("dashboard:poll_detail", args=[self.poll.pk])
        ).content.decode()

        self.assertIn("Casablanca", html)
        self.assertIn("1 vote", html)

    def test_requires_staff(self) -> None:
        self.client.logout()
        response = self.client.get(
            reverse("dashboard:poll_detail", args=[self.poll.pk])
        )
        self.assertEqual(response.status_code, 302)


class PollOptionTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")
        self.poll = Poll.objects.create(title="Round One")
        self.film = Film.objects.create(title="Casablanca")

    def test_add_an_option(self) -> None:
        self.client.post(
            reverse("dashboard:poll_option_add", args=[self.poll.pk]),
            {"film_id": self.film.pk},
        )
        self.assertEqual(self.poll.options.count(), 1)
        self.assertEqual(self.poll.options.first().film, self.film)

    def test_adding_the_same_film_twice_is_a_no_op(self) -> None:
        for _ in range(2):
            self.client.post(
                reverse("dashboard:poll_option_add", args=[self.poll.pk]),
                {"film_id": self.film.pk},
            )
        self.assertEqual(self.poll.options.count(), 1)

    def test_adding_after_a_removal_takes_a_fresh_slot(self) -> None:
        films = [Film.objects.create(title=t) for t in ("A", "B", "C")]
        for position, film in enumerate(films, start=1):
            PollOption.objects.create(poll=self.poll, film=film, sort_order=position)
        self.poll.options.get(film=films[0]).delete()
        self.client.post(
            reverse("dashboard:poll_option_add", args=[self.poll.pk]),
            {"film_id": self.film.pk},
        )
        orders = list(self.poll.options.values_list("sort_order", flat=True))
        self.assertEqual(sorted(orders), [2, 3, 4])

    def test_added_options_get_increasing_sort_order(self) -> None:
        other = Film.objects.create(title="The Thing")
        for film in (self.film, other):
            self.client.post(
                reverse("dashboard:poll_option_add", args=[self.poll.pk]),
                {"film_id": film.pk},
            )
        orders = list(self.poll.options.values_list("sort_order", flat=True))
        self.assertEqual(orders, sorted(orders))
        self.assertEqual(len(set(orders)), 2)

    def test_add_with_an_unknown_film_is_a_bad_request(self) -> None:
        response = self.client.post(
            reverse("dashboard:poll_option_add", args=[self.poll.pk]),
            {"film_id": 999999},
        )
        self.assertEqual(response.status_code, 400)

    def test_remove_an_option(self) -> None:
        option = PollOption.objects.create(poll=self.poll, film=self.film)
        self.client.post(
            reverse("dashboard:poll_option_remove", args=[self.poll.pk, option.pk])
        )
        self.assertEqual(self.poll.options.count(), 0)

    def test_cannot_change_the_ballot_of_an_open_poll(self) -> None:
        self.poll.status = PollStatus.OPEN
        self.poll.save()
        response = self.client.post(
            reverse("dashboard:poll_option_add", args=[self.poll.pk]),
            {"film_id": self.film.pk},
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.poll.options.count(), 0)


class PollOptionReorderTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")
        self.poll = Poll.objects.create(title="Round One")
        self.first = PollOption.objects.create(
            poll=self.poll,
            film=Film.objects.create(title="Casablanca"),
            sort_order=1,
        )
        self.second = PollOption.objects.create(
            poll=self.poll,
            film=Film.objects.create(title="The Thing"),
            sort_order=2,
        )

    def _titles(self) -> list[str]:
        return [o.film.title for o in self.poll.options.all()]

    def test_move_down_swaps_with_the_next_option(self) -> None:
        self.client.post(
            reverse("dashboard:poll_option_move", args=[self.poll.pk, self.first.pk]),
            {"direction": "down"},
        )
        self.assertEqual(self._titles(), ["The Thing", "Casablanca"])

    def test_move_up_swaps_with_the_previous_option(self) -> None:
        self.client.post(
            reverse("dashboard:poll_option_move", args=[self.poll.pk, self.second.pk]),
            {"direction": "up"},
        )
        self.assertEqual(self._titles(), ["The Thing", "Casablanca"])

    def test_moving_the_first_option_up_is_a_no_op(self) -> None:
        self.client.post(
            reverse("dashboard:poll_option_move", args=[self.poll.pk, self.first.pk]),
            {"direction": "up"},
        )
        self.assertEqual(self._titles(), ["Casablanca", "The Thing"])

    def test_moving_the_last_option_down_is_a_no_op(self) -> None:
        self.client.post(
            reverse("dashboard:poll_option_move", args=[self.poll.pk, self.second.pk]),
            {"direction": "down"},
        )
        self.assertEqual(self._titles(), ["Casablanca", "The Thing"])

    def test_unknown_direction_is_a_bad_request(self) -> None:
        response = self.client.post(
            reverse("dashboard:poll_option_move", args=[self.poll.pk, self.first.pk]),
            {"direction": "sideways"},
        )
        self.assertEqual(response.status_code, 400)

    def test_cannot_reorder_once_voting_is_open(self) -> None:
        self.poll.status = PollStatus.OPEN
        self.poll.save()
        response = self.client.post(
            reverse("dashboard:poll_option_move", args=[self.poll.pk, self.first.pk]),
            {"direction": "down"},
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self._titles(), ["Casablanca", "The Thing"])
