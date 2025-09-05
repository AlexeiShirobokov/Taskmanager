from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.http import FileResponse, HttpResponseForbidden
from django.utils.timezone import make_aware
from django.db.models import Q, Count
from django.contrib import messages
from django.utils import timezone
from datetime import timedelta
from .forms import TaskForm
from .models import Task, TaskParticipant, TaskMessage, TaskFile, User
from io import BytesIO
from datetime import datetime
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.offline import plot


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
    # Сортируем пользователей по имени и фамилии
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


@login_required
def dashboard(request):
    try:
        # Получаем все задачи пользователя
        user_tasks = Task.objects.filter(
            Q(creator=request.user) |
            Q(responsible=request.user) |
            Q(participants__user=request.user)
        ).distinct()

        # Основная статистика
        total_tasks = user_tasks.count()
        completed_tasks = user_tasks.filter(is_completed=True).count()
        overdue_tasks = user_tasks.filter(is_completed=False, deadline__lt=timezone.now()).count()
        completion_rate = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0

        # Статистика по времени
        thirty_days_ago = timezone.now() - timedelta(days=30)
        recent_tasks = user_tasks.filter(created_at__gte=thirty_days_ago)
        on_time_tasks = recent_tasks.filter(is_completed=True).count()

        # Создаем графики
        completion_chart = create_completion_chart(completed_tasks, total_tasks - completed_tasks)
        timeline_chart = create_timeline_chart(user_tasks)
        responsible_chart = create_responsible_chart(user_tasks)
        deadline_chart = create_deadline_chart(user_tasks)

        # Последние выполненные задачи
        recently_completed = user_tasks.filter(
            is_completed=True
        ).select_related('responsible').order_by('-created_at')[:5]

        # Предстоящие задачи
        upcoming_tasks = user_tasks.filter(
            is_completed=False,
            deadline__gte=timezone.now(),
            deadline__lte=timezone.now() + timedelta(days=7)
        ).select_related('responsible').order_by('deadline')[:5]

        context = {
            'total_tasks': total_tasks,
            'completed_tasks': completed_tasks,
            'overdue_tasks': overdue_tasks,
            'completion_rate': round(completion_rate, 1),
            'on_time_tasks': on_time_tasks,
            'recently_completed': recently_completed,
            'upcoming_tasks': upcoming_tasks,
            'completion_chart': completion_chart,
            'timeline_chart': timeline_chart,
            'responsible_chart': responsible_chart,
            'deadline_chart': deadline_chart,
        }

        return render(request, 'tasks/dashboard.html', context)

    except Exception as e:
        print(f"Error in dashboard: {e}")
        # Возвращаем базовый контекст в случае ошибки
        return render(request, 'tasks/dashboard.html', {
            'total_tasks': 0,
            'completed_tasks': 0,
            'overdue_tasks': 0,
            'completion_rate': 0,
            'on_time_tasks': 0,
            'recently_completed': [],
            'upcoming_tasks': [],
        })


def create_completion_chart(completed, pending):
    fig = go.Figure(data=[go.Pie(
        labels=['Выполнено', 'В работе'],
        values=[completed, pending],
        hole=.6,
        marker_colors=['#00cc96', '#636efa']
    )])

    fig.update_layout(
        showlegend=True,
        annotations=[dict(text=f'{completed}', x=0.5, y=0.5, font_size=20, showarrow=False)],
        margin=dict(t=0, b=0, l=0, r=0),
        height=300
    )

    return plot(fig, output_type='div', include_plotlyjs=False)


def create_timeline_chart(tasks):
    # Упрощенная версия без pandas
    timeline_data = []
    for task in tasks:
        timeline_data.append({
            'date': task.created_at.date(),
            'count': 1,
            'status': 'Выполнено' if task.is_completed else 'В работе'
        })

    if not timeline_data:
        return "<div class='notification is-warning'>Нет данных для графика</div>"

    # Создаем простой график без pandas
    dates = sorted(set(item['date'] for item in timeline_data))
    completed_counts = [sum(1 for item in timeline_data if item['date'] == date and item['status'] == 'Выполнено') for
                        date in dates]
    pending_counts = [sum(1 for item in timeline_data if item['date'] == date and item['status'] == 'В работе') for date
                      in dates]

    fig = go.Figure()
    fig.add_trace(go.Bar(x=dates, y=completed_counts, name='Выполнено', marker_color='#00cc96'))
    fig.add_trace(go.Bar(x=dates, y=pending_counts, name='В работе', marker_color='#636efa'))

    fig.update_layout(
        height=300,
        showlegend=True,
        margin=dict(t=40, b=0, l=0, r=0),
        title='Динамика создания задач'
    )

    return plot(fig, output_type='div', include_plotlyjs=False)


def create_responsible_chart(tasks):
    # Статистика по ответственным
    responsible_stats = {}
    for task in tasks:
        if task.responsible:
            responsible_name = task.responsible.get_full_name() or task.responsible.username
            if responsible_name not in responsible_stats:
                responsible_stats[responsible_name] = {'total': 0, 'completed': 0}
            responsible_stats[responsible_name]['total'] += 1
            if task.is_completed:
                responsible_stats[responsible_name]['completed'] += 1

    if not responsible_stats:
        return "<div class='notification is-warning'>Нет данных для графика</div>"

    names = list(responsible_stats.keys())
    totals = [responsible_stats[name]['total'] for name in names]
    completion_rates = [
        (responsible_stats[name]['completed'] / responsible_stats[name]['total'] * 100) if responsible_stats[name][
                                                                                               'total'] > 0 else 0 for
        name in names]

    fig = go.Figure(data=[go.Bar(
        x=names,
        y=totals,
        marker_color=completion_rates,
        marker_colorscale='Viridis',
        text=[f'{rate:.1f}%' for rate in completion_rates],
        textposition='auto'
    )])

    fig.update_layout(
        height=300,
        showlegend=False,
        margin=dict(t=40, b=0, l=0, r=0),
        title='Распределение по ответственным',
        xaxis_title='Ответственный',
        yaxis_title='Количество задач'
    )

    return plot(fig, output_type='div', include_plotlyjs=False)


def create_deadline_chart(tasks):
    # Анализ сроков выполнения
    deadline_data = []
    for task in tasks:
        if task.deadline:
            days_until_deadline = (task.deadline.date() - timezone.now().date()).days
            status = 'Выполнено' if task.is_completed else 'Просрочено' if days_until_deadline < 0 else 'В процессе'
            deadline_data.append({
                'days_until_deadline': days_until_deadline,
                'status': status
            })

    if not deadline_data:
        return "<div class='notification is-warning'>Нет данных для графика</div>"

    # Группируем данные
    status_counts = {'Выполнено': 0, 'В процессе': 0, 'Просрочено': 0}
    for item in deadline_data:
        status_counts[item['status']] += 1

    fig = go.Figure(data=[go.Pie(
        labels=list(status_counts.keys()),
        values=list(status_counts.values()),
        marker_colors=['#00cc96', '#636efa', '#ef553b']
    )])

    fig.update_layout(
        height=300,
        showlegend=True,
        margin=dict(t=40, b=0, l=0, r=0),
        title='Статус задач по срокам'
    )

    return plot(fig, output_type='div', include_plotlyjs=False)