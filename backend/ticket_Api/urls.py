from django.urls import path

from .views import (
    ComplaintCreateView,
    MyComplaintsView,
    PendingComplaintsView,
    ConvertComplaintToTicketView,
    TicketListView,
    TicketDetailView,
    TicketUpdateView,
    TicketAssignmentView,
    TicketHistoryView,
    FirstResponseView,
)

urlpatterns = [
    # Customer APIs
    path("complaints/", ComplaintCreateView.as_view(), name="submit-complaint"),
    path("complaints/my/", MyComplaintsView.as_view(), name="my-complaints"),

    # Agent APIs
    path("complaints/pending/", PendingComplaintsView.as_view(),
         name="pending-complaints"),
    path("complaints/<int:complaint_id>/convert/",
         ConvertComplaintToTicketView.as_view(), name="convert-complaint"),

    # Ticket APIs
    path("tickets/", TicketListView.as_view(), name="ticket-list"),
    path("tickets/<int:ticket_id>/",
         TicketDetailView.as_view(), name="ticket-detail"),
    path("tickets/<int:ticket_id>/update/",
         TicketUpdateView.as_view(), name="ticket-update"),
    path("tickets/<int:ticket_id>/assign/",
         TicketAssignmentView.as_view(), name="ticket-assign"),
    path("tickets/<int:ticket_id>/history/",
         TicketHistoryView.as_view(), name="ticket-history"),
    # SLA APIs
    path("tickets/<int:ticket_id>/first-response/",
         FirstResponseView.as_view(), name="ticket-first-response"),
]
