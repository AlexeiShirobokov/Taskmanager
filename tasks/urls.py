from django.urls import path
from . import views

# urlpatterns = [
#     path('', views.task_list, name='task_list'),
#     path('task/<int:pk>/', views.task_detail, name='task_detail'),
#     path('task/new/', views.task_create, name='task_create'),
#     path('task/<int:pk>/complete/', views.complete_task, name='complete_task'),
#     path('task/<int:pk>/upload-files/', views.upload_files, name='upload_files'),
#     path('task/<int:pk>/delegate/', views.delegate_task, name='delegate_task'),
#     path('dashboard/', views.dashboard, name='dashboard'),
# ]

urlpatterns = [
    path("", views.task_list, name="task_list"),
    path("dashboard/", views.dashboard, name="dashboard"),

    path("tasks/new/", views.task_create, name="task_create"),
    path('task/new/', views.task_create, name='task_create'),
    path("tasks/<int:pk>/", views.task_detail, name="task_detail"),
    path("tasks/<int:pk>/edit/", views.edit_task, name="edit_task"),
    path("tasks/<int:pk>/delegate/", views.delegate_task, name="delegate_task"),
    path("tasks/<int:pk>/complete/", views.complete_task, name="complete_task"),
    path("tasks/<int:pk>/upload/", views.upload_files, name="upload_files"),
    path('task/<int:pk>/upload-files/', views.upload_files, name='upload_files'),
    path('', views.task_list, name='task_list'),
    path('task/<int:pk>/', views.task_detail, name='task_detail'),
    path('task/new/', views.task_create, name='task_create'),
    path('task/<int:pk>/complete/', views.complete_task, name='complete_task'),
    path('task/<int:pk>/upload-files/', views.upload_files, name='upload_files'),
    path('task/<int:pk>/delegate/', views.delegate_task, name='delegate_task'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path("projects/new/", views.project_create, name="project_create"),
    # Project
    path("projects/new/", views.project_create, name="project_create"),
    path("projects/<int:pk>/", views.project_detail, name="project_detail"),
    path("projects/<int:pk>/edit/", views.project_edit, name="project_edit"),
    path("projects/<int:pk>/upload/", views.project_upload_files, name="project_upload_files"),
    path("projects/", views.project_list, name="project_list"),
]