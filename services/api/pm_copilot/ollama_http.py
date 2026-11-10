"""HTTP-only local inference transport; no TLS certificate work on the event loop."""
import httpx


async def _loopback_only(request):
    if request.url.scheme != 'http' or request.url.host != '127.0.0.1' or request.url.port != 11434:
        raise ValueError('The Ollama client only permits http://127.0.0.1:11434')


def ollama_client(timeout):
    # HTTPX otherwise loads/parses a CA bundle synchronously even for plain HTTP.
    # Doing that in every resource poll can stall Windows event-loop timers and
    # cancellation. HTTPS is forbidden here; external model downloads retain TLS.
    return httpx.AsyncClient(verify=False, trust_env=False, follow_redirects=False,
                             timeout=timeout, event_hooks={'request': [_loopback_only]})
