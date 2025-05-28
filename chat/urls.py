from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('login/', auth_views.LoginView.as_view(template_name='login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('settings/', views.manage_user_settings, name='user_settings'),
    path('create_new_chat/', views.create_new_chat_view, name='create_new_chat'), # New URL
    path('api/chat/<int:chat_id>/', views.get_chat_details, name='get_chat_details'),
    path('api/chat/<int:chat_id>/add_message/', views.add_message_to_chat, name='add_message_to_chat'),
    path('api/chat/<int:chat_id>/message/<int:message_id>/update_role/', views.update_message_role, name='update_message_role'),
    path('api/chat/<int:chat_id>/set_active_child/', views.set_active_child_view, name='set_active_child'),
    path('api/chat/<int:chat_id>/message/<int:message_id>/delete/', views.delete_message_view, name='delete_message'),
    path('api/chat/<int:chat_id>/message/<int:source_message_id>/add_sibling/', views.add_sibling_view, name='add_sibling_message'),
    path('api/chat/<int:chat_id>/message/<int:message_id>/update_content/', views.update_message_content, name='update_message_content'),
    path('api/chat/<int:chat_id>/rename_title/', views.rename_chat_title, name='rename_chat_title'),
    path('api/chat/<int:chat_id>/delete/', views.delete_chat, name='delete_chat'),
    # Folder management API URLs
    path('api/folder/create/', views.create_folder_api, name='create_folder_api'),
    path('api/folder/rename/', views.rename_folder_api, name='rename_folder_api'),
    path('api/folder/delete/', views.delete_folder_api, name='delete_folder_api'),
]
