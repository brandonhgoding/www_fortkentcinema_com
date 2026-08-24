from cinema.studio_catalog import clean_cell, normalize_title, parse_runtime
from django.test import SimpleTestCase


class NormalizeTitleTests(SimpleTestCase):
    def test_moves_trailing_article_to_front(self):
        self.assertEqual(normalize_title("BAD GUYS 2, THE"), "The Bad Guys 2")
        self.assertEqual(normalize_title("MAN WHO LAUGHS, THE"), "The Man Who Laughs")
        self.assertEqual(normalize_title("355, THE"), "The 355")

    def test_moves_article_before_a_subtitle_colon(self):
        self.assertEqual(
            normalize_title("PURGE, THE: ANARCHY"), "The Purge: Anarchy"
        )
        self.assertEqual(
            normalize_title("CROODS, THE: A NEW AGE"), "The Croods: A New Age"
        )
        self.assertEqual(
            normalize_title("AMERICAN TAIL, AN: FIEVEL GOES WEST"),
            "An American Tail: Fievel Goes West",
        )
        self.assertEqual(
            normalize_title("LOST WORLD, THE: JURASSIC PARK"),
            "The Lost World: Jurassic Park",
        )

    def test_mid_title_comma_article_is_not_moved(self):
        # Regression guard: ", THE"/", A"/", AN" only means "moved article"
        # when it is the whole remainder (end of string, or immediately
        # before a subtitle colon) — not whenever it appears mid-title.
        self.assertEqual(normalize_title("HONEY, DON'T!"), "Honey, Don't!")
        self.assertEqual(
            normalize_title("20,000 LEAGUES UNDER THE SEA"),
            "20,000 Leagues Under the Sea",
        )

    def test_keeps_small_words_lowercase_inside_title(self):
        self.assertEqual(
            normalize_title("SECRET LIFE OF PETS, THE"),
            "The Secret Life of Pets",
        )
        self.assertEqual(
            normalize_title("20,000 LEAGUES UNDER THE SEA"),
            "20,000 Leagues Under the Sea",
        )

    def test_does_not_split_at_apostrophes(self):
        # str.title() would produce "Freddy'S" here.
        self.assertEqual(
            normalize_title("FIVE NIGHTS AT FREDDY'S 2"),
            "Five Nights at Freddy's 2",
        )
        self.assertEqual(normalize_title("HONEY, DON'T!"), "Honey, Don't!")

    def test_capitalizes_after_a_colon(self):
        self.assertEqual(
            normalize_title("GABBY'S DOLLHOUSE: THE MOVIE"),
            "Gabby's Dollhouse: The Movie",
        )

    def test_hyphenated_words_are_each_capitalized(self):
        self.assertEqual(
            normalize_title("40-YEAR-OLD VIRGIN, THE"),
            "The 40-Year-Old Virgin",
        )

    def test_year_parenthetical_is_preserved(self):
        self.assertEqual(normalize_title("SCARFACE (1932)"), "Scarface (1932)")
        self.assertEqual(normalize_title("9 (2009)"), "9 (2009)")

    def test_already_cased_parenthetical_is_left_alone(self):
        self.assertEqual(
            normalize_title("2 FAST 2 FURIOUS (aka Fast & Furious 2)"),
            "2 Fast 2 Furious (aka Fast & Furious 2)",
        )

    def test_numeric_title_survives(self):
        self.assertEqual(normalize_title("1917"), "1917")

    def test_empty_input(self):
        self.assertEqual(normalize_title(""), "")
        self.assertEqual(normalize_title(None), "")


class ParseRuntimeTests(SimpleTestCase):
    def test_integer_passes_through_with_no_raw(self):
        self.assertEqual(parse_runtime(132), (132, ""))

    def test_takes_leading_number_and_keeps_raw(self):
        self.assertEqual(parse_runtime("119 & 146"), (119, "119 & 146"))
        self.assertEqual(parse_runtime("93 & 95"), (93, "93 & 95"))

    def test_handles_embedded_newline_and_short_note(self):
        self.assertEqual(
            parse_runtime("94\n(incl 5min short)"),
            (94, "94\n(incl 5min short)"),
        )
        self.assertEqual(
            parse_runtime("91 (inc. 4 min. short)"),
            (91, "91 (inc. 4 min. short)"),
        )

    def test_unparseable_returns_none_but_keeps_raw(self):
        self.assertEqual(parse_runtime("unknown"), (None, "unknown"))

    def test_none_is_empty(self):
        self.assertEqual(parse_runtime(None), (None, ""))


class CleanCellTests(SimpleTestCase):
    def test_none_becomes_empty_string(self):
        self.assertEqual(clean_cell(None), "")

    def test_float_drops_trailing_zero(self):
        # openpyxl reads the AUDIO column as 5.1 (float) and 1 (int).
        self.assertEqual(clean_cell(5.1), "5.1")
        self.assertEqual(clean_cell(1.0), "1")

    def test_string_is_stripped(self):
        self.assertEqual(clean_cell("  5.1, 7.1, Atmos  "), "5.1, 7.1, Atmos")
