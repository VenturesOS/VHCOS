// Pure, bounded presentation helpers. Never render an arbitrary captured object.
export const reviewList = (value, limit = 12) => Array.isArray(value) ? value.slice(0, limit) : [];
export function reviewText(value) {
  if (typeof value !== 'string' && typeof value !== 'number') return '';
  if (typeof value === 'number' && !Number.isFinite(value)) return '';
  return String(value).slice(0, 600)
    .replace(/[^\s@]+@[^\s@]+\.[^\s@]+/g, '[contact hidden]')
    .replace(/\+?\d[\d\s().-]{7,}\d/g, (match) =>
      match.replace(/\D/g, '').length >= 9 ? '[contact hidden]' : match);
}
const first = (row, keys) => keys.map(key => reviewText(row?.[key])).find(Boolean) || '';
function connected(value, keys) {
  if (typeof value === 'string') return reviewText(value);
  if (!value || typeof value !== 'object' || Array.isArray(value)) return '';
  return keys.map(group => first(value, group)).filter(Boolean).join(' · ');
}
function entries(value, keys) {
  const values = Array.isArray(value) ? value : value ? [value] : [];
  return values.slice(0, 12).map(item => connected(item, keys)).filter(Boolean);
}
export function reviewContextRows(row = {}) {
  const work = row.work_history_details || row.work_history || row.experience || row.work_experience || row.employment_history;
  const education = row.education_details || row.education;
  return [
    ['Name', [first(row, ['name', 'full_name'])]],
    ['Employer', [first(row, ['employer', 'current_employer', 'current_company', 'company'])]],
    ['Role', [first(row, ['designation', 'current_designation', 'current_title', 'title'])]],
    ['Location', [first(row, ['location', 'current_location'])]],
    ['Experience (years)', [first(row, ['experience_years', 'total_experience_years', 'total_experience'])]],
    ['Skills', entries(row.skills || row.key_skills, [['name', 'skill']])],
    ['Employment history', entries(work, [
      ['company', 'employer', 'organization'], ['title', 'designation', 'role'],
      ['location', 'city'], ['start_date', 'from', 'start_year'], ['end_date', 'to', 'end_year'],
    ])],
    ['Education', entries(education, [
      ['degree', 'qualification', 'name'], ['institution', 'university', 'college'],
      ['graduation_year', 'year', 'end_year'],
    ])],
    ['Certifications', entries(row.certifications, [['name', 'title'], ['issuer'], ['year']])],
    ['Projects', entries(row.projects, [['name', 'title']])],
    ['Languages', entries(row.languages, [['name', 'language']])],
  ].map(([label, values]) => [label, values.filter(Boolean)]);
}
export function reviewSuggestions(observation) {
  const resolution = observation?.resolution || observation || {};
  const rows = Array.isArray(resolution.ranked_matches) ? resolution.ranked_matches
    : resolution.top_match ? [resolution.top_match] : [];
  const seen = new Set();
  return rows.filter(row => {
    const id = row?.candidate_id;
    if (typeof id !== 'string' || !id || id.length > 256 || seen.has(id)) return false;
    seen.add(id);
    return true;
  }).slice(0, 5);
}
// These are UI guards only; the server independently validates revision and state.
export function reviewDecisions(observation) {
  if (['unresolved', 'deferred'].includes(observation?.status)) return ['link', 'new_person', 'defer'];
  if (observation?.status === 'resolving') return ['new_person'];
  if (observation?.status === 'linked') return ['defer'];
  return [];
}
export function reviewPayload(observation, decision, candidateId, reason) {
  if (typeof observation?.id !== 'string' || !observation.id ||
      !Number.isInteger(observation.revision) || observation.revision < 0)
    throw new Error('Reload this observation before reviewing it.');
  if (!['link', 'new_person', 'defer'].includes(decision)) throw new Error('Choose a review decision.');
  if (!reviewDecisions(observation).includes(decision))
    throw new Error('This decision is not available in the current state. Refresh the observation.');
  const explanation = String(observation.status === 'resolving'
    ? observation.pending_review?.reason || '' : reason || '').trim();
  if (explanation.length < 10 || explanation.length > 2000)
    throw new Error('Explain your decision in 10–2,000 characters.');
  const payload = { revision: observation.revision, decision, reason: explanation };
  if (decision === 'link') {
    const id = String(candidateId || '').trim();
    if (!id || id.length > 256) throw new Error('Select or enter an existing candidate ID.');
    payload.candidate_id = id;
  }
  return payload;
}
