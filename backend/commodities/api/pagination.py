from rest_framework.pagination import PageNumberPagination


class DefaultPagination(PageNumberPagination):
    """Default page size 50, but callers may request more via ?page_size= (e.g. a
    dropdown that needs the whole catalogue), capped at max_page_size."""

    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 1000
