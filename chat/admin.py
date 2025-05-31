from django.contrib import admin
from .models import UserSettings, AIEndpoint, AIModel, Folder, Chat, Message, SavedPrompt, Idea # Add SavedPrompt, Idea

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
    list_display = ('name', 'user', 'provider')
    search_fields = ('name', 'user__username', 'provider')
    list_filter = ('user', 'provider',)
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
    search_fields = ('title', 'user__username', 'folder__name')
    date_hierarchy = 'created_at'
    raw_id_fields = ('user', 'folder', 'root_message', 'ai_model_used') # Added ai_model_used
    list_display = ('title', 'user', 'created_at', 'folder', 'root_message', 'ai_model_used', 'ai_temperature') # Added ai_model_used and ai_temperature
    list_filter = ('created_at', 'user', 'folder', 'ai_model_used') # Added ai_model_used

    class MessageInline(admin.TabularInline):
        model = Message
        extra = 1
        raw_id_fields = ('parent', 'active_child')
        readonly_fields = ('created_at',)
        fields = ('role', 'message', 'parent', 'active_child', 'created_at')

    inlines = [MessageInline] # Added MessageInline

    class Media:
        css = {
            'all': ('https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css',)
        }

admin.site.register(Chat, ChatAdmin)


class MessageAdmin(admin.ModelAdmin):
    list_display = ('chat_title', 'role', 'created_at', 'message_summary', 'parent_summary')
    search_fields = ('message', 'chat__title', 'role')
    list_filter = ('created_at', 'role', 'chat__user') # Changed chat to chat__user for better filtering
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

class SavedPromptAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'created_at', 'updated_at')
    search_fields = ('name', 'user__username', 'prompt_text')
    list_filter = ('user', 'created_at', 'updated_at')
    raw_id_fields = ('user',)
    # class Media:
    #     css = {'all': ('https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css',)}
admin.site.register(SavedPrompt, SavedPromptAdmin)

class IdeaAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'created_at', 'updated_at')
    search_fields = ('name', 'user__username', 'idea_text')
    list_filter = ('user', 'created_at', 'updated_at')
    raw_id_fields = ('user',)
    # class Media:
    #     css = {'all': ('https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css',)}
admin.site.register(Idea, IdeaAdmin)
