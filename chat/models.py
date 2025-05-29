from django.db import models
from django.contrib.auth.models import User # Import User
from django.db.models.signals import post_save
from django.dispatch import receiver

class UserSettings(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='settings') # This is a OneToOneField, usually created when user is created or on first access.
    default_model = models.ForeignKey('AIModel', on_delete=models.SET_NULL, null=True, blank=True, help_text="User's preferred default AI model")
    theme = models.CharField(max_length=50, default='light', help_text="User's preferred UI theme (e.g., 'light', 'dark')")
    system_prompt = models.TextField(default="You are playing the role of a friendly and helpful chatbot.", help_text="Default system prompt for the user's interactions.")
    last_active_chat = models.ForeignKey('Chat', on_delete=models.SET_NULL, null=True, blank=True, related_name='+', help_text="The last chat session the user had open")
    default_temp = models.FloatField('Default Temp', default=1.0)
    # For more complex or numerous settings, a JSONField could be used:
    # preferences = models.JSONField(default=dict, help_text="User-specific preferences as a JSON object")
    # Add other user-specific settings here, e.g., items_per_page, notification_preferences

    def __str__(self):
        return f"{self.user.username}'s Settings"

class AIEndpoint(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ai_endpoints', help_text="The user who owns this AI endpoint configuration", null=True, blank=True)
    name = models.CharField(max_length=255, help_text="A custom name for the AI endpoint (e.g., 'My OpenAI GPT-4')")
    url = models.CharField(max_length=1024, help_text="The base URL of the AI endpoint")
    apikey = models.CharField(max_length=4096, help_text="API key for accessing this endpoint (user-specific)", null=True, blank=True) # Renamed from apitkey

    def __str__(self):
        return f"{self.name} ({self.user.username})"

class AIModel(models.Model):
    # No direct user link here, assuming models are primarily defined by their endpoint, which is user-owned.
    # If models can be user-customized beyond the endpoint, a ForeignKey to User could be added.
    name = models.CharField(max_length=255, help_text="A custom name for the AI model (e.g., 'Davinci Advanced')")
    model_id = models.CharField(max_length=255, help_text="The actual model identifier used by the API (e.g., 'gpt-4-turbo')")
    endpoint = models.ForeignKey(AIEndpoint, on_delete=models.CASCADE, related_name='models', help_text="The AI endpoint this model belongs to", null=True, blank=True)
    default_temperature = models.FloatField(null=True, blank=True, help_text="Default temperature for this model (e.g., 0.7)")
    default_max_tokens = models.IntegerField(null=True, blank=True, help_text="Default maximum tokens for this model (e.g., 2048)")
    input_cost_per_million_tokens = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True, help_text="Cost for 1 million input tokens (e.g., 1.50 for $1.50/1M tokens)")
    output_cost_per_million_tokens = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True, help_text="Cost for 1 million output tokens (e.g., 2.00 for $2.00/1M tokens)")
    currency = models.CharField(max_length=3, default="USD", help_text="Currency of the cost (e.g., USD, EUR)")

    def __str__(self):
        return f"{self.name} ({self.endpoint.name})"

class Folder(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='folders', help_text="The user who owns this folder", null=True, blank=True)
    name = models.CharField(max_length=255, help_text="Name of the folder")
    is_open = models.BooleanField(default=True, help_text="Indicates if the folder is open in the UI by default")

    def __str__(self):
        return f"{self.name} ({self.user.username})"

    class Meta:
        unique_together = ('user', 'name') # Ensures folder names are unique per user

class Chat(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='chats', help_text="The user who owns this chat", null=True, blank=True)
    title = models.CharField(max_length=255, help_text="Title of the chat session")
    created_at = models.DateTimeField(auto_now_add=True)
    folder = models.ForeignKey(Folder, on_delete=models.CASCADE, null=True, blank=True, related_name='chats_in_folder', help_text="Folder this chat belongs to (optional)") # Changed related_name, allow null/blank, CASCADE
    root_message = models.ForeignKey('Message', on_delete=models.SET_NULL, null=True, blank=True, related_name='+', help_text="The first message in this chat, acting as the root of the conversation tree")
    # Optional: Store the AI model used for this specific chat
    ai_model_used = models.ForeignKey(AIModel, on_delete=models.SET_NULL, null=True, blank=True, help_text="The AI model used for this chat session")
    ai_temperatue = models.FloatField('AI Temperature', default=1.0)

    def __str__(self):
        return f"'{self.title}' by {self.user.username}"

class Message(models.Model):
    # No direct user link needed here as it's tied to Chat, which is tied to User.
    message = models.TextField(help_text="Content of the message")
    role = models.CharField(max_length=255, help_text="Role of the message sender (e.g., 'user', 'assistant')")
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='children', help_text="Parent message in a threaded conversation (optional)")
    chat = models.ForeignKey('Chat', on_delete=models.CASCADE, related_name='messages', help_text="The chat session this message belongs to")
    created_at = models.DateTimeField(auto_now_add=True, null=True) # Added for sorting messages
    active_child = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
        help_text="The active child message, if this message has children and one is designated as active."
    )

    def save(self, *args, **kwargs):
        if self.active_child and self.active_child.parent != self:
            # Or self.active_child.parent_id != self.id if self.id is already set and self.active_child.parent_id is available
            raise ValueError("The active_child must be a direct child of this message.")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.role}: {self.message[:50]}... (Chat: {self.chat.title})"

    class Meta:
        ordering = ['created_at'] # Ensure messages are ordered by creation time by default

class SavedPrompt(models.Model): # Renamed from FavoritePrompt
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='saved_prompts', help_text="The user who saved this prompt") # Updated related_name
    name = models.CharField(max_length=255, help_text="A name for this saved prompt (e.g., 'Story Idea Generator')")
    prompt_text = models.TextField(help_text="The content of the saved prompt")
    created_at = models.DateTimeField(auto_now_add=True, help_text="When the prompt was first saved")
    updated_at = models.DateTimeField(auto_now=True, help_text="When the prompt was last updated")
    # Optional: We could add a category or tags later if needed for organization.

    def __str__(self):
        return f"'{self.name}' by {self.user.username} (Saved Prompt)" # Updated __str__ for clarity

    class Meta:
        ordering = ['-created_at'] # Show newest saved prompts first
        unique_together = ('user', 'name') # Ensure prompt names are unique per user
        verbose_name = "Saved Prompt"         # For singular name in Django admin
        verbose_name_plural = "Saved Prompts" # For plural name in Django admin


class Idea(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='saved_ideas', help_text="The user who saved this idea")
    name = models.CharField(max_length=255, help_text="A name for this saved idea (e.g., 'Blog Post Concept')")
    idea_text = models.TextField(help_text="The content of the saved idea") # Changed from prompt_text
    created_at = models.DateTimeField(auto_now_add=True, help_text="When the idea was first saved")
    updated_at = models.DateTimeField(auto_now=True, help_text="When the idea was last updated")

    def __str__(self):
        return f"'{self.name}' by {self.user.username} (Saved Idea)"

    class Meta:
        ordering = ['-created_at'] # Show newest saved ideas first
        unique_together = ('user', 'name') # Ensure idea names are unique per user
        verbose_name = "Saved Idea"
        verbose_name_plural = "Saved Ideas"

@receiver(post_save, sender=User)
def create_user_settings(sender, instance, created, **kwargs):
    """
    Signal handler to create UserSettings and default entities for a new user.
    """
    if created:
        # Create default AI Endpoint
        # AIEndpoint, AIModel, UserSettings, Chat, Message models are defined in this file.
        default_endpoint = AIEndpoint.objects.create(
            user=instance,
            name="Default OpenAI",
            url="https://api.openai.com/v1"
            # apikey is left blank as per model definition (null=True, blank=True)
        )

        # Create default AI Model associated with the endpoint
        default_model = AIModel.objects.create(
            endpoint=default_endpoint,
            name="GPT-3.5 Turbo",
            model_id="gpt-3.5-turbo"
        )

        # Create UserSettings with the new default model
        UserSettings.objects.create(
            user=instance,
            default_model=default_model
            # system_prompt and theme will use their model defaults
        )

        # Create default Chat
        default_chat = Chat.objects.create(
            user=instance,
            title="My First Chat"
        )

        # Create initial welcome message for the chat
        welcome_message = Message.objects.create(
            chat=default_chat,
            message="Welcome! How can I help you today?",
            role="assistant"
        )
        
        # Set the root message for the chat
        default_chat.root_message = welcome_message
        default_chat.save(update_fields=['root_message'])
