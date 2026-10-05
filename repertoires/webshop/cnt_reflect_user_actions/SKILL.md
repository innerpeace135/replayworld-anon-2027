---
name: cnt_reflect_user_actions
description: USE WHEN: generating a next observation after an action. Ensures observation matches the action's outcome, tool context, and query domain.
---
# Reflect User Actions & Tool Context

## Core Principle
  The World Model MUST generate observations that logically follow the agent's previous action. State transitions must be verifiable and consistent with e-commerce logic.

## State Transition Requirements
  - **Search Action**: Observation MUST show search results relevant to the query, not a product detail page or home page.
  - **Click Product**: Observation MUST transition from Search Results to Product Detail Page (PDP) for the specific clicked item ID.
  - **Pagination (Next/Prev)**: Observation MUST show a different set of products and update the page number indicator (e.g., Page 1 -> Page 2).
  - **Add to Cart/Buy**: Observation MUST reflect a confirmation state, cart update, or checkout flow, not return to search results immediately unless specified.
  - **Back Navigation**: Observation MUST return to the previous valid state (e.g., PDP -> Search Results).

## Consistency Checks
  - **Item Identity**: If viewing a product detail, the Title, Price, and ID must match the item selected in the previous step.
  - **Query Relevance**: Search results must contain items matching the search terms, not random unrelated products.
  - **No Hallucinated States**: Do not generate a "Success" message if the action was invalid or the item was out of stock.

## Failure Mode Prevention
  - Avoid generating the exact same observation after a navigation action.
  - Avoid skipping intermediate states (e.g., jumping from Search to Checkout without PDP).
