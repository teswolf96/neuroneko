from django import forms
from .models import UserSettings, AIModel, AIEndpoint

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
        fields = ['default_model', 'theme', 'system_prompt', 'default_temp'] # Added default_temp
        widgets = {
            'system_prompt': forms.Textarea(attrs={'rows': 4, 'cols': 50}),
        }
        help_texts = {
            'default_model': 'Select your preferred default AI model for new chats.',
            'default_temp': 'Set your default temperature for AI responses (e.g., 0.7 for creative, 0.2 for factual).',
        }

class AIEndpointForm(forms.ModelForm):
    class Meta:
        model = AIEndpoint
        fields = ['name', 'url', 'apikey']
        widgets = {
            'apikey': forms.PasswordInput(render_value=False, attrs={'placeholder': 'Enter API Key'}),
        }
        help_texts = {
            'name': "A friendly name for this API configuration (e.g., 'My Personal OpenAI').",
            'url': "The base URL for the API provider (e.g., 'https://api.openai.com/v1').",
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
        fields = ['name', 'model_id', 'endpoint', 'default_temperature', 'default_max_tokens']
        help_texts = {
            'name': "A friendly display name for this model (e.g., 'GPT-4 Turbo').",
            'model_id': "The exact model ID used by the API provider (e.g., 'gpt-4-1106-preview').",
            'endpoint': "Select the API Endpoint this model uses.",
            'default_temperature': "Default temperature for this model (overrides user's general default). Leave blank to use user/endpoint default.",
            'default_max_tokens': "Default max tokens for this model. Leave blank to use user/endpoint default.",
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
