---
name: search-results-pattern
description: USE WHEN: observation contains multiple items separated by [SEP] delimiters, each item has an ID and price, with 'Page N' pagination and 'Next >' navigation. Typical for SEP_SHOP search result pages after a search action.
---
# Search Results Patterns (General)

## Product Listing
- Show 5-10 products per page, listed by relevance
- Each product has: unique identifier, full product name (with brand), price
- Product names should include brand, key features, and size info when relevant
- Price ranges vary by category: electronics $15-$500, clothing $10-$80, household $5-$50
- Some products may show price ranges for multi-variant items
- Total results: 30-100 for specific queries, 100+ for broad queries

## Navigation
- Results page should have: back to search, page number, next page link
- Page numbering is sequential
- Navigation elements must always be present

## Product Relevance
- Products should be relevant to the search keywords
- At least 3-5 products should match the query's key constraints
- Include some less-relevant products for realism (not everything is a perfect match)

## State Transition
- Search action → generates results page
- The user's original query should appear at the top of the page
- Products should be relevant to search keywords
