---
name: cnt_search_result_diversity
description: USE WHEN: generating search result pages — ensures the list contains diverse brands, price points, and attribute variations to avoid homogeneity.
---
# Search Result Diversity

## Core Principle
Real e-commerce search results contain a variety of sellers, brands, and price points. Homogenous lists (all same brand, all same price) signal simulation.

## Diversity Requirements
1. **Brand Variety**: Unless the query specifies a brand, search results must include at least 3 different brands.
2. **Price Variance**: Prices should not be uniform. Include a range (e.g., budget, mid-range, premium) even for similar items.
3. **Attribute Variance**: Items should differ in secondary attributes (e.g., material, capacity, color options) even if they match the primary category.

## Anti-Patterns
- **Monoculture**: All 10 results are from the same brand "GenericBrand".
- **Price Cloning**: All results are priced at exactly $19.99.
- **Attribute Cloning**: All results have identical descriptions with only ID changed.

## Implementation
- When generating a page of 10 items, ensure at least 50% differ in Brand or Price Tier from the first item.
