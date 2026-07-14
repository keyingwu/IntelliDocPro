import type {
  FieldSpec,
  SchemaChatMessage,
  SchemaRefinement,
} from '../api/types'

export interface RefineChatEntry {
  id: string
  role: 'user' | 'assistant' | 'error'
  content: string
  result?: SchemaRefinement
}

interface PendingRefine {
  id: string
  instruction: string
  revision: number
  sampleKey: string
  beforeFields: FieldSpec[]
}

export interface SchemaRefineState {
  fields: FieldSpec[]
  history: SchemaChatMessage[]
  messages: RefineChatEntry[]
  pending: PendingRefine | null
  undoSnapshot: FieldSpec[] | null
  revision: number
  lastResult: SchemaRefinement | null
  error: string | null
}

export type SchemaRefineAction =
  | { type: 'hydrate'; fields: FieldSpec[] }
  | { type: 'manual-change'; fields: FieldSpec[] }
  | { type: 'sample-replaced' }
  | {
      type: 'refine-started'
      requestId: string
      instruction: string
      sampleKey: string
    }
  | {
      type: 'refine-succeeded'
      requestId: string
      sampleKey: string
      result: SchemaRefinement
    }
  | { type: 'refine-failed'; requestId: string; message: string }
  | { type: 'undo' }

function cloneFields(fields: FieldSpec[]): FieldSpec[] {
  return fields.map((field) => ({
    ...field,
    enum_values: field.enum_values ? [...field.enum_values] : field.enum_values,
  }))
}

export function initialSchemaRefineState(fields: FieldSpec[] = []): SchemaRefineState {
  return {
    fields: cloneFields(fields),
    history: [],
    messages: [],
    pending: null,
    undoSnapshot: null,
    revision: 0,
    lastResult: null,
    error: null,
  }
}

export function schemaRefineReducer(
  state: SchemaRefineState,
  action: SchemaRefineAction,
): SchemaRefineState {
  switch (action.type) {
    case 'hydrate':
      return initialSchemaRefineState(action.fields)

    case 'manual-change':
      return {
        ...state,
        fields: cloneFields(action.fields),
        pending: null,
        undoSnapshot: null,
        revision: state.revision + 1,
        lastResult: null,
        error: null,
      }

    case 'sample-replaced':
      return {
        ...state,
        history: [],
        messages: [],
        pending: null,
        undoSnapshot: null,
        revision: state.revision + 1,
        lastResult: null,
        error: null,
      }

    case 'refine-started': {
      const pending: PendingRefine = {
        id: action.requestId,
        instruction: action.instruction,
        revision: state.revision,
        sampleKey: action.sampleKey,
        beforeFields: cloneFields(state.fields),
      }
      return {
        ...state,
        pending,
        messages: [
          ...state.messages,
          {
            id: `${action.requestId}-user`,
            role: 'user',
            content: action.instruction,
          },
        ],
        error: null,
      }
    }

    case 'refine-succeeded': {
      const pending = state.pending
      if (
        pending === null ||
        pending.id !== action.requestId ||
        pending.revision !== state.revision ||
        pending.sampleKey !== action.sampleKey
      ) {
        return {
          ...state,
          messages: [
            ...state.messages,
            {
              id: `${action.requestId}-stale`,
              role: 'error',
              content: 'The AI response was not applied because the schema or sample changed.',
            },
          ],
        }
      }

      const assistantMessage: SchemaChatMessage = {
        role: 'assistant',
        content: action.result.message,
      }
      const changed = action.result.changed
      return {
        ...state,
        fields: changed ? cloneFields(action.result.schema.fields) : state.fields,
        history: [
          ...state.history,
          { role: 'user' as const, content: pending.instruction },
          assistantMessage,
        ].slice(-20),
        messages: [
          ...state.messages,
          {
            id: `${action.requestId}-assistant`,
            role: 'assistant',
            content: action.result.message,
            result: action.result,
          },
        ],
        pending: null,
        undoSnapshot: changed ? pending.beforeFields : state.undoSnapshot,
        revision: changed ? state.revision + 1 : state.revision,
        lastResult: action.result,
        error: null,
      }
    }

    case 'refine-failed':
      if (state.pending?.id !== action.requestId) return state
      return {
        ...state,
        pending: null,
        messages: [
          ...state.messages,
          {
            id: `${action.requestId}-error`,
            role: 'error',
            content: action.message,
          },
        ],
        error: action.message,
      }

    case 'undo':
      if (state.undoSnapshot === null) return state
      return {
        ...state,
        fields: cloneFields(state.undoSnapshot),
        pending: null,
        undoSnapshot: null,
        revision: state.revision + 1,
        lastResult: null,
        error: null,
      }
  }
}

export function sampleFileKey(file: File): string {
  return `${file.name}:${file.size}:${file.lastModified}`
}
