import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import {
  evaluateIntentContract,
  intentContractKey,
  isConfirmationValid,
  verifyIntentPayloadHashes,
} from '../frontend/js/intent_contract_gate.js';

function sha(text) {
  return createHash('sha256').update(text, 'utf8').digest('hex');
}

function goodPayload() {
  const job_spec = { features: [{ id: 'F1', operation: 'CIRCULAR_POCKET' }] };
  const job_spec_canonical_json = '{"features":[{"id":"F1","operation":"CIRCULAR_POCKET"}]}';
  const gcode = 'G21\nM30';
  return {
    status: 'VALIDATED_DRAFT',
    job_spec,
    job_spec_canonical_json,
    job_spec_sha256: sha(job_spec_canonical_json),
    gcode,
    gcode_sha256: sha(gcode),
    ambiguities: [],
    errors: [],
    semantic_clause_accounting: [
      { clause_id: 'C001', disposition: 'BOUND', safety_relevant: true },
      { clause_id: 'C002', disposition: 'IGNORED_WITH_JUSTIFICATION', safety_relevant: false },
    ],
    pipeline_status: {
      semantic: 'BOUND', context: 'FOUND', validation: 'PASSED', draft: 'GENERATED', authorization: 'BLOCKED',
    },
    resolved_process_contract: {
      schema: 'resolved-process-contract-v2',
      material: { name: 'Aluminum 6061' },
      tool: { tool_id: 'T1', family: 'END_MILL', diameter_mm: 6, flute_length_mm: 20, center_cutting: true, supported_entry_modes: ['plunge','ramp','helix'] },
      machine: { work_volume_mm: '400x300x100' },
      features: [{ feature_id: 'F1', operation: 'CIRCULAR_POCKET', range_id: 'OR1', feed_min_mm_min: 600, feed_max_mm_min: 1100, spindle_min_rpm: 15000, spindle_max_rpm: 19000, min_stepdown_mm: 1, max_stepdown_mm: 2, stepover_ratio: 0.4 }],
    },
    authorization_blockers: [],
  };
}

test('exact validated payload is confirmable and action eligible', () => {
  const payload = goodPayload();
  const result = evaluateIntentContract(payload);
  assert.equal(result.confirmable, true);
  assert.equal(result.actionEligible, true);
  assert.equal(result.contractKey, `${payload.job_spec_sha256}:${payload.gcode_sha256}`);
  assert.equal(intentContractKey(payload), result.contractKey);
});

test('exact payload hashes are recomputed successfully', async () => {
  const result = await verifyIntentPayloadHashes(goodPayload());
  assert.equal(result.valid, true);
  assert.equal(result.jobSpecHashMatches, true);
  assert.equal(result.gcodeHashMatches, true);
});

test('tampered gcode is rejected even when hash field format is valid', async () => {
  const payload = goodPayload();
  payload.gcode = payload.gcode + '\nG0 X99';
  const result = await verifyIntentPayloadHashes(payload);
  assert.equal(result.valid, false);
  assert.ok(result.reasons.includes('gcode_hash_mismatch'));
});

test('canonical JobSpec mismatch blocks confirmation before hashing', () => {
  const payload = goodPayload();
  payload.job_spec.features[0].operation = 'RECTANGULAR_POCKET';
  const result = evaluateIntentContract(payload);
  assert.equal(result.confirmable, false);
  assert.ok(result.reasons.includes('job_spec_canonical_payload_mismatch'));
});

test('safety-relevant unaccounted clause blocks confirmation', () => {
  const payload = goodPayload();
  payload.semantic_clause_accounting[0].disposition = 'UNACCOUNTED';
  const result = evaluateIntentContract(payload);
  assert.equal(result.confirmable, false);
  assert.ok(result.reasons.includes('semantic_clauses_not_fully_accounted'));
  assert.deepEqual(result.unsafeClauseIds, ['C001']);
});

test('missing process contract blocks confirmation', () => {
  const payload = goodPayload();
  delete payload.resolved_process_contract;
  const result = evaluateIntentContract(payload);
  assert.equal(result.confirmable, false);
  assert.ok(result.reasons.includes('missing_resolved_process_contract'));
});

test('conditional draft may be confirmed but actions remain blocked', () => {
  const payload = goodPayload();
  payload.pipeline_status.draft = 'CONDITIONAL';
  payload.authorization_blockers = ['fixture.clearance'];
  const result = evaluateIntentContract(payload);
  assert.equal(result.confirmable, true);
  assert.equal(result.actionEligible, false);
  assert.deepEqual(result.authorizationBlockers, ['fixture.clearance']);
});


test('v1 or incomplete process contract cannot unlock actions', () => {
  const payload = goodPayload();
  payload.resolved_process_contract = { schema: 'resolved-process-contract-v1', features: [{ feature_id: 'F1', operation: 'CIRCULAR_POCKET', range_id: 'OR1' }] };
  const result = evaluateIntentContract(payload);
  assert.equal(result.confirmable, false);
  assert.ok(result.reasons.includes('resolved_process_contract_incomplete'));
});

test('confirmation is valid only for exact hash pair', () => {
  const payload = goodPayload();
  const key = `${payload.job_spec_sha256}:${payload.gcode_sha256}`;
  assert.equal(isConfirmationValid(payload, { confirmed: true, contractKey: key }), true);
  assert.equal(isConfirmationValid(payload, { confirmed: true, contractKey: `${payload.job_spec_sha256}:${'c'.repeat(64)}` }), false);
  assert.equal(isConfirmationValid(payload, { confirmed: false, contractKey: key }), false);
});

test('missing hashes and zero-feature payload cannot be confirmed', () => {
  const payload = goodPayload();
  payload.job_spec.features = [];
  payload.job_spec_canonical_json = '{"features":[]}';
  payload.job_spec_sha256 = '';
  payload.gcode_sha256 = '';
  const result = evaluateIntentContract(payload);
  assert.equal(result.confirmable, false);
  assert.ok(result.reasons.includes('missing_features'));
  assert.ok(result.reasons.includes('missing_or_invalid_job_spec_sha256'));
  assert.ok(result.reasons.includes('missing_or_invalid_gcode_sha256'));
});
