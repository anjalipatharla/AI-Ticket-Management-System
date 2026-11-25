from django.contrib import admin

from .models import (
    KnowledgeCategory,
    KnowledgeArticle,
    FAQ,
    TicketMessage,
)


@admin.register(KnowledgeCategory)
class KnowledgeCategoryAdmin(admin.ModelAdmin):

    list_display = ("id", "name", "created_at")
    search_fields = ("name",)
    ordering = ("name",)


@admin.register(KnowledgeArticle)
class KnowledgeArticleAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "title",
        "category",
        "author",
        "status",
        "views_count",
        "created_at",
    )

    list_filter = ("status", "category", "created_at")
    search_fields = ("title", "content")
    readonly_fields = ("views_count", "created_at", "updated_at")


@admin.register(FAQ)
class FAQAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "question",
        "category",
        "author",
        "status",
        "views_count",
        "created_at",
    )

    list_filter = ("status", "category", "created_at")
    search_fields = ("question", "answer")
    readonly_fields = ("views_count", "created_at", "updated_at")


@admin.register(TicketMessage)
class TicketMessageAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "ticket",
        "sender",
        "created_at",
    )

    search_fields = (
        "ticket__ticket_number",
        "sender__username",
        "message",
    )

    list_filter = ("created_at",)
    readonly_fields = ("created_at",)
