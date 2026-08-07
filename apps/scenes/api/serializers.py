from rest_framework import serializers

from apps.scenes.models import Scene


class SceneSerializer(serializers.ModelSerializer):
    class Meta:
        model = Scene
        fields = ["index", "start_time", "end_time"]
