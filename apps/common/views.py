from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET


@require_GET
def health_check(request: HttpRequest) -> JsonResponse:
    """Liveness probe for load balancers / container orchestrators."""
    return JsonResponse({"status": "ok"})
