from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """Custom user model.

    Defined from project start (rather than using django.contrib.auth.User
    directly) because swapping AUTH_USER_MODEL later requires a full
    migration reset — see docs/architecture.md.

    No extra fields yet; this is deliberately a thin subclass so future
    profile/plan/quota fields have somewhere to land without a disruptive
    migration.
    """

    class Meta:
        db_table = "accounts_user"

    def __str__(self) -> str:
        return self.username
