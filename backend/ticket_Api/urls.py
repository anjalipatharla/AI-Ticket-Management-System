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
    KnowledgeCategoryListCreateView,
    KnowledgeCategoryDetailView,
    KnowledgeArticleListCreateView,
    KnowledgeArticleDetailView,
    FAQListCreateView,
    FAQDetailView,
    KnowledgeArticlePublishView,
    FAQPublishView,
    TicketMessageListCreateView,
    AIReplyGenerationView,
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
    # Ticket Communication API
    path("tickets/<int:ticket_id>/messages/",
         TicketMessageListCreateView.as_view(), name="ticket-messages"),
    # SLA APIs
    path("tickets/<int:ticket_id>/first-response/",
         FirstResponseView.as_view(), name="ticket-first-response"),
    # Knowledge Base - Category APIs
    path("knowledge/categories/", KnowledgeCategoryListCreateView.as_view(),
         name="knowledge-category-list-create"),

    path("knowledge/categories/<int:pk>/",
         KnowledgeCategoryDetailView.as_view(), name="knowledge-category-detail"),

    # Knowledge Base - Article APIs
    path("knowledge/articles/",
         KnowledgeArticleListCreateView.as_view(),
         name="knowledge-article-list-create"),

    path("knowledge/articles/<int:pk>/",
         KnowledgeArticleDetailView.as_view(),
         name="knowledge-article-detail"),

    # FAQ APIs
    path("faqs/",
         FAQListCreateView.as_view(),
         name="faq-list-create"),

    path("faqs/<int:pk>/",
         FAQDetailView.as_view(),
         name="faq-detail"),
    # Knowledge Base - Publishing APIs
    path("knowledge/articles/<int:pk>/publish/",
         KnowledgeArticlePublishView.as_view(),
         name="knowledge-article-publish"),

    path("faqs/<int:pk>/publish/",
         FAQPublishView.as_view(),
         name="faq-publish"),
    path("tickets/<int:ticket_id>/ai-reply/",
         AIReplyGenerationView.as_view(), name="ticket-ai-reply"),
]
