from django.db import models
from django.contrib.auth.models import User
from django.conf import settings

import os


class TaskFile(models.Model):
    task = models.ForeignKey("Task", on_delete=models.CASCADE, related_name="files")
    file = models.FileField(upload_to="task_files/%Y/%m/%d/")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"{self.file.name}"

    @property
    def filename(self):
        return os.path.basename(self.file.name)


class Task(models.Model):
    title = models.CharField("Тема", max_length=255)
    description = models.TextField("Описание задачи")
    deadline = models.DateTimeField("Срок выполнения")
    created_at = models.DateTimeField("Создано", auto_now_add=True)

    creator = models.ForeignKey(
        User, related_name='created_tasks',
        on_delete=models.CASCADE, verbose_name="Автор"
    )
    responsible = models.ForeignKey(
        User, related_name='responsible_tasks',
        on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="Ответственный"
    )
    is_delegated = models.BooleanField("Делегировано", default=False)
    is_completed = models.BooleanField(default=False)
    delegated_from = models.ForeignKey(
        User, related_name='delegated_tasks',
        on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="Делегировано от"
    )
    delegated_at = models.DateTimeField("Дата делегирования", null=True, blank=True)

    def __str__(self):
        return f"{self.title} (до {self.deadline.strftime('%d.%m.%Y')})"


class TaskParticipant(models.Model):
    ROLE_CHOICES = [
        ('executor', 'Исполнитель'),
        ('responsible', 'Ответственный'),
        ('observer', 'Наблюдатель'),
    ]

    task = models.ForeignKey(
        Task, on_delete=models.CASCADE, related_name='participants',
        verbose_name="Задача"
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE,
        verbose_name="Пользователь"
    )
    role = models.CharField(
        max_length=20, choices=ROLE_CHOICES,
        verbose_name="Роль"
    )

    class Meta:
        unique_together = ('task', 'user')
        verbose_name = "Участник задачи"
        verbose_name_plural = "Участники задачи"

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} — {self.get_role_display()}"


class TaskMessage(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='messages', verbose_name="Задача")
    sender = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Отправитель")
    content = models.TextField("Сообщение")
    timestamp = models.DateTimeField("Дата и время", auto_now_add=True)

    def __str__(self):
        return f"Сообщение от {self.sender.get_full_name() or self.sender.username} — {self.timestamp.strftime('%d.%m.%Y %H:%M')}"

# tasks/models.py
from django.db import models
from django.contrib.auth.models import User

class Project(models.Model):
    title = models.CharField("Название проекта", max_length=255)
    description = models.TextField("Описание", blank=True)
    deadline = models.DateTimeField("Срок", null=True, blank=True)
    created_at = models.DateTimeField("Создано", auto_now_add=True)

    creator = models.ForeignKey(User, related_name="created_projects", on_delete=models.CASCADE, verbose_name="Автор")
    manager = models.ForeignKey(User, related_name="managed_projects", on_delete=models.SET_NULL, null=True, blank=True,
                                verbose_name="Руководитель проекта")

    def __str__(self):
        return self.title


class ProjectMember(models.Model):
    ROLE_CHOICES = [
        ('manager', 'Руководитель проекта'),
        ('member', 'Участник'),
        ('observer', 'Наблюдатель'),
    ]
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='member')

    class Meta:
        unique_together = ('project', 'user')

    def __str__(self):
        return f"{self.user} — {self.get_role_display()}"


class ProjectItem(models.Model):
    """Пункт чек-листа внутри проекта"""
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="items")
    title = models.CharField("Пункт", max_length=255)
    deadline = models.DateTimeField("Срок", null=True, blank=True)
    is_completed = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)

    assignees = models.ManyToManyField(User, through="ProjectItemAssignee", related_name="project_items",
                                       verbose_name="Исполнители")

    class Meta:
        ordering = ("order", "id")

    def __str__(self):
        return self.title


class ProjectItemAssignee(models.Model):
    item = models.ForeignKey(ProjectItem, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    class Meta:
        unique_together = ("item", "user")

class ProjectMessage(models.Model):
    project = models.ForeignKey('Project', on_delete=models.CASCADE, related_name='messages', verbose_name="Проект")
    sender  = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Отправитель")
    content = models.TextField("Сообщение")
    timestamp = models.DateTimeField("Дата и время", auto_now_add=True)

    class Meta:
        ordering = ("timestamp",)

    def __str__(self):
        return f"{self.project_id} / {self.sender} / {self.timestamp:%Y-%m-%d %H:%M}"

class ProjectFile(models.Model):
    project = models.ForeignKey("Project", on_delete=models.CASCADE, related_name="files")
    file     = models.FileField(upload_to="project_files/%Y/%m/%d/")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return self.file.name

    @property
    def filename(self):
        return os.path.basename(self.file.name)