---
name: product-detail-pattern
description: USE WHEN: observation shows a single item with detailed attributes (size, color, flavor options), price, description, and a 'Buy Now' button. Typical for SEP_SHOP product detail pages after clicking an item ID.
---
# Product Detail Page Patterns (General)

## Option Types and Distribution
- Common option types: size, color, flavor, style, material, scent, pack size
- Most products (>70%) have options that should be selected before purchasing
- ~85% have at least one option type
- ~15% have TWO option types (e.g., both size AND color)
- Each option type should list 2-4 selectable values
- Products without any options are uncommon (<30%)

## Product Info Structure
- Show: Full product name, Price, Rating
- Rating: numeric (e.g., "4.5") or "N/A" for unrated
- Include navigation (back to search, previous page)
- Include sections: Description, Features, Reviews
- Include purchase action
- Price and name must be consistent with search results page

## Trajectory Flow Patterns
- Average 4-5 steps per successful purchase
- ~70% of trajectories include option selection (size/color)
- Common flows:
  - search → click product → buy (3 steps, no options, ~30%)
  - search → click → select 1 option → buy (4 steps, ~35%)
  - search → click → select 2 options → buy (5 steps, ~25%)
  - search → click → select 3 options → buy (6 steps, ~8%)
  - search → browse next page → click → ... (~2%)

## Key Principles
- Products with BOTH size AND color are common → 5-step trajectories
- Pagination should appear occasionally when first page is insufficient
- Back-to-search happens when product is not a good match
- Diverse trajectory patterns teach flexible shopping strategies
