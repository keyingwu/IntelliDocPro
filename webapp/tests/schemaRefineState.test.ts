import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { SchemaRefinement } from '../src/api/types.ts'
import {
  initialSchemaRefineState,
  schemaRefineReducer,
} from '../src/pages/schemaRefineState.ts'

const changedResult: SchemaRefinement = {
  schema: {
    fields: [
      { name: 'A', type: 'text' },
      { name: 'B', type: 'date' },
    ],
  },
  message: 'Added B.',
  changed: true,
  applied: ['Added field: B'],
  rejected: [],
}

test('successful refinement updates fields and creates one undo snapshot', () => {
  let state = initialSchemaRefineState([{ name: 'A', type: 'text' }])
  state = schemaRefineReducer(state, {
    type: 'refine-started',
    requestId: 'r1',
    instruction: 'add B',
    sampleKey: 'sample',
  })
  state = schemaRefineReducer(state, {
    type: 'refine-succeeded',
    requestId: 'r1',
    sampleKey: 'sample',
    result: changedResult,
  })

  assert.deepEqual(state.fields.map((field) => field.name), ['A', 'B'])
  assert.deepEqual(state.undoSnapshot?.map((field) => field.name), ['A'])
  assert.equal(state.history.length, 2)

  state = schemaRefineReducer(state, { type: 'undo' })
  assert.deepEqual(state.fields.map((field) => field.name), ['A'])
  assert.equal(state.undoSnapshot, null)
})

test('manual changes invalidate undo and stale pending responses cannot overwrite fields', () => {
  let state = initialSchemaRefineState([{ name: 'A', type: 'text' }])
  state = schemaRefineReducer(state, {
    type: 'refine-started',
    requestId: 'r1',
    instruction: 'add B',
    sampleKey: 'sample',
  })
  state = schemaRefineReducer(state, {
    type: 'manual-change',
    fields: [{ name: 'Manual', type: 'text' }],
  })
  state = schemaRefineReducer(state, {
    type: 'refine-succeeded',
    requestId: 'r1',
    sampleKey: 'sample',
    result: changedResult,
  })

  assert.deepEqual(state.fields.map((field) => field.name), ['Manual'])
  assert.equal(state.undoSnapshot, null)
  assert.equal(state.messages.at(-1)?.role, 'error')
})

test('a refusal preserves the previous undo snapshot', () => {
  const oldUndo = [{ name: 'Before', type: 'text' as const }]
  let state = {
    ...initialSchemaRefineState([{ name: 'A', type: 'text' }]),
    undoSnapshot: oldUndo,
  }
  state = schemaRefineReducer(state, {
    type: 'refine-started',
    requestId: 'r2',
    instruction: 'add missing field',
    sampleKey: 'sample',
  })
  state = schemaRefineReducer(state, {
    type: 'refine-succeeded',
    requestId: 'r2',
    sampleKey: 'sample',
    result: {
      schema: { fields: [{ name: 'A', type: 'text' }] },
      message: 'Not found.',
      changed: false,
      applied: [],
      rejected: [{ request: 'missing field', reason: 'Not in sample' }],
    },
  })

  assert.deepEqual(state.undoSnapshot, oldUndo)
  assert.equal(state.lastResult?.rejected.length, 1)
})

test('replacing the sample clears conversation and undo but keeps fields', () => {
  const state = schemaRefineReducer(
    {
      ...initialSchemaRefineState([{ name: 'A', type: 'text' }]),
      history: [{ role: 'user', content: 'old' }],
      undoSnapshot: [{ name: 'Before', type: 'text' }],
    },
    { type: 'sample-replaced' },
  )

  assert.deepEqual(state.fields.map((field) => field.name), ['A'])
  assert.deepEqual(state.history, [])
  assert.equal(state.undoSnapshot, null)
})
