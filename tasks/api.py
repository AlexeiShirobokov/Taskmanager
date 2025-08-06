from rest_framework import serializers, viewsets
from .models import Task, TaskMessage

class TaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = Task
        fields = '__all__'

class TaskMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskMessage
        fields = '__all__'

class TaskViewSet(viewsets.ModelViewSet):
    queryset = Task.objects.all()
    serializer_class = TaskSerializer

class TaskMessageViewSet(viewsets.ModelViewSet):
    queryset = TaskMessage.objects.all()
    serializer_class = TaskMessageSerializer