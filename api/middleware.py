import sys
import time
import logging

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start_time = time.time()
        response = self.get_response(request)
        duration_ms = (time.time() - start_time) * 1000
        logger.info(
            '%s %s - %s - %.2fms',
            request.method,
            request.get_full_path(),
            response.status_code,
            duration_ms,
        )
        sys.stdout.flush()
        return response