---
name: cnt_error_state_handling
description: USE WHEN: an action results in failure, item unavailability, or navigation error. Prevents hallucination of actionable elements.
---
# Error State Handling & Fidelity

## When to Trigger
  - Action fails (API error, timeout).
  - Item is out of stock/unavailable.
  - Navigation leads to dead end (404).

## Error Message Fidelity
  1. **Realistic Error Codes**: Use standard HTTP/API status codes (e.g., `404 Not Found`, `503 Service Unavailable`, `400 Bad Request`) where applicable.
  2. **Specific Error Text**: Match the tone and structure of real API error messages.
     - **Bad**: "Error happened."
     - **Good**: "Error 404: Product ID B08N5KWB9H not found in catalog."
  3. **No Hallucinated Actions**: Do not offer actionable buttons (e.g., "Buy Now") on error pages unless the error page specifically provides recovery actions (e.g., "Try Again").
  4. **Consistent State**: If an item is unavailable, the observation must clearly state "Out of Stock" or "Unavailable" rather than showing a normal product page.

## Recovery Guidance
  - Provide clear next steps for the agent (e.g., "Return to Search", "Contact Support").
  - Ensure the error state is parseable and distinct from success states.

## Example (Correct)
  ```
  Status: 404
  Message: Item unavailable.
  Action: [Back to Search]
  ```

## Example (Incorrect)
  ```
  Status: Success
  Message: Error
  Action: [Buy Now] (Hallucinated on error page)
  ```
