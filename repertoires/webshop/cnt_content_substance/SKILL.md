---
name: cnt_content_substance
description: USE WHEN: generating ANY observation - mandates meaningful, non-empty semantic content in all descriptive fields to prevent hollow observations.
---
# Content Substance & Semantic Density

## Core Principle
  Generated observations must contain rich, substantive semantic content. Empty, generic, or placeholder text is prohibited.

## Content Requirements
  1. **Descriptive Fields**: Titles, descriptions, and features must be specific and informative (min 10 words for descriptions).
     - **Bad**: "High quality product."
     - **Good**: "Premium stainless steel water bottle with double-wall vacuum insulation, keeps drinks cold for 24 hours."
  2. **Attribute Specificity**: 
     - Include brand names, model numbers, colors, sizes, and materials where applicable.
     - Avoid generic terms like "Item" or "Product".
  3. **No Placeholders**: Do not use "Lorem Ipsum", "TBD", "To Be Announced", or repeated generic text.
  4. **Contextual Relevance**: Content must match the query category (e.g., electronics specs for electronics, fabric details for clothing).

## Density Check
  - Before finalizing, verify that no text field is < 5 characters unless it is a code/ID.
  - Ensure the observation provides enough information for the agent to make a decision.

## Example (Correct)
  - Title: "Sony WH-1000XM5 Wireless Headphones - Black"
  - Description: "Industry-leading noise cancellation with Auto NC Optimizer. Up to 30-hour battery life with quick charging."

## Example (Incorrect)
  - Title: "Headphones"
  - Description: "Good sound quality."
  - Specs: "N/A"
