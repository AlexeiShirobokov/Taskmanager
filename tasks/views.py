from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.http import FileResponse, HttpResponseForbidden
from django.utils.timezone import make_aware
from django.db.models import Q
from django.contrib import messages
from django.utils import timezone
from datetime import timedelta, datetime
from io import BytesIO
import pandas as pd

from .forms import TaskForm
from .models import Task, TaskParticipant, TaskMessage, TaskFile, User

# ===== Вспомогательные =====
def get_user_role(user, task):
    if task.creator_id == user.id:
        return 'Создатель'
    if task.responsible_id == user.id:
        return 'Ответственный'
    p = TaskParticipant.objects.filter(task=task, user=user).first()
    return p.get_role_display() if p else '-'

def user_can_access_task(user, task):
    return (
        task.creator_id == user.id or
        task.responsible_id == user.id or
        task.participants.filter(user=user).exists()
    )

def user_can_upload_files(user, task):
    return user_can_access_task(user, task)

def user_can_complete_task(user, task):
    return (
        task.creator_id == user.id or
        task.responsible_id == user.id or
        task.participants.filter(user=user, role__in=['executor', 'responsible']).exists()
    )

# (1) Редактировать: Создатель или Наблюдатель
def user_can_edit_task(user, task):
    return (
        task.creator_id == user.id or
        TaskParticipant.objects.filter(task=task, user=user, role='observer').exists()
    )

# (2) Делегировать: Создатель, Ответственный, Исполнитель, Наблюдатель
def user_can_delegate_task(user, task):
    return (
        task.creator_id == user.id or
        task.responsible_id == user.id or
        TaskParticipant.objects.filter(task=task, user=user, role__in=['executor', 'observer']).exists()
    )

# Подсветка дедлайна
def calc_deadline_status(task):
    """
    Возвращает один из статусов:
    done / overdue / soon / ok / no_deadline
    """
    if not task.deadline:
        return "no_deadline"
    if task.is_completed:
        return "done"
    now = timezone.now()
    if task.deadline < now:
        return "overdue"
    if task.deadline <= now + timedelta(days=1):
        return "soon"
    return "ok"

# ===== Views =====
@login_required
def task_list(request):
    query = request.GET.get('q', '').strip()
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    active_tab = request.GET.get('tab', 'creator')

    # Базы
    qs_creator = Task.objects.filter(creator=request.user)
    qs_responsible = Task.objects.filter(responsible=request.user)
    qs_participant = Task.objects.filter(participants__user=request.user)
    qs_completed = Task.objects.filter(
        Q(creator=request.user) | Q(responsible=request.user) | Q(participants__user=request.user),
        is_completed=True
    )

    # Поиск
    if query:
        f = (Q(title__icontains=query) |
             Q(description__icontains=query) |
             Q(responsible__first_name__icontains=query) |
             Q(responsible__last_name__icontains=query))
        qs_creator = qs_creator.filter(f)
        qs_responsible = qs_responsible.filter(f)
        qs_participant = qs_participant.filter(f)
        qs_completed = qs_completed.filter(f)

    # Даты
    if date_from:
        dtf = make_aware(datetime.strptime(date_from, "%Y-%m-%d"))
        qs_creator = qs_creator.filter(deadline__gte=dtf)
        qs_responsible = qs_responsible.filter(deadline__gte=dtf)
        qs_participant = qs_participant.filter(deadline__gte=dtf)
        qs_completed = qs_completed.filter(deadline__gte=dtf)

    if date_to:
        dtt = make_aware(datetime.strptime(date_to, "%Y-%m-%d"))
        qs_creator = qs_creator.filter(deadline__lte=dtt)
        qs_responsible = qs_responsible.filter(deadline__lte=dtt)
        qs_participant = qs_participant.filter(deadline__lte=dtt)
        qs_completed = qs_completed.filter(deadline__lte=dtt)

    # Экспорт
    if 'export' in request.GET:
        all_tasks = qs_creator.union(qs_responsible, qs_participant, qs_completed)
        data = [{
            'Тема': t.title,
            'Описание': t.description,
            'Срок': t.deadline.strftime('%Y-%m-%d %H:%M') if t.deadline else '',
            'Ответственный': t.responsible.get_full_name() if t.responsible else '',
            'Роль': get_user_role(request.user, t),
            'Статус': 'Завершена' if t.is_completed else 'В работе'
        } for t in all_tasks]
        output = BytesIO()
        pd.DataFrame(data).to_excel(output, index=False)
        output.seek(0)
        return FileResponse(output, as_attachment=True, filename="tasks.xlsx")

    tabs = {
        'creator': qs_creator.filter(is_completed=False),
        'responsible': qs_responsible.filter(is_completed=False).exclude(creator=request.user),
        'participant': qs_participant.filter(is_completed=False).exclude(creator=request.user).exclude(responsible=request.user),
        'completed': qs_completed,
    }
    current_qs = tabs.get(active_tab, tabs['creator']).select_related('responsible').prefetch_related('files').distinct()

    # Подготовка объектов для шаблона
    current_tasks = []
    for t in current_qs.order_by('-created_at'):
        t.my_role = get_user_role(request.user, t)
        t.files_count = t.files.count()
        t.deadline_status = calc_deadline_status(t)
        current_tasks.append(t)

    return render(request, 'tasks/task_list.html', {
        'query': query,
        'date_from': date_from,
        'date_to': date_to,
        'active_tab': active_tab,
        'current_tasks': current_tasks,
    })


@login_required
def task_create(request):
    users = User.objects.exclude(id=request.user.id).order_by('first_name', 'last_name', 'username')
    if request.method == 'POST':
        form = TaskForm(request.POST)
        if form.is_valid():
            task = form.save(commit=False)
            task.creator = request.user
            responsible_id = request.POST.get('responsible')
            if responsible_id:
                task.responsible_id = responsible_id
            task.save()

            # участники
            for user_id, role in zip(request.POST.getlist('participants'), request.POST.getlist('roles')):
                if user_id:
                    TaskParticipant.objects.create(task=task, user_id=user_id, role=role)

            # файлы
            for f in request.FILES.getlist('files'):
                TaskFile.objects.create(task=task, file=f, uploaded_by=request.user)

            return redirect('task_detail', pk=task.pk)
    else:
        form = TaskForm()
    return render(request, 'tasks/task_form.html', {'form': form, 'users': users})


@login_required
def task_detail(request, pk):
    task = get_object_or_404(Task, pk=pk)
    if not user_can_access_task(request.user, task):
        return HttpResponseForbidden("У вас нет доступа к этой задаче")

    # права
    can_complete = user_can_complete_task(request.user, task)
    can_upload_files = user_can_upload_files(request.user, task)
    can_edit = user_can_edit_task(request.user, task)
    can_delegate = user_can_delegate_task(request.user, task)

    # подсветка срока
    task.deadline_status = calc_deadline_status(task)

    # POST
    if request.method == 'POST':
        # файлы
        if 'files' in request.FILES:
            if not can_upload_files:
                return HttpResponseForbidden("У вас нет прав для загрузки файлов")
            for f in request.FILES.getlist('files'):
                TaskFile.objects.create(task=task, file=f, uploaded_by=request.user)
            messages.success(request, 'Файлы загружены')
            return redirect('task_detail', pk=pk)

        # сообщение
        content = request.POST.get('content')
        if content:
            TaskMessage.objects.create(task=task, sender=request.user, content=content)
            return redirect('task_detail', pk=pk)

    participants = TaskParticipant.objects.filter(task=task)
    task_messages = task.messages.all().order_by('timestamp')

    return render(request, 'tasks/task_detail.html', {
        'task': task,
        'participants': participants,
        'task_messages': task_messages,
        'can_complete': can_complete,
        'can_upload_files': can_upload_files,
        'can_edit': can_edit,
        'can_delegate': can_delegate,
    })


@login_required
def edit_task(request, pk):
    task = get_object_or_404(Task, pk=pk)
    if not user_can_edit_task(request.user, task):
        return HttpResponseForbidden("У вас нет прав для редактирования этой задачи")

    users = User.objects.exclude(id=request.user.id).order_by('first_name', 'last_name', 'username')
    if request.method == 'POST':
        form = TaskForm(request.POST, instance=task)
        if form.is_valid():
            task = form.save()
            # участники
            TaskParticipant.objects.filter(task=task).delete()
            for user_id, role in zip(request.POST.getlist('participants'), request.POST.getlist('roles')):
                if user_id:
                    TaskParticipant.objects.create(task=task, user_id=user_id, role=role)
            # файлы
            for f in request.FILES.getlist('files'):
                TaskFile.objects.create(task=task, file=f, uploaded_by=request.user)
            messages.success(request, 'Задача успешно обновлена')
            return redirect('task_detail', pk=task.pk)
    else:
        form = TaskForm(instance=task)

    current_participants = TaskParticipant.objects.filter(task=task)
    return render(request, 'tasks/task_form.html', {
        'form': form, 'users': users, 'task': task, 'is_edit': True, 'current_participants': current_participants
    })


@login_required
def delegate_task(request, pk):
    task = get_object_or_404(Task, pk=pk)
    if not user_can_delegate_task(request.user, task):
        return HttpResponseForbidden("У вас нет прав для делегирования этой задачи")

    users = User.objects.exclude(id=request.user.id).order_by('first_name', 'last_name', 'username')
    if request.method == 'POST':
        new_responsible_id = request.POST.get('new_responsible')
        if new_responsible_id:
            new_resp = get_object_or_404(User, id=new_responsible_id)
            if task.responsible and task.responsible != new_resp:
                TaskParticipant.objects.get_or_create(task=task, user=task.responsible, defaults={'role': 'observer'})
            task.responsible = new_resp
            task.is_delegated = True
            task.save()
            TaskParticipant.objects.get_or_create(task=task, user=new_resp, defaults={'role': 'responsible'})
            TaskMessage.objects.create(task=task, sender=request.user,
                                       content=f"Задача делегирована от {request.user.get_full_name()} к {new_resp.get_full_name()}")
            messages.success(request, f'Задача успешно делегирована {new_resp.get_full_name()}')
            return redirect('task_detail', pk=task.pk)

    return render(request, 'tasks/delegate_task.html', {'task': task, 'users': users})


@login_required
def complete_task(request, pk):
    task = get_object_or_404(Task, pk=pk)
    if not user_can_complete_task(request.user, task):
        return HttpResponseForbidden("У вас нет прав для завершения этой задачи")
    if not task.is_completed:
        task.is_completed = True
        task.save()
        messages.success(request, 'Задача отмечена как завершенная')
    return redirect('task_list')


@login_required
def upload_files(request, pk):
    task = get_object_or_404(Task, pk=pk)
    if not user_can_upload_files(request.user, task):
        return HttpResponseForbidden("У вас нет прав для загрузки файлов в эту задачу")
    if request.method == 'POST':
        for f in request.FILES.getlist('files'):
            TaskFile.objects.create(task=task, file=f, uploaded_by=request.user)
        messages.success(request, 'Файлы загружены')
    return redirect('task_detail', pk=task.pk)

@login_required
def dashboard(request):
    user_tasks = Task.objects.filter(
        Q(creator=request.user) |
        Q(responsible=request.user) |
        Q(participants__user=request.user)
    ).distinct()

    total_tasks = user_tasks.count()
    completed_tasks = user_tasks.filter(is_completed=True).count()
    overdue_tasks = user_tasks.filter(is_completed=False, deadline__lt=timezone.now()).count()

    context = {
        "total_tasks": total_tasks,
        "completed_tasks": completed_tasks,
        "overdue_tasks": overdue_tasks,
        # при желании добавь графики и пр., как раньше
    }
    return render(request, "tasks/dashboard.html", context)