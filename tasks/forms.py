from django import forms
from .models import Task
from django.contrib.auth.models import User
from django.forms import inlineformset_factory
from .models import Project, ProjectItem




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

class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ["title", "description", "deadline", "manager"]
        widgets = {
            "deadline": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }

class ProjectItemForm(forms.ModelForm):
    assignees = forms.ModelMultipleChoiceField(
        queryset=None, required=False,
        widget=forms.SelectMultiple(attrs={"class": "form-select", "size": 4})
    )
    class Meta:
        model = ProjectItem
        fields = ["title", "deadline", "is_completed", "order"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "deadline": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "order": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
        }
    def __init__(self, *args, **kwargs):
        qs = kwargs.pop("assignees_qs", None)
        super().__init__(*args, **kwargs)
        if qs is not None:
            self.fields["assignees"].queryset = qs

ProjectItemFormSet = inlineformset_factory(
    Project, ProjectItem,
    form=ProjectItemForm,
    fields=["title", "deadline", "is_completed", "order"],
    extra=1, can_delete=True
)