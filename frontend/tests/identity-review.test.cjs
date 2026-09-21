const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../src/lib/identityReview.js'), 'utf8');
const helpers = import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));

test('malformed evidence arrays and contact strings are bounded safely', async () => {
  const { reviewList, reviewText, reviewSuggestions } = await helpers;
  assert.deepEqual(reviewList({ field: 'name' }), []);
  assert.equal(reviewText({ email: 'secret@example.com' }), '');
  assert.equal(reviewText('secret@example.com +91 9876543210'), '[contact hidden] [contact hidden]');
  assert.deepEqual(reviewSuggestions({ ranked_matches: [{ candidate_id: 'a' }, { candidate_id: 'a' }, null] }), [{ candidate_id: 'a' }]);
});

test('zero experience and connected job dates survive presentation', async () => {
  const { reviewContextRows } = await helpers;
  const rows = Object.fromEntries(reviewContextRows({ experience_years: 0, work_history_details: [
    { company: 'TCS', title: 'Engineer', location: 'Delhi', start_date: '2019', end_date: '2022' },
    { company: 'Infosys', title: 'Lead', location: 'Mumbai', start_date: '2023' },
  ] }));
  assert.deepEqual(rows['Experience (years)'], ['0']);
  assert.deepEqual(rows['Employment history'], ['TCS · Engineer · Delhi · 2019 · 2022', 'Infosys · Lead · Mumbai · 2023']);
});

test('review decisions are explicit and revision guarded', async () => {
  const { reviewPayload, reviewDecisions } = await helpers;
  const observation = { id: 'obs', revision: 0, status: 'unresolved' };
  assert.throws(() => reviewPayload(observation, 'link', '', 'Checked the evidence'), /candidate ID/);
  assert.throws(() => reviewPayload({ ...observation, revision: null }, 'defer', '', 'Checked the evidence'), /Reload/);
  assert.deepEqual(reviewPayload(observation, 'link', ' person ', 'Checked the evidence'), {
    revision: 0, decision: 'link', candidate_id: 'person', reason: 'Checked the evidence',
  });
  assert.deepEqual(reviewDecisions({ status: 'linked' }), ['defer']);
  assert.throws(() => reviewPayload({ ...observation, status: 'linked' }, 'new_person', '', 'Checked the evidence'), /not available/);
});

test('interrupted creation resumes the original reason, not a new decision', async () => {
  const { reviewPayload, reviewDecisions } = await helpers;
  const observation = { id: 'obs', revision: 1, status: 'resolving', pending_review: { reason: 'Original reviewed evidence' } };
  assert.deepEqual(reviewDecisions(observation), ['new_person']);
  const payload = reviewPayload(observation, 'new_person', '', 'A different reason');
  assert.equal(payload.reason, observation.pending_review.reason);
  assert.throws(() => reviewPayload(observation, 'defer', '', 'Checked the evidence'), /not available/);
});
