---
name: cnt_product_attribute_specificity
description: USE WHEN: generating product details or search snippets — mandates specific brands, ingredients, and technical specs instead of generic text.
---
# Product Attribute Specificity

## Core Principle
  Product attributes MUST be specific, realistic, and varied to simulate high-fidelity e-commerce environments. Generic or repetitive data reduces agent training value.

## Specificity Requirements
  - **Brand Names**: Use realistic, varied brand names (e.g., "Sony", "Nike", "Anker") instead of "Brand A", "Brand X", or "Generic".
  - **Product Titles**: Include model numbers, colors, sizes, or key features (e.g., "Wireless Noise Cancelling Headphones WH-1000XM5 - Black" vs "Headphones").
  - **Pricing**: Use realistic price points with cents (e.g., "$19.99", "$249.50") rather than round integers ("$20", "$250") unless typical for the category.
  - **Specifications**: Include concrete technical details (e.g., "5000mAh Battery", "100% Cotton", "Intel i7 Processor") instead of "Good Battery", "Nice Material".

## Variance Enforcement
  - **Price Distribution**: Ensure search results show a range of prices, not identical pricing for all items.
  - **Attribute Diversity**: Different products should highlight different features (e.g., one emphasizes battery life, another emphasizes camera quality).
  - **Rating Realism**: Use varied star ratings (3.5, 4.2, 5.0) and review counts, not uniform 5.0 stars for all items.

## Low Fidelity Triggers to Avoid
  - Repeating the same description across multiple products.
  - Using "N/A" or "-" for optional but commonly available fields.
  - Generating technically impossible specs (e.g., negative weight, 10000% discount).
