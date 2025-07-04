from django import forms
from .models import UserSettings, AIModel, AIEndpoint, SavedPrompt, Idea # Added Idea

class UserSettingsForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user:
            user_endpoints = AIEndpoint.objects.filter(user=user)
            self.fields['default_model'].queryset = AIModel.objects.filter(endpoint__in=user_endpoints)
            if not self.fields['default_model'].queryset.exists():
                self.fields['default_model'].empty_label = "No models available (configure API endpoints and models first)"
            else:
                self.fields['default_model'].empty_label = "Select a default model"
        else:
            # Handle case where user is not provided, e.g. for admin or initial setup
            self.fields['default_model'].queryset = AIModel.objects.none()
            self.fields['default_model'].empty_label = "User context required to list models"


    class Meta:
        model = UserSettings
        fields = ['default_model', 'system_prompt', 'default_temp', 'chat_font_size'] # Added chat_font_size
        widgets = {
            'system_prompt': forms.Textarea(attrs={'rows': 4, 'cols': 50}),
        }
        help_texts = {
            'default_model': 'Select your preferred default AI model for new chats.',
            'default_temp': 'Set your default temperature for AI responses (e.g., 0.7 for creative, 0.2 for factual).',
            'chat_font_size': 'Select your preferred text size for chat messages.',
        }

class AIEndpointForm(forms.ModelForm):
    class Meta:
        model = AIEndpoint
        fields = ['name', 'provider', 'apikey'] # Removed 'url', added 'provider'
        widgets = {
            'name': forms.TextInput(attrs={'class': 'mt-1 block w-full bg-gray-700 border border-gray-600 rounded-md shadow-sm py-2 px-3 text-white focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm'}),
            'provider': forms.Select(attrs={'class': 'mt-1 block w-full bg-gray-700 border border-gray-600 rounded-md shadow-sm py-2 px-3 text-white focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm'}),
            'apikey': forms.PasswordInput(render_value=False, attrs={'placeholder': 'Enter API Key', 'class': 'mt-1 block w-full bg-gray-700 border border-gray-600 rounded-md shadow-sm py-2 px-3 text-white focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm'}),
        }
        help_texts = {
            'name': "A friendly name for this API configuration (e.g., 'My Personal OpenAI').",
            'provider': "Select the AI provider for this endpoint.",
            'apikey': "Your API key for this provider. Will be stored securely.",
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.apikey:
             self.fields['apikey'].widget.attrs['placeholder'] = 'API Key is set (leave blank to keep unchanged)'
             self.fields['apikey'].required = False # Not required if already set and editing


    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.user:
            instance.user = self.user
        
        # Handle API key: only update if a new value is provided
        new_apikey = self.cleaned_data.get('apikey')
        if not new_apikey and self.instance and self.instance.pk:
            # If editing and apikey field is blank, keep the old one
            instance.apikey = self.instance.apikey
        elif new_apikey:
            # If a new apikey is provided (either creating or explicitly changing)
            instance.apikey = new_apikey
            
        if commit:
            instance.save()
        return instance

class AIModelForm(forms.ModelForm):
    class Meta:
        model = AIModel
        fields = [
            'name', 'model_id', 'endpoint', 
            'default_temperature', 'default_max_tokens', 
            'input_cost_per_million_tokens', 'output_cost_per_million_tokens', 
            'cache_creation_cost_per_million_tokens', 'cache_read_cost_per_million_tokens',
            'currency'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'mt-1 block w-full bg-gray-700 border border-gray-600 rounded-md shadow-sm py-2 px-3 text-white focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm'}),
            'model_id': forms.TextInput(attrs={'class': 'mt-1 block w-full bg-gray-700 border border-gray-600 rounded-md shadow-sm py-2 px-3 text-white focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm'}),
            'endpoint': forms.Select(attrs={'class': 'mt-1 block w-full bg-gray-700 border border-gray-600 rounded-md shadow-sm py-2 px-3 text-white focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm'}),
            'default_temperature': forms.NumberInput(attrs={'class': 'mt-1 block w-full bg-gray-700 border border-gray-600 rounded-md shadow-sm py-2 px-3 text-white focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm'}),
            'default_max_tokens': forms.NumberInput(attrs={'class': 'mt-1 block w-full bg-gray-700 border border-gray-600 rounded-md shadow-sm py-2 px-3 text-white focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm'}),
            'input_cost_per_million_tokens': forms.NumberInput(attrs={'class': 'mt-1 block w-full bg-gray-700 border border-gray-600 rounded-md shadow-sm py-2 px-3 text-white focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm'}),
            'output_cost_per_million_tokens': forms.NumberInput(attrs={'class': 'mt-1 block w-full bg-gray-700 border border-gray-600 rounded-md shadow-sm py-2 px-3 text-white focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm'}),
            'cache_creation_cost_per_million_tokens': forms.NumberInput(attrs={'class': 'mt-1 block w-full bg-gray-700 border border-gray-600 rounded-md shadow-sm py-2 px-3 text-white focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm'}),
            'cache_read_cost_per_million_tokens': forms.NumberInput(attrs={'class': 'mt-1 block w-full bg-gray-700 border border-gray-600 rounded-md shadow-sm py-2 px-3 text-white focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm'}),
            'currency': forms.TextInput(attrs={'class': 'mt-1 block w-full bg-gray-700 border border-gray-600 rounded-md shadow-sm py-2 px-3 text-white focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm'}),
        }
        help_texts = {
            'name': "A friendly display name for this model (e.g., 'GPT-4 Turbo').",
            'model_id': "The exact model ID used by the API provider (e.g., 'gpt-4-1106-preview').",
            'endpoint': "Select the API Endpoint this model uses.",
            'default_temperature': "Default temperature for this model (overrides user's general default). Leave blank to use user/endpoint default.",
            'default_max_tokens': "Default max tokens for this model. Leave blank to use user/endpoint default.",
            'input_cost_per_million_tokens': "Cost for 1 million input tokens (e.g., 0.50 for $0.50/1M tokens).",
            'output_cost_per_million_tokens': "Cost for 1 million output tokens (e.g., 1.50 for $1.50/1M tokens).",
            'cache_creation_cost_per_million_tokens': "Cost for 1 million cache creation tokens. Leave blank if not applicable.",
            'cache_read_cost_per_million_tokens': "Cost for 1 million cache read tokens. Leave blank if not applicable.",
            'currency': "Currency code for the cost (e.g., USD, EUR).",
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user:
            self.fields['endpoint'].queryset = AIEndpoint.objects.filter(user=user)
            if not self.fields['endpoint'].queryset.exists():
                 self.fields['endpoint'].empty_label = "No API Endpoints configured"
                 self.fields['endpoint'].widget = forms.HiddenInput() # Or disable, or show message
            else:
                self.fields['endpoint'].empty_label = "Select an API Endpoint"
        else:
            self.fields['endpoint'].queryset = AIEndpoint.objects.none()
            self.fields['endpoint'].empty_label = "User context required"

class SavedPromptForm(forms.ModelForm):
    class Meta:
        model = SavedPrompt
        fields = ['name', 'prompt_text']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'mt-1 block w-full bg-gray-700 border border-gray-600 rounded-md shadow-sm py-2 px-3 text-white focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm',
                'placeholder': 'Enter a name for your prompt'
            }),
            'prompt_text': forms.Textarea(attrs={
                'rows': 5,
                'class': 'mt-1 block w-full bg-gray-700 border border-gray-600 rounded-md shadow-sm py-2 px-3 text-white focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm',
                'placeholder': 'Enter the prompt text'
            }),
        }
        help_texts = {
            'name': "A short, descriptive name for your prompt.",
            'prompt_text': "The actual text of the prompt you want to save.",
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None) # Store user if passed
        super().__init__(*args, **kwargs)

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.user:
            instance.user = self.user # Assign user before saving
        if commit:
            instance.save()
        return instance

class IdeaForm(forms.ModelForm):
    class Meta:
        model = Idea
        fields = ['name', 'idea_text']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'mt-1 block w-full bg-gray-700 border border-gray-600 rounded-md shadow-sm py-2 px-3 text-white focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm',
                'placeholder': 'Enter a name for your idea'
            }),
            'idea_text': forms.Textarea(attrs={
                'rows': 5,
                'class': 'mt-1 block w-full bg-gray-700 border border-gray-600 rounded-md shadow-sm py-2 px-3 text-white focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm',
                'placeholder': 'Enter the idea text'
            }),
        }
        help_texts = {
            'name': "A short, descriptive name for your idea.",
            'idea_text': "The actual text of the idea you want to save.",
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None) # Store user if passed
        super().__init__(*args, **kwargs)

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.user:
            instance.user = self.user # Assign user before saving
        if commit:
            instance.save()
        return instance
