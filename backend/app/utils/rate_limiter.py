from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

def get_tenant_or_ip_address(request: Request) -> str:
    """
    Identifies requests based on authorization credentials (JWT tokens)
    to enable tenant-scoped rate limits, falling back to the client IP address.
    """
    auth = request.headers.get("Authorization")
    if auth and auth.startswith("Bearer "):
        return auth
    return get_remote_address(request)

# Global rate limiter configuration
limiter = Limiter(key_func=get_tenant_or_ip_address)
