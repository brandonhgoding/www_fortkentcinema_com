# tests/factories/film_factories.py

import random
import factory
from faker import Faker

from cinema.models import Film, FilmGenre, FilmRating  # <-- change "cinema" to your app label

fake = Faker()


class FilmGenreFactory(factory.django.DjangoModelFactory):
    """
    Simple genre factory, e.g. "Action", "Comedy", etc.
    """

    class Meta:
        model = FilmGenre

    # Keep it readable instead of nonsense words
    name = factory.Iterator(
        [
            "Action",
            "Adventure",
            "Comedy",
            "Drama",
            "Family",
            "Fantasy",
            "Horror",
            "Romance",
            "Sci-Fi",
            "Thriller",
            "Animation",
        ]
    )


class FilmFactory(factory.django.DjangoModelFactory):
    """
    Film with reasonably realistic dummy data:
    - title: short sentence
    - description: paragraph
    - unique imdb_id / youtube_id
    - rating: one of your FilmRating choices
    - runtime: 80–160 min
    - poster_url: fake image URL
    - genres: 1–3 genres via post_generation
    """

    class Meta:
        model = Film

    title = factory.Faker("sentence", nb_words=3)
    description = factory.Faker("paragraph", nb_sentences=3)

    # Avoid unique collisions using a sequence
    imdb_id = factory.Sequence(lambda n: f"tt{n:07d}")
    youtube_id = factory.Sequence(lambda n: f"ytvideo{n:06d}")

    rating = factory.Iterator([choice[0] for choice in FilmRating.choices])

    runtime = factory.Faker("pyint", min_value=80, max_value=160)
    poster_url = factory.Faker("image_url")

    @factory.post_generation
    def genres(self, create, extracted, **kwargs):
        """
        - If genres passed in, attach those.
        - Otherwise, attach 1–3 random genres using FilmGenreFactory.
        """
        if not create:
            return

        if extracted:
            for genre in extracted:
                self.genres.add(genre)
        else:
            for _ in range(random.randint(1, 3)):
                genre = FilmGenreFactory()
                self.genres.add(genre)
