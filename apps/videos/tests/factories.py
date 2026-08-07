import factory
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.models import User
from apps.videos.models import Project, UploadedVideo


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda o: f"{o.username}@example.com")


class ProjectFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Project

    owner = factory.SubFactory(UserFactory)
    title = "My Videos"


class UploadedVideoFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = UploadedVideo
        skip_postgeneration_save = True

    project = factory.SubFactory(ProjectFactory)
    file = factory.LazyFunction(
        lambda: SimpleUploadedFile("clip.mp4", b"fake-bytes", content_type="video/mp4")
    )
    original_filename = "clip.mp4"
    file_size_bytes = 10

    @factory.post_generation
    def init_steps(self, create, extracted, **kwargs):
        if create:
            self.init_pipeline_steps()
            self.save(update_fields=["pipeline_steps"])
