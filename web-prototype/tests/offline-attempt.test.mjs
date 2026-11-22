import assert from 'node:assert/strict'
import { test } from 'node:test'
import { gradeAnswer, localRecordId } from '../src/offline/attempt.ts'

test('grades both a correct first option and a wrong answer', () => {
  assert.equal(gradeAnswer(0, 0), true)
  assert.equal(gradeAnswer(1, 0), false)
})

test('creates distinct local IDs without randomUUID', t => {
  Object.defineProperty(crypto, 'randomUUID', { value: undefined, configurable: true })
  t.after(() => { delete crypto.randomUUID })
  const first = localRecordId()
  const next = localRecordId()
  assert.match(first, /^[0-9a-f]{32}$/)
  assert.notEqual(first, next)
})
