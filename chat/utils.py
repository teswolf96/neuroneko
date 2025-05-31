import anthropic
import httpx
from typing import List, Dict, Optional

# Consistent with api_client.py for SSL verification bypass if needed
# However, for count_tokens, a default client might often suffice if it's a local operation
# or if the environment is already configured for Anthropic API access.
# For robustness, mirroring the http_client setup from api_client.py is safer.
http_client_without_ssl_verification = httpx.Client(verify=False)


def _count_anthropic_tokens_internal(api_key: str, model_id_str: str, messages_for_api: List[Dict[str, str]], system_prompt_for_api: Optional[str] = None) -> int:
    """
    Internal function to count tokens for Anthropic models.
    Note: The Anthropic SDK's direct count_tokens for messages API might require specific versions or handling.
    This implementation assumes client.messages.count_tokens exists and works as expected.
    """
    try:
        client = anthropic.Anthropic(
            api_key=api_key,  # Can be None, SDK will try env vars
            http_client=http_client_without_ssl_verification
            )

        result = client.messages.count_tokens(
            model=model_id_str,
            messages=messages_for_api,
            system = system_prompt_for_api,

        )
        return int(result.input_tokens)
    except Exception as e:
        print(f"Error counting Anthropic tokens: {e}")
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
    # elif model.endpoint.provider == 'openai':
    #     return _count_openai_tokens_internal(model_id_str=model.model_id, messages_for_api=messages_for_api, system_prompt_for_api=system_prompt_for_api) # To be implemented
    else:
        print(f"Token counting not implemented for provider: {model.endpoint.provider}")
        # Fallback for unknown providers: very rough character-based estimate
        num_chars = sum(len(msg.get("content", "")) for msg in messages_for_api)
        if system_prompt_for_api:
            num_chars += len(system_prompt_for_api)
        return num_chars // 4 # Extremely rough estimate
