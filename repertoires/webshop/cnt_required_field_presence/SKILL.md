---
name: cnt_required_field_presence
description: USE WHEN: generating ANY observation - ensures all mandatory parseable fields are present, non-empty, and contain valid data types.
---
# Required Field Presence & Validity

## Core Principle
  Every observation MUST contain all schema-mandatory fields. Presence alone is insufficient; fields must contain valid, parseable data.

## Mandatory Field Rules
  1. **Existence**: All fields defined in the observation schema (e.g., `product_id`, `price`, `title`, `availability`) must be present.
  2. **Non-Empty Values**: Fields cannot contain empty strings, `null`, `N/A`, `TBD`, or placeholders.
  3. **Type Correctness**: 
     - Prices must be numeric (e.g., `19.99`, not `$19.99` unless schema specifies currency symbol).
     - IDs must be alphanumeric strings (e.g., `B08N5KWB9H`, not `null`).
     - Booleans must be `true`/`false` (not `yes`/`no`).
  4. **Parse Safety**: Field values MUST NOT contain structural delimiters (e.g., `[SEP]`, `|`, `{`, `}`) unless properly escaped, to prevent parser breakdown.

## Failure Prevention
  - If data is unknown, generate a realistic plausible value consistent with the context rather than leaving it empty.
  - Validate that the generated observation can be programmatically parsed before finalizing.

## Example (Correct)
  ```
  product_id: B08N5KWB9H
  price: 24.99
  title: Wireless Noise Cancelling Headphones
  ```

## Example (Incorrect)
  ```
  product_id: [MISSING]
  price: N/A
  title: 
  ```
