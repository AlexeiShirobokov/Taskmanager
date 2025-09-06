from django import forms
from .models import Task
from django.contrib.auth.models import User

class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ['title', 'description', 'deadline']


class DelegateTaskForm(forms.ModelForm):
    new_responsible = forms.ModelChoiceField(
        queryset=User.objects.all(),
        label="Новый ответственный",
        required=True
    )

    class Meta:
        model = Task
        fields = ['new_responsible']