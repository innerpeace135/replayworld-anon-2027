---
name: cnt_relevant_product_selection
description: USE WHEN: generating search result items — enforces realistic relevance variance including partial matches and noise.
---
# Relevant Product Selection

## Core Principle
Search results must simulate real-world search engine behavior, which rarely returns 100% perfect matches for niche constraints.

## Relevance Distribution
- **Exact Matches (Max 60%)**: Items that fully satisfy all user constraints (type, attributes, price).
- **Partial Matches (Min 30%)**: Items that match the category but miss 1-2 constraints (e.g., wrong color, slightly out of budget, different brand).
- **Irrelevant/Noise (Min 10%)**: Items that are category-adjacent but do not meet the core request (e.g., accessories instead of main product).

## Constraint Handling
- Do NOT generate a list where every item perfectly matches a niche query (e.g., "red wool socks size 10").
- If the query is highly specific, explicitly show "No exact matches" or broaden the results with partial matches rather than hallucinating perfect availability.

## Examples
- **Query**: "Organic green tea"
- **Bad**: 10 results all labeled "Organic Green Tea".
- **Good**: 4 results "Organic Green Tea", 3 results "Green Tea (Non-organic)", 2 results "Herbal Tea", 1 result "Tea Infuser".
