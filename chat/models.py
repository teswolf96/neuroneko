from django.db import models
from django.contrib.auth.models import User # Import User
from django.db.models.signals import post_save
from django.dispatch import receiver

class UserSettings(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='settings') # This is a OneToOneField, usually created when user is created or on first access.

    TEXT_SIZE_CHOICES = [
        ('text-xs', 'X-Small'),
        ('text-sm', 'Small'),
        ('text-base', 'Medium'),
        ('text-lg', 'Large'),
        ('text-xl', 'X-Large'),
    ]
    chat_font_size = models.CharField(
        max_length=10,
        choices=TEXT_SIZE_CHOICES,
        default='text-base',
        help_text="User's preferred chat text size"
    )

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
    apikey = models.CharField(max_length=4096, help_text="API key for accessing this endpoint (user-specific)", null=True, blank=True)

    PROVIDER_CHOICES = [
        ('anthropic', 'Anthropic'),
        ('openai', 'OpenAI'),
        ('google', 'Google'),
        # ('custom', 'Custom API'), # For generic HTTP endpoints - can be added later
    ]
    provider = models.CharField(
        max_length=50,
        choices=PROVIDER_CHOICES,
        default='anthropic',
        help_text="The AI provider for this endpoint."
    )

    def __str__(self):
        return f"{self.name} ({self.user.username if self.user else 'System Default'}) - {self.get_provider_display()}"

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
    cache_creation_cost_per_million_tokens = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True, help_text="Cost for 1 million cache creation tokens (e.g., 0.20 for $0.20/1M tokens)")
    cache_read_cost_per_million_tokens = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True, help_text="Cost for 1 million cache read tokens (e.g., 0.10 for $0.10/1M tokens)")
    currency = models.CharField(max_length=3, default="USD", help_text="Currency of the cost (e.g., USD, EUR)")

    def __str__(self):
        return f"{self.name} ({self.endpoint.name if self.endpoint else 'No Endpoint'})"

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
    ai_temperature = models.FloatField('AI Temperature', default=1.0) # Corrected typo
    cache_until_message = models.ForeignKey(
        'Message',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+', # No reverse relation needed from Message to Chat for this specific field
        help_text="The message up to which the conversation is explicitly cached."
    )

    def __str__(self):
        return f"'{self.title}' by {self.user.username}"

class Message(models.Model):
    # No direct user link needed here as it's tied to Chat, which is tied to User.
    ROLE_CHOICES = [
        ('user', 'User'),
        ('assistant', 'Assistant'),
        ('system', 'System'),
    ]
    message = models.TextField(help_text="Content of the message")
    role = models.CharField(max_length=255, choices=ROLE_CHOICES, help_text="Role of the message sender (e.g., 'user', 'assistant')")
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
    input_tokens = models.IntegerField(null=True, blank=True, help_text="Tokens in the input to the model for this message generation.")
    output_tokens = models.IntegerField(null=True, blank=True, help_text="Tokens in the output from the model for this message generation.")
    cache_creation_input_tokens = models.IntegerField(null=True, blank=True, help_text="Input tokens used for cache creation (Anthropic specific).")
    cache_read_input_tokens = models.IntegerField(null=True, blank=True, help_text="Input tokens read from cache (Anthropic specific).")

    def save(self, *args, **kwargs):
        if self.active_child and self.active_child.parent != self:
            # Or self.active_child.parent_id != self.id if self.id is already set and self.active_child.parent_id is available
            raise ValueError("The active_child must be a direct child of this message.")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.role}: {self.message[:50]}... (Chat: {self.chat.title})"

    def get_cost_details(self):
        """
        Calculates the cost of this message based on its token counts and the AI model's rates.
        Returns a dictionary with cost breakdown or None if not applicable.
        """
        if not (self.input_tokens is not None or \
                self.output_tokens is not None or \
                self.cache_creation_input_tokens is not None or \
                self.cache_read_input_tokens is not None):
            return None

        ai_model = self.chat.ai_model_used
        if not ai_model:
            return None # Cannot calculate cost without model rates

        details = {
            'input_tokens': self.input_tokens or 0,
            'output_tokens': self.output_tokens or 0,
            'cache_creation_tokens': self.cache_creation_input_tokens or 0,
            'cache_read_tokens': self.cache_read_input_tokens or 0,
            'input_cost': 0.0,
            'output_cost': 0.0,
            'cache_creation_cost': 0.0,
            'cache_read_cost': 0.0,
            'total_cost': 0.0,
            'currency': ai_model.currency or "USD"
        }

        cost_calculated = False

        if ai_model.input_cost_per_million_tokens is not None and self.input_tokens:
            details['input_cost'] = (self.input_tokens / 1_000_000.0) * float(ai_model.input_cost_per_million_tokens)
            details['total_cost'] += details['input_cost']
            cost_calculated = True
        
        if ai_model.output_cost_per_million_tokens is not None and self.output_tokens:
            details['output_cost'] = (self.output_tokens / 1_000_000.0) * float(ai_model.output_cost_per_million_tokens)
            details['total_cost'] += details['output_cost']
            cost_calculated = True

        if ai_model.cache_creation_cost_per_million_tokens is not None and self.cache_creation_input_tokens:
            details['cache_creation_cost'] = (self.cache_creation_input_tokens / 1_000_000.0) * float(ai_model.cache_creation_cost_per_million_tokens)
            details['total_cost'] += details['cache_creation_cost']
            cost_calculated = True
        
        if ai_model.cache_read_cost_per_million_tokens is not None and self.cache_read_input_tokens:
            details['cache_read_cost'] = (self.cache_read_input_tokens / 1_000_000.0) * float(ai_model.cache_read_cost_per_million_tokens)
            details['total_cost'] += details['cache_read_cost']
            cost_calculated = True
            
        return details if cost_calculated else None

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
        # Create default Anthropic AI Endpoint (since 'anthropic' is the default provider)
        default_anthropic_endpoint = AIEndpoint.objects.create(
            user=instance,
            name="Default Anthropic",
            provider="anthropic"
            # apikey is left blank as per model definition (null=True, blank=True)
            # url field is removed
        )

        # Create default AI Model associated with the Anthropic endpoint
        # For Anthropic, a common model might be claude-3-haiku
        default_anthropic_model = AIModel.objects.create(
            endpoint=default_anthropic_endpoint,
            name="Claude 3 Haiku", # Example model name
            model_id="claude-3-haiku-20240307" # Example model ID
        )

        # Create UserSettings with the new default model
        UserSettings.objects.create(
            user=instance,
            default_model=default_anthropic_model
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
