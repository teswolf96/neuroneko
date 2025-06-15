import json
import asyncio
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404 # For sync usage if needed, but prefer async alternatives

from .models import Chat, Message, AIModel, UserSettings
from .api_client import stream_completion
# Removed incorrect import of get_active_path_json from .views
from .utils import count_tokens # Updated import


# This is the old consumer, can be removed or kept if used elsewhere.
# For now, we assume it's not directly used by the new streaming logic.
class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_group_name = 'chat' # Generic group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'message': 'A user joined the chat!',
                'username': 'System'
            }
        )

    async def disconnect(self, close_code):
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'message': 'A user left the chat!',
                'username': 'System'
            }
        )
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message = text_data_json['message']
        username = text_data_json.get('username', 'Anonymous')
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'message': message,
                'username': username
            }
        )

    async def chat_message(self, event):
        message = event['message']
        username = event['username']
        await self.send(text_data=json.dumps({
            'message': message,
            'username': username
        }))


class StreamingChatConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.chat_id = None
        self.user = None
        self.room_group_name = None
        self.current_stream_task = None
        self.cancel_stream_flag = asyncio.Event()

    async def connect(self):
        self.user = self.scope.get("user")
        if not self.user or not self.user.is_authenticated:
            await self.close()
            return

        self.chat_id = self.scope['url_route']['kwargs']['chat_id']
        
        # Verify user has access to this chat
        try:
            chat_exists = await database_sync_to_async(Chat.objects.filter(id=self.chat_id, user=self.user).exists)()
            if not chat_exists:
                await self.close()
                return
        except Exception as e: # Handle potential errors like invalid UUID for chat_id
            print(f"Error verifying chat access: {e}")
            await self.close()
            return

        self.room_group_name = f"chat_stream_{self.chat_id}_{self.user.id}"
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()
        print(f"WebSocket connected for chat {self.chat_id}, user {self.user.id}, group {self.room_group_name}")

    async def disconnect(self, close_code):
        if self.current_stream_task:
            self.cancel_stream_flag.set() # Signal cancellation
            try:
                await asyncio.wait_for(self.current_stream_task, timeout=5.0) # Give it a moment to clean up
            except asyncio.TimeoutError:
                print(f"Stream task for chat {self.chat_id} did not finish cleanly on disconnect.")
            except Exception as e:
                print(f"Exception during stream task cleanup on disconnect: {e}")
            self.current_stream_task = None

        if self.room_group_name:
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )
        print(f"WebSocket disconnected for chat {self.chat_id}, user {self.user.id}")

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_type = data.get('type')

            if message_type == 'start_generation':
                if self.current_stream_task and not self.current_stream_task.done():
                    await self.send_error_to_client("A generation is already in progress.")
                    return
                self.cancel_stream_flag.clear() # Reset flag for new stream
                # Launch as a background task
                self.current_stream_task = asyncio.create_task(self.handle_start_generation(data))
            elif message_type == 'generate_reply_to_message':
                if self.current_stream_task and not self.current_stream_task.done():
                    await self.send_error_to_client("A generation is already in progress.")
                    return
                self.cancel_stream_flag.clear()
                self.current_stream_task = asyncio.create_task(self.handle_generate_reply_to_message(data))
            elif message_type == 'generate_into_empty_message':
                if self.current_stream_task and not self.current_stream_task.done():
                    await self.send_error_to_client("A generation is already in progress.")
                    return
                self.cancel_stream_flag.clear()
                self.current_stream_task = asyncio.create_task(self.handle_generate_into_empty_message(data))
            elif message_type == 'cancel_generation':
                if self.current_stream_task and not self.current_stream_task.done():
                    self.cancel_stream_flag.set()
                    await self.send_info_to_client("Cancellation request received.")
                else:
                    await self.send_info_to_client("No active generation to cancel.")
            elif message_type == 'estimate_cost':
                # Cost estimation can run even if a generation is in progress, as it's a lightweight operation.
                asyncio.create_task(self.handle_estimate_cost(data))
            else:
                await self.send_error_to_client(f"Unknown message type: {message_type}")
        except json.JSONDecodeError:
            await self.send_error_to_client("Invalid JSON received.")
        except Exception as e:
            print(f"Error in receive method: {e}")
            await self.send_error_to_client(f"An server error occurred: {str(e)}")

    async def handle_start_generation(self, data):
        try:
            user_message_content = data.get('user_message_content')
            # chat_id is self.chat_id
            model_id = data.get('model_id')
            # temperature = data.get('temperature', 0.7) # Get from model default or user settings
            # max_tokens = data.get('max_tokens', 1000) # Get from model default or user settings

            if not user_message_content or not model_id:
                await self.send_error_to_client("Missing user message content or model ID.")
                return

            # 1. Get Chat and AIModel instances
            chat = await database_sync_to_async(Chat.objects.select_related('user', 'ai_model_used__endpoint', 'root_message').get)(id=self.chat_id, user=self.user)
            ai_model_instance = await database_sync_to_async(AIModel.objects.select_related('endpoint').get)(id=model_id, endpoint__user=self.user)
            user_settings = await database_sync_to_async(UserSettings.objects.get)(user=self.user)
            
            temperature = chat.ai_temperature if chat.ai_temperature is not None else user_settings.default_temp
            max_tokens = ai_model_instance.default_max_tokens # Assuming this field exists, or use a global default

            # 2. Save User Message
            # Find the current last message in the active path to set as parent
            # This logic needs to be robust. For simplicity, let's assume we append to the latest active message.
            # A more robust way would be to get the full active path and find the leaf.
            
            # Simplified: Get the last message in the active path.
            # The `get_active_path_json` function from views.py returns a tree. We need to traverse it.
            # For now, let's assume a simpler parent finding logic or that the client sends parent_message_id.
            # For this iteration, we'll assume the client might send the ID of the message to reply to.
            # Or, we find the leaf of the active branch.
            
            # Let's adapt the logic from `add_message_to_chat_api` view
            # This requires getting the current leaf of the active branch.
            # The `get_chat_details_api` in views.py has `get_active_path_json`.
            # We need a way to get the ID of the last message in the active path.
            
            # For now, let's assume the client sends the ID of the message it's replying to,
            # or we find the absolute last message in the chat's active path.
            # Let's try to find the leaf of the active path.
            last_active_message = await self.get_last_active_message(chat)
            if not last_active_message: # Should not happen if chat has a root message
                await self.send_error_to_client("Cannot determine parent message for user input.")
                return

            user_msg_obj = await database_sync_to_async(Message.objects.create)(
                chat=chat,
                message=user_message_content,
                role='user',
                parent=last_active_message
            )
            await database_sync_to_async(self.set_as_active_child)(last_active_message, user_msg_obj)
            
            await self.send_to_client({
                'type': 'user_message_created',
                'message_id': user_msg_obj.id,
                'content': user_msg_obj.message,
                'role': user_msg_obj.role,
                'parent_id': last_active_message.id
                # Potentially send rendered HTML or more data for client to render
            })

            # 3. Create Blank Assistant Message
            assistant_msg_obj = await database_sync_to_async(Message.objects.create)(
                chat=chat,
                message="", # Blank content initially
                role='assistant',
                parent=user_msg_obj
            )
            await database_sync_to_async(self.set_as_active_child)(user_msg_obj, assistant_msg_obj)
            
            await self.send_to_client({
                'type': 'assistant_message_placeholder_created',
                'message_id': assistant_msg_obj.id,
                'role': assistant_msg_obj.role,
                'parent_id': user_msg_obj.id
            })

            # 4. Lock Sidebar (client-side action)
            await self.send_to_client({'type': 'lock_sidebar'})

            # 5. Prepare messages for API
            # This needs to reconstruct the conversation history in the format the API expects.
            api_messages = await self.get_formatted_message_history(chat, user_msg_obj)
            
            # System prompt is handled by the stream_completion function if it's part of messages
            # or passed as a kwarg. For Anthropic, it's extracted from messages or taken from kwargs.

            # 6. Start Streaming
            accumulated_content = ""
            current_input_tokens = None
            current_cache_creation_tokens = None
            current_cache_read_tokens = None
            current_output_tokens = None
            
            async def on_chunk(chunk_data): # chunk_data is now standardized
                nonlocal accumulated_content, current_input_tokens, current_cache_creation_tokens, current_cache_read_tokens, current_output_tokens
                if self.cancel_stream_flag.is_set():
                    await self.send_to_client({
                        'type': 'stream_cancelled',
                        'assistant_message_id': assistant_msg_obj.id,
                    })
                    assistant_msg_obj.message = accumulated_content
                    await database_sync_to_async(assistant_msg_obj.save)(update_fields=['message'])
                    await self.send_to_client({'type': 'unlock_sidebar'})
                    return False 

                chunk_type = chunk_data.get("type")
                
                if chunk_type == "error":
                    error_message = chunk_data.get("message", "Unknown API error during stream.")
                    assistant_msg_obj.message = f"Error: {error_message}" 
                    await database_sync_to_async(assistant_msg_obj.save)(update_fields=['message'])
                    await self.send_error_to_client(f"API Error: {error_message}", assistant_msg_obj.id)
                    await self.send_to_client({'type': 'unlock_sidebar'})
                    return False

                if chunk_type == "delta":
                    delta_text = chunk_data.get("text_delta", "")
                    if delta_text:
                        accumulated_content += delta_text
                        await self.send_to_client({
                            'type': 'stream_chunk',
                            'assistant_message_id': assistant_msg_obj.id,
                            'text_delta': delta_text
                        })
                elif chunk_type == "stop":
                    final_data = chunk_data.get("text_delta", "") # Anthropic might not send text_delta in message_delta
                    accumulated_content += final_data # Ensure any final text is appended

                    assistant_msg_obj.message = accumulated_content # Save full content

                    # Get usage from the stop chunk
                    usage_info = chunk_data.get("usage", {})
                    current_output_tokens = usage_info.get('output_tokens')

                    # Assign all collected token data
                    assistant_msg_obj.input_tokens = current_input_tokens
                    assistant_msg_obj.output_tokens = current_output_tokens
                    assistant_msg_obj.cache_creation_input_tokens = current_cache_creation_tokens
                    assistant_msg_obj.cache_read_input_tokens = current_cache_read_tokens

                    await database_sync_to_async(assistant_msg_obj.save)(
                        update_fields=[
                            'message',
                            'input_tokens',
                            'output_tokens',
                            'cache_creation_input_tokens',
                            'cache_read_input_tokens'
                        ]
                    )
                    
                    stop_reason = chunk_data.get("stop_reason")
                    
                    # Get cost details after saving the message and its tokens
                    cost_details = await database_sync_to_async(assistant_msg_obj.get_cost_details)()
                    
                    await self.send_to_client({
                        'type': 'stream_end',
                        'assistant_message_id': assistant_msg_obj.id,
                        'full_content': accumulated_content, # Send the final full content
                        'stop_reason': stop_reason,
                        'usage': { # Send all collected usage back to client
                            'input_tokens': current_input_tokens,
                            'output_tokens': current_output_tokens,
                            'cache_creation_input_tokens': current_cache_creation_tokens,
                            'cache_read_input_tokens': current_cache_read_tokens,
                        },
                        'cost_details': cost_details # Add cost_details here
                    })
                    await self.send_to_client({'type': 'unlock_sidebar'})
                    return False
                elif chunk_type == "metadata":
                    # Handle metadata if needed, e.g., message ID from provider
                    # For now, we primarily use our DB-generated IDs.
                    # print(f"Stream metadata received: {chunk_data.get('data')}")
                    data_payload = chunk_data.get('data', {})
                    current_input_tokens = data_payload.get('input_tokens')
                    current_cache_creation_tokens = data_payload.get('cache_creation_input_tokens')
                    current_cache_read_tokens = data_payload.get('cache_read_input_tokens')
                    pass

                return True

            # Call the API client's stream_completion with the AIModel instance
            await stream_completion(
                model=ai_model_instance, # Pass the AIModel instance
                messages=api_messages,
                on_chunk_callback=on_chunk,
                temperature=temperature,
                max_tokens=max_tokens
                # System prompt is handled within stream_completion based on messages or kwargs
            )

        except AIModel.DoesNotExist:
            await self.send_error_to_client("Selected AI Model not found or not accessible.")
        except Chat.DoesNotExist:
            await self.send_error_to_client("Chat session not found.")
        except UserSettings.DoesNotExist:
            await self.send_error_to_client("User settings not found.")
        except Exception as e:
            print(f"Error in handle_start_generation: {type(e).__name__} {e}")
            await self.send_error_to_client(f"Server error during generation: {str(e)}")
            # Ensure sidebar is unlocked if an error occurs before stream_completion or in its setup
            await self.send_to_client({'type': 'unlock_sidebar'})
        finally:
            # This task is finishing, clear it from the consumer instance
            if self.current_stream_task is asyncio.current_task(): # Check if it's this task
                 self.current_stream_task = None

    async def handle_generate_reply_to_message(self, data):
        try:
            parent_message_id = data.get('parent_message_id')
            model_id = data.get('model_id')

            if not parent_message_id or not model_id:
                await self.send_error_to_client("Missing parent message ID or model ID.")
                return

            chat = await database_sync_to_async(Chat.objects.select_related('user', 'ai_model_used__endpoint', 'root_message').get)(id=self.chat_id, user=self.user)
            ai_model_instance = await database_sync_to_async(AIModel.objects.select_related('endpoint').get)(id=model_id, endpoint__user=self.user)
            user_settings = await database_sync_to_async(UserSettings.objects.get)(user=self.user)
            
            temperature = chat.ai_temperature if chat.ai_temperature is not None else user_settings.default_temp
            max_tokens = ai_model_instance.default_max_tokens

            parent_message = await database_sync_to_async(Message.objects.get)(id=parent_message_id, chat=chat)

            # Create Blank Assistant Message
            assistant_msg_obj = await database_sync_to_async(Message.objects.create)(
                chat=chat,
                message="", 
                role='assistant',
                parent=parent_message
            )
            await database_sync_to_async(self.set_as_active_child)(parent_message, assistant_msg_obj)
            
            await self.send_to_client({
                'type': 'assistant_message_placeholder_created',
                'message_id': assistant_msg_obj.id,
                'role': assistant_msg_obj.role,
                'parent_id': parent_message.id
            })

            await self.send_to_client({'type': 'lock_sidebar'})

            api_messages = await self.get_formatted_message_history(chat, parent_message) # History up to the parent

            accumulated_content = ""
            current_input_tokens = None
            current_cache_creation_tokens = None
            current_cache_read_tokens = None
            current_output_tokens = None
            async def on_chunk(chunk_data): # chunk_data is now standardized
                nonlocal accumulated_content, current_input_tokens, current_cache_creation_tokens, current_cache_read_tokens, current_output_tokens
                if self.cancel_stream_flag.is_set():
                    assistant_msg_obj.message = accumulated_content
                    await database_sync_to_async(assistant_msg_obj.save)(update_fields=['message'])
                    await self.send_to_client({'type': 'stream_cancelled', 'assistant_message_id': assistant_msg_obj.id})
                    await self.send_to_client({'type': 'unlock_sidebar'})
                    return False

                chunk_type = chunk_data.get("type")
                if chunk_type == "error":
                    error_message = chunk_data.get("message", "Unknown API error during stream.")
                    assistant_msg_obj.message = f"Error: {error_message}"
                    await database_sync_to_async(assistant_msg_obj.save)(update_fields=['message'])
                    await self.send_error_to_client(f"API Error: {error_message}", assistant_msg_obj.id)
                    await self.send_to_client({'type': 'unlock_sidebar'})
                    return False

                if chunk_type == "delta":
                    delta_text = chunk_data.get("text_delta", "")
                    if delta_text:
                        accumulated_content += delta_text
                        await self.send_to_client({
                            'type': 'stream_chunk',
                            'assistant_message_id': assistant_msg_obj.id,
                            'text_delta': delta_text
                        })
                elif chunk_type == "stop":
                    final_data = chunk_data.get("text_delta", "") # Anthropic might not send text_delta in message_delta
                    accumulated_content += final_data # Ensure any final text is appended

                    assistant_msg_obj.message = accumulated_content # Save full content

                    # Get usage from the stop chunk
                    usage_info = chunk_data.get("usage", {})
                    current_output_tokens = usage_info.get('output_tokens')

                    # Assign all collected token data
                    assistant_msg_obj.input_tokens = current_input_tokens
                    assistant_msg_obj.output_tokens = current_output_tokens
                    assistant_msg_obj.cache_creation_input_tokens = current_cache_creation_tokens
                    assistant_msg_obj.cache_read_input_tokens = current_cache_read_tokens

                    await database_sync_to_async(assistant_msg_obj.save)(
                        update_fields=[
                            'message',
                            'input_tokens',
                            'output_tokens',
                            'cache_creation_input_tokens',
                            'cache_read_input_tokens'
                        ]
                    )
                    stop_reason = chunk_data.get("stop_reason")
                    
                    # Get cost details after saving the message and its tokens
                    cost_details = await database_sync_to_async(assistant_msg_obj.get_cost_details)()
                    
                    await self.send_to_client({
                        'type': 'stream_end',
                        'assistant_message_id': assistant_msg_obj.id,
                        'full_content': accumulated_content, # Send the final full content
                        'stop_reason': stop_reason,
                        'usage': { # Send all collected usage back to client
                            'input_tokens': current_input_tokens,
                            'output_tokens': current_output_tokens,
                            'cache_creation_input_tokens': current_cache_creation_tokens,
                            'cache_read_input_tokens': current_cache_read_tokens,
                        },
                        'cost_details': cost_details # Add cost_details here
                    })
                    await self.send_to_client({'type': 'unlock_sidebar'})
                    return False
                elif chunk_type == "metadata":
                    data_payload = chunk_data.get('data', {})
                    current_input_tokens = data_payload.get('input_tokens')
                    current_cache_creation_tokens = data_payload.get('cache_creation_input_tokens')
                    current_cache_read_tokens = data_payload.get('cache_read_input_tokens')
                    pass # Handle metadata if needed

                return True

            await stream_completion(
                model=ai_model_instance, # Pass the AIModel instance
                messages=api_messages,
                on_chunk_callback=on_chunk,
                temperature=temperature,
                max_tokens=max_tokens
            )

        except Message.DoesNotExist:
            await self.send_error_to_client("Parent message not found.")
        except AIModel.DoesNotExist:
            await self.send_error_to_client("Selected AI Model not found or not accessible.")
        except Chat.DoesNotExist:
            await self.send_error_to_client("Chat session not found.")
        except UserSettings.DoesNotExist:
            await self.send_error_to_client("User settings not found.")
        except Exception as e:
            print(f"Error in handle_generate_reply_to_message: {type(e).__name__} {e}")
            await self.send_error_to_client(f"Server error during generation: {str(e)}")
            await self.send_to_client({'type': 'unlock_sidebar'})
        finally:
            if self.current_stream_task is asyncio.current_task():
                 self.current_stream_task = None

    async def handle_generate_into_empty_message(self, data):
        try:
            target_message_id = data.get('target_message_id')
            model_id = data.get('model_id')

            if not target_message_id or not model_id:
                await self.send_error_to_client("Missing target message ID or model ID.")
                return

            chat = await database_sync_to_async(Chat.objects.select_related('user', 'ai_model_used__endpoint', 'root_message').get)(id=self.chat_id, user=self.user)
            ai_model_instance = await database_sync_to_async(AIModel.objects.select_related('endpoint').get)(id=model_id, endpoint__user=self.user)
            user_settings = await database_sync_to_async(UserSettings.objects.get)(user=self.user)

            temperature = chat.ai_temperature if chat.ai_temperature is not None else user_settings.default_temp
            max_tokens = ai_model_instance.default_max_tokens

            target_message = await database_sync_to_async(Message.objects.select_related('parent').get)(id=target_message_id, chat=chat)
            if target_message.message != "": # Ensure it's empty or handle as an error/overwrite
                # For now, we'll proceed, assuming it's meant to be overwritten if not empty.
                # Or, send an error: await self.send_error_to_client("Target message is not empty.") return
                pass
            
            if not target_message.parent:
                await self.send_error_to_client("Target message for generation cannot be a root message.")
                return

            await self.send_to_client({'type': 'lock_sidebar'})
            
            # History up to the parent of the target message
            api_messages = await self.get_formatted_message_history(chat, target_message.parent) 

            accumulated_content = ""
            current_input_tokens = None
            current_cache_creation_tokens = None
            current_cache_read_tokens = None
            current_output_tokens = None
            async def on_chunk(chunk_data): # chunk_data is now standardized
                nonlocal accumulated_content, current_input_tokens, current_cache_creation_tokens, current_cache_read_tokens, current_output_tokens
                if self.cancel_stream_flag.is_set():
                    target_message.message = accumulated_content
                    await database_sync_to_async(target_message.save)(update_fields=['message'])
                    await self.send_to_client({'type': 'stream_cancelled', 'assistant_message_id': target_message.id})
                    await self.send_to_client({'type': 'unlock_sidebar'})
                    return False

                chunk_type = chunk_data.get("type")
                if chunk_type == "error":
                    error_message = chunk_data.get("message", "Unknown API error during stream.")
                    target_message.message = f"Error: {error_message}"
                    await database_sync_to_async(target_message.save)(update_fields=['message'])
                    await self.send_error_to_client(f"API Error: {error_message}", target_message.id)
                    await self.send_to_client({'type': 'unlock_sidebar'})
                    return False

                if chunk_type == "delta":
                    delta_text = chunk_data.get("text_delta", "")
                    if delta_text:
                        accumulated_content += delta_text
                        await self.send_to_client({
                            'type': 'stream_chunk',
                            'assistant_message_id': target_message.id, 
                            'text_delta': delta_text
                        })
                elif chunk_type == "stop":
                    final_data = chunk_data.get("text_delta", "") # Anthropic might not send text_delta in message_delta
                    accumulated_content += final_data # Ensure any final text is appended

                    target_message.message = accumulated_content # Save full content

                    # Get usage from the stop chunk
                    usage_info = chunk_data.get("usage", {})
                    current_output_tokens = usage_info.get('output_tokens')

                    # Assign all collected token data
                    target_message.input_tokens = current_input_tokens
                    target_message.output_tokens = current_output_tokens
                    target_message.cache_creation_input_tokens = current_cache_creation_tokens
                    target_message.cache_read_input_tokens = current_cache_read_tokens

                    await database_sync_to_async(target_message.save)(
                        update_fields=[
                            'message',
                            'input_tokens',
                            'output_tokens',
                            'cache_creation_input_tokens',
                            'cache_read_input_tokens'
                        ]
                    )
                    stop_reason = chunk_data.get("stop_reason")
                    
                    # Get cost details after saving the message and its tokens
                    cost_details = await database_sync_to_async(target_message.get_cost_details)()
                    
                    await self.send_to_client({
                        'type': 'stream_end',
                        'assistant_message_id': target_message.id,
                        'full_content': accumulated_content, # Send the final full content
                        'stop_reason': stop_reason,
                        'usage': { # Send all collected usage back to client
                            'input_tokens': current_input_tokens,
                            'output_tokens': current_output_tokens,
                            'cache_creation_input_tokens': current_cache_creation_tokens,
                            'cache_read_input_tokens': current_cache_read_tokens,
                        },
                        'cost_details': cost_details # Add cost_details here
                    })
                    await self.send_to_client({'type': 'unlock_sidebar'})
                    return False
                elif chunk_type == "metadata":
                    data_payload = chunk_data.get('data', {})
                    current_input_tokens = data_payload.get('input_tokens')
                    current_cache_creation_tokens = data_payload.get('cache_creation_input_tokens')
                    current_cache_read_tokens = data_payload.get('cache_read_input_tokens')
                    pass # Handle metadata if needed
                return True

            await stream_completion(
                model=ai_model_instance, # Pass the AIModel instance
                messages=api_messages,
                on_chunk_callback=on_chunk,
                temperature=temperature,
                max_tokens=max_tokens
            )

        except Message.DoesNotExist:
            await self.send_error_to_client("Target message or its parent not found.")
        except AIModel.DoesNotExist:
            await self.send_error_to_client("Selected AI Model not found or not accessible.")
        except Chat.DoesNotExist:
            await self.send_error_to_client("Chat session not found.")
        except UserSettings.DoesNotExist:
            await self.send_error_to_client("User settings not found.")
        except Exception as e:
            print(f"Error in handle_generate_into_empty_message: {type(e).__name__} {e}")
            await self.send_error_to_client(f"Server error during generation: {str(e)}")
            await self.send_to_client({'type': 'unlock_sidebar'})
        finally:
            if self.current_stream_task is asyncio.current_task():
                 self.current_stream_task = None

    @database_sync_to_async
    def get_last_active_message(self, chat_obj: Chat) -> Message | None:
        current_message = chat_obj.root_message
        if not current_message:
            return None
        while current_message.active_child:
            current_message = current_message.active_child
        return current_message

    def set_as_active_child(self, parent_msg_obj: Message, child_msg_obj: Message):
        # This needs to be a sync method called by database_sync_to_async
        parent_msg_obj.active_child = child_msg_obj
        parent_msg_obj.save(update_fields=['active_child'])

    @database_sync_to_async
    def get_formatted_message_history(self, chat_obj: Chat, last_message_in_history: Message):
        # Traverse from root_message up to last_message_in_history along the active path
        # and format for the API, applying cache_control if needed.
        history = []
        
        # Get the ID of the message that should have the cache_control tag from the Chat model
        target_cache_db_message_id = chat_obj.cache_until_message_id
        
        # Collect messages along the active path up to last_message_in_history
        path_messages = []
        current_msg_in_path = chat_obj.root_message
        if not current_msg_in_path: # Handle chats with no root message (should ideally not happen)
            return []

        while current_msg_in_path:
            path_messages.append(current_msg_in_path)
            if current_msg_in_path.id == last_message_in_history.id:
                break
            current_msg_in_path = current_msg_in_path.active_child
            if not current_msg_in_path: # Path ended before reaching last_message_in_history
                # This means last_message_in_history might not be on the active path from root,
                # or the path is shorter than expected.
                # We will proceed with the path collected. If last_message_in_history was not found,
                # the subsequent check will handle it.
                break
        
        # Ensure the collected path_messages ends at last_message_in_history if it was found.
        # If last_message_in_history was not found in the traversed path, this indicates a potential logic issue
        # or inconsistent state, as last_message_in_history should be part of the active conversation thread.
        if not path_messages or path_messages[-1].id != last_message_in_history.id:
            # Attempt to find last_message_in_history in the collected path and truncate if necessary.
            # This handles cases where last_message_in_history is an earlier message in the active path.
            try:
                idx = next(i for i, msg_iter in enumerate(path_messages) if msg_iter.id == last_message_in_history.id)
                path_messages = path_messages[:idx+1]
            except StopIteration:
                # last_message_in_history was not found in the active path from root_message.
                print(f"Error: last_message_in_history (ID: {last_message_in_history.id}) not found in the active path for chat (ID: {chat_obj.id}).")
                return [] # Return empty list or raise an error, as history cannot be correctly constructed.

        for msg_in_path in path_messages:
            content_text = msg_in_path.message
            
            # Create the basic content block structure required by Anthropic API
            content_block = {"type": "text", "text": content_text}
            
            # Add cache_control if this message is the one designated in the Chat model
            if target_cache_db_message_id and msg_in_path.id == target_cache_db_message_id:
                content_block["cache_control"] = {"type": "ephemeral"}
            
            history.append({
                "role": msg_in_path.role,
                "content": [content_block] # Content must be an array of blocks
            })
        
        # System prompt considerations:
        # The api_client.py's stream_completion (and _get_static_completion_anthropic_internal)
        # extracts a "system" role message from the 'messages' list and places its content
        # into a top-level 'system' parameter for the Anthropic API.
        # If a system message from the DB (e.g., root_message.role == 'system') is formatted by this loop,
        # its 'content' will be `[{"type": "text", "text": "...", "cache_control": ...}]` if it's the cache point.
        # The api_client will then correctly pass this structured content to the 'system' API parameter.
        return history


    async def send_to_client(self, data_dict):
        await self.send(text_data=json.dumps(data_dict))

    async def send_error_to_client(self, error_message, assistant_message_id=None):
        payload = {'type': 'stream_error', 'error': error_message}
        if assistant_message_id:
            payload['assistant_message_id'] = assistant_message_id
        await self.send_to_client(payload)

    async def send_info_to_client(self, info_message):
        await self.send_to_client({'type': 'info', 'message': info_message})

    # Handle messages sent to this group (e.g., if broadcasting was needed, but not for this consumer)
    # async def chat_stream_message(self, event):
    #     await self.send(text_data=json.dumps(event))

    async def handle_estimate_cost(self, data):
        try:
            current_input_content = data.get('current_input_content', "") # Default to empty string if not provided
            model_id = data.get('model_id')

            if not model_id:
                await self.send_error_to_client("Model ID is required for cost estimation.")
                return

            chat = await database_sync_to_async(Chat.objects.select_related('user', 'ai_model_used__endpoint', 'root_message').get)(id=self.chat_id, user=self.user)
            ai_model_instance = await database_sync_to_async(AIModel.objects.select_related('endpoint').get)(id=model_id, endpoint__user=self.user)
            user_settings = await database_sync_to_async(UserSettings.objects.get)(user=self.user)

            # Get message history up to the last saved message
            last_saved_message_in_thread = await self.get_last_active_message(chat)
            
            history_messages = []
            if last_saved_message_in_thread:
                 history_messages = await self.get_formatted_message_history(chat, last_saved_message_in_thread)
            else: # No messages in chat yet, or root_message is null (edge case)
                 history_messages = []


            # Append the user's current (unsubmitted) input to the history
            # If current_input_content is empty, this effectively counts the current thread + system prompt
            current_full_conversation = history_messages + [{"role": "user", "content": current_input_content}]
            
            # Extract system prompt and prepare final messages list for counter (mirroring api_client.py)
            system_prompt_in_list = next((msg for msg in current_full_conversation if msg.get("role") == "system"), None)
            
            final_system_prompt_str = None
            messages_for_counter = []

            if system_prompt_in_list:
                final_system_prompt_str = system_prompt_in_list["content"]
                messages_for_counter = [msg for msg in current_full_conversation if msg.get("role") != "system"]
            else:
                # Use UserSettings.system_prompt (or chat-specific if that feature is added later)
                final_system_prompt_str = user_settings.system_prompt 
                messages_for_counter = current_full_conversation
            
            # Ensure messages_for_counter doesn't have any system messages if final_system_prompt_str is set
            if final_system_prompt_str:
                 messages_for_counter = [m for m in messages_for_counter if m.get("role") != "system"]

            messages_for_counter = [m for m in messages_for_counter if m.get("content") != ""]

            if messages_for_counter != []:
                # Use the new generic count_tokens function
                token_count = await database_sync_to_async(count_tokens)( # Updated call
                    model=ai_model_instance, # Pass the AIModel instance
                    messages_for_api=messages_for_counter,
                    system_prompt_for_api=final_system_prompt_str
                )
            else:
                token_count = 0

            estimated_cost_val = None
            if ai_model_instance.input_cost_per_million_tokens is not None:
                estimated_cost_val = (token_count / 1_000_000.0) * float(ai_model_instance.input_cost_per_million_tokens)
            
            cost_display_str = f"{estimated_cost_val:.6f}" if estimated_cost_val is not None else "N/A"

            await self.send_to_client({
                'type': 'cost_estimation_result',
                'token_count': token_count,
                'estimated_cost': cost_display_str,
                'currency': "USD" # As per user confirmation
            })

        except AIModel.DoesNotExist:
            await self.send_error_to_client("Selected AI Model not found for cost estimation.")
        except Chat.DoesNotExist:
            await self.send_error_to_client("Chat session not found for cost estimation.")
        except UserSettings.DoesNotExist:
            await self.send_error_to_client("User settings not found for cost estimation.")
        except Exception as e:
            print(f"Error in handle_estimate_cost: {type(e).__name__} {e}")
            await self.send_error_to_client(f"Server error during cost estimation: {str(e)}")
