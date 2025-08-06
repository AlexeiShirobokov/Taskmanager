from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.http import FileResponse
from django.utils.timezone import make_aware
from django.db.models import Q
from .forms import TaskForm
from .models import Task, TaskParticipant, TaskMessage, User
from io import BytesIO
from datetime import datetime
import pandas as pd


def get_user_role(user, task):
    if task.creator == user:
        return 'Создатель'
    if task.responsible == user:
        return 'Ответственный'
    participant = TaskParticipant.objects.filter(task=task, user=user).first()
    if participant:
        return participant.get_role_display()
    return '-'


@login_required
def task_list(request):
    query = request.GET.get('q', '')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')

    created_tasks = Task.objects.filter(creator=request.user, is_completed=False)
    responsible_tasks = Task.objects.filter(responsible=request.user, is_completed=False)
    participant_tasks = Task.objects.filter(participants__user=request.user, is_completed=False)

    completed_tasks = Task.objects.filter(
        Q(creator=request.user) |
        Q(responsible=request.user) |
        Q(participants__user=request.user),
        is_completed=True
    ).distinct()

    all_tasks = (created_tasks | responsible_tasks | participant_tasks).distinct()

    if query:
        all_tasks = all_tasks.filter(
            Q(title__icontains=query) |
            Q(responsible__first_name__icontains=query) |
            Q(responsible__last_name__icontains=query)
        )

    if date_from:
        all_tasks = all_tasks.filter(deadline__gte=make_aware(datetime.strptime(date_from, "%Y-%m-%d")))
    if date_to:
        all_tasks = all_tasks.filter(deadline__lte=make_aware(datetime.strptime(date_to, "%Y-%m-%d")))

    if 'export' in request.GET:
        data = [{
            'Тема': t.title,
            'Описание': t.description,
            'Срок': t.deadline.strftime('%Y-%m-%d %H:%M'),
            'Ответственный': t.responsible.get_full_name() if t.responsible else '',
            'Роль': get_user_role(request.user, t),
        } for t in all_tasks]

        df = pd.DataFrame(data)
        output = BytesIO()
        df.to_excel(output, index=False)
        output.seek(0)
        return FileResponse(output, as_attachment=True, filename="tasks.xlsx")

    tasks_by_role = {
        'creator': created_tasks,
        'responsible': responsible_tasks.exclude(id__in=created_tasks),
        'participant': participant_tasks.exclude(id__in=created_tasks).exclude(id__in=responsible_tasks),
        'completed': completed_tasks,
    }

    roles_by_task = {
        task.id: get_user_role(request.user, task)
        for task in all_tasks | completed_tasks
    }

    return render(request, 'tasks/task_list.html', {
        'query': query,
        'date_from': date_from,
        'date_to': date_to,
        'tasks_by_role': tasks_by_role,
        'roles_by_task': roles_by_task,
    })


@login_required
def task_create(request):
    users = User.objects.exclude(id=request.user.id)

    if request.method == 'POST':
        form = TaskForm(request.POST, request.FILES)
        if form.is_valid():
            task = form.save(commit=False)
            task.creator = request.user

            responsible_id = request.POST.get('responsible')
            if responsible_id:
                task.responsible_id = responsible_id
            task.save()

            participants = request.POST.getlist('participants')
            roles = request.POST.getlist('roles')
            for user_id, role in zip(participants, roles):
                if user_id:
                    TaskParticipant.objects.create(
                        task=task,
                        user_id=user_id,
                        role=role
                    )
            return redirect('task_list')
    else:
        form = TaskForm()

    return render(request, 'tasks/task_form.html', {'form': form, 'users': users})


@login_required
def task_detail(request, pk):
    task = get_object_or_404(Task, pk=pk)
    participants = TaskParticipant.objects.filter(task=task)
    messages = task.messages.all().order_by('timestamp')

    can_complete = (
        request.user == task.creator or
        request.user == task.responsible or
        TaskParticipant.objects.filter(task=task, user=request.user).exists()
    )

    if request.method == 'POST':
        if 'new_file' in request.FILES:
            task.file = request.FILES['new_file']
            task.save()
            return redirect('task_detail', pk=pk)
        elif request.POST.get("content"):
            TaskMessage.objects.create(
                task=task,
                sender=request.user,
                content=request.POST["content"]
            )
            return redirect('task_detail', pk=pk)

    return render(request, 'tasks/task_detail.html', {
        'task': task,
        'participants': participants,
        'messages': messages,
        'can_complete': can_complete,
    })


@login_required
def complete_task(request, pk):
    task = get_object_or_404(Task, pk=pk)
    if not task.is_completed and (
        request.user == task.creator or
        request.user == task.responsible or
        TaskParticipant.objects.filter(task=task, user=request.user).exists()
    ):
        task.is_completed = True
        task.save()
    return redirect('task_list')
