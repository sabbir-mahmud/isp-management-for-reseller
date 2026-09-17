"""Small request-level helpers."""


class HtmxMiddleware:
    """Flag HTMX requests as `request.htmx`.

    A one-header check, so it is not worth a third-party dependency.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.htmx = request.headers.get("HX-Request") == "true"
        return self.get_response(request)
