from django.contrib import admin
from .models import UserSettings, AIEndpoint, AIModel, Folder, Chat, Message

class UserSettingsAdmin(admin.ModelAdmin):
    list_display = ('user', 'default_model', 'theme', 'system_prompt')
    search_fields = ('user__username', 'theme')
    list_filter = ('theme',)
    raw_id_fields = ('user', 'default_model') # Good for ForeignKey fields to avoid large dropdowns

    class Media:
        css = {
            'all': ('https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css',)
        }

admin.site.register(UserSettings, UserSettingsAdmin)


class AIEndpointAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'url')
    search_fields = ('name', 'user__username', 'url')
    list_filter = ('user',)
    raw_id_fields = ('user',)

    class Media:
        css = {
            'all': ('https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css',)
        }

admin.site.register(AIEndpoint, AIEndpointAdmin)


class AIModelAdmin(admin.ModelAdmin):
    list_display = ('name', 'model_id', 'endpoint')
    search_fields = ('name', 'model_id', 'endpoint__name')
    list_filter = ('endpoint',)
    raw_id_fields = ('endpoint',)

    class Media:
        css = {
            'all': ('https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css',)
        }

admin.site.register(AIModel, AIModelAdmin)


class FolderAdmin(admin.ModelAdmin):
    list_display = ('name', 'user')
    search_fields = ('name', 'user__username')
    list_filter = ('user',)
    raw_id_fields = ('user',)

    class Media:
        css = {
            'all': ('https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css',)
        }

admin.site.register(Folder, FolderAdmin)


class ChatAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'created_at', 'folder', 'root_message')
    search_fields = ('title', 'user__username', 'folder__name')
    list_filter = ('created_at', 'user', 'folder')
    date_hierarchy = 'created_at'
    raw_id_fields = ('user', 'folder', 'root_message')

    class Media:
        css = {
            'all': ('https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css',)
        }

admin.site.register(Chat, ChatAdmin)


class MessageAdmin(admin.ModelAdmin):
    list_display = ('chat_title', 'role', 'created_at', 'message_summary', 'parent_summary')
    search_fields = ('message', 'chat__title', 'role')
    list_filter = ('created_at', 'role', 'chat')
    date_hierarchy = 'created_at'
    raw_id_fields = ('chat', 'parent')

    def message_summary(self, obj):
        return (obj.message[:75] + '...') if len(obj.message) > 75 else obj.message
    message_summary.short_description = 'Message'

    def chat_title(self, obj):
        return obj.chat.title
    chat_title.short_description = 'Chat'
    chat_title.admin_order_field = 'chat__title'

    def parent_summary(self, obj):
        if obj.parent:
            return (obj.parent.message[:50] + '...') if len(obj.parent.message) > 50 else obj.parent.message
        return None
    parent_summary.short_description = 'Parent Message'


    class Media:
        css = {
            'all': ('https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css',)
        }

admin.site.register(Message, MessageAdmin)
