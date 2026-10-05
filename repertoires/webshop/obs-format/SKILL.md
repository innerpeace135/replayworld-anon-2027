---
name: obs-format
description: USE WHEN: generating ANY observation in [SEP]-delimited text format (SEP_SHOP convention). Enforces consistent delimiter usage, instruction echoing, and available-action lists.
---
# E-Commerce Observation Format (General)

## Search Results Page

When generating a search results page, include:
- The user's original query/instruction at the top
- Navigation elements (back to search, pagination)
- A list of 5-10 relevant products, each with:
  - Unique product identifier
  - Full product name (brand + key features)
  - Price (realistic for the category)
- Total result count and page number

## Product Detail Page

When generating a product detail page, include:
- The user's original query/instruction at the top
- Navigation (back to search, previous page)
- Product variant options (if applicable):
  - Color options (list 2-4 available colors)
  - Size options (list 3-5 available sizes)
  - Other variants (flavor, material, pack size)
- Full product name
- Price
- Rating (numeric or N/A)
- Sections: Description, Features, Reviews
- Purchase action button

## Key Rules
1. The user's query must appear consistently on every page
2. Product info must be consistent between search results and detail pages
3. Product identifier in search results must match what gets clicked
4. Most products (70%+) should have at least one variant option (color or size)
5. Prices must be realistic for the product category
6. After selecting an option, the page structure stays the same
