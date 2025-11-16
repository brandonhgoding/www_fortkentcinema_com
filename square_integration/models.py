import enum
from django.db import models
from pydantic import BaseModel
from typing import Literal


class CatalogObjectType(enum.Enum):
    IMAGE = "IMAGE"
    CATEGORY = "CATEGORY"
    ITEM = "ITEM"
    ITEM_VARIATION = "ITEM_VARIATION"
    TAX = "TAX"
    DISCOUNT = "DISCOUNT"
    MODIFIER_LIST = "MODIFIER_LIST"
    MODIFIER = "MODIFIER"
    PRICING_RULE = "PRICING_RULE"
    PRODUCT_SET = "PRODUCT_SET"
    TIME_PERIOD = "TIME_PERIOD"
    MEASUREMENT_UNIT = "MEASUREMENT_UNIT"
    SUBSCRIPTION_PLAN_VARIATION = "SUBSCRIPTION_PLAN_VARIATION"
    ITEM_OPTION = "ITEM_OPTION"
    ITEM_OPTION_VAL = "ITEM_OPTION_VAL"
    CUSTOM_ATTRIBUTE_DEFINITION = "CUSTOM_ATTRIBUTE_DEFINITION"
    QUICK_AMOUNTS_SETTINGS = "QUICK_AMOUNTS_SETTINGS"
    SUBSCRIPTION_PLAN = "SUBSCRIPTION_PLAN"
    AVAILABILITY_PERIOD = "AVAILABILITY_PERIOD"


class SquareItem(models.Model):
    square_id = models.CharField(max_length=255, blank=True, null=True)
    version = models.BigIntegerField(blank=True, null=True)

    def get_item_type(self) -> CatalogObjectType:
        raise NotImplementedError("Subclasses must implement get_item_type method")


# Django models unchanged
class CatalogCategory(SquareItem):
    name = models.CharField(max_length=255)
    parent = models.ForeignKey(
        "CatalogCategory", on_delete=models.RESTRICT, blank=True, null=True, related_name="subcategories"
    )
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

    def get_item_type(self) -> CatalogObjectType:
        return CatalogObjectType.CATEGORY


class TaxRate(SquareItem):
    name = models.CharField(max_length=100)
    percentage = models.DecimalField(max_digits=5, decimal_places=3)
    active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} ({self.percentage}%)"

    def get_item_type(self) -> CatalogObjectType:
        return CatalogObjectType.TAX


class Item(SquareItem):
    name = models.CharField(max_length=255, default="Regular Item")
    description = models.TextField(blank=True, null=True, default="This is the default variation of this item")
    abbreviation = models.CharField(max_length=10, blank=True, null=True)
    categories = models.ManyToManyField(CatalogCategory, related_name="items", blank=True)
    is_taxable = models.BooleanField(default=False)
    tax_rates = models.ManyToManyField(TaxRate, related_name="items", blank=True)
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

    def get_item_type(self) -> CatalogObjectType:
        return CatalogObjectType.ITEM
