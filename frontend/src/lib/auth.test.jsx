import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const authState = vi.hoisted(() => ({
  configurationError: null,
  isProduction: false,
  isSupabaseConfigured: false,
  supabase: null,
}))

vi.mock('./supabase.js', () => ({
  get configurationError() { return authState.configurationError },
  get isProduction() { return authState.isProduction },
  get isSupabaseConfigured() { return authState.isSupabaseConfigured },
  get supabase() { return authState.supabase },
}))

import {
  DEVELOPMENT_TOKEN,
  getAccessToken,
  setAnonymousDisplayName,
  useAuth,
} from './auth.js'

function anonymousSession(displayName = 'Guest') {
  return {
    access_token: 'anonymous-token',
    user: {
      id: 'anonymous-user',
      email: null,
      is_anonymous: true,
      user_metadata: { display_name: displayName },
    },
  }
}

function authClient() {
  const session = anonymousSession()
  return {
    auth: {
      getSession: vi.fn().mockResolvedValue({ data: { session: null }, error: null }),
      onAuthStateChange: vi.fn().mockReturnValue({
        data: { subscription: { unsubscribe: vi.fn() } },
      }),
      signInAnonymously: vi.fn().mockResolvedValue({
        data: { session, user: session.user }, error: null,
      }),
      updateUser: vi.fn().mockResolvedValue({
        data: { user: anonymousSession('Maya').user }, error: null,
      }),
    },
  }
}

beforeEach(() => {
  authState.configurationError = null
  authState.isProduction = false
  authState.isSupabaseConfigured = false
  authState.supabase = null
})

describe('registration-free authentication', () => {
  it('uses an anonymous development identity when Supabase is absent', async () => {
    const { result } = renderHook(() => useAuth())
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.user).toEqual(expect.objectContaining({
      displayName: 'Facilitator', isAnonymous: true, isDevelopment: true,
    }))
    await expect(getAccessToken()).resolves.toBe(DEVELOPMENT_TOKEN)
    await expect(setAnonymousDisplayName('Maya')).resolves.toEqual(
      expect.objectContaining({ displayName: 'Maya', isAnonymous: true }),
    )
  })

  it('reports production configuration errors without creating a session', async () => {
    authState.configurationError = 'Missing Supabase configuration'
    authState.isProduction = true
    const { result } = renderHook(() => useAuth())
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current).toEqual({
      user: null, loading: false, error: 'Missing Supabase configuration',
    })
    await expect(getAccessToken()).resolves.toBeNull()
  })

  it('provisions a persistent anonymous identity without registration', async () => {
    const client = authClient()
    authState.isSupabaseConfigured = true
    authState.supabase = client

    const { result } = renderHook(() => useAuth())
    await waitFor(() => expect(result.current.user?.displayName).toBe('Guest'))

    expect(client.auth.signInAnonymously).toHaveBeenCalledWith({
      options: { data: { display_name: 'Guest' } },
    })
    expect(result.current.user).toEqual(expect.objectContaining({
      id: 'anonymous-user', isAnonymous: true,
    }))
  })

  it('restores sessions, reacts to auth changes, and unsubscribes', async () => {
    const client = authClient()
    const session = anonymousSession('Maya Chen')
    client.auth.getSession.mockResolvedValue({ data: { session }, error: null })
    authState.isSupabaseConfigured = true
    authState.supabase = client

    const { result, unmount } = renderHook(() => useAuth())
    await waitFor(() => expect(result.current.user?.displayName).toBe('Maya Chen'))
    expect(client.auth.signInAnonymously).not.toHaveBeenCalled()
    await expect(getAccessToken()).resolves.toBe('anonymous-token')

    const callback = client.auth.onAuthStateChange.mock.calls[0][0]
    act(() => callback('USER_UPDATED', anonymousSession('Renamed')))
    expect(result.current.user?.displayName).toBe('Renamed')
    unmount()
    expect(client.auth.onAuthStateChange.mock.results[0].value.data.subscription.unsubscribe)
      .toHaveBeenCalled()
  })

  it('sets a display name on an existing or new anonymous identity', async () => {
    const client = authClient()
    authState.isSupabaseConfigured = true
    authState.supabase = client

    client.auth.getSession.mockResolvedValueOnce({
      data: { session: anonymousSession() }, error: null,
    })
    await expect(setAnonymousDisplayName('Maya')).resolves.toEqual(
      expect.objectContaining({ id: 'anonymous-user' }),
    )
    expect(client.auth.updateUser).toHaveBeenCalledWith({
      data: { display_name: 'Maya' },
    })

    client.auth.getSession.mockResolvedValueOnce({ data: { session: null }, error: null })
    await setAnonymousDisplayName('Sam')
    expect(client.auth.signInAnonymously).toHaveBeenCalledWith({
      options: { data: { display_name: 'Sam' } },
    })
  })

  it('surfaces anonymous identity provider errors', async () => {
    const client = authClient()
    const providerError = new Error('Provider unavailable')
    authState.isSupabaseConfigured = true
    authState.supabase = client

    client.auth.getSession.mockResolvedValueOnce({ data: {}, error: providerError })
    await expect(setAnonymousDisplayName('Maya')).rejects.toThrow(providerError)

    client.auth.getSession.mockResolvedValueOnce({ data: { session: null }, error: null })
    client.auth.signInAnonymously.mockResolvedValueOnce({ data: {}, error: providerError })
    await expect(setAnonymousDisplayName('Maya')).rejects.toThrow(providerError)

    client.auth.getSession.mockResolvedValueOnce({
      data: { session: anonymousSession() }, error: null,
    })
    client.auth.updateUser.mockResolvedValueOnce({ data: {}, error: providerError })
    await expect(setAnonymousDisplayName('Maya')).rejects.toThrow(providerError)
  })
})
