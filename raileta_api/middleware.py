from django.conf import settings


class CorsMiddleware:
    """Small dependency-free CORS layer for the local dashboards and CRIS adapters."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        allowed = {
            "http://localhost:3000", "http://localhost:3001", "http://localhost:3002",
            "http://localhost:4173", "http://localhost:4174", "http://localhost:4175",
            "http://127.0.0.1:3000", "http://127.0.0.1:3001", "http://127.0.0.1:3002",
            "http://127.0.0.1:4173", "http://127.0.0.1:4174", "http://127.0.0.1:4175",
        }
        origin = request.headers.get("Origin")
        if origin in allowed:
            response["Access-Control-Allow-Origin"] = origin
            response["Access-Control-Allow-Credentials"] = "true"
            response["Vary"] = "Origin"
        if request.method == "OPTIONS":
            response["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            response["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return response
