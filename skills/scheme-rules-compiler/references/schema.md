# RuleSet format and vocabulary

Rules are a flat list of groups (`root` has `parent: null`; `logic` is ALL or ANY) and conditions
(`field`, `op`, `value`, `group`, `citation{page, quote, verified}`). Evaluation uses Kleene logic:
a missing field is UNKNOWN; ALL is FALSE if any child is FALSE; ANY is TRUE if any child is TRUE.

## Fields

| field | type | unit | operators | options |
|---|---|---|---|---|
| `age_years` | number | years | >= > <= < == != |  |
| `family_annual_income_inr` | number | INR | >= > <= < == != |  |
| `applicant_annual_income_inr` | number | INR | >= > <= < == != |  |
| `residence_years_in_jurisdiction` | number | years | >= > <= < == != |  |
| `disability_percent` | number | percent | >= > <= < == != |  |
| `number_of_children` | number | count | >= > <= < == != |  |
| `gender` | category |  | == != in not_in | female, male, transgender |
| `marital_status` | category |  | == != in not_in | unmarried, married, widowed, divorced, separated, deserted |
| `social_category` | category |  | == != in not_in | general, sc, st, obc, ews |
| `is_domicile_of_jurisdiction` | boolean |  | == |  |
| `has_bpl_card` | boolean |  | == |  |
| `is_government_employee` | boolean |  | == |  |
| `receives_other_pension` | boolean |  | == |  |
| `is_student` | boolean |  | == |  |
| `is_pregnant_or_lactating` | boolean |  | == |  |

Conditions that cannot be expressed with these fields go to `unmapped_conditions` and need human verification.
