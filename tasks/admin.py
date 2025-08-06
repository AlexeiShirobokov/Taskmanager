from django.contrib import admin
from .models import Task, TaskParticipant, TaskMessage

admin.site.register(Task)
admin.site.register(TaskParticipant)
admin.site.register(TaskMessage)
