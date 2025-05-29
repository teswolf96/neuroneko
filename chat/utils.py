import anthropic
import httpx
from typing import List, Dict, Optional

# Consistent with api_client.py for SSL verification bypass if needed
# However, for count_tokens, a default client might often suffice if it's a local operation
# or if the environment is already configured for Anthropic API access.
# For robustness, mirroring the http_client setup from api_client.py is safer.
http_client_without_ssl_verification = httpx.Client(verify=False)


def count_anthropic_tokens(model, messages_for_api: List[Dict[str, str]], system_prompt_for_api: Optional[str] = None) -> int:
    try:
        client = anthropic.Anthropic(
            api_key=model.endpoint.apikey,  # Can be None, SDK will try env vars
            http_client=http_client_without_ssl_verification
            )

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
