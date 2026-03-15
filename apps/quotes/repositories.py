"""
Repository Quotes : accès aux demandes de devis.
"""
from .models import QuoteRequest, QuoteRequestItem


class QuoteRequestRepository:
    @staticmethod
    def get_all():
        return QuoteRequest.objects.select_related("client").prefetch_related("items").order_by("-created_at")

    @staticmethod
    def get_by_client(user_id):
        return QuoteRequest.objects.filter(client_id=user_id).order_by("-created_at")

    @staticmethod
    def get_by_id(pk):
        return QuoteRequest.objects.select_related("client").prefetch_related("items").filter(pk=pk).first()

    @staticmethod
    def create(client, subject, message, items=None):
        quote = QuoteRequest.objects.create(client=client, subject=subject, message=message)
        if items:
            for item in items:
                QuoteRequestItem.objects.create(quote_request=quote, **item)
        return quote
