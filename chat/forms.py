from django import forms
from .models import UserSettings

class UserSettingsForm(forms.ModelForm):
    class Meta:
        model = UserSettings
        fields = ['default_model', 'theme', 'system_prompt']
        widgets = {
            'system_prompt': forms.Textarea(attrs={'rows': 4, 'cols': 50}),
        }
