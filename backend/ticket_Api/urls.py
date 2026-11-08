
from django.urls import path

from .views import (
    ComplaintCreateView,
    MyComplaintsView,
    PendingComplaintsView,
    ConvertComplaintToTicketView,
    TicketListView,
)

urlpatterns = [
    # Customer APIs
    path(
        "complaints/",
        ComplaintCreateView.as_view(),
        name="submit-complaint"
    ),
    path(
        "complaints/my/",
        MyComplaintsView.as_view(),
        name="my-complaints"
    ),

    # Agent APIs
    path(
        "complaints/pending/",
        PendingComplaintsView.as_view(),
        name="pending-complaints"
    ),
    path(
        "complaints/<int:complaint_id>/convert/",
        ConvertComplaintToTicketView.as_view(),
        name="convert-complaint"
    ),

    # Ticket APIs
    path(
        "tickets/",
        TicketListView.as_view(),
        name="ticket-list"
    ),
]
