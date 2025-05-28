from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponseBadRequest, Http404
from django.views.decorators.http import require_POST
from django.db import transaction # Added for atomic transactions
import json

from .models import Chat, Folder, UserSettings, Message, AIModel # Added Message and AIModel
from .forms import UserSettingsForm

@login_required
@require_POST
def set_active_child_view(request, chat_id):
    try:
        data = json.loads(request.body)
        parent_message_id = data.get('parent_message_id')
        child_to_activate_id = data.get('child_to_activate_id')

        if not parent_message_id or not child_to_activate_id:
            return JsonResponse({'error': 'Parent message ID and child to activate ID are required.'}, status=400)

        chat = get_object_or_404(Chat, pk=chat_id, user=request.user)
        parent_message = get_object_or_404(Message, pk=parent_message_id, chat=chat)
        child_to_activate = get_object_or_404(Message, pk=child_to_activate_id, chat=chat)

        if child_to_activate.parent != parent_message:
            return JsonResponse({'error': 'Specified child is not a direct child of the specified parent message.'}, status=400)

        parent_message.active_child = child_to_activate
        parent_message.save(update_fields=['active_child'])

        return JsonResponse({'status': 'success', 'message': 'Active child updated successfully.'})

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON.'}, status=400)
    except Chat.DoesNotExist:
        return JsonResponse({'error': 'Chat not found.'}, status=404)
    except Message.DoesNotExist:
        return JsonResponse({'error': 'Message not found.'}, status=404)
    except Exception as e:
        # Log e
        return JsonResponse({'error': str(e)}, status=500)

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
        # Fetch all messages for the chat, ordered by created_at, and include related parent
        all_chat_message_objects = list(chat.messages.select_related('parent', 'active_child').all().order_by('created_at'))
        
        # Store Message objects by ID for quick lookup
        all_messages_map = {msg.id: msg for msg in all_chat_message_objects}

        # This will store the serialized nodes for the tree
        serialized_nodes = {}

        for msg_obj in all_chat_message_objects:
            parent_obj = all_messages_map.get(msg_obj.parent_id) if msg_obj.parent_id else None
            
            node_data = {
                'id': msg_obj.id,
                'role': msg_obj.role,
                'content': msg_obj.message,
                'created_at': msg_obj.created_at.isoformat() if msg_obj.created_at else None,
                'parent_id': msg_obj.parent_id,
                'children': [],
                'active_child_id': msg_obj.active_child_id,
                'is_active_sibling': False,
                'previous_sibling_id': None,
                'next_sibling_id': None,
            }

            if parent_obj:
                # Determine if this message is the active child of its parent
                if parent_obj.active_child_id == msg_obj.id:
                    node_data['is_active_sibling'] = True
                elif not parent_obj.active_child_id:
                    # If no explicit active child, check if it's the only child
                    # Need to query children of parent_obj directly or filter all_messages_map
                    parent_children_ids = [m.id for m_id, m in all_messages_map.items() if m.parent_id == parent_obj.id]
                    if len(parent_children_ids) == 1 and parent_children_ids[0] == msg_obj.id:
                        node_data['is_active_sibling'] = True
                
                # Get siblings of current message, ordered by creation_at
                siblings_of_current_message = sorted(
                    [m for m_id, m in all_messages_map.items() if m.parent_id == parent_obj.id],
                    key=lambda m_item: m_item.created_at 
                )
                
                try:
                    current_index = [s.id for s in siblings_of_current_message].index(msg_obj.id)
                    if current_index > 0:
                        node_data['previous_sibling_id'] = siblings_of_current_message[current_index - 1].id
                    if current_index < len(siblings_of_current_message) - 1:
                        node_data['next_sibling_id'] = siblings_of_current_message[current_index + 1].id
                except ValueError:
                    # This can happen if a message's parent_id points to a message not in all_messages_map (e.g. deleted parent)
                    # Or if msg_obj itself is not found among its supposed siblings (data integrity issue)
                    pass # Log error if necessary

            serialized_nodes[msg_obj.id] = node_data

        # Build the tree structure from serialized_nodes
        for node_id, current_node_dict in serialized_nodes.items():
            parent_id = current_node_dict.get('parent_id')
            if parent_id and parent_id in serialized_nodes:
                parent_node_dict = serialized_nodes[parent_id]
                
                # Simple cycle check: if this node's ID is the parent_id of its designated parent_node_dict,
                # it forms a direct 2-cycle (e.g., A's parent is B, B's parent is A).
                # To break the cycle for JSON serialization, we avoid adding current_node_dict as a child in this case.
                if parent_node_dict.get('parent_id') == node_id:
                    # This check is for parent_node_dict's own parent_id.
                    # If parent_node_dict's parent is current_node_dict, then current_node_dict should not be a child of parent_node_dict.
                    print(f"Warning: Detected potential 2-cycle involving {node_id} and {parent_id}. "
                          f"Not linking {node_id} as child of {parent_id} if {parent_id}'s parent is {node_id}.")
                    continue # Skip appending this child to break the cycle

                parent_node_dict['children'].append(current_node_dict)
        
        # Sort children lists after all children have been appended
        for node_val_dict in serialized_nodes.values():
            if node_val_dict['children']: # Check if 'children' list is not empty
                node_val_dict['children'].sort(key=lambda x: x['created_at'])
        
        if chat.root_message_id in serialized_nodes:
            messages_data_for_response.append(serialized_nodes[chat.root_message_id])
            
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

            if parent_message:
                parent_message.active_child = new_message
                parent_message.save(update_fields=['active_child'])
            
            # Prepare data for the new message to send back, including sibling info
            new_message_data = {
                'id': new_message.id,
                'role': new_message.role,
                'content': new_message.message,
                'created_at': new_message.created_at.isoformat() if new_message.created_at else None,
                'parent_id': new_message.parent_id,
                'children': [], 
                'active_child_id': None, 
                'is_active_sibling': True, # A new message becomes the active sibling
                'previous_sibling_id': None,
                'next_sibling_id': None,
            }

            if parent_message:
                # Get siblings of new_message (children of parent_message)
                # Ensure new_message is included if the query is cached or doesn't see it yet
                # Re-fetch parent_message with children to be safe or add new_message to a local list
                siblings = list(parent_message.children.all().order_by('created_at'))
                try:
                    # Find new_message among its siblings
                    current_index = -1
                    for i, s in enumerate(siblings):
                        if s.id == new_message.id:
                            current_index = i
                            break
                    
                    if current_index != -1 and current_index > 0:
                        new_message_data['previous_sibling_id'] = siblings[current_index - 1].id
                    # A new message is typically the last, so no next_sibling_id among *previously existing* ones.
                    # If other messages could be added concurrently, this logic might need adjustment or rely on client re-fetch.
                except ValueError: 
                    pass # Should not happen if new_message is correctly parented

            return JsonResponse({'status': 'success', 'message': new_message_data}, status=201)

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

@login_required
@require_POST
@transaction.atomic
def delete_message_view(request, chat_id, message_id):
    try:
        chat = get_object_or_404(Chat, id=chat_id, user=request.user)
        message_to_delete = get_object_or_404(Message, id=message_id, chat=chat)
    except Http404:
        return JsonResponse({'status': 'error', 'error': 'Chat or Message not found or permission denied.'}, status=404)

    parent_message = message_to_delete.parent

    # If the deleted message has a parent and was its active child
    if parent_message and parent_message.active_child_id == message_to_delete.id:
        # Find other siblings to potentially set as new active child
        siblings = list(parent_message.children.exclude(id=message_to_delete.id).order_by('-created_at'))

        new_active_child = None
        if siblings:
            new_active_child = siblings[0] # Select the most recent remaining sibling

        parent_message.active_child = new_active_child
        parent_message.save(update_fields=['active_child'])

    # Recursively delete the message and all its children
    def _recursive_delete(message_node):
        children_to_delete = list(message_node.children.all()) # Materialize queryset before iterating
        for child in children_to_delete:
            _recursive_delete(child)
        message_node.delete()

    _recursive_delete(message_to_delete)

    return JsonResponse({'status': 'success', 'message': 'Message and its replies deleted successfully.'})

@login_required
@require_POST
@transaction.atomic
def add_sibling_view(request, chat_id, source_message_id):
    try:
        chat = get_object_or_404(Chat, pk=chat_id, user=request.user)
        source_message = get_object_or_404(Message, pk=source_message_id, chat=chat)

        # Create the new sibling message
        new_sibling_message = Message.objects.create(
            chat=chat,
            parent=source_message.parent, # Sibling shares the same parent
            role=source_message.role,     # Sibling shares the same role
            message="",                   # Blank content
            # created_at will be set automatically
        )

        # If the parent had the source_message as its active_child,
        # we might want to set the new sibling as the active_child,
        # or leave it to the user to navigate. For now, let's make the new sibling active.
        if source_message.parent:
            source_message.parent.active_child = new_sibling_message
            source_message.parent.save(update_fields=['active_child'])
        # If source_message has no parent (it's a root), then active_child logic
        # for the chat's root_message might need consideration, but typically
        # root messages don't have an 'active_child' in the same way.
        # The frontend re-fetch will handle displaying the new message.

        return JsonResponse({
            'status': 'success',
            'message': 'Sibling message added successfully.',
            'new_message_id': new_sibling_message.id
        }, status=201)

    except Chat.DoesNotExist:
        return JsonResponse({'error': 'Chat not found.'}, status=404)
    except Message.DoesNotExist:
        return JsonResponse({'error': 'Source message not found.'}, status=404)
    except Exception as e:
        # Log e for debugging
        return JsonResponse({'error': str(e)}, status=500)

@login_required
@require_POST # Ensures this view only accepts POST requests
def update_message_content(request, chat_id, message_id):
    try:
        data = json.loads(request.body)
        new_content = data.get('new_content')

        if new_content is None: # Check for None explicitly, as empty string might be valid
            return JsonResponse({'error': 'New content is required.'}, status=400)

        # Ensure the user owns the chat and the message belongs to that chat
        chat = get_object_or_404(Chat, pk=chat_id, user=request.user)
        message_to_update = get_object_or_404(Message, pk=message_id, chat=chat)

        message_to_update.message = new_content # 'message' is the field name in the Message model for content
        message_to_update.save(update_fields=['message'])

        return JsonResponse({'status': 'success', 'message': 'Message content updated successfully.'})

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON.'}, status=400)
    except Chat.DoesNotExist:
        return JsonResponse({'error': 'Chat not found or you do not have permission to access it.'}, status=404)
    except Message.DoesNotExist:
        return JsonResponse({'error': 'Message not found in this chat.'}, status=404)
    except Exception as e:
        # Log the exception e for server-side debugging
        # import logging
        # logger = logging.getLogger(__name__)
        # logger.error(f"Error updating message content: {e}")
        return JsonResponse({'error': f'An unexpected error occurred: {str(e)}'}, status=500)

@login_required # Ensure this view also requires login
def create_new_chat_view(request): # Renamed for clarity
    user = request.user
    
    # Get_or_create user settings to ensure they exist and to update last_active_chat later
    user_settings, created_settings = UserSettings.objects.get_or_create(
        user=user,
        defaults={ # Sensible defaults if UserSettings record is created now
            'system_prompt': "You are playing the role of a friendly and helpful chatbot.",
            'default_temp': 1.0,
            # 'default_model' will be None initially if created here, might need handling
        }
    )

    default_model = user_settings.default_model
    default_temp = user_settings.default_temp
    default_system_prompt = user_settings.system_prompt

    if not default_model:
        # The post_save signal on User creation in models.py should set a default_model.
        # If it can still be None (e.g., UserSettings existed before signal or manual deletion),
        # this is a configuration issue.
        messages.error(request, "Default AI model not configured. Please check your settings.")
        return redirect('user_settings') # Redirect to settings page

    # Determine folder for the new chat
    target_folder = None
    folder_name_from_query = request.GET.get('folder')
    if folder_name_from_query:
        # Try to find an existing folder or create a new one if it doesn't exist
        # This assumes folder names are unique per user.
        # If your Folder model doesn't enforce this, you might need to adjust.
        target_folder, created = Folder.objects.get_or_create(
            user=user, 
            name=folder_name_from_query
        )

    # Create the new Chat
    new_chat = Chat.objects.create(
        user=user,
        title="New Chat", # Consider a more dynamic title, e.g., "Chat - May 28, 4:17 PM"
        folder=target_folder, # Assign the folder
        ai_model_used=default_model,
        ai_temperatue=default_temp # Field name from model (ai_temperatue)
    )

    # Create the initial System Message
    system_message = Message.objects.create(
        chat=new_chat,
        message=default_system_prompt,
        role='system'
        # parent will be None for the first message
    )

    # Set the root message for the chat
    new_chat.root_message = system_message
    new_chat.save(update_fields=['root_message'])

    # Update the user's last active chat to this new one
    user_settings.last_active_chat = new_chat
    user_settings.save(update_fields=['last_active_chat'])

    # Redirect to the main index page. The JavaScript on that page
    # should pick up the last_active_chat_id and load it.
    return redirect('index') # 'index' is the name of the main chat view

@login_required
@require_POST
def rename_chat_title(request, chat_id):
    try:
        data = json.loads(request.body)
        new_title = data.get('new_title')

        if not new_title or not new_title.strip():
            return JsonResponse({'error': 'New title cannot be empty.'}, status=400)

        chat = get_object_or_404(Chat, pk=chat_id, user=request.user)
        
        chat.title = new_title.strip()
        chat.save(update_fields=['title'])

        return JsonResponse({'status': 'success', 'message': 'Chat title updated successfully.', 'new_title': chat.title})

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON.'}, status=400)
    except Chat.DoesNotExist:
        return JsonResponse({'error': 'Chat not found or permission denied.'}, status=404)
    except Exception as e:
        # Log e for server-side debugging
        # logger.error(f"Error renaming chat title: {e}")
        return JsonResponse({'error': f'An unexpected error occurred: {str(e)}'}, status=500)

@login_required
@require_POST
def delete_chat(request, chat_id):
    try:
        chat = get_object_or_404(Chat, id=chat_id, user=request.user)
        chat.delete()
        # If this was the last_active_chat, clear it from user settings
        if hasattr(request.user, 'settings') and request.user.settings.last_active_chat_id == chat_id: # Check against chat_id directly
            request.user.settings.last_active_chat = None
            request.user.settings.save(update_fields=['last_active_chat'])
        return JsonResponse({'status': 'success', 'message': 'Chat deleted successfully.'})
    except Http404:
        return JsonResponse({'status': 'error', 'message': 'Chat not found or permission denied.'}, status=404)
    except Exception as e:
        # Log e for server-side debugging
        # logger.error(f"Error deleting chat: {e}")
        return JsonResponse({'status': 'error', 'message': f'An unexpected error occurred: {str(e)}'}, status=500)

@login_required
@require_POST
@transaction.atomic
def rename_folder_api(request):
    try:
        data = json.loads(request.body)
        old_folder_name = data.get('old_folder_name')
        new_folder_name = data.get('new_folder_name')

        if not old_folder_name or not new_folder_name:
            return JsonResponse({'error': 'Old and new folder names are required.'}, status=400)
        
        if old_folder_name == new_folder_name:
            return JsonResponse({'status': 'success', 'message': 'Folder name is already up to date.'})

        user = request.user

        # Check if a folder with the new name already exists for this user
        if Folder.objects.filter(user=user, name=new_folder_name).exists():
            return JsonResponse({'error': f"A folder named '{new_folder_name}' already exists."}, status=400)

        # Find the folder to rename
        folder_to_rename = get_object_or_404(Folder, user=user, name=old_folder_name)
        
        folder_to_rename.name = new_folder_name
        folder_to_rename.save(update_fields=['name'])

        return JsonResponse({'status': 'success', 'message': f"Folder '{old_folder_name}' renamed to '{new_folder_name}'."})

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON.'}, status=400)
    except Folder.DoesNotExist:
        return JsonResponse({'error': f"Folder '{old_folder_name}' not found."}, status=404)
    except Exception as e:
        # Log e
        return JsonResponse({'error': f'An unexpected error occurred: {str(e)}'}, status=500)

@login_required
@require_POST
@transaction.atomic
def create_folder_api(request):
    try:
        data = json.loads(request.body)
        folder_name = data.get('folder_name', '').strip()

        if not folder_name:
            return JsonResponse({'error': 'Folder name cannot be empty.'}, status=400)

        user = request.user

        # Check if a folder with this name already exists for the user
        if Folder.objects.filter(user=user, name=folder_name).exists():
            return JsonResponse({'error': f"A folder named '{folder_name}' already exists."}, status=400)

        # Create the new folder
        Folder.objects.create(user=user, name=folder_name)

        return JsonResponse({'status': 'success', 'message': f"Folder '{folder_name}' created successfully."})

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON.'}, status=400)
    except Exception as e:
        # Log e for server-side debugging
        # logger.error(f"Error creating folder: {e}")
        return JsonResponse({'error': f'An unexpected error occurred: {str(e)}'}, status=500)

@login_required
@require_POST
@transaction.atomic
def delete_folder_api(request):
    try:
        data = json.loads(request.body)
        folder_name = data.get('folder_name')

        if not folder_name:
            return JsonResponse({'error': 'Folder name is required.'}, status=400)

        user = request.user
        folder_to_delete = get_object_or_404(Folder, user=user, name=folder_name)

        # Move chats from this folder to "Other Chats" (i.e., set their folder to None)
        Chat.objects.filter(user=user, folder=folder_to_delete).update(folder=None)
        
        # Delete the folder
        folder_to_delete.delete()

        return JsonResponse({'status': 'success', 'message': f"Folder '{folder_name}' deleted. Chats moved to 'Other Chats'."})

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON.'}, status=400)
    except Folder.DoesNotExist:
        return JsonResponse({'error': f"Folder '{folder_name}' not found."}, status=404)
    except Exception as e:
        # Log e
        return JsonResponse({'error': f'An unexpected error occurred: {str(e)}'}, status=500)
