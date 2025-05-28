from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse

from .models import Chat, Folder, UserSettings, Message # Added Message
from .forms import UserSettingsForm

@login_required
def index(request):
    current_user = request.user
    
    organized_data = []

    # Get user's folders and their chats
    # Ensure the related_name 'chats_in_folder' matches your Chat model's ForeignKey to Folder
    user_folders = Folder.objects.filter(user=current_user).prefetch_related('chats_in_folder').order_by('name')
    
    for folder in user_folders:
        organized_data.append({
            'id': folder.id,
            'name': folder.name,
            'chats': list(folder.chats_in_folder.all().order_by('-created_at')) 
        })

    # Get chats not in any folder ("Other Chats") for the current user
    other_chats_list = list(Chat.objects.filter(user=current_user, folder__isnull=True).order_by('-created_at'))
    
    # Add "Other Chats" section, it will be present even if empty
    organized_data.append({
        'id': None, # Using None for ID to signify it's not a real folder
        'name': "Other Chats",
        'chats': other_chats_list
    })
        
    return render(request, 'chat/index.html', {'folder_structure': organized_data})

@login_required
def manage_user_settings(request):
    user_settings, created = UserSettings.objects.get_or_create(
        user=request.user,
        defaults={'system_prompt': "You are playing the role of a friendly and helpful chatbot."} # Ensure default is set if created
    )

    if request.method == 'POST':
        form = UserSettingsForm(request.POST, instance=user_settings)
        if form.is_valid():
            form.save()
            messages.success(request, 'Your settings have been updated successfully!')
            return redirect('user_settings') # Redirect to the same page
    else:
        form = UserSettingsForm(instance=user_settings)

    return render(request, 'chat/user_settings.html', {'form': form})

@login_required
def get_chat_details(request, chat_id):
    chat = get_object_or_404(Chat, pk=chat_id, user=request.user)
    # Ensure UserSettings exist, or create with defaults if necessary.
    # The signal handler in models.py should create UserSettings on User creation.
    # However, to be robust, especially if users existed before the signal:
    user_settings, created = UserSettings.objects.get_or_create(
        user=request.user,
        defaults={
            'system_prompt': "You are playing the role of a friendly and helpful chatbot.",
            # Add other defaults from UserSettings model if needed
        }
    )

    ai_model_name = "Default Model" # Fallback
    if chat.ai_model_used:
        ai_model_name = chat.ai_model_used.name
    elif user_settings.default_model:
        ai_model_name = user_settings.default_model.name
    
    messages_data = []
    for message in chat.messages.all().order_by('created_at'):
        messages_data.append({
            'role': message.role,
            'content': message.message,
            'created_at': message.created_at.isoformat() if message.created_at else None
        })

    chat_data = {
        'id': chat.id,
        'title': chat.title,
        'ai_model_name': ai_model_name,
        'system_prompt': user_settings.system_prompt,
        'messages': messages_data,
    }
    return JsonResponse(chat_data)
