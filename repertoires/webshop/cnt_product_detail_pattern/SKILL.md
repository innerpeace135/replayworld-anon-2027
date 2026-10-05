---
name: cnt_product_detail_pattern
description: USE WHEN: observation shows a single AVAILABLE item with detailed attributes. Do not use for unavailable items.
---
# Product Detail Page Patterns (Available Items)

## Prerequisites
- **ONLY** use this pattern if the item is confirmed **available**.
- If the item is unavailable, out of stock, or ID is invalid, use `cnt_error_state_handling` instead.

## Attribute Rules
- **Price/Options/Ratings:** Valid ONLY for available items.
- **Buy Button:** Only include if item is purchasable.
- **Consistency:** Ensure attributes match the search result listing for this item.

## Option Types
- Size, Color, Flavor options should be presented as selectable only if in stock.
- If specific options are out of stock, mark them as 'Unavailable' rather than removing the product entirely (unless all options are gone).
