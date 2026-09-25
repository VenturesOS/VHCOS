"""Pure, conservative candidate identity resolution; no database or model imports.

Codes are lookup keys, not identity proofs. Evidence points are deliberately NOT
probabilities. Only a unique, server-vetted source-profile anchor can produce
``confirmed_duplicate``; ordinary fields can suggest a match, never prove it.

The caller owns retrieval completeness and the trust boundary: it must construct
``_identity_trusted_anchors`` from server-owned data, never from request JSON.
Browser ``identity_evidence`` is an extraction hint, not trusted verification.
"""
from __future__ import annotations

import math
import re
import unicodedata
import calendar
from collections.abc import Mapping
from datetime import date

SIGNATURE_VERSION = "identity-v1"
MATCHER_VERSION = "identity-resolution-1"
SCORE_KIND = "evidence_points"
PROBABLE_THRESHOLD = 52.0
MINIMUM_MARGIN = 10.0
SOFT_SCORE_CAP = 90.0  # Always below the 100-point server-vetted source anchor.
WEIGHTS = {
    "name": 24.0,
    "name_compatible": 18.0,
    "company": 18.0,
    "title": 12.0,
    "employment_cap": 24.0,
    "location": 14.0,
    "skill": 16.0,
    "education": 10.0,
    "education_cap": 10.0,
    "experience": 6.0,
    # Longitudinal context is useful for retrieval and review, but it is capped
    # and deliberately weaker than current employment.  A shared past employer
    # or university is corroboration, not an identity proof.
    "experience_company": 8.0,
    "experience_title": 5.0,
    "experience_location": 5.0,
    "institution": 6.0,
    "certification": 4.0,
    "project": 3.0,
    "language": 2.0,
    "source_id_hint": 4.0,
    "trusted_source_profile": 100.0,
}

_PLACEHOLDERS = {
    "", "-", "--", "n/a", "na", "n.a.", "none", "null", "unknown",
    "not available", "not provided", "not disclosed", "not specified",
    "confidential", "private", "hidden", "candidate", "anonymous",
}
_FIELD_NAMES = {
    "name": "name", "full_name": "name", "name_token": "name_token",
    "company": "company", "current_employer": "company", "current_company": "company",
    "location": "location", "current_location": "location", "city": "location",
    "title": "title", "designation": "title", "current_title": "title", "current_designation": "title",
    "skill": "skill", "skills": "skill", "education": "education",
    "experience_company": "experience_company", "past_company": "experience_company",
    "company_history": "experience_company", "experience_title": "experience_title",
    "past_title": "experience_title", "experience_location": "experience_location",
    "past_location": "experience_location", "institution": "institution",
    "institute": "institution", "university": "institution", "certification": "certification",
    "certifications": "certification", "project": "project", "projects": "project",
    "language": "language", "languages": "language",
}
_ALIASES = {
    "company": {"tcs": "tata consultancy services"},
    "location": {"bombay": "mumbai"},
    "skill": {"nodejs": "node.js", "javascript": "javascript"},
}
_RAW_FIELDS = {
    "name": ("name", "full_name"),
    "company": ("current_employer", "current_company", "company"),
    "location": ("location", "current_location"),
    "title": ("designation", "current_designation", "current_title", "title"),
    "skill": ("skills", "technical_skills", "key_skills"),
    "education": ("education", "education_details", "highest_degree", "highest_qualification"),
    "experience_company": ("experience", "work_experience", "employment_history", "company_history", "previous_employers"),
    "experience_title": ("experience", "work_experience", "employment_history", "title_history"),
    "experience_location": ("experience", "work_experience", "employment_history", "location_history"),
    "institution": ("education", "education_details"),
    "certification": ("certifications", "certification"),
    "project": ("projects", "project"),
    "language": ("languages", "language"),
}
_TRUSTED_PROVENANCE = {"server_verified"}
_NAME_HONORIFICS = {"mr", "mrs", "ms", "dr", "prof", "shri", "smt"}
_MAX_CONTEXT_VALUES = 40

_HISTORY_KEYS = {
    "experience_company": ("company", "company_name", "employer", "organization", "organisation", "current_company", "current_employer"),
    "experience_title": ("title", "job_title", "designation", "current_title", "current_designation", "role", "position"),
    "experience_location": ("location", "city", "work_location", "current_location"),
    "institution": ("institution", "institute", "university", "college", "school"),
    "certification": ("name", "certification", "title", "certificate"),
    "project": ("name", "project", "title"),
    "language": ("name", "language"),
}


def normalize_text(value) -> str:
    """Normalize Unicode/case/whitespace without conflating meaningful punctuation.

    In particular C, C++, and C# stay distinct; non-Latin names remain usable.
    Unknown/masked values provide no evidence, even when both records have them.
    """
    if not isinstance(value, str):
        return ""
    value = " ".join(unicodedata.normalize("NFKC", value).casefold().split())
    if value in _PLACEHOLDERS or not any(char.isalnum() for char in value):
        return ""
    if "*" in value or "•" in value:
        return ""
    return value


def canonical_code(field: str, value) -> str:
    """Return an immutable, field-scoped canonical key, or empty for missing data.

    Alias additions that alter existing meanings require a signature version
    change and reindex. Cities in a region are never aliases of that region:
    Delhi, New Delhi, NCR, Noida, and Gurgaon are distinct codes.
    """
    field = _FIELD_NAMES.get(field, "")
    if not field:
        raise ValueError("Unsupported identity field")
    value = normalize_text(value)
    if not value:
        return ""
    alias_field = {"experience_company": "company", "experience_location": "location"}.get(field, field)
    value = _ALIASES.get(alias_field, {}).get(value, value)
    return f"{field}:{value}"


def _values(value, *, split=False, depth=0):
    if depth > 4:
        return []
    if isinstance(value, str):
        return re.split(r"[,;|\n]", value) if split else [value]
    if isinstance(value, (list, tuple)):
        return [item for entry in value[:200] for item in _values(entry, split=split, depth=depth + 1)]
    if isinstance(value, Mapping):
        # Explicit education keys avoid embedding stringified dictionaries or
        # unrelated dates/flags in the dictionary. Unknown shapes are omitted.
        keys = ("degree", "course", "qualification", "field_of_study", "specialization")
        return [item for key in keys for item in _values(value.get(key), split=False, depth=depth + 1)]
    return []


def _nested_values(value, keys: tuple[str, ...], *, allow_text=False, depth=0) -> list:
    """Extract bounded human-entered values from history-like structures."""
    if depth > 4:
        return []
    if isinstance(value, str):
        return re.split(r"[,;|\n]", value) if allow_text else []
    if isinstance(value, (list, tuple)):
        out = []
        for item in value[:200]:
            out.extend(_nested_values(item, keys, allow_text=allow_text, depth=depth + 1))
        return out
    if isinstance(value, Mapping):
        out = []
        for key in keys:
            if key in value:
                item = value.get(key)
                if isinstance(item, (str, int, float)) and not isinstance(item, bool):
                    out.append(item)
        return out
    return []


def _extract_field_values(profile: Mapping, field: str) -> list:
    """Return raw values for one signature field without stringifying records."""
    aliases = _RAW_FIELDS[field]
    if field in _HISTORY_KEYS:
        values = []
        for alias in aliases:
            if alias not in profile:
                continue
            # Free-form experience/education is not simultaneously a company,
            # job title, city and institution. Explicitly typed lists may use
            # scalar entries; shared record containers require structured keys.
            typed_aliases = {
                "experience_company": {"company_history", "previous_employers"},
                "experience_title": {"title_history"},
                "experience_location": {"location_history"},
                "institution": set(),
                "certification": {"certifications", "certification"},
                "project": {"projects", "project"}, "language": {"languages", "language"},
            }
            values.extend(_nested_values(profile.get(alias), _HISTORY_KEYS[field], allow_text=alias in typed_aliases[field]))
        return values
    for alias in aliases:
        if alias not in profile:
            continue
        values = _values(profile.get(alias), split=field in {"skill", "education"})
        if any(normalize_text(value) for value in values):
            return values
    return []


def _normalized_job_date(value) -> str | None:
    """Normalize an observed date without inventing its missing month or day."""
    if isinstance(value, Mapping):
        year, month, day = value.get("year"), value.get("month"), value.get("day")
        parts = [year] + ([month] if month is not None else []) + ([day] if day is not None else [])
        if (year is None or (day is not None and month is None)
                or any(isinstance(part, bool) or not isinstance(part, int) for part in parts)):
            return None
        value = f"{year:04d}" + (f"-{month:02d}" if month is not None else "") + (f"-{day:02d}" if day is not None else "")
    if isinstance(value, int) and not isinstance(value, bool):
        value = str(value)
    if not isinstance(value, str):
        return None
    value = normalize_text(value)
    if value in {"present", "current", "now", "till date", "ongoing"}:
        return "present"
    # A time-of-day attached to a complete ISO date is irrelevant to job tenure.
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}t\d{2}:\d{2}.*", value):
        value = value[:10]
    months = {name.casefold(): index for index, name in enumerate(calendar.month_name) if name}
    months.update({name.casefold(): index for index, name in enumerate(calendar.month_abbr) if name})
    named = re.fullmatch(r"([a-z]+)\.?[\s-]+(\d{4})", value)
    if named and named.group(1) in months:
        value = f"{named.group(2)}-{months[named.group(1)]:02d}"
    numeric_month = re.fullmatch(r"(\d{1,2})/(\d{4})", value)
    if numeric_month:
        value = f"{numeric_month.group(2)}-{int(numeric_month.group(1)):02d}"
    value = value.replace("/", "-")
    if not re.fullmatch(r"\d{4}(?:-\d{1,2})?(?:-\d{1,2})?", value):
        return None
    parts = [int(part) for part in value.split("-")]
    try:
        date(parts[0], parts[1] if len(parts) > 1 else 1, parts[2] if len(parts) > 2 else 1)
    except ValueError:
        return None
    return f"{parts[0]:04d}" + (f"-{parts[1]:02d}" if len(parts) > 1 else "") + (f"-{parts[2]:02d}" if len(parts) > 2 else "")


def _job_time_metadata(entry: Mapping) -> dict:
    metadata = {}
    for field, keys in {
        "start_date": ("start_date", "from_date", "startDate", "started_at"),
        "end_date": ("end_date", "to_date", "endDate", "ended_at"),
    }.items():
        raw = [entry[key] for key in keys if key in entry and entry[key] not in (None, "")
               and not (isinstance(entry[key], str) and not normalize_text(entry[key]))]
        parsed = [_normalized_job_date(value) for value in raw]
        valid = set(parsed) - {None}
        if len(valid) == 1 and (field != "start_date" or "present" not in valid):
            metadata[field] = next(iter(valid))
        if raw and (None in parsed or len(valid) > 1 or (field == "start_date" and "present" in valid)):
            metadata["time_status"] = "invalid_or_conflicting"
    for key in ("is_current", "isCurrent", "currently_working"):
        if isinstance(entry.get(key), bool):
            metadata["is_current"] = entry[key]
            break
    return metadata


def _job_date_bounds(value):
    if not value or value == "present":
        return None
    parts = [int(part) for part in value.split("-")]
    year = parts[0]
    if len(parts) == 1:
        return date(year, 1, 1), date(year, 12, 31)
    if len(parts) == 2:
        return date(year, parts[1], 1), date(year, parts[1], calendar.monthrange(year, parts[1])[1])
    exact = date(*parts)
    return exact, exact


def _job_time_relation(left: dict, right: dict) -> str:
    """Classify observed intervals; absent endpoints never become today's date."""
    if left.get("time_status") or right.get("time_status"):
        return "invalid"
    a_start, a_end = _job_date_bounds(left.get("start_date")), _job_date_bounds(left.get("end_date"))
    b_start, b_end = _job_date_bounds(right.get("start_date")), _job_date_bounds(right.get("end_date"))
    if ((a_start and a_end and a_start[0] > a_end[1])
            or (b_start and b_end and b_start[0] > b_end[1])):
        return "invalid"
    if ((a_end and b_start and a_end[1] < b_start[0])
            or (b_end and a_start and b_end[1] < a_start[0])):
        return "disjoint"
    return "possible_overlap" if all((a_start, a_end, b_start, b_end)) else "unknown"


def _employment_context(profile: Mapping, fields: dict) -> list[dict]:
    """Preserve company/role/location belonging to the same observed record.

    Historical records have no asserted chronology: absent dates and a current
    flag are not inferred. A typed company-only history entry stays unpaired.
    """
    records = []
    current = {field: fields[field][0] for field in ("company", "title", "location") if fields[field]}
    if current:
        records.append({"kind": "current", **current})
    for alias in ("experience", "work_experience", "employment_history"):
        entries = profile.get(alias)
        entries = [entries] if isinstance(entries, Mapping) else entries
        if not isinstance(entries, (list, tuple)):
            continue
        for entry in entries[:200]:
            if not isinstance(entry, Mapping):
                continue
            record = {"kind": "history", **_job_time_metadata(entry)}
            for field in ("company", "title", "location"):
                values = _nested_values(entry, _HISTORY_KEYS[f"experience_{field}"])
                normalized = sorted({canonical_code(field, value).split(":", 1)[1]
                                     for value in values if canonical_code(field, value)})
                # Conflicting aliases in one record cannot manufacture a pair.
                if len(normalized) == 1:
                    record[field] = normalized[0]
            if any(field in record for field in ("company", "title", "location")):
                records.append(record)
    # A structured record explicitly marked current can date the corresponding
    # flat current claim. Missing chronology remains unknown. Ambiguous multiple
    # current records never select an arbitrary date range.
    dated_current = [record for record in records if record.get("is_current") is True
                     and record.get("company") and record.get("company") == current.get("company")
                     and (not current.get("title") or not record.get("title") or record["title"] == current["title"])]
    if len(dated_current) == 1 and records and records[0].get("kind") == "current":
        records[0].update({key: value for key, value in dated_current[0].items()
                           if key in {"start_date", "end_date", "is_current", "time_status"}})
    for company in fields["experience_company"]:
        if not any(record.get("company") == company for record in records):
            records.append({"kind": "history", "company": company})
    unique = {tuple(sorted(record.items())) for record in records}
    ordered = sorted(unique, key=lambda record: (dict(record).get("kind") != "current", record))
    return [dict(record) for record in ordered[:_MAX_CONTEXT_VALUES]]


def _historical_match(incoming, stored, code_frequencies, population_size):
    """Choose one coherent history/current pair, never a bag of mixed roles."""
    pairs, comparisons = [], []
    for left in incoming["context"]["employment"]:
        for right in stored["context"]["employment"]:
            if left["kind"] == right["kind"] == "current":
                continue
            if not left.get("company") or left.get("company") != right.get("company"):
                continue
            temporal_relation = _job_time_relation(left, right)
            comparison = {
                "incoming_job": dict(left), "candidate_job": dict(right),
                "temporal_relation": temporal_relation, "used_for_score": False,
            }
            comparison_index = len(comparisons)
            comparisons.append(comparison)
            if temporal_relation in {"disjoint", "invalid"}:
                continue
            common = {f"experience_{field}": {left[field]} for field in ("company", "title", "location")
                      if left.get(field) and left.get(field) == right.get(field)}
            # Do not count the same current claim again because it is repeated
            # in a work history block.
            for field in ("company", "title", "location"):
                current_common = set(incoming["fields"][field]) & set(stored["fields"][field])
                if f"experience_{field}" in common:
                    common[f"experience_{field}"] -= current_common
            common = {field: values for field, values in common.items() if values}
            score = sum(WEIGHTS[field] * _frequency_factor(field, values, code_frequencies, population_size)[0]
                        for field, values in common.items())
            pairs.append((score, tuple((field, tuple(sorted(values))) for field, values in sorted(common.items())), comparison_index))
    if not pairs:
        return {}, comparisons[:12]
    _, best, comparison_index = max(pairs)
    comparisons[comparison_index]["used_for_score"] = bool(best)
    # Surface the supporting pair first, followed by rejected/unknown examples.
    explanation = [comparisons[comparison_index]] + [item for index, item in enumerate(comparisons) if index != comparison_index]
    return {field: set(values) for field, values in best}, explanation[:12]


def _name_tokens(name: str) -> list[str]:
    # Hyphens separate name words, but accents and combining marks survive.
    words = [word.strip(".,") for word in re.split(r"[\s\-]+", name) if word]
    return [word for word in words if word and word not in _NAME_HONORIFICS]


def _source_id(source: str, value) -> str:
    if not isinstance(value, str) or not normalize_text(value):
        return ""
    value = value.strip()
    if source == "naukri" and value.startswith("naukri_"):
        value = value[len("naukri_"):]
    if not value or len(value) > 256 or not re.fullmatch(r"[\w.\-]+", value):
        return ""
    return value.casefold() if source == "linkedin" else value


def build_identity_signature(profile: dict) -> dict:
    """Build deterministic codes from observed fields, ignoring browser trust flags.

    ``fields`` contains canonical values grouped by field. ``source_ids`` are
    unverified retrieval hints only; they never confer trust on their own.
    Preferred locations/headlines are intentionally excluded from current-field
    evidence, and neither name tokens nor repeated aliases create extra points.
    """
    profile = profile if isinstance(profile, Mapping) else {}
    fields = {}
    codes = set()
    for field, aliases in _RAW_FIELDS.items():
        values = _extract_field_values(profile, field)
        field_codes = {canonical_code(field, value) for value in values}
        field_codes.discard("")
        # A malformed import can contain thousands of repeated history items.
        # Keep the signature deterministic and bounded before it reaches the
        # multikey Mongo index.
        field_codes = set(sorted(field_codes)[:_MAX_CONTEXT_VALUES])
        codes.update(field_codes)
        fields[field] = sorted(code.split(":", 1)[1] for code in field_codes)
    token_codes = {
        canonical_code("name_token", token)
        for name in fields["name"] for token in _name_tokens(name)
    } - {""}
    codes.update(token_codes)
    fields["name_token"] = sorted(code.split(":", 1)[1] for code in token_codes)

    source_ids = {"naukri": set(), "linkedin": set()}
    for source, keys in {
        "naukri": ("naukri_profile_id", "naukri_id"),
        "linkedin": ("linkedin_profile_id", "linkedin_id"),
    }.items():
        source_ids[source].update(_source_id(source, profile.get(key)) for key in keys)
    evidence = profile.get("identity_evidence")
    if (isinstance(evidence, Mapping) and isinstance(evidence.get("source"), str)
            and evidence.get("source") in source_ids
            and evidence.get("provenance") != "canonical_profile_url"):
        source = evidence["source"]
        source_ids[source].add(_source_id(source, evidence.get("profile_id")))
    return {
        "version": SIGNATURE_VERSION,
        "codes": sorted(codes),
        "fields": fields,
        "context": {"employment": _employment_context(profile, fields)},
        "source_ids": {source: sorted(ids - {""}) for source, ids in source_ids.items()},
    }


def _name_match(left: list[str], right: list[str]) -> str:
    if not left or not right:
        return "missing"
    for a in left:
        for b in right:
            a_tokens, b_tokens = _name_tokens(a), _name_tokens(b)
            if a_tokens and a_tokens == b_tokens:
                return "exact"
            if (len(a_tokens) >= 2 and len(b_tokens) >= 2
                    and a_tokens[0] == b_tokens[0] and a_tokens[-1] == b_tokens[-1]):
                # Missing middle names are compatible; contradictory middle
                # names are not. Do not match only a common first/last token.
                a_middle, b_middle = a_tokens[1:-1], b_tokens[1:-1]
                if not a_middle or not b_middle or a_middle == b_middle:
                    return "compatible"
    return "different"


def names_are_compatible(left: str, right: str, *, require_multiple_tokens=False) -> bool:
    """Public deterministic name guard; never use this alone as identity proof."""
    left, right = normalize_text(left), normalize_text(right)
    if not left or not right:
        return False
    if require_multiple_tokens and (len(_name_tokens(left)) < 2 or len(_name_tokens(right)) < 2):
        return False
    return _name_match([left], [right]) in {"exact", "compatible"}


def _experience(profile: dict) -> float | None:
    for key in ("experience_years", "total_experience_years", "total_experience"):
        value = profile.get(key)
        if value is None or isinstance(value, bool):
            continue
        try:
            value = float(value)
        except (TypeError, ValueError, OverflowError):
            continue
        if math.isfinite(value) and 0 <= value <= 80:
            return value
    return None


def _incoming_anchor(profile: dict) -> tuple[str, str] | None:
    evidence = profile.get("identity_evidence")
    if not isinstance(evidence, Mapping):
        return None
    source = evidence.get("source")
    identifier = _source_id(source, evidence.get("profile_id"))
    if not identifier:
        return None
    if source == "naukri" and evidence.get("provenance") == "data-target-id":
        return source, identifier
    return None


def _trusted_anchors(candidate: dict) -> set[tuple[str, str]]:
    anchors = candidate.get("_identity_trusted_anchors")
    if not isinstance(anchors, (list, tuple)):
        return set()
    result = set()
    for anchor in anchors:
        if (not isinstance(anchor, Mapping) or anchor.get("source") not in {"naukri", "linkedin"}
                or anchor.get("kind") != "source_profile"
                or anchor.get("provenance") not in _TRUSTED_PROVENANCE):
            continue
        identifier = _source_id(anchor["source"], anchor.get("id"))
        if identifier:
            result.add((anchor["source"], identifier))
    return result


def _frequency_factor(field, values, code_frequencies, population_size):
    """Downweight common corpus codes; never infer rarity from retrieved rows.

    Counts must represent candidate-document frequency, not occurrences. Missing
    or invalid counts preserve the baseline and are disclosed to the caller.
    This is an evidence heuristic, not a calibrated likelihood ratio.
    """
    factors, missing = [], False
    for value in values:
        count = code_frequencies.get(canonical_code(field, value)) if code_frequencies else None
        if (isinstance(count, bool) or not isinstance(count, int)
                or population_size is None or not 1 <= count <= population_size):
            missing = True
            continue
        factor = math.log(population_size / count) / math.log(population_size) if population_size > 1 else 1.0
        factors.append(max(0.2, min(1.0, factor)))
    if not factors:
        return 1.0, missing
    return (sum(factors) / len(factors) if field == "skill" else max(factors)), missing


def _compare(profile: dict, incoming: dict, candidate: dict, incoming_anchor,
             code_frequencies, population_size) -> dict:
    stored = build_identity_signature(candidate)
    left, right = incoming["fields"], stored["fields"]
    score, signals, conflicts, adjustments = 0.0, [], [], []
    frequency_missing = False

    def points(field, values, baseline):
        nonlocal frequency_missing
        factor, missing = _frequency_factor(field, values, code_frequencies, population_size)
        frequency_missing |= missing
        adjusted = baseline * factor
        adjustments.append({"field": field, "base_points": round(baseline, 3),
                            "factor": round(factor, 4), "adjusted_points": round(adjusted, 3)})
        return adjusted

    name_match = _name_match(left["name"], right["name"])
    if name_match in {"exact", "compatible"}:
        signals.append("name" if name_match == "exact" else "name_compatible")
        score += points("name", set(left["name"]) & set(right["name"]) or set(right["name"]), WEIGHTS[signals[-1]])
    elif name_match == "different":
        conflicts.append("name_differs")
    employment, education_points, location_points = 0.0, 0.0, 0.0
    for field in ("company", "title", "location", "education"):
        a, b = set(left[field]), set(right[field])
        if a & b:
            signals.append(field)
            if field in {"company", "title"}:
                employment += points(field, a & b, WEIGHTS[field])
            elif field == "education":
                education_points += points(field, a & b, WEIGHTS[field])
            else:
                location_points += points(field, a & b, WEIGHTS[field])
        elif a and b and field in {"company", "location"}:
            # People change jobs/cities: these are differences to inspect, not
            # proof of distinct identity and not automatic confirmation vetoes.
            conflicts.append(f"{field}_differs")

    # Longitudinal context makes collisions easier to inspect without making a
    # past employer, university, certification, or project an identity proof.
    # Current company/title and historical company/title share the employment
    # cap so a long resume cannot overwhelm the more discriminative fields.
    history_common, dated_job_evidence = _historical_match(incoming, stored, code_frequencies, population_size)
    for field in ("experience_company", "experience_title", "experience_location", "institution", "certification", "project", "language"):
        common = history_common.get(field, set()) if field.startswith("experience_") else set(left[field]) & set(right[field])
        if not common:
            continue
        signals.append(field)
        if field in {"experience_company", "experience_title"}:
            employment += points(field, common, WEIGHTS[field])
        elif field == "experience_location":
            location_points += points(field, common, WEIGHTS[field])
        elif field == "institution":
            education_points += points(field, common, WEIGHTS[field])
        else:
            score += points(field, common, WEIGHTS[field])
    score += min(employment, WEIGHTS["employment_cap"])
    score += min(education_points, WEIGHTS["education_cap"])
    score += min(location_points, WEIGHTS["location"])
    a, b = set(left["skill"]), set(right["skill"])
    if a & b:
        signals.append("skill")
        score += points("skill", a & b, WEIGHTS["skill"] * len(a & b) / len(a | b))
    incoming_exp, stored_exp = _experience(profile), _experience(candidate)
    if incoming_exp is not None and stored_exp is not None:
        if abs(incoming_exp - stored_exp) <= 1:
            signals.append("experience")
            score += WEIGHTS["experience"]
        elif abs(incoming_exp - stored_exp) > 5:
            conflicts.append("experience_differs")
    anchor_match = bool(incoming_anchor and incoming_anchor in _trusted_anchors(candidate))
    if not anchor_match and any(set(incoming["source_ids"][source]) & set(stored["source_ids"][source])
           for source in ("naukri", "linkedin")):
        signals.append("source_id_hint")
        score += WEIGHTS["source_id_hint"]
    name_guard = name_match in {"exact", "compatible"}
    soft_score = min(score, SOFT_SCORE_CAP) if name_guard else 0.0
    score, anchor_points = soft_score, 0.0
    if anchor_match:
        signals.append("trusted_source_profile")
        if name_guard:
            anchor_points = WEIGHTS["trusted_source_profile"]
            score += anchor_points
        else:
            conflicts.append("source_anchor_name_conflict")
    if name_match == "different":
        # A rich but differently named record must not bury a sparsely observed
        # compatible name merely because it contains more generic work fields.
        score = 0.0
    elif name_match == "missing":
        score = 0.0
    # Keep a compact, explainable view of the compared canonical values.  These
    # values are normalized identity tokens (never contacts, resume text, or
    # hidden source data), so callers can explain a suggestion without exposing
    # the complete bank document.
    evidence = []
    for field in ("name", "company", "title", "location", "skill", "education",
                  "experience_company", "experience_title", "experience_location",
                  "institution", "certification", "project", "language"):
        left_values = list(left[field])[:12]
        right_values = list(right[field])[:12]
        if field.startswith("experience_"):
            base_field = field.removeprefix("experience_")
            left_values = sorted(set(left_values) | set(left[base_field]))[:12]
            right_values = sorted(set(right_values) | set(right[base_field]))[:12]
            common = sorted(history_common.get(field, set()))
        else:
            common = sorted(set(left_values) & set(right_values))
        if common:
            status = "match"
        elif left_values and right_values:
            status = "different"
        else:
            status = "missing"
        evidence.append({
            "field": field,
            "incoming_values": left_values,
            "candidate_values": right_values,
            "matched_values": common,
            "status": status,
        })
    return {
        "candidate_id": str(candidate.get("id") or candidate.get("candidate_id") or candidate.get("_id") or ""),
        "name": candidate.get("name") or candidate.get("full_name") or "",
        "score": round(score, 3), "matched_signals": signals, "conflicts": conflicts,
        "soft_score": round(soft_score, 3), "source_anchor_points": anchor_points,
        "evidence": evidence,
        "dated_job_evidence": dated_job_evidence,
        "frequency_adjustments": adjustments,
        "_anchor_match": anchor_match, "_name_guard": name_guard,
        "_frequency_missing": frequency_missing,
        "_signature_key": "|".join(stored["codes"]),
    }


def resolve_profile(profile: dict, candidates: list[dict], retrieval_complete=True,
                    *, code_frequencies=None, population_size=None,
                    authoritative_retrieval_complete=False) -> dict:
    """Rank all retrieved records, expose ambiguity and never infer absence.

    ``exists`` means a unique matching source profile was confirmed. It is false
    for probable/ambiguous results. Callers should show possible matches without
    merging candidates. Incomplete retrieval cannot establish a unique winner.
    """
    profile = profile if isinstance(profile, Mapping) else {}
    valid_population = (isinstance(population_size, int) and not isinstance(population_size, bool)
                        and population_size > 0)
    frequencies_available = isinstance(code_frequencies, Mapping) and bool(code_frequencies) and valid_population
    if not frequencies_available:
        code_frequencies, population_size = None, None
    signature = build_identity_signature(profile)
    anchor = _incoming_anchor(profile)
    # Linked observations are server-selected historical views of an already
    # resolved person. Compare each view on its own; never fabricate a profile
    # by borrowing a company from one observation and a city from another.
    observation_fields = {key for aliases in _RAW_FIELDS.values() for key in aliases}
    observation_fields.update({"experience_years", "total_experience_years", "total_experience"})
    grouped, canonical_anchor_rows = {}, []
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, Mapping):
            continue
        canonical = _compare(profile, signature, candidate, anchor, code_frequencies, population_size)
        canonical.update({"evidence_observation_id": None, "evidence_observed_at": None})
        if canonical["_anchor_match"]:
            canonical_anchor_rows.append(canonical)
        views = [canonical]
        observations = candidate.get("_identity_observations")
        if isinstance(observations, (list, tuple)):
            for observation in observations[:8]:
                if not isinstance(observation, Mapping) or not isinstance(observation.get("snapshot"), Mapping):
                    continue
                # Only field evidence crosses this boundary. Legacy provider
                # IDs, nested flags, URLs and anchors never confer authority.
                snapshot = {key: value for key, value in observation["snapshot"].items() if key in observation_fields}
                snapshot["id"] = canonical["candidate_id"]
                view = _compare(profile, signature, snapshot, None, code_frequencies, population_size)
                view.update({
                    "evidence_observation_id": observation.get("id") if isinstance(observation.get("id"), str) else None,
                    "evidence_observed_at": observation.get("observed_at") if isinstance(observation.get("observed_at"), str) else None,
                })
                views.append(view)
        views.sort(key=lambda row: (-row["score"], row["evidence_observation_id"] is not None,
                                    row["evidence_observation_id"] or "", row["_signature_key"]))
        best = views[0]
        # Missing canonical IDs remain separate, unusable-for-confirmation rows.
        person_key = canonical["candidate_id"] or f"__missing_id_{index}"
        existing = grouped.get(person_key)
        if existing is None or (-best["score"], best["_signature_key"]) < (-existing["score"], existing["_signature_key"]):
            grouped[person_key] = best
    ranked = list(grouped.values())
    # Deterministic tie-break affects display ordering only; a tie stays ambiguous.
    ranked.sort(key=lambda row: (-row["score"], row["candidate_id"], row["_signature_key"]))
    top = ranked[0] if ranked else None
    second = ranked[1] if len(ranked) > 1 else None
    margin = round(top["score"] - second["score"], 3) if top and second else None
    missing = [field for field in _RAW_FIELDS if not signature["fields"][field]]
    if _experience(profile) is None:
        missing.append("experience")
    reasons = []
    # A historical soft view cannot hide contradictory canonical anchor evidence.
    anchor_hits = list({row["candidate_id"]: row for row in canonical_anchor_rows}.values())
    relevant = bool(top and top["_name_guard"])
    # An exact, server-validated source anchor can be complete even when a
    # broad fallback (for example a common-name prefix scan) was capped.  The
    # caller must prove this separately; a boolean supplied by browser JSON is
    # never accepted.  This avoids losing an exact source match merely because
    # a popular-name safety query returned its quota.
    anchor_complete = bool(authoritative_retrieval_complete and len(anchor_hits) == 1
                           and anchor_hits[0]["_name_guard"] and anchor_hits[0]["candidate_id"])
    if not retrieval_complete and not anchor_complete:
        decision = "ambiguous" if relevant or anchor_hits else "insufficient_data"
        reasons.append("retrieval_incomplete")
    elif len(anchor_hits) > 1:
        decision = "ambiguous"
        reasons.append("source_anchor_multiple_records")
    elif anchor_hits and not anchor_hits[0]["_name_guard"]:
        decision = "ambiguous"
        reasons.append("source_anchor_name_conflict")
    elif top and top["_anchor_match"] and top["_name_guard"] and top["candidate_id"] and (retrieval_complete or anchor_complete):
        decision = "confirmed_duplicate"
        reasons.append("unique_trusted_source_profile")
        if anchor_complete and not retrieval_complete:
            reasons.append("authoritative_anchor_complete")
    elif not signature["fields"]["name"] or len(missing) >= len(_RAW_FIELDS):
        decision = "insufficient_data"
        reasons.append("insufficient_observed_fields")
    elif relevant and second and second["_name_guard"] and margin < MINIMUM_MARGIN:
        decision = "ambiguous"
        reasons.append("close_alternative")
    elif (relevant and top["score"] >= PROBABLE_THRESHOLD
          and len(set(top["matched_signals"]) & {
              "company", "location", "skill", "education", "experience",
              "experience_company", "experience_title", "experience_location",
              "institution", "certification", "project", "language",
          }) >= 2):
        decision = "probable_match"
        reasons.append("multiple_supporting_fields_without_identity_proof")
    elif relevant:
        decision = "insufficient_data"
        reasons.append("weak_or_common_evidence")
    else:
        decision = "no_match_found"
        reasons.append("no_supported_match_in_retrieved_candidates")
    if not frequencies_available:
        reasons.append("corpus_frequencies_unavailable")
    elif top and top["_frequency_missing"]:
        reasons.append("corpus_frequency_coverage_partial")

    def public(row):
        return {key: value for key, value in row.items() if not key.startswith("_")} if row else None

    ranked_public = [public(row) for row in ranked[:5]]

    return {
        "decision": decision, "exists": decision == "confirmed_duplicate",
        "match_score": top["score"] if top else 0.0, "score_kind": SCORE_KIND,
        "top_match": public(top), "second_match": public(second), "margin": margin,
        # A small ranked window gives reviewers enough context to see close
        # alternatives without returning the full candidate bank.
        "ranked_matches": ranked_public,
        "matched_signals": top["matched_signals"] if top else [],
        "conflicts": top["conflicts"] if top else [], "missing_fields": missing,
        "frequency_adjustments": top["frequency_adjustments"] if top else [],
        "corpus_frequencies_available": bool(frequencies_available),
        "matcher_version": MATCHER_VERSION, "reason_codes": reasons,
    }
