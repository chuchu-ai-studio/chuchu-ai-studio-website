# Inquiry → Agreement pre-fill

This local tool copies duplicate facts and prepares an **internal draft**, not a ready-to-sign contract. The Inquiry records what the client wants; the Agreement records what CHUCHU AI STUDIO approves. No AI service, network upload, email, or signature generation is used.

## Canonical files

Paths are relative to `business-documents/`:

- **Original Inquiry, preserved:** `templates/CHUCHU_AI_STUDIO_Client_Project_Inquiry_Form.pdf`
- **New Inquiry to use going forward:** `templates/CHUCHU_AI_STUDIO_Client_Project_Inquiry_Form_With_Address.pdf`
- **Agreement master, preserved:** `templates/CHUCHU_AI_STUDIO_Master_Service_Agreement_Fillable.pdf`

The new Inquiry adds `client_address` on page 1 below Email/Phone, in Client Information. All original fields remain in place and page 2 is unchanged. Both original master files retain their recorded SHA-256 checksums. Do not overwrite them. `prepare_inquiry_address.py` documents how the versioned copy was made and refuses to replace an existing output.

`pdf_field_inventory.json` records the inspected AcroForm names, widget types, page positions, and original checksums. It does not retain sample client answers. `inquiry_agreement_field_map.json` is the active mapping/configuration.

## Setup

From the website repository root:

```bash
python3 -m venv business-documents/internal/.venv
business-documents/internal/.venv/bin/pip install -r business-documents/internal/requirements.txt
source business-documents/internal/.venv/bin/activate
```

After activation, the requested command works:

```bash
python3 business-documents/internal/prefill_agreement_from_inquiry.py \
  "<completed client inquiry.pdf>" \
  --output "<new client agreement.pdf>"
```

Create the client destination directory first (normally its `02_Contract/` folder). The output must be a new filename outside `templates/`. The script also creates `<new client agreement>_REVIEW.txt` beside it. If either destination already exists, it refuses to overwrite. Input PDFs and templates are read-only. Output files are created with owner-only filesystem permissions where supported.

## Automatic mappings

| Inquiry | Agreement | Behavior |
| --- | --- | --- |
| `client_name` | `client_rep`, `client_name` | Copy into representative and signature **name** fields; confirm legal authority separately. |
| `company_name` | `client_company` | Fall back to `client_name` for an individual. |
| `job_title` | every `client_title` widget | Includes client details and signature page. |
| `client_email` | every `client_email` widget | Includes both email occurrences. |
| `client_phone` | `client_phone` | Direct copy. |
| `client_address` | `client_address` | Direct copy; old inquiries produce a missing-address warning. |
| One `svc_*` selection | `project_type` | Exact requested service mapping from the JSON. None/multiple selections leave this field blank and require Studio selection. |
| Selected `platform_*` fields | `platforms` | Comma-separated mapped names. Conflicting “Not sure” selections are flagged. |
| `product_summary`, `problem_users` | `project_objective` | Short source-based draft, with no invented features or outcomes. |
| `must_haves`, all selected `feat_*`, `feat_other_text`, `ai_technical_goal` | `included_features` | Client-request draft only, not approved scope. |
| Selected `asset_*`, sensitive-data answers/notes | `additional_terms` | Concise operational context requiring confirmation. |
| `success_criteria`, `additional_notes` | Review report + pointer in `additional_terms` | Full answers retained internally; not blindly copied into contractual obligations. |

Objective, included features, and additional terms visibly start with **REQUIRES STUDIO REVIEW**. Complete source answers and full draft candidates remain in the report. If a draft exceeds its existing field rectangle, it is shortened with an explicit review-report pointer, not silently clipped. No field geometry or Agreement wording changes. Factual values that cannot fit legibly cause an error rather than silent truncation.

`target_date`, `budget_range`, `decision_maker`, and `preferred_contact` are report-only references. Even a budget answer saying “total project fee” is not treated as an approved fee. The decision maker is not assumed to be the legal signatory. Project type and platforms also require scope confirmation.

## Studio approval and payment amounts

The default run does not set agreement number, effective date, jurisdiction, currency, provider details, Studio signature details, project name, exclusions, deliverables, start/delivery dates, total fee, or payment currency. It leaves these master values untouched. Client signature and client date are always cleared and cannot be set through configuration.

After reviewing scope and approving a quote, enter the final fee explicitly:

```bash
python3 business-documents/internal/prefill_agreement_from_inquiry.py \
  "<completed client inquiry.pdf>" \
  --output "<new reviewed client agreement.pdf>" \
  --total-fee 4800.00 \
  --payment-currency USD
```

This calculates `deposit_30`, `development_30`, `beta_25`, and `handover_15`: USD 1,440.00, USD 1,440.00, USD 1,200.00, and USD 720.00. Use a plain positive decimal with at most two decimal places and a three-letter currency code. The first three amounts round to the nearest cent; the final handover amount absorbs any cent rounding so all installments total the fee. Display uses an unambiguous currency code, such as `USD` or `PHP`.

**Calculations run when the tool runs.** Editing `total_fee` later in a PDF viewer does not recalculate milestones. Rerun with the final reviewed amount to a new filename. The tool deliberately does not rely on PDF JavaScript, whose support varies across viewers. This version uses two-decimal currency amounts; do not use it for currencies/contracts needing a different minor-unit convention without adapting and testing the calculation.

For other deliberately approved Studio values, pass `--studio-config "<reviewed values.json>"`. Allowed keys are `studio_controlled` in the mapping plus reviewed `project_objective`, `included_features`, `additional_terms`, `project_type`, and `platforms`. Unknown keys and client-signature/date overrides are rejected. CLI fee/currency options override their JSON equivalents.

Example structure (illustrative only; never assume these are approved for a real client):

```json
{
  "project_name": "Studio-approved project name",
  "included_features": "User accounts; activity catalog; booking requests; booking confirmations.",
  "excluded_features": "Payments; AI assistant; advanced analytics.",
  "total_fee": "4800.00",
  "payment_currency": "USD"
}
```

Reviewed overrides replace the generated draft in those fields, while the report still retains the original requests and draft. Edit/signature approval remains a human step. Do not change the schema or stored master checksum merely to bypass validation; inspect a new master’s fields before deliberately updating the map.

## Input checks and limitations

- Requires a two-page CHUCHU AI STUDIO Client Project Inquiry & Discovery Form with the inspected field names and types. This is schema/branding validation, not proof of authenticity or client identity.
- Handles the original inquiry without an address and the new version with the address.
- Rejects flattened/wrong-schema PDFs, encrypted PDFs requiring passwords, conflicting repeated field values, unknown checkbox states, and unusually large/invalid text values.
- Reads checkbox export states rather than treating the literal `Off` as truthy.
- Helvetica-based master fields support Western text; equivalent punctuation is normalized. Unsupported characters cause a clear error instead of an unreadable generated document. Arrange a reviewed Unicode-font template for such clients.
- Existing field values remain editable; no flattening or simulated signatures.
- Keep completed inquiries, configurations, generated agreements, reports, and QA samples out of the public repository. This task does not stage or publish anything.

## Samples and verification

Original supplied sample (read-only): `SAMPLES/CHUCHU_AI_STUDIO_Client_Project_Inquiry_Form_SAMPLE_FILLED.pdf` at the website root. It has no address.

Generated files under `internal/samples/`:

- `Sample_Inquiry_With_Address.pdf`: copy of that sample with **123 Sample Street, Sample City (SYNTHETIC TEST ADDRESS ONLY)** for address-transfer QA. This address was not inferred from a client answer.
- `Sample_Agreement_Review_Draft.pdf` and `_REVIEW.txt`: primary review sample; fee, dates, exclusions, deliverables, and signatures remain blank.
- `Sample_Original_Inquiry_Agreement.pdf` and `_REVIEW.txt`: original inquiry without address; missing-address report demonstrated.
- `Sample_Approved_Fee_Agreement.pdf` and `_REVIEW.txt`: separate explicit USD 4,800 test of 30/30/25/15 payments; not an approval of a real quote.

Run tests:

```bash
business-documents/internal/.venv/bin/python business-documents/internal/test_inquiry_automation.py
```

Tests check exact field transfers and repeated widgets, individual-client fallback, all service/platform/feature mappings, ambiguous selections, no budget/date binding, blank signatures, explicit fee calculations/rounding, invalid config, wrong-schema forms, duplicate fields, no-overwrite behavior, original master checksums, unchanged Agreement backgrounds, unchanged original Inquiry fields, and post-generation editability.

Review the generated Agreement together with its report. Finalize scope, exclusions, deliverables, fees/currency, legal details, dates and signatory authority before issuing a client-facing Agreement. Only the client supplies their signature/date.
