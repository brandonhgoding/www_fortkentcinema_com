import enum
from typing import ClassVar

from django.db import models
from pydantic import BaseModel


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
    item_id: str | None = None


class CatalogItemVariation(BaseModel):
    type: str
    id: str
    item_variation_data: CatalogItemVariationData
    version: int | None = None


class CategoryParent(BaseModel):
    id: str


class CategoryData(BaseModel):
    name: str
    category_type: str = "REGULAR_CATEGORY"
    is_top_level: bool = True
    parent_category: CategoryParent | None = None


class CatalogItemData(BaseModel):
    abbreviation: str | None = None
    description: str | None = None
    name: str
    variations: list[CatalogItemVariation] | None = None
    is_taxable: bool = False


class CatalogObject(BaseModel):
    type: CatalogObjectType
    id: str
    item_data: CatalogItemData | None = None
    category_data: CategoryData | None = None
    version: int | None = None


class CatalogRequest(BaseModel):
    idempotency_key: str
    object: CatalogObject


class CatalogCategory(models.Model):
    name = models.CharField(max_length=255)
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name='subcategories'
    )
    square_id = models.CharField(max_length=255, blank=True, null=True)
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.name
