import { describe, expect, it } from 'vitest'
import { jiraOAuthCallbackFromLocation } from './routing.js'

describe('Jira OAuth routing', () => {
  it('reads successful and rejected Atlassian callbacks only on the callback path', () => {
    expect(jiraOAuthCallbackFromLocation({
      pathname: '/jira/oauth/callback',
      search: '?code=auth-code&state=encrypted-state',
    })).toEqual({ code: 'auth-code', state: 'encrypted-state', error: '' })
    expect(jiraOAuthCallbackFromLocation({
      pathname: '/jira/oauth/callback',
      search: '?error=access_denied&error_description=No+thanks',
    })).toEqual({ code: '', state: '', error: 'No thanks' })
    expect(jiraOAuthCallbackFromLocation({ pathname: '/', search: '' })).toBeNull()
  })
})
