import anthropic
from google import genai
from google.genai import types

import httpx
import tiktoken # Added tiktoken import
from typing import List, Dict, Optional

# Consistent with api_client.py for SSL verification bypass if needed
# However, for count_tokens, a default client might often suffice if it's a local operation
# or if the environment is already configured for Anthropic API access.
# For robustness, mirroring the http_client setup from api_client.py is safer.
http_client_without_ssl_verification = httpx.Client(verify=False)


def _count_anthropic_tokens_internal(api_key: str, model_id_str: str, messages_for_api: List[Dict[str, any]], system_prompt_for_api: Optional[str | List[Dict[str, str]]] = None) -> int:
    """
    Internal function to count tokens for Anthropic models.
    """
    try:
        processed_messages = []
        for i, msg_original in enumerate(messages_for_api):
            msg = msg_original.copy() # Work on a copy
            content = msg.get('content')
            
            # Apply rstrip to the text of the last text block if the message is the last one and from assistant
            if i == len(messages_for_api) - 1 and msg.get('role') == 'assistant':
                if isinstance(content, str):
                    msg['content'] = content.rstrip()
                elif isinstance(content, list) and content: # It's a list of blocks
                    new_content_list = []
                    # Iterate backwards to find the last text block to rstrip
                    processed_last_text_block = False
                    for block_idx in range(len(content) - 1, -1, -1):
                        block_original = content[block_idx]
                        block = block_original.copy()
                        if not processed_last_text_block and block.get("type") == "text" and isinstance(block.get("text"), str):
                            block["text"] = block["text"].rstrip()
                            processed_last_text_block = True
                        new_content_list.insert(0, block) # Insert at beginning to maintain order
                    
                    if processed_last_text_block:
                         msg['content'] = new_content_list
                    # If not modified (e.g. no text block, or last block not text), content remains as is in the copy
            
            processed_messages.append(msg)

        final_system_prompt_str = None
        if isinstance(system_prompt_for_api, str):
            final_system_prompt_str = system_prompt_for_api
        elif isinstance(system_prompt_for_api, list) and system_prompt_for_api:
            # Extract text from the first text block if system_prompt_for_api is a list of blocks
            # Anthropic system prompt is a single string.
            for block in system_prompt_for_api: # Find the first text block
                if block.get("type") == "text" and isinstance(block.get("text"), str):
                    final_system_prompt_str = block.get("text")
                    break 
        
        # Ensure final_system_prompt_str is not an empty string if it was derived from an empty block list or non-text block
        # An empty string as system prompt is different from None (no system prompt) for Anthropic.
        # If it was intentionally an empty string, preserve it. If it became empty due to no text block, make it None.
        # However, the Anthropic SDK might treat "" and None similarly for the 'system' parameter.
        # For clarity, if it's an empty string from processing, let it be. If it was None initially, it stays None.

        client = anthropic.Anthropic(
            api_key=api_key,
            http_client=http_client_without_ssl_verification
        )
        
        # Filter out messages with content that might be problematic for count_tokens if necessary.
        # Anthropic expects 'content' to be a string or a list of content blocks.
        # An empty string content e.g. `{"role":"user", "content":""}` is valid.
        # A list of blocks like `{"role":"user", "content":[{"type":"text", "text":""}]}` is also valid.
        # The `processed_messages` list should maintain this validity.

        result = client.messages.count_tokens(
            model=model_id_str,
            messages=processed_messages, # Use the potentially modified messages
            system=final_system_prompt_str, # Use the processed string system prompt
        )
        return int(result.input_tokens)
    except Exception as e:
        # For more detailed debugging, one could log the types and content structure:
        # system_prompt_type = type(system_prompt_for_api).__name__
        # messages_sample_str = str(messages_for_api[:2]) # Example of first two messages
        # print(f"Error counting Anthropic tokens (system_prompt_type: {system_prompt_type}, messages_sample: {messages_sample_str}): {e}")
        print(f"Error counting Anthropic tokens: {e}") # Original print
        return 0 # Fallback to 0 on other errors


def _count_google_tokens_internal(api_key: str, model_id_str: str, messages_for_api: List[Dict[str, str]], system_prompt_for_api: Optional[str] = None) -> int:
    """
    Internal function to count tokens for Anthropic models.
    Note: The Anthropic SDK's direct count_tokens for messages API might require specific versions or handling.
    This implementation assumes client.messages.count_tokens exists and works as expected.
    """
    try:
        client = genai.Client(api_key=api_key)
        contents = ""
        system_prompt_message = None

        for msg in messages_for_api:
            if msg.get('role') == "system":
                system_prompt_message = msg.get('content')
                continue
            contents += msg.get('content')

        result = client.models.count_tokens(
            model=model_id_str,
            contents=contents
        )
        return result.total_tokens
    #     return int(result.input_tokens)
    except Exception as e:
        print(f"Error counting Google tokens: {e}")
        return 0 # Fallback to 0 on other errors
    

def count_tokens(model, messages_for_api: List[Dict[str, str]], system_prompt_for_api: Optional[str] = None) -> int:
    """
    Public function to count tokens. Dispatches to provider-specific implementation.
    Args:
        model: The AIModel instance.
        messages_for_api: List of message dictionaries.
        system_prompt_for_api: Optional system prompt string.
    Returns:
        The estimated number of tokens.
    """
    if not model.endpoint:
        print("Error: AIModel has no associated endpoint for token counting.")
        return 0

    if model.endpoint.provider == 'anthropic':
        return _count_anthropic_tokens_internal(
            api_key=model.endpoint.apikey,
            model_id_str=model.model_id,
            messages_for_api=messages_for_api,
            system_prompt_for_api=system_prompt_for_api
        )
    elif model.endpoint.provider == 'openai':
        return _count_openai_tokens_internal(model_id_str=model.model_id, messages_for_api=messages_for_api, system_prompt_for_api=system_prompt_for_api)
    elif model.endpoint.provider == 'google':
        return _count_google_tokens_internal(
            api_key=model.endpoint.apikey,
            model_id_str=model.model_id,
            messages_for_api=messages_for_api,
            system_prompt_for_api=system_prompt_for_api
        )
    else:
        print(f"Token counting not implemented for provider: {model.endpoint.provider}")
        # Fallback for unknown providers: very rough character-based estimate
        num_chars = sum(len(msg.get("content", "")) for msg in messages_for_api)
        if system_prompt_for_api:
            num_chars += len(system_prompt_for_api)
        return num_chars // 4 # Extremely rough estimate

def _count_openai_tokens_internal(model_id_str: str, messages_for_api: List[Dict[str, str]], system_prompt_for_api: Optional[str] = None) -> int:
    """
    Internal function to count tokens for OpenAI models using tiktoken.
    """
    try:
        encoding = tiktoken.encoding_for_model(model_id_str)
    except KeyError:
        print(f"Warning: Encoding not found for model {model_id_str}. Using o200k_base encoding.")
        encoding = tiktoken.get_encoding("o200k_base")
    
    num_tokens = 0
    # OpenAI specific token counting logic
    # Reference: https://github.com/openai/openai-cookbook/blob/main/examples/How_to_count_tokens_with_tiktoken.ipynb
    # For chat models, the pattern is:
    # every message follows <|start|>{role/name}\n{content}<|end|>\n
    # if there's a name, the role is omitted
    # every reply is primed with <|start|>assistant\n
    #
    # For gpt-3.5-turbo-0301, it's 4 tokens per message.
    # For gpt-4-0314, gpt-4-32k-0314, gpt-3.5-turbo-0613, gpt-4-0613, gpt-4-32k-0613 it's 3 tokens per message.
    # This can vary, so we'll use a more general approach of encoding each part.

    # Simplified approach: encode content of each message.
    # A more precise implementation would account for role tokens, etc.
    # but this is often sufficient for estimation.
    
    # Based on OpenAI's documentation, for chat completions:
    # Each message incurs a fixed cost of tokens for metadata (role, name if present).
    # The content of each message is tokenized.
    # A system message also incurs this cost.

    # A common approximation for newer models (like gpt-3.5-turbo-0613 and gpt-4 models):
    # Each message costs 3 tokens for role/metadata.
    # The content of each message is tokenized.
    # If there's a system prompt, it's treated like a message.

    tokens_per_message = 3 # Default for newer models
    tokens_per_name = 1 # If name is present

    if model_id_str == "gpt-3.5-turbo-0301":
        tokens_per_message = 4 # Older model specific
        tokens_per_name = -1 # Name is included in message tokens for this model

    if system_prompt_for_api:
        num_tokens += tokens_per_message 
        num_tokens += len(encoding.encode(system_prompt_for_api))

    for message in messages_for_api:
        num_tokens += tokens_per_message
        for key, value in message.items():
            if value: # Ensure value is not None or empty
                 num_tokens += len(encoding.encode(str(value))) # Convert value to string
            if key == "name":
                num_tokens += tokens_per_name
    
    num_tokens += 3  # every reply is primed with <|start|>assistant<|message|>
    return num_tokens
