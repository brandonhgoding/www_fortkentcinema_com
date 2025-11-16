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


class CatalogPriceMoney(BaseModel):
    amount: int
    currency: str = "USD"


class CatalogItemVariationData(BaseModel):
    name: str
    price_money: CatalogPriceMoney
    pricing_type: str = "FIXED_PRICING"
    is_taxable: bool = False
    tax_ids: list[str] = []
    item_id: str | None = None


class CatalogItemVariation(BaseModel):
    # Type is fixed for this model; you rarely need to override
    type: Literal["ITEM_VARIATION"] = "ITEM_VARIATION"
    id: str | None = None
    item_variation_data: CatalogItemVariationData
    version: int | None = None


class CategoryData(BaseModel):
    name: str
    category_type: str = "REGULAR_CATEGORY"
    is_top_level: bool = True
    parent_category_id: str | None = None


class CatalogItemData(BaseModel):
    name: str
    description: str | None = None
    abbreviation: str | None = None
    variations: list[CatalogItemVariation] = []
    is_taxable: bool = False
    tax_ids: list[str] = []
    # store raw category IDs instead of nested objects
    categories: list[str] = []


class CatalogObject(BaseModel):
    type: CatalogObjectType
    id: str | None = None
    item_data: CatalogItemData | None = None
    category_data: CategoryData | None = None
    version: int | None = None


# Django models unchanged
class CatalogCategory(models.Model):
    name = models.CharField(max_length=255)
    parent = models.ForeignKey(
        "self", on_delete=models.CASCADE, blank=True, null=True, related_name="subcategories"
    )
    square_id = models.CharField(max_length=255, blank=True, null=True)
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class TaxRate(models.Model):
    name = models.CharField(max_length=100)
    percentage = models.DecimalField(max_digits=5, decimal_places=3)
    square_id = models.CharField(max_length=255, blank=True, null=True)
    active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} ({self.percentage}%)"
