from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views

from rest_framework.routers import DefaultRouter
from tasks.api import TaskViewSet, TaskMessageViewSet

router = DefaultRouter()
router.register(r'api/tasks', TaskViewSet)
router.register(r'api/messages', TaskMessageViewSet)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/login/', auth_views.LoginView.as_view(), name='login'),
    path('', include('tasks.urls')),

] + router.urls + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)