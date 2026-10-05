---
name: cnt_actionable_observation_content
description: USE WHEN: generating ANY observation. Mandates presence of decision-critical data fields required for agent logic (Price, Stock, Navigation).
---
# Actionable Observation Content

## Core Principle
  Every observation MUST contain sufficient semantic information for the agent to make a logical next decision. Observations with missing or generic decision-critical fields are invalid.

## Decision-Critical Field Requirements
  - **Product Listings**: Every item in a search result MUST include:
    - **Price**: Specific numeric value (e.g., "$24.99", not "See Price").
    - **Availability**: Clear status (e.g., "In Stock", "Only 2 left", not "Unknown").
    - **Title**: Descriptive name allowing relevance judgment.
    - **ID**: Unique identifier for selection actions.
  - **Product Details**: MUST include:
    - **Full Description**: Features, specs, or ingredients.
    - **Action Buttons**: Clear availability of "Add to Cart", "Buy Now", or "Back".
  - **Navigation**: MUST include valid targets (e.g., "Page 2", "Next", "Back to Results").

## Prohibited Content Patterns
  - **Placeholder Text**: Do not use "Lorem Ipsum", "Product Name", or "Price TBD".
  - **Empty Actions**: Do not list actions in the `available_actions` field that are not supported by the observation content (e.g., listing "Buy" when price is missing).
  - **Ambiguous States**: Avoid vague status messages like "Something happened". Use specific state descriptions.

## Agent Usability Test
  - Ask: "Can the agent decide whether to buy, click, or search next based solely on this text?"
  - If No, the observation content is insufficient.
