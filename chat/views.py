from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_POST
import json

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

    last_active_chat_id = None
    if hasattr(request.user, 'settings') and request.user.settings.last_active_chat:
        last_active_chat_id = request.user.settings.last_active_chat.id
        
    return render(request, 'chat/index.html', {
        'folder_structure': organized_data,
        'last_active_chat_id': last_active_chat_id
    })

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
    
    # Update last_active_chat for the user
    user_settings, created = UserSettings.objects.get_or_create(user=request.user)
    user_settings.last_active_chat = chat
    user_settings.save(update_fields=['last_active_chat'])

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
    
    messages_data_for_response = []
    if chat.root_message_id:
        all_chat_messages = list(chat.messages.all().order_by('created_at'))

        message_nodes = {}
        # Initialize all nodes
        for msg in all_chat_messages:
            message_nodes[msg.id] = {
                'id': msg.id, # Include message ID
                'role': msg.role,
                'content': msg.message,
                'created_at': msg.created_at.isoformat() if msg.created_at else None,
                'children': []
            }

        # Build the tree structure
        # We will create a new dictionary for the actual tree to avoid modifying while iterating if issues arise
        # However, direct modification of message_nodes[parent_id]['children'] is usually fine.
        
        # Temporary dictionary to hold fully formed tree nodes
        # This helps ensure we are appending actual node dictionaries to children lists
        # and not just references that might get altered unexpectedly if we were rebuilding message_nodes.
        
        # We will build the tree directly within message_nodes.
        # The root_nodes list will store the actual root(s) of any trees.
        # In our case, we expect one primary root: chat.root_message.
        
        # Link children to their parents
        # Iterate through the original list of messages to ensure parent_id access
        for msg in all_chat_messages:
            if msg.parent_id:
                if msg.parent_id in message_nodes and msg.id in message_nodes:
                    parent_node = message_nodes[msg.parent_id]
                    child_node = message_nodes[msg.id]
                    parent_node['children'].append(child_node)
                    # Ensure children are sorted by creation time if not already guaranteed
                    # parent_node['children'].sort(key=lambda x: x['created_at']) # Usually not needed if all_chat_messages is sorted

        # The response should contain the root message of the chat, with all descendants nested.
        if chat.root_message_id in message_nodes:
            messages_data_for_response.append(message_nodes[chat.root_message_id])
    
    chat_data = {
        'id': chat.id,
        'title': chat.title,
        'ai_model_name': ai_model_name,
        'system_prompt': user_settings.system_prompt,
        'messages': messages_data_for_response, # Use the new tree structure
        'temperature': chat.ai_temperatue
    }
    return JsonResponse(chat_data)

@login_required
def add_message_to_chat(request, chat_id):
    if request.method == 'POST':
        try:
            import json
            data = json.loads(request.body)
            message_content = data.get('message_content')
            parent_message_id = data.get('parent_message_id')

            if not message_content:
                return JsonResponse({'error': 'Message content is required.'}, status=400)

            chat = get_object_or_404(Chat, pk=chat_id, user=request.user)
            
            parent_message = None
            if parent_message_id:
                try:
                    # Ensure parent_message belongs to the same chat and user
                    parent_message = get_object_or_404(Message, pk=parent_message_id, chat=chat)
                except Message.DoesNotExist:
                    return JsonResponse({'error': 'Parent message not found or does not belong to this chat.'}, status=404)
            else:
                # If no parent_message_id is provided, this implies the new message is a child of the chat's root_message
                # Or, if the chat has no messages yet, this could be the new root.
                # For this task, "add a new child message to the newest child Message" implies a parent_message_id should exist.
                # However, if the frontend logic for "newest child" might sometimes yield no ID (e.g. first user message after initial assistant message),
                # we might default to the chat's root_message if it exists and has no children yet, or handle as an error.
                # For now, strictly require parent_message_id based on the task.
                 return JsonResponse({'error': 'Parent message ID is required to add a child message.'}, status=400)


            new_message = Message.objects.create(
                chat=chat,
                message=message_content,
                role='user',  # Assuming 'user' for messages saved via this button
                parent=parent_message
            )
            
            # Optionally, prepare data for the new message to send back
            message_data = {
                'id': new_message.id,
                'role': new_message.role,
                'content': new_message.message,
                'created_at': new_message.created_at.isoformat() if new_message.created_at else None,
                'parent_id': parent_message.id if parent_message else None,
                'children': [] # New messages don't have children yet
            }
            return JsonResponse({'status': 'success', 'message': message_data}, status=201)

        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON.'}, status=400)
        except Exception as e:
            # Log the exception e for debugging
            return JsonResponse({'error': str(e)}, status=500)
    else:
        return JsonResponse({'error': 'Only POST requests are allowed.'}, status=405)

@login_required
@require_POST # Ensures this view only accepts POST requests
def update_message_role(request, chat_id, message_id):
    try:
        data = json.loads(request.body)
        new_role = data.get('new_role')

        if not new_role:
            return JsonResponse({'error': 'New role is required.'}, status=400)

        # Validate the role value if necessary (e.g., against a list of allowed roles)
        allowed_roles = ['user', 'assistant', 'system']
        if new_role.lower() not in allowed_roles:
            return JsonResponse({'error': f'Invalid role specified. Must be one of {", ".join(allowed_roles)}.'}, status=400)

        chat = get_object_or_404(Chat, pk=chat_id, user=request.user)
        message_to_update = get_object_or_404(Message, pk=message_id, chat=chat)

        message_to_update.role = new_role.lower() # Ensure role is stored in lowercase or as per model's expectation
        message_to_update.save(update_fields=['role'])

        return JsonResponse({'status': 'success', 'message': 'Role updated successfully.'})

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON.'}, status=400)
    except Chat.DoesNotExist:
        return JsonResponse({'error': 'Chat not found or you do not have permission to access it.'}, status=404)
    except Message.DoesNotExist:
        return JsonResponse({'error': 'Message not found in this chat.'}, status=404)
    except Exception as e:
        # Log the exception e for server-side debugging
        # logger.error(f"Error updating message role: {e}")
        return JsonResponse({'error': f'An unexpected error occurred: {str(e)}'}, status=500)
