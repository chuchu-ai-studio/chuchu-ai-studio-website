#!/usr/bin/env python3
"""Local-only, review-first AcroForm prefill. Never sends data or overwrites files."""
import argparse
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import json
import os
from pathlib import Path
import re

import pymupdf as fitz

HERE = Path(__file__).resolve().parent
CONFIG = HERE / 'inquiry_agreement_field_map.json'
REVIEW = 'REQUIRES STUDIO REVIEW'


def load_map():
    return json.loads(CONFIG.read_text(encoding='utf-8'))


def clean(value):
    text = str(value or '').replace('\r\n', '\n').replace('\r', '\n').strip()
    if len(text) > 50000 or any(ord(c) < 32 and c not in '\n\t' for c in text):
        raise ValueError('Invalid or excessively long form value')
    return text


def read_fields(doc):
    if doc.needs_pass:
        raise ValueError('Encrypted PDF: provide an unlocked copy')
    values, types = {}, {}
    for page in doc:
        for w in page.widgets() or []:
            name = w.field_name
            if not name:
                raise ValueError('Unnamed form field')
            if w.field_type == fitz.PDF_WIDGET_TYPE_CHECKBOX:
                value = clean(w.field_value)
                if value in ('', 'Off'):
                    value = False
                elif value == str(w.on_state()):
                    value = True
                else:
                    raise ValueError(f'Unrecognized checkbox state: {name}')
            else:
                value = clean(w.field_value)
            if name in values and (values[name] != value or types[name] != w.field_type_string):
                raise ValueError(f'Conflicting repeated field: {name}')
            values[name], types[name] = value, w.field_type_string
    return values, types


def validate_inquiry(doc, config):
    values, types = read_fields(doc)
    title = ' '.join(doc[0].get_text().split()) if len(doc) else ''
    if len(doc) != 2 or 'CHUCHU AI STUDIO' not in title or 'Client Project Inquiry & Discovery Form' not in title:
        raise ValueError('Not the supported CHUCHU AI STUDIO Inquiry & Discovery Form')
    missing = [key for key, kind in config['inquiry_required_schema'].items() if types.get(key) != kind]
    if missing:
        raise ValueError('Missing/incompatible inquiry fields (possibly flattened PDF): ' + ', '.join(missing))
    if 'client_address' in types and types['client_address'] != 'Text':
        raise ValueError('client_address must be a text field')
    return values


def selected(values, mapping):
    return [label for field, label in mapping.items() if values.get(field) is True]


def compact(text):
    return ' '.join(clean(text).split())


def draft_values(values, config):
    result = {}
    for source, targets in config['direct'].items():
        value = values.get(source, '')
        if source == 'company_name' and not value:
            value = values.get(config['company_fallback'], '')
        for target in targets:
            result[target] = value
    types = selected(values, config['project_types'])
    result['project_type'] = types[0] if len(types) == 1 else ''
    result['platforms'] = ', '.join(selected(values, config['platforms']))
    objective = []
    if values.get('product_summary'):
        objective.append('Client proposes: ' + compact(values['product_summary']))
    if values.get('problem_users'):
        objective.append('Purpose / users: ' + compact(values['problem_users']))
    features = selected(values, config['features'])
    requested = []
    if values.get('must_haves'):
        requested.append('Requested priorities: ' + compact(values['must_haves']))
    if features:
        requested.append('Requested features: ' + '; '.join(features))
    for field, label in [('feat_other_text', 'Other requests'), ('ai_technical_goal', 'Technical context')]:
        if values.get(field):
            requested.append(label + ': ' + compact(values[field]))
    terms = []
    assets = selected(values, config['assets'])
    if assets:
        terms.append('Client reports assets: ' + ', '.join(assets) + '. Confirm availability and responsibilities.')
    sensitivity = selected(values, {'sensitive_yes': 'Yes', 'sensitive_no': 'No', 'sensitive_unsure': 'Unsure'})
    if sensitivity:
        terms.append('Client-reported sensitive data: ' + ', '.join(sensitivity) + '. Confirm handling requirements.')
    if values.get('sensitive_notes'):
        terms.append('Data-handling context: ' + compact(values['sensitive_notes']))
    # Long/ambiguous free text stays in the report, never silently becomes a contractual term.
    if values.get('success_criteria'):
        terms.append('Client success criteria require acceptance review; see review report.')
    if values.get('additional_notes'):
        terms.append('Client notes require scope/terms review; see review report.')
    drafts = {'project_objective': ' '.join(objective), 'included_features': '\n'.join(requested),
              'additional_terms': '\n'.join(terms)}
    for field, value in drafts.items():
        result[field] = REVIEW + '\n' + value if value else ''
    return result, drafts


def apply_studio(result, config, studio):
    allowed = set(config['studio_controlled']) | {'project_objective', 'included_features', 'additional_terms', 'project_type', 'platforms'}
    if set(studio) - allowed:
        raise ValueError('Unsupported Studio configuration keys: ' + ', '.join(sorted(set(studio) - allowed)))
    for key, value in studio.items():
        if not isinstance(value, (str, int, float)) or isinstance(value, bool):
            raise ValueError(f'Studio value must be text or a number: {key}')
        result[key] = clean(value)
    if 'total_fee' in studio:
        currency = result.get('payment_currency', '')
        if not re.fullmatch(r'[A-Z]{3}', currency):
            raise ValueError('Approved fee requires a three-letter payment_currency, e.g. USD or PHP')
        try:
            fee = Decimal(str(studio['total_fee']))
        except InvalidOperation as exc:
            raise ValueError('total_fee must be a plain decimal, e.g. 4800.00') from exc
        if not fee.is_finite() or fee <= 0 or fee != fee.quantize(Decimal('.01')):
            raise ValueError('total_fee must be positive with at most two decimal places')
        amounts = {}
        for key, share in list(config['milestones'].items())[:-1]:
            amounts[key] = (fee * Decimal(share)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
        amounts['handover_15'] = fee - sum(amounts.values())
        result['total_fee'] = f'{currency} {fee:,.2f}'
        result.update({key: f'{currency} {amount:,.2f}' for key, amount in amounts.items()})


def display_text(text):
    # Keep typographic substitutions limited to equivalent punctuation supported by Helvetica.
    return text.translate(str.maketrans({'—': '-', '–': '-', '’': "'", '‘': "'", '“': '"', '”': '"', '\u00a0': ' '}))


def fits(text, rect, size, multiline):
    font = fitz.Font('helv')
    width = rect.width - 8
    if not multiline:
        return '\n' not in text and font.text_length(text, fontsize=size) <= width
    lines = 0
    for paragraph in text.split('\n'):
        line = ''
        lines += 1
        for word in paragraph.split():
            if font.text_length(word, fontsize=size) > width:
                return False
            candidate = (line + ' ' + word).strip()
            if font.text_length(candidate, fontsize=size) > width:
                lines += 1
                line = word
            else:
                line = candidate
    return lines * size * 1.25 <= rect.height - 6


def populate(doc, result, config, warnings):
    emitted = {}
    for page in doc:
        for w in page.widgets() or []:
            key = w.field_name
            if key not in result and key not in config['always_blank']:
                continue
            value = '' if key in config['always_blank'] else result[key]
            value = display_text(value)
            try:
                value.encode('cp1252')
            except UnicodeEncodeError as exc:
                raise ValueError(f'{key}: characters unsupported by the master Helvetica font; prepare a Unicode-font copy manually. No output written.') from exc
            multiline = bool(w.field_flags & fitz.PDF_TX_FIELD_IS_MULTILINE)
            if not multiline:
                value = compact(value)
            size = 8
            for candidate in (8, 7.5, 7):
                size = candidate
                if fits(value, w.rect, size, multiline):
                    break
            else:
                if key not in config['draft_sources'] or not value.startswith(REVIEW):
                    raise ValueError(f'{key} will not fit legibly in the master field; shorten/confirm it before generating. No output written.')
                suffix = ' [Continued in review report.]'
                while value and not fits(value + suffix, w.rect, size, multiline):
                    value = value.rsplit(' ', 1)[0] if ' ' in value else ''
                value += suffix
                warnings.append(f'{key}: shortened visibly to fit; full draft retained in the review report.')
            w.field_value = value
            w.text_fontsize = size
            w.update()
            emitted[key] = value
    return emitted


def make_report(values, result, drafts, emitted, config, warnings, studio):
    sections = []
    def section(title, lines):
        sections.append(title + '\n' + '\n'.join('- ' + line for line in lines))
    section('INTERNAL DRAFT - REQUIRES STUDIO REVIEW', [
        'Client requests are not approved contractual scope. Do not send this draft for signature.',
        'Confirm representative identity and legal signing authority; decision maker is reference only.',
        'Review project type and platforms before agreeing to deliver them.',
        'Client signature and date intentionally blank. No signature has been generated.'])
    section('CLIENT DETAILS TRANSFERRED', [f'{key}: {result.get(key) or "NOT PROVIDED"}' for key in config['required_client_details']])
    section('PROJECT INFORMATION', ['Selected project type(s): ' + (', '.join(selected(values, config['project_types'])) or 'NOT PROVIDED'),
        'Agreement project_type: ' + (result.get('project_type') or 'STUDIO MUST SELECT ONE'),
        'Platforms: ' + (result.get('platforms') or 'NOT PROVIDED')])
    section('CLIENT REQUESTS', [f'{key}: {values.get(key) or "Not provided"}' for key in ['must_haves', 'feat_other_text', 'ai_technical_goal']] +
        ['Selected feature requests: ' + '; '.join(selected(values, config['features']))])
    section('CLIENT PREFERENCES', [f'{label}: {values.get(key) or "Not provided"}' for key, label in [
        ('budget_range', 'Client stated budget'), ('target_date', 'Client preferred target date'),
        ('preferred_contact', 'Preferred communication method'), ('decision_maker', 'Decision maker (authority unconfirmed)')]])
    section('ADDITIONAL CLIENT CONTEXT - REFERENCE ONLY', [f'{key}: {values.get(key) or "Not provided"}' for key in [
        'product_summary', 'problem_users', 'success_criteria', 'additional_notes', 'sensitive_notes']] +
        ['Assets: ' + '; '.join(selected(values, config['assets']))])
    section('DRAFTED AGREEMENT FIELDS - REQUIRES STUDIO REVIEW', [f'{key}:\n{value or "Not enough information"}' for key, value in drafts.items()])
    section('ACTUAL PDF VALUES', [f'{key}: {value or "BLANK"}' for key, value in emitted.items()])
    section('STUDIO ACTION REQUIRED', [
        'Confirm final project name, primary type and platforms.',
        'Approve/rewrite included features; move deferred requests to excluded/future features.',
        'Define deliverables and acceptance criteria.',
        'Approve start date, delivery estimate, final fee and currency; client preferences are not commitments.',
        'Assign agreement number, effective date and jurisdiction.',
        'Confirm provider legal identity, addresses, contacts, any special terms and signatory authority.',
        'Review all fields below, including Studio overrides, before sharing.'])
    missing = [key for key in config['required_client_details'] + config['required_studio_details'] +
               ['project_type', 'platforms', 'project_objective', 'included_features'] if not result.get(key)]
    section('MISSING INFORMATION', missing or ['None of the configured pre-signing fields are blank; Studio review still required.'])
    section('EXPLICIT STUDIO OVERRIDES', [f'{key}: {value}' for key, value in studio.items()] or ['None. No client budget/date converted to Studio commitments.'])
    section('PAYMENT MILESTONES', [f'{key}: {result.get(key) or "Not calculated - approved total_fee required"}' for key in config['milestones']] +
        ['Calculated only from explicit approved total_fee. Final installment absorbs cent rounding so installments sum exactly to fee.'])
    section('WARNINGS', warnings or ['None.'])
    return '\n\n'.join(sections) + '\n'


def generate(inquiry, output, studio=None):
    config = load_map()
    studio = studio or {}
    inquiry, output = Path(inquiry).resolve(), Path(output).resolve()
    master = (HERE / config['agreement_master']).resolve()
    report = output.with_name(output.stem + '_REVIEW.txt')
    templates = master.parent
    if output.suffix.lower() != '.pdf' or output == inquiry or templates in output.parents:
        raise ValueError('Output must be a NEW .pdf outside templates and cannot replace the inquiry')
    if output.exists() or report.exists():
        raise ValueError('Output or review report already exists; choose a new output filename')
    if not output.parent.is_dir():
        raise ValueError('Create the client output directory first')
    if hashlib.sha256(master.read_bytes()).hexdigest() != config['original_master_sha256']['agreement']:
        raise ValueError('Agreement master changed: inspect and update the field map/checksum deliberately')
    with fitz.open(inquiry) as source:
        values = validate_inquiry(source, config)
    warnings = []
    if not values.get('client_address'):
        warnings.append('Client address unavailable. Collect it using the updated inquiry; never invent a real address.')
    if len(selected(values, config['project_types'])) != 1:
        warnings.append('Select/confirm one primary project type. Ambiguous selections are left blank in the Agreement.')
    if values.get('platform_unsure') and len(selected(values, config['platforms'])) > 1:
        warnings.append('Platforms include Not sure and concrete platforms; confirm scope.')
    if values.get('asset_none') and len(selected(values, config['assets'])) > 1:
        warnings.append('Client asset selections conflict: None yet plus supplied assets.')
    if sum(values.get(k) is True for k in ['sensitive_yes','sensitive_no','sensitive_unsure']) > 1:
        warnings.append('Client sensitive-data selections conflict; confirm requirements.')
    result, drafts = draft_values(values, config)
    apply_studio(result, config, studio)
    with fitz.open(master) as doc:
        current, _ = read_fields(doc)
        if set(config['agreement_required_fields']) - set(current):
            raise ValueError('Agreement schema mismatch')
        emitted = populate(doc, result, config, warnings)
        pdf_bytes = doc.tobytes(deflate=True)
    report_text = make_report(values, result, drafts, emitted, config, warnings, studio)
    # Exclusive creation: no overwrite even if a destination appears after validation.
    created = []
    try:
        for path, content in [(output, pdf_bytes), (report, report_text.encode('utf-8'))]:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            created.append(path)
            with os.fdopen(fd, 'wb') as f:
                f.write(content)
    except Exception:
        for path in created:
            path.unlink()
        raise
    return output, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('inquiry', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--studio-config', type=Path, help='Explicit reviewed field overrides as a JSON object')
    parser.add_argument('--total-fee', help='Final approved plain decimal amount; never read from inquiry budget')
    parser.add_argument('--payment-currency', help='Three-letter currency, e.g. USD')
    args = parser.parse_args()
    try:
        studio = json.loads(args.studio_config.read_text(encoding='utf-8')) if args.studio_config else {}
        if not isinstance(studio, dict):
            raise ValueError('Studio config must be a JSON object')
        if args.total_fee is not None:
            studio['total_fee'] = args.total_fee
        if args.payment_currency is not None:
            studio['payment_currency'] = args.payment_currency
        output, report = generate(args.inquiry, args.output, studio)
    except (ValueError, OSError, RuntimeError) as exc:
        parser.exit(2, f'Error: {exc}\n')
    print(f'Created draft: {output}\nStudio review report: {report}')

if __name__ == '__main__':
    main()
