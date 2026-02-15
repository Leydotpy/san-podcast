from django.contrib import admin

from .models import Transaction, Source, SourceType, Bankcard


class TransactionAdmin(admin.ModelAdmin):
    list_display = ('amount', 'txn_type', 'reference', 'currency', 'status', 'source__reference', 'completed_at',)
    list_filter = ('status', 'created_at', 'completed_at',)
    search_fields = ('id', 'amount', 'status', 'reference', 'currency')
    ordering = ('-completed_at',)
    readonly_fields = ('created_at', 'completed_at', 'metadata', )

    class Meta:
        model = Transaction


admin.site.register(Transaction, TransactionAdmin)
admin.site.register(Source)
admin.site.register(SourceType)
admin.site.register(Bankcard)