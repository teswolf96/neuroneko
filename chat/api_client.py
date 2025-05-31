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

# Standardized response format for static completion (as a comment for now)
# {
#   "id": "provider_message_id",
#   "content": "Full AI response text",
#   "role": "assistant",
#   "model_used": "provider_model_string",
#   "stop_reason": "e.g., length, stop_sequence",
#   "usage": { "input_tokens": 100, "output_tokens": 50 },
#   "error": null // or { "type": "...", "message": "..." }
# }

# Standardized stream chunk format (as a comment for now)
# // For text delta
# { "type": "delta", "text_delta": "some text" }
# // For stop event
# { "type": "stop", "stop_reason": "length", "usage": { "output_tokens": 50 } } // Optionally include usage at stop
# // For error
# { "type": "error", "message": "API error details" }
# // For full message metadata (if applicable, like Anthropic's message_start/message_stop)
# { "type": "metadata", "data": { ... } }


def _test_anthropic_internal(api_key: str) -> Dict[str, Any]:
    """
    Synchronously tests an Anthropic API endpoint by making a minimal call.
    Args:
        api_key: The API key.
    Returns:
        A dictionary with 'status', 'message', and 'details'.
    """
    try:
        # Base URL is handled by the SDK environment variables or defaults
        client = anthropic.Anthropic(api_key=api_key, http_client=http_client_without_ssl_verification)
        # A lightweight call, like listing models or a very short completion, can be used.
        # client.models.list() is a good option if available and doesn't consume significant resources.
        response = client.models.list(limit=1) # Limit to 1 to be minimal
        return {
            "status": "success",
            "message": "Anthropic endpoint test successful!"
        }
    except anthropic.AuthenticationError as e:
        return {"status": "error", "message": "Authentication failed. Check API key.", "details": {"error_type": type(e).__name__, "error_message": str(e), "status_code": e.status_code if hasattr(e, 'status_code') else None}}
    except anthropic.APIConnectionError as e:
        # This error can occur if the base URL is incorrect or unreachable,
        # even if the SDK usually handles the base URL.
        return {"status": "error", "message": "Connection error. Check API URL or network.", "details": {"error_type": type(e).__name__, "error_message": str(e)}}
    except anthropic.RateLimitError as e:
        return {"status": "error", "message": "Rate limit exceeded.", "details": {"error_type": type(e).__name__, "error_message": str(e), "status_code": e.status_code if hasattr(e, 'status_code') else None}}
    except anthropic.APIStatusError as e: 
        return {"status": "error", "message": f"API error (status {e.status_code}).", "details": {"error_type": type(e).__name__, "error_message": str(e.response.text if e.response else e), "status_code": e.status_code}}
    except anthropic.APIError as e: 
        return {"status": "error", "message": "An Anthropic API error occurred.", "details": {"error_type": type(e).__name__, "error_message": str(e)}}
    except Exception as e: 
        return {"status": "error", "message": "An unexpected error occurred during the Anthropic test.", "details": {"error_type": type(e).__name__, "error_message": str(e)}}

def test_endpoint(endpoint) -> Dict[str, Any]: # endpoint is an AIEndpoint model instance
    """
    Tests an API endpoint based on its provider.
    Args:
        endpoint: The AIEndpoint model instance.
    Returns:
        A dictionary with 'status', 'message', and 'details'.
    """
    if not endpoint.apikey:
        return {"status": "error", "message": "API key is missing for this endpoint.", "details": None}

    if endpoint.provider == 'anthropic':
        return _test_anthropic_internal(api_key=endpoint.apikey)
    # elif endpoint.provider == 'openai':
    #     return _test_openai_internal(api_key=endpoint.apikey) # To be implemented
    else:
        return {"status": "error", "message": f"Testing not implemented for provider: {endpoint.provider}", "details": None}


async def _get_static_completion_anthropic_internal(
    ai_model_id: str,
    api_key: str,
    messages: List[ChatMessage],
    temperature: float = None,
    max_tokens: int = None,
    **kwargs: Any
) -> Dict[str, Any]:
    """
    Makes a static (non-streaming) API call to an Anthropic model.
    Returns a standardized dictionary.
    """
    try:
        # Base URL is handled by the SDK environment variables or defaults
        client = anthropic.Anthropic(api_key=api_key, http_client=http_client_without_ssl_verification)
        
        payload = {
            "model": ai_model_id,
            "messages": messages,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        
        system_prompt_message = next((msg for msg in messages if msg.get("role") == "system"), None)
        if system_prompt_message:
            payload["system"] = system_prompt_message["content"]
            payload["messages"] = [msg for msg in messages if msg.get("role") != "system"]
        elif "system" in kwargs: # Allow passing system prompt via kwargs as well
            payload["system"] = kwargs.pop("system")

        payload.update(kwargs)
        
        api_response = client.messages.create(**payload)
        
        # Normalize to standard format
        # For Anthropic, content is a list of blocks. We'll concatenate text blocks.
        response_text_content = ""
        if api_response.content:
            for block in api_response.content:
                if hasattr(block, 'text'):
                    response_text_content += block.text
        
        return {
            "id": api_response.id,
            "content": response_text_content,
            "role": api_response.role, # Should be 'assistant'
            "model_used": api_response.model,
            "stop_reason": api_response.stop_reason,
            "usage": {"input_tokens": api_response.usage.input_tokens, "output_tokens": api_response.usage.output_tokens},
            "error": None
        }
    except anthropic.APIStatusError as e:
        error_payload = {"type": type(e).__name__, "message": str(e.response.text if e.response else e), "status_code": e.status_code}
        print(f"Anthropic API Error (Static): {error_payload}")
        return {"id": None, "content": None, "role": "error", "model_used": ai_model_id, "stop_reason": "error", "usage": None, "error": error_payload}
    except anthropic.APIConnectionError as e:
        error_payload = {"type": type(e).__name__, "message": str(e)}
        print(f"Anthropic Connection Error (Static): {error_payload}")
        return {"id": None, "content": None, "role": "error", "model_used": ai_model_id, "stop_reason": "error", "usage": None, "error": error_payload}
    except Exception as e: # Catch any other unexpected errors
        error_payload = {"type": type(e).__name__, "message": str(e)}
        print(f"Unexpected Error (Static Anthropic): {error_payload}")
        return {"id": None, "content": None, "role": "error", "model_used": ai_model_id, "stop_reason": "error", "usage": None, "error": error_payload}


async def get_static_completion(
    model, # AIModel instance
    messages: List[ChatMessage],
    temperature: float = None,
    max_tokens: int = None,
    **kwargs: Any
) -> Dict[str, Any]:
    """
    Public function for static completion. Dispatches to provider-specific implementation.
    """
    if not model.endpoint or not model.endpoint.apikey:
        return {"id": None, "content": None, "role": "error", "model_used": model.model_id, "stop_reason": "error", "usage": None, "error": {"type": "ConfigurationError", "message": "Endpoint or API key is missing."}}

    # Use model's default temp/tokens if not provided in call
    effective_temperature = temperature if temperature is not None else model.default_temperature
    effective_max_tokens = max_tokens if max_tokens is not None else model.default_max_tokens

    if model.endpoint.provider == 'anthropic':
        return await _get_static_completion_anthropic_internal(
            ai_model_id=model.model_id,
            api_key=model.endpoint.apikey,
            messages=messages,
            temperature=effective_temperature,
            max_tokens=effective_max_tokens,
            **kwargs
        )
    # elif model.endpoint.provider == 'openai':
    #     return await _get_static_completion_openai_internal(...) # To be implemented
    else:
        return {"id": None, "content": None, "role": "error", "model_used": model.model_id, "stop_reason": "error", "usage": None, "error": {"type": "UnsupportedProviderError", "message": f"Static completion not implemented for provider: {model.endpoint.provider}"}}


async def _stream_completion_anthropic_internal(
    ai_model_id: str,
    api_key: str,
    messages: List[ChatMessage],
    on_chunk_callback: Callable[[Dict[str, Any]], Awaitable[None]], # Callback expects standardized chunk
    temperature: float = None,
    max_tokens: int = None,
    **kwargs: Any
):
    """
    Makes a streaming API call to an Anthropic model and invokes a callback with standardized chunks.
    """
    try:
        # Base URL is handled by the SDK environment variables or defaults
        client = AsyncAnthropic(api_key=api_key, http_client=http_async_client_without_ssl_verification)
        
        payload = {
            "model": ai_model_id,
            "messages": messages,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        system_prompt_message = next((msg for msg in messages if msg.get("role") == "system"), None)
        if system_prompt_message:
            payload["system"] = system_prompt_message["content"]
            payload["messages"] = [msg for msg in messages if msg.get("role") != "system"]
        elif "system" in kwargs:
            payload["system"] = kwargs.pop("system")
            
        payload.update(kwargs)

        async with client.messages.stream(**payload) as stream:
            async for event in stream:
                standardized_chunk = None
                if event.type == "message_start":
                    standardized_chunk = {
                        "type": "metadata", 
                        "data": {
                            "id": event.message.id,
                            "input_tokens": event.message.usage.input_tokens
                        }
                    }
                elif event.type == "content_block_delta":
                    if event.delta.type == "text_delta" and event.delta.text:
                        standardized_chunk = {"type": "delta", "text_delta": event.delta.text}
                elif event.type == "message_delta": # Anthropic sends this for stop_reason and output_tokens
                    standardized_chunk = {
                        "type": "stop", 
                        "stop_reason": event.delta.stop_reason,
                        "usage": {"output_tokens": event.usage.output_tokens}
                    }
                elif event.type == "message_stop":
                    # This is a final confirmation, often doesn't carry new data beyond what message_delta provided.
                    # We can choose to send a specific "final_stop" or rely on message_delta's stop.
                    # For simplicity, we can ignore this if message_delta already signals stop.
                    # If message_delta didn't have usage, this might be a place to confirm it.
                    pass # Already handled by message_delta for stop_reason and usage

                if standardized_chunk:
                    await on_chunk_callback(standardized_chunk)

    except anthropic.APIStatusError as e:
        error_detail = {"type": "error", "message": f"API Error (status {e.status_code}): {e.response.text if e.response else str(e)}"}
        await on_chunk_callback(error_detail)
    except anthropic.APIConnectionError as e:
        error_detail = {"type": "error", "message": f"Connection Error: {str(e)}"}
        await on_chunk_callback(error_detail)
    except Exception as e:
        error_detail = {"type": "error", "message": f"Unexpected error during Anthropic stream: {str(e)}"}
        await on_chunk_callback(error_detail)

async def stream_completion(
    model, # AIModel instance
    messages: List[ChatMessage],
    on_chunk_callback: Callable[[Dict[str, Any]], Awaitable[None]],
    temperature: float = None,
    max_tokens: int = None,
    **kwargs: Any
):
    """
    Public function for streaming completion. Dispatches to provider-specific implementation.
    """
    if not model.endpoint or not model.endpoint.apikey:
        await on_chunk_callback({"type": "error", "message": "Endpoint or API key is missing."})
        return

    effective_temperature = temperature if temperature is not None else model.default_temperature
    effective_max_tokens = max_tokens if max_tokens is not None else model.default_max_tokens

    if model.endpoint.provider == 'anthropic':
        await _stream_completion_anthropic_internal(
            ai_model_id=model.model_id,
            api_key=model.endpoint.apikey,
            messages=messages,
            on_chunk_callback=on_chunk_callback,
            temperature=effective_temperature,
            max_tokens=effective_max_tokens,
            **kwargs
        )
    # elif model.endpoint.provider == 'openai':
    #     await _stream_completion_openai_internal(...) # To be implemented
    else:
        await on_chunk_callback({"type": "error", "message": f"Streaming not implemented for provider: {model.endpoint.provider}"})


# Example usage (conceptual, would be called from views.py or consumers.py):
# async def example_static_call(ai_model_obj): # Assuming ai_model_obj has needed attributes
#     response = await get_static_completion( # Now takes the model object
#         model=ai_model_obj, 
#         messages=[{"role": "user", "content": "Tell me a joke."}],
#         # temperature and max_tokens can be omitted to use model defaults
#     )
#     print(response)

# async def example_streaming_call(ai_model_obj):
#     async def my_chunk_handler(chunk): # Expects standardized chunk
#         # In ChatConsumer, this would be self.send(text_data=json.dumps(chunk))
#         print(json.dumps(chunk)) 

#     await stream_completion( # Now takes the model object
#         model=ai_model_obj,
#         messages=[{"role": "user", "content": "Write a short story about a brave robot."}],
#         on_chunk_callback=my_chunk_handler,
#         # temperature and max_tokens can be omitted
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
