import anthropic
import httpx
from typing import List, Dict, Optional

# Consistent with api_client.py for SSL verification bypass if needed
# However, for count_tokens, a default client might often suffice if it's a local operation
# or if the environment is already configured for Anthropic API access.
# For robustness, mirroring the http_client setup from api_client.py is safer.
http_client_without_ssl_verification = httpx.Client(verify=False)

def get_anthropic_client(api_key: Optional[str] = None, base_url: Optional[str] = None):
    """
    Instantiates and returns an Anthropic client.
    Uses a shared httpx.Client that bypasses SSL verification, similar to api_client.py.
    API key and base_url are optional; if not provided, the SDK will try to use
    environment variables (ANTHROPIC_API_KEY, ANTHROPIC_BASE_URL) or defaults.
    For token counting, a key/URL might not always be strictly necessary if it's a local calculation,
    but providing them ensures consistency if the SDK ever needs to make a call.
    """
    return anthropic.Anthropic(
        api_key=api_key,  # Can be None, SDK will try env vars
        base_url=base_url, # Can be None
        http_client=http_client_without_ssl_verification
    )

def count_anthropic_tokens(model, messages_for_api: List[Dict[str, str]], system_prompt_for_api: Optional[str] = None) -> int:
    """
    Estimates the number of tokens for a given set of messages and a system prompt
    using the Anthropic SDK.

    Args:
        messages_for_api: A list of message dictionaries (e.g., {"role": "user", "content": "..."}),
                          should only contain 'user' and 'assistant' roles.
        system_prompt_for_api: An optional string for the system prompt.

    Returns:
        The estimated token count as an integer. Returns 0 if counting fails.
    """
    try:
        client = anthropic.Anthropic(
            api_key=model.endpoint.apikey,  # Can be None, SDK will try env vars
            http_client=http_client_without_ssl_verification
            )
        print(messages_for_api)
        result = client.messages.count_tokens(
            model=model.model_id,
            messages=messages_for_api,
            system = system_prompt_for_api,

        )
        return int(result.input_tokens)
    except Exception as e:
        print(f"Error counting Anthropic tokens: {e}")
        # Depending on how critical failure is, could raise or return a specific error indicator.
        # For now, returning 0 on failure.
        return 0

if __name__ == '__main__':
    # Example Usage (for testing this file directly)
    # Ensure ANTHROPIC_API_KEY is set in your environment if your SDK version requires it for count_tokens
    
    # Test case 1: Simple user message
    messages1 = [{"role": "user", "content": "Hello, world!"}]
    count1 = count_anthropic_tokens(messages1)
    print(f"Test Case 1 Tokens: {count1}") # Expected: Varies by model, e.g., 4-6 tokens

    # Test case 2: User and assistant messages
    messages2 = [
        {"role": "user", "content": "How are you?"},
        {"role": "assistant", "content": "I am doing well, thank you!"}
    ]
    count2 = count_anthropic_tokens(messages2)
    print(f"Test Case 2 Tokens: {count2}")

    # Test case 3: With a system prompt
    messages3 = [{"role": "user", "content": "Tell me a joke."}]
    system3 = "You are a helpful assistant that tells jokes."
    count3 = count_anthropic_tokens(messages3, system_prompt_for_api=system3)
    print(f"Test Case 3 Tokens (with system prompt): {count3}")

    # Test case 4: Empty messages
    messages4 = []
    system4 = "You are a bot."
    count4 = count_anthropic_tokens(messages4, system_prompt_for_api=system4)
    print(f"Test Case 4 Tokens (empty messages, with system prompt): {count4}")
    
    messages5 = []
    system5 = None
    count5 = count_anthropic_tokens(messages5, system_prompt_for_api=system5)
    print(f"Test Case 5 Tokens (empty messages, no system prompt): {count5}") # Expected: 0
    
    messages6 = [{"role": "user", "content": "你好"}] # Chinese characters
    count6 = count_anthropic_tokens(messages6)
    print(f"Test Case 6 Tokens (Chinese): {count6}")
