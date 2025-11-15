from django.db import models
from django.db.models import Q

from square_integration.models import TaxRate


# Create your models here.
class InventoryItem(models.Model):
    name = models.CharField(max_length=100)
    price_cents = models.PositiveIntegerField()  # price in cents
    currency = models.CharField(max_length=3, default="USD")
    description = models.TextField(blank=True)
    category = models.ForeignKey(
        "square_integration.CatalogCategory", on_delete=models.SET_NULL, null=True, blank=True, related_name="inventory_items"
    )
    parent_item = models.ForeignKey(to="inventory.InventoryItem", on_delete=models.CASCADE, null=True, blank=True, related_name="variations")

    is_taxable = models.BooleanField(default=False)
    tax_rate = models.ForeignKey(
        TaxRate, on_delete=models.SET_NULL, null=True, blank=True, related_name="inventory_items"
    )
    active = models.BooleanField(default=True)

    square_item_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    square_version = models.BigIntegerField(null=True, blank=True)

    square_item_variation_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    square_variation_version = models.BigIntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    def get_active_variations_or_self(self):
        if self.parent_item is None:
            return InventoryItem.objects.filter(
                pk=self.pk, active=True
            )
        return InventoryItem.objects.filter(
             parent_item=self, active=True
        )
