---
name: reflect-user-actions
description: USE WHEN: generating a next observation after an action — verify the observation actually reflects what the action would produce (search shows new results, click shows detail page, option selection updates state).
---
# Reflect User Actions

## Guidelines
- **Product Click → Detail Page**: When the agent clicks on a product (by ID), the next observation MUST show that product's detail page with matching name, price, and options
- **Option Selection → Page Update**: When the agent selects an option (size, color, etc.), the page should update to show the selected option and any resulting changes (e.g., price adjustment)
- **Buy Now → Confirmation**: When the agent clicks "Buy Now", the page should show an order confirmation message
- **Search → Results**: When the agent searches, results must be for the searched terms
- **Consistency**: Product name and price on the detail page MUST match what was shown on the search results page
- **No Phantom Products**: Never show a product detail page for a product that wasn't in the search results
