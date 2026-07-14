import { en, type MessageKey } from './en'

// Minimal i18n: a flat dictionary per locale and a t() with {placeholders}.
// Adding a language = adding a locales file and switching `messages`.
const messages: Record<MessageKey, string> = en

export function t(key: MessageKey, params?: Record<string, string | number>): string {
  let text: string = messages[key] ?? key
  if (params) {
    for (const [name, value] of Object.entries(params)) {
      text = text.replaceAll(`{${name}}`, String(value))
    }
  }
  return text
}
