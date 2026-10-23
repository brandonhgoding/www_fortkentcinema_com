from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """The site's user, kept on the table Django's own User already used.

    Same columns as auth.User for now, so existing staff accounts, their
    group memberships and the foreign keys pointing at them carry over.
    """

    class Meta:
        db_table = "auth_user"
