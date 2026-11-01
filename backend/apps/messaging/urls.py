"""F16 routes. The public pair carry no session and are token-gated."""

from django.urls import path

from .views import (
    BindingList, Inbox, IssueLinkToken, PublicAccept, PublicLink,
    RevokeBinding, SendQuotation, SendTicketConfirmation,
)

urlpatterns = [
    path("customers/<int:pk>/telegram-token/", IssueLinkToken.as_view(), name="telegram-token"),
    path("telegram/bindings/", BindingList.as_view(), name="telegram-bindings"),
    path("telegram/bindings/<int:pk>/revoke/", RevokeBinding.as_view(), name="telegram-revoke"),
    path("telegram/inbox/", Inbox.as_view(), name="telegram-inbox"),
    path("quotations/<int:pk>/send/", SendQuotation.as_view(), name="quotation-send"),
    path("tickets/<int:pk>/request-confirmation/", SendTicketConfirmation.as_view(),
         name="ticket-request-confirmation"),

    # No session, no account: the token in the path is the authorisation.
    path("public/links/<str:token>/", PublicLink.as_view(), name="public-link"),
    path("public/links/<str:token>/accept/", PublicAccept.as_view(), name="public-link-accept"),
]
