# chat/api_client.py
import anthropic
from anthropic import AsyncAnthropic
import json
from typing import Callable, Awaitable, Dict, Any, List
import httpx
http_client_without_ssl_verification = httpx.Client(verify=False)
http_async_client_without_ssl_verification = httpx.AsyncClient(verify=False)


# Define a type for the message structure, common in chat APIs
ChatMessage = Dict[str, str]  # e.g., {"role": "user", "content": "Hello"}

def test_anthropic_endpoint(api_key: str, base_url: str) -> Dict[str, Any]:
    """
    Synchronously tests an Anthropic API endpoint by making a minimal call.
    Args:
        api_key: The API key.
        base_url: The base URL for the Anthropic API.
    Returns:
        A dictionary with 'status', 'message', and 'details'.
    """
    try:
        client = anthropic.Anthropic(api_key=api_key, http_client=http_client_without_ssl_verification)
        response = client.models.list(limit=20)
        return {
            "status": "success",
            "message": "Endpoint test successful!"
        }
    except anthropic.AuthenticationError as e:
        return {"status": "error", "message": "Authentication failed. Check API key.", "details": {"error_type": type(e).__name__, "error_message": str(e), "status_code": e.status_code if hasattr(e, 'status_code') else None}}
    except anthropic.APIConnectionError as e:
        return {"status": "error", "message": "Connection error. Check API URL or network.", "details": {"error_type": type(e).__name__, "error_message": str(e)}}
    except anthropic.RateLimitError as e:
        return {"status": "error", "message": "Rate limit exceeded.", "details": {"error_type": type(e).__name__, "error_message": str(e), "status_code": e.status_code if hasattr(e, 'status_code') else None}}
    except anthropic.APIStatusError as e: # Catch other API status errors (4xx, 5xx)
        return {"status": "error", "message": f"API error (status {e.status_code}).", "details": {"error_type": type(e).__name__, "error_message": str(e.response.text if e.response else e), "status_code": e.status_code}}
    except anthropic.APIError as e: # Catch-all for other Anthropic SDK errors
        return {"status": "error", "message": "An Anthropic API error occurred.", "details": {"error_type": type(e).__name__, "error_message": str(e)}}
    except Exception as e: # Catch any other unexpected errors
        return {"status": "error", "message": "An unexpected error occurred during the test.", "details": {"error_type": type(e).__name__, "error_message": str(e)}}

async def get_static_completion(
    ai_model_id: str,
    api_base_url: str, # Anthropic SDK might not use this directly if ANTHROPIC_API_URL is set or using default
    api_key: str,
    messages: List[ChatMessage],
    temperature: float = None,
    max_tokens: int = None,
    **kwargs: Any
) -> Dict[str, Any]:
    """
    Makes a static (non-streaming) API call to an Anthropic model.

    Args:
        ai_model_id: The identifier of the AI model to use (e.g., 'claude-3-opus-20240229').
        api_base_url: The base URL for the Anthropic API. If None, the SDK default or ANTHROPIC_API_URL env var is used.
        api_key: The API key for authentication.
        messages: A list of message objects for the conversation.
        temperature: The temperature setting for the AI model (0.0 to 1.0).
        max_tokens: The maximum number of tokens to generate.
        **kwargs: Additional parameters to pass to the API (e.g., top_p, top_k, system prompt).

    Returns:
        The API response as a dictionary.
    """
    try:
        client = anthropic.Anthropic(api_key=api_key, base_url=api_base_url if api_base_url else None, http_client=http_client_without_ssl_verification)
        
        # Prepare payload, system prompt can be passed via kwargs or extracted if needed
        payload = {
            "model": ai_model_id,
            "messages": messages,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            # Anthropic's Python SDK uses max_tokens for the parameter name
            payload["max_tokens"] = max_tokens
        
        # Handle system prompt if provided in messages or kwargs
        # Anthropic expects system prompt as a top-level parameter
        system_prompt_message = next((msg for msg in messages if msg.get("role") == "system"), None)
        if system_prompt_message:
            payload["system"] = system_prompt_message["content"]
            # Remove system message from messages list if it was there
            payload["messages"] = [msg for msg in messages if msg.get("role") != "system"]
        elif "system" in kwargs:
            payload["system"] = kwargs.pop("system")

        payload.update(kwargs) # Add any other specific params

        print(payload)
        response = client.messages.create(**payload)
        
        # Convert the response object to a dictionary for consistent return type
        # This structure aims to mimic the previous httpx response.json()
        # You might need to adjust based on what parts of the response object are needed
        response_dict = {
            "id": response.id,
            "type": response.type,
            "role": response.role,
            "content": [{"type": content_block.type, "text": content_block.text} for content_block in response.content],
            "model": response.model,
            "stop_reason": response.stop_reason,
            "stop_sequence": response.stop_sequence,
            "usage": {"input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens},
        }
        return response_dict
    except anthropic.APIStatusError as e:
        print(f"Anthropic API Error: {e.status_code} - {e.response.text}")
        # Re-raise or handle as custom exception
        raise
    except anthropic.APIConnectionError as e:
        print(f"Anthropic Connection Error: {e}")
        raise
    except anthropic.APIError as e:
        print(f"Anthropic API Error: {e}")
        raise


async def stream_completion(
    ai_model_id: str,
    api_base_url: str, # Anthropic SDK might not use this directly
    api_key: str,
    messages: List[ChatMessage],
    on_chunk_callback: Callable[[Dict[str, Any]], Awaitable[None]],
    temperature: float = None,
    max_tokens: int = None,
    **kwargs: Any
):
    """
    Makes a streaming API call to an Anthropic model and invokes a callback for each chunk.

    Args:
        ai_model_id: The identifier of the AI model to use.
        api_base_url: The base URL for the Anthropic API.
        api_key: The API key for authentication.
        messages: A list of message objects for the conversation.
        on_chunk_callback: An async function to call with each received data chunk.
        temperature: The temperature setting for the AI model.
        max_tokens: The maximum number of tokens to generate.
        **kwargs: Additional parameters to pass to the API.
    """
    try:
        print(api_key)
        client = AsyncAnthropic(api_key=api_key, base_url=api_base_url if api_base_url else None, http_client=http_async_client_without_ssl_verification)
        
        payload = {
            "model": ai_model_id,
            "messages": messages,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens # SDK uses max_tokens

        # Handle system prompt
        system_prompt_message = next((msg for msg in messages if msg.get("role") == "system"), None)
        if system_prompt_message:
            payload["system"] = system_prompt_message["content"]
            payload["messages"] = [msg for msg in messages if msg.get("role") != "system"]
        elif "system" in kwargs:
            payload["system"] = kwargs.pop("system")
            
        payload.update(kwargs)

        async with client.messages.stream(**payload) as stream:
            async for event in stream:
                chunk_data = {}
                if event.type == "message_start":
                    # Contains metadata about the message, including usage for input tokens
                    chunk_data = {
                        "type": "message_start",
                        "message": {
                            "id": event.message.id,
                            "type": event.message.type,
                            "role": event.message.role,
                            "model": event.message.model,
                            "usage": {"input_tokens": event.message.usage.input_tokens}
                        }
                    }
                elif event.type == "content_block_start":
                    chunk_data = {
                        "type": "content_block_start",
                        "index": event.index,
                        "content_block": {"type": event.content_block.type}
                    }
                elif event.type == "content_block_delta":
                    if event.delta.type == "text_delta":
                        chunk_data = {
                            "type": "content_block_delta",
                            "index": event.index,
                            "delta": {"type": "text_delta", "text": event.delta.text}
                        }
                elif event.type == "content_block_stop":
                     chunk_data = {
                        "type": "content_block_stop",
                        "index": event.index
                    }
                elif event.type == "message_delta":
                    # Contains usage for output tokens and stop reason
                    chunk_data = {
                        "type": "message_delta",
                        "delta": {
                            "stop_reason": event.delta.stop_reason,
                            "stop_sequence": event.delta.stop_sequence,
                        },
                        "usage": {"output_tokens": event.usage.output_tokens}
                    }
                elif event.type == "message_stop":
                    # Final event indicating the stream is complete.
                    chunk_data = {"type": "message_stop"}
                
                if chunk_data:
                    await on_chunk_callback(chunk_data)

    except anthropic.APIStatusError as e:
        error_detail = {"error": True, "status_code": e.status_code, "detail": e.response.text if e.response else str(e)}
        print(f"Anthropic API Error during stream: {error_detail}")
        await on_chunk_callback(error_detail)
        raise
    except anthropic.APIConnectionError as e:
        error_detail = {"error": True, "detail": str(e)}
        print(f"Anthropic Connection Error during stream: {error_detail}")
        await on_chunk_callback(error_detail)
        raise
    except anthropic.APIError as e: # Catch other Anthropic errors
        error_detail = {"error": True, "detail": str(e)}
        print(f"Anthropic API Error during stream: {error_detail}")
        await on_chunk_callback(error_detail)
        raise
    except Exception as e: # Catch any other unexpected errors
        error_detail = {"error": True, "detail": f"Unexpected error during stream: {str(e)}"}
        print(error_detail["detail"])
        await on_chunk_callback(error_detail)
        raise

# Example usage (conceptual, would be called from views.py or consumers.py):
# async def example_static_call(ai_model_obj): # Assuming ai_model_obj has needed attributes
#     response = await get_static_completion(
#         ai_model_id=ai_model_obj.model_id, # e.g., "claude-3-opus-20240229"
#         api_base_url=ai_model_obj.endpoint.url, # Optional, SDK might use ANTHROPIC_API_URL
#         api_key=ai_model_obj.endpoint.apikey,
#         messages=[{"role": "user", "content": "Tell me a joke."}],
#         temperature=ai_model_obj.default_temperature or 0.7,
#         max_tokens=150 # Example max_tokens
#     )
#     print(response)

# async def example_streaming_call(ai_model_obj):
#     async def my_chunk_handler(chunk):
#         # In ChatConsumer, this would be self.send(text_data=json.dumps(chunk))
#         print(json.dumps(chunk)) # Print the structured chunk

#     await stream_completion(
#         ai_model_id=ai_model_obj.model_id,
#         api_base_url=ai_model_obj.endpoint.url,
#         api_key=ai_model_obj.endpoint.apikey,
#         messages=[{"role": "user", "content": "Write a short story about a brave robot."}],
#         on_chunk_callback=my_chunk_handler,
#         temperature=ai_model_obj.default_temperature or 0.7,
#         max_tokens=500 # Example max_tokens
#     )
