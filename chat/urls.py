from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('login/', auth_views.LoginView.as_view(template_name='login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('settings/', views.manage_user_settings, name='user_settings'),
    path('api/chat/<int:chat_id>/', views.get_chat_details, name='get_chat_details'),
    path('api/chat/<int:chat_id>/add_message/', views.add_message_to_chat, name='add_message_to_chat'),
]
