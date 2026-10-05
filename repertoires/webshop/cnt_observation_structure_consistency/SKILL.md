---
name: cnt_observation_structure_consistency
description: USE WHEN: generating ANY observation - ensures structural consistency across all page types for reliable agent parsing
---
# Observation Structure Consistency

## Core Principle
Observations must follow a consistent structural pattern within each page type. Inconsistent structure causes parsing errors and reduces trajectory learning quality.

## Structure Templates

### Search Results Structure
```
[Page Header]
- Search Query: [query text]
- Results Count: [N] items
- Page: [N] of [M]

[Product List]
[SEP]
- ID: [product_id]
- Name: [product_name]
- Price: [price]
- Status: [availability]
[SEP]
- ID: [product_id]
- Name: [product_name]
- Price: [price]
- Status: [availability]

[Navigation]
- Available Actions: [action list]
```

### Product Detail Structure
```
[Product Header]
- ID: [product_id]
- Name: [product_name]
- Price: [price]
- Status: [availability]

[Product Details]
- Description: [description]
- Options: [variants if applicable]
- Reviews: [rating summary]

[Actions]
- Available Actions: [action list]
```

## Consistency Rules

### Field Order
- Maintain same field order within each page type
- Don't reorder fields between observations of same type

### Field Naming
- Use identical field names across all observations
- No variations (Price vs. price vs. Cost)

### Section Headers
- Include section headers for clarity
- Use consistent header format

### Delimiter Usage
- Use [SEP] consistently between products
- Don't mix delimiter styles

## Common Inconsistency Issues
- Different field orders between similar pages
- Missing section headers on some pages
- Inconsistent product ID labeling
- Variable action list formatting
- Mixed delimiter usage

## Quality Indicators
- Agent can parse 100% of observations without errors
- Same page type produces structurally identical observations
- Field names are predictable and consistent
- No surprise structural changes mid-trajectory

## Validation Before Output
1. ✓ Structure matches page type template
2. ✓ Field order is consistent with previous observations
3. ✓ All section headers present
4. ✓ Delimiters used consistently
5. ✓ Action list format matches previous observations
