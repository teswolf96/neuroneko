from django.urls import path
from . import views

urlpatterns = [
    path('', views.index_view, name='index'),
    path('signup/', views.signup_view, name='signup'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('settings/', views.user_settings_view, name='user_settings'),
    path('manage-prompts/', views.manage_prompts_view, name='manage_prompts'),
    path('manage-prompts/update/<int:pk>/', views.prompt_update_view, name='prompt_update'),
    path('manage-prompts/delete/<int:pk>/', views.prompt_delete_view, name='prompt_delete'),
    
    # Saved Ideas URLs
    path('manage-ideas/', views.manage_ideas_view, name='manage_ideas'),
    path('manage-ideas/update/<int:pk>/', views.idea_update_view, name='idea_update'),
    path('manage-ideas/delete/<int:pk>/', views.idea_delete_view, name='idea_delete'),
    
    path('create_new_chat/', views.create_new_chat_view, name='create_new_chat'),

    # API Configuration URLs
    path('api-config/', views.api_endpoint_list_create_view, name='api_config'),
    # path('api-config/endpoint/add/', views.api_endpoint_create_view, name='api_endpoint_add'), # Handled by api_config POST
    path('api-config/endpoint/<int:pk>/edit/', views.api_endpoint_update_view, name='api_endpoint_edit'),
    path('api-config/endpoint/<int:pk>/delete/', views.api_endpoint_delete_view, name='api_endpoint_delete'),
    path('test_api_endpoint/<int:endpoint_id>/', views.test_api_endpoint_view, name='test_api_endpoint'),
    path('api-config/endpoint/<int:endpoint_pk>/import-models/', views.import_ai_models_view, name='import_ai_models'),
    
    path('api-config/model/add/', views.api_model_create_view, name='api_model_add'), # General add model
    path('api-config/endpoint/<int:endpoint_pk>/model/add/', views.api_model_create_view, name='api_model_add_to_endpoint'), # Add model to specific endpoint
    path('api-config/model/<int:pk>/edit/', views.api_model_update_view, name='api_model_edit'),
    path('api-config/model/<int:pk>/delete/', views.api_model_delete_view, name='api_model_delete'),

    # API endpoints for chat functionality (AJAX)
    path('api/chat/<int:chat_id>/', views.get_chat_details_api, name='get_chat_details_api'),
    path('api/chat/<int:chat_id>/add_message/', views.add_message_to_chat_api, name='add_message_to_chat_api'),
    path('api/chat/<int:chat_id>/message/<int:message_id>/update_content/', views.update_message_content_api, name='update_message_content_api'),
    path('api/chat/<int:chat_id>/message/<int:message_id>/update_role/', views.update_message_role_api, name='update_message_role_api'),
    path('api/chat/<int:chat_id>/message/<int:message_id>/delete/', views.delete_message_api, name='delete_message_api'),
    path('api/chat/<int:chat_id>/message/<int:message_id>/clean_remove/', views.clean_remove_message_api, name='clean_remove_message_api'),
    path('api/chat/<int:chat_id>/message/<int:message_id>/delete_children/', views.delete_children_api, name='delete_children_api'),
    path('api/chat/<int:chat_id>/message/<int:message_id>/isolate/', views.isolate_message_api, name='isolate_message_api'),
    path('api/chat/<int:chat_id>/message/<int:source_message_id>/add_sibling/', views.add_sibling_message_api, name='add_sibling_message_api'),
    path('api/chat/<int:chat_id>/set_active_child/', views.set_active_child_api, name='set_active_child_api'),
    path('api/chat/<int:chat_id>/message/<int:parent_message_id>/add_child_message/', views.add_child_message_api, name='add_child_message_api'), # New route
    path('api/chat/<int:chat_id>/rename_title/', views.rename_chat_title_api, name='rename_chat_title_api'),
    path('api/chat/<int:chat_id>/delete/', views.delete_chat_api, name='delete_chat_api'),
    path('api/chat/<int:chat_id>/cache_point/', views.set_cache_point_api, name='set_cache_point_api'),

    # API endpoint for saved prompts
    path('api/prompts/', views.get_saved_prompts_api, name='get_saved_prompts_api'),

    # API endpoint for saved ideas
    path('api/ideas/', views.get_saved_ideas_api, name='get_saved_ideas_api'),

    # API endpoints for folder management
    path('api/folder/create/', views.create_folder_api, name='create_folder_api'),
    path('api/folder/rename/', views.rename_folder_api, name='rename_folder_api'),
    path('api/folder/delete/', views.delete_folder_api, name='delete_folder_api'),
    path('api/folder/<int:folder_id>/toggle_open/', views.toggle_folder_open_api, name='toggle_folder_open_api'),
    path('api/chat/<int:chat_id>/move_to_folder/', views.move_chat_to_folder_api, name='move_chat_to_folder_api'),
    path('api/chat/<int:chat_id>/set_model/', views.set_chat_model_api, name='set_chat_model_api'),
    path('api/chat/<int:chat_id>/regenerate_title/', views.regenerate_chat_title_api, name='regenerate_chat_title_api'),
    path('api/chat/<int:chat_id>/clone/', views.clone_chat_api, name='clone_chat_api'),
    path('api/chat/<int:chat_id>/continue/', views.continue_chat_api, name='continue_chat_api'),
    path('api/chat/advanced_search/', views.advanced_search_api, name='advanced_search_api'),
    path('api/chat/<int:chat_id>/activate_message_path/<int:message_id>/', views.activate_message_path, name='activate_message_path'),
]
