from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.http import FileResponse, HttpResponseForbidden
from django.utils.timezone import make_aware
from django.db.models import Q
from django.contrib import messages
from .forms import TaskForm
from .models import Task, TaskParticipant, TaskMessage, TaskFile, User
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
    active_tab = request.GET.get('tab', 'creator')

    # Создаем базовые запросы без distinct()
    created_tasks = Task.objects.filter(creator=request.user)
    responsible_tasks = Task.objects.filter(responsible=request.user)
    participant_tasks = Task.objects.filter(participants__user=request.user)

    # Для completed_tasks также убираем distinct() и используем filter()
    completed_tasks = Task.objects.filter(
        Q(creator=request.user) |
        Q(responsible=request.user) |
        Q(participants__user=request.user),
        is_completed=True
    )

    # Применяем фильтры ко всем запросам
    if query:
        query_filter = Q(title__icontains=query) | Q(responsible__first_name__icontains=query) | Q(
            responsible__last_name__icontains=query)
        created_tasks = created_tasks.filter(query_filter)
        responsible_tasks = responsible_tasks.filter(query_filter)
        participant_tasks = participant_tasks.filter(query_filter)
        completed_tasks = completed_tasks.filter(query_filter)

    if date_from:
        date_from_dt = make_aware(datetime.strptime(date_from, "%Y-%m-%d"))
        created_tasks = created_tasks.filter(deadline__gte=date_from_dt)
        responsible_tasks = responsible_tasks.filter(deadline__gte=date_from_dt)
        participant_tasks = participant_tasks.filter(deadline__gte=date_from_dt)
        completed_tasks = completed_tasks.filter(deadline__gte=date_from_dt)

    if date_to:
        date_to_dt = make_aware(datetime.strptime(date_to, "%Y-%m-%d"))
        created_tasks = created_tasks.filter(deadline__lte=date_to_dt)
        responsible_tasks = responsible_tasks.filter(deadline__lte=date_to_dt)
        participant_tasks = participant_tasks.filter(deadline__lte=date_to_dt)
        completed_tasks = completed_tasks.filter(deadline__lte=date_to_dt)

    if 'export' in request.GET:
        # Для экспорта используем union() вместо | для объединения запросов
        all_tasks = created_tasks.union(
            responsible_tasks,
            participant_tasks,
            completed_tasks
        )

        data = [{
            'Тема': t.title,
            'Описание': t.description,
            'Срок': t.deadline.strftime('%Y-%m-%d %H:%M'),
            'Ответственный': t.responsible.get_full_name() if t.responsible else '',
            'Роль': get_user_role(request.user, t),
            'Статус': 'Завершена' if t.is_completed else 'В работе'
        } for t in all_tasks]

        df = pd.DataFrame(data)
        output = BytesIO()
        df.to_excel(output, index=False)
        output.seek(0)
        return FileResponse(output, as_attachment=True, filename="tasks.xlsx")

    # Для отображения в шаблоне используем отдельные запросы
    tasks_by_role = {
        'creator': created_tasks.filter(is_completed=False),
        'responsible': responsible_tasks.filter(is_completed=False).exclude(creator=request.user),
        'participant': participant_tasks.filter(is_completed=False).exclude(creator=request.user).exclude(
            responsible=request.user),
        'completed': completed_tasks,
    }

    # Создаем roles_by_task без объединения запросов
    roles_by_task = {}
    for task in created_tasks:
        roles_by_task[task.id] = get_user_role(request.user, task)
    for task in responsible_tasks:
        roles_by_task[task.id] = get_user_role(request.user, task)
    for task in participant_tasks:
        roles_by_task[task.id] = get_user_role(request.user, task)
    for task in completed_tasks:
        roles_by_task[task.id] = get_user_role(request.user, task)

    return render(request, 'tasks/task_list.html', {
        'query': query,
        'date_from': date_from,
        'date_to': date_to,
        'tasks_by_role': tasks_by_role,
        'roles_by_task': roles_by_task,
        'active_tab': active_tab,
    })

@login_required
def task_create(request):
    users = User.objects.exclude(id=request.user.id)

    if request.method == 'POST':
        form = TaskForm(request.POST)
        if form.is_valid():
            task = form.save(commit=False)
            task.creator = request.user

            responsible_id = request.POST.get('responsible')
            if responsible_id:
                task.responsible_id = responsible_id
            task.save()

            # Обрабатываем участников
            participants = request.POST.getlist('participants')
            roles = request.POST.getlist('roles')
            for user_id, role in zip(participants, roles):
                if user_id:
                    TaskParticipant.objects.create(
                        task=task,
                        user_id=user_id,
                        role=role
                    )

            # Обрабатываем файлы
            files = request.FILES.getlist('files')
            for file in files:
                TaskFile.objects.create(
                    task=task,
                    file=file,
                    uploaded_by=request.user
                )

            return redirect('task_detail', pk=task.pk)
    else:
        form = TaskForm()

    return render(request, 'tasks/task_form.html', {'form': form, 'users': users})


@login_required
def task_detail(request, pk):
    task = get_object_or_404(Task, pk=pk)

    # Проверка прав доступа
    if not (request.user == task.creator or
            request.user == task.responsible or
            task.participants.filter(user=request.user).exists()):
        return HttpResponseForbidden("У вас нет доступа к этой задаче")

    participants = TaskParticipant.objects.filter(task=task)
    task_messages = task.messages.all().order_by('timestamp')

    can_complete = (
            request.user == task.creator or
            request.user == task.responsible or
            TaskParticipant.objects.filter(task=task, user=request.user, role__in=['executor', 'responsible']).exists()
    )

    if request.method == 'POST':
        # Обработка загрузки файлов
        if 'files' in request.FILES:
            files = request.FILES.getlist('files')
            for file in files:
                TaskFile.objects.create(
                    task=task,
                    file=file,
                    uploaded_by=request.user
                )
            messages.success(request, f'Загружено {len(files)} файлов')
            return redirect('task_detail', pk=pk)

        # Обработка отправки сообщения
        elif 'content' in request.POST:
            content = request.POST.get('content')
            if content:
                TaskMessage.objects.create(
                    task=task,
                    sender=request.user,
                    content=content
                )
                return redirect('task_detail', pk=pk)

    return render(request, 'tasks/task_detail.html', {
        'task': task,
        'participants': participants,
        'task_messages': task_messages,
        'can_complete': can_complete,
    })


@login_required
def complete_task(request, pk):
    task = get_object_or_404(Task, pk=pk)

    # Проверка прав доступа
    if not (request.user == task.creator or
            request.user == task.responsible or
            TaskParticipant.objects.filter(task=task, user=request.user,
                                           role__in=['executor', 'responsible']).exists()):
        return HttpResponseForbidden("У вас нет прав для завершения этой задачи")

    if not task.is_completed:
        task.is_completed = True
        task.save()
        messages.success(request, 'Задача отмечена как завершенная')

    return redirect('task_list')


@login_required
def upload_files(request, pk):
    task = get_object_or_404(Task, pk=pk)

    # Проверка прав доступа
    if not (request.user == task.creator or
            request.user == task.responsible or
            task.participants.filter(user=request.user).exists()):
        return HttpResponseForbidden("У вас нет прав для загрузки файлов в эту задачу")

    if request.method == 'POST':
        files = request.FILES.getlist('files')
        for file in files:
            TaskFile.objects.create(
                task=task,
                file=file,
                uploaded_by=request.user
            )
        messages.success(request, f'Загружено {len(files)} файлов')

    return redirect('task_detail', pk=task.pk)