---
name: cnt_action_list_integrity
description: USE WHEN: generating ANY observation - ensures available actions list is complete, consistent, and parseable by the agent
---
# Action List Integrity

## Core Principle
The available actions list is critical for agent navigation. Incomplete or malformed action lists cause parse failures and prevent proper trajectory learning.

## Action List Requirements

### Format Consistency
- Actions must use consistent verb-noun format (e.g., "Click Buy Now", "Select Size M")
- Each action must be clearly delimited and parseable
- Action list must never be empty (provide at least one recovery action)

### Required Actions by Context

#### Search Results
- `Click [Product ID]` - for each listed product
- `Next Page` - if more results exist
- `Previous Page` - if not on first page
- `Back to Search` - always available
- `Refine Search` - optional but recommended

#### Product Detail Page
- `Buy Now` or `Add to Cart`
- `Select [Option]` - for variants (size, color, etc.)
- `Back to Search` or `Back to Results`
- `View Similar Items` - optional

#### Error/Unavailable States
- `Back to Search`
- `Try Different Query`
- `View Alternative Products`

## Common Integrity Failures
- Action list missing entirely
- Actions without clear targets (e.g., "Click" without what to click)
- Inconsistent action naming across pages
- Actions that don't match page context (e.g., "Buy Now" on out-of-stock item)
- Special characters breaking parser

## Validation Rules
1. Every observation has at least one valid action
2. Action targets are specific and unambiguous
3. Actions match current page context
4. No duplicate actions in the list
5. Actions use agent-understandable vocabulary

## Example Compliance
GOOD: `Available Actions: [Click Product 12345, Click Product 67890, Next Page, Back to Search]`
BAD: `Available Actions: [Click, Next, Back]` (ambiguous targets)
