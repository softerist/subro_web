from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

API_KEY_PREFIX_LEN = 8

# Initialize the Limiter with the get_remote_address key function
# This identifies clients by their IP address
limiter = Limiter(key_func=get_remote_address)


def get_api_key_or_ip(request: Request) -> str:
    api_key = request.headers.get("X-API-Key")
    if api_key:
        return f"api_key:{api_key[:API_KEY_PREFIX_LEN]}"
    return get_remote_address(request)
