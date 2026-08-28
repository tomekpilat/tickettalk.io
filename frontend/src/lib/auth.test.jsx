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
  sendMagicLink,
  signInAsMember,
  signOut,
  useAuth,
} from './auth.js'

function authClient() {
  return {
    auth: {
      getSession: vi.fn().mockResolvedValue({ data: { session: null }, error: null }),
      onAuthStateChange: vi.fn().mockReturnValue({
        data: { subscription: { unsubscribe: vi.fn() } },
      }),
      signInWithOtp: vi.fn().mockResolvedValue({ error: null }),
      signInAnonymously: vi.fn().mockResolvedValue({ data: { user: { id: 'member' } }, error: null }),
      signOut: vi.fn().mockResolvedValue({}),
    },
  }
}

beforeEach(() => {
  authState.configurationError = null
  authState.isProduction = false
  authState.isSupabaseConfigured = false
  authState.supabase = null
})

describe('authentication helpers', () => {
  it('uses the explicit development identity when Supabase is absent', async () => {
    const { result } = renderHook(() => useAuth())
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.user).toEqual(expect.objectContaining({
      displayName: 'Tomasz Pilat', isDevelopment: true,
    }))
    await expect(getAccessToken()).resolves.toBe(DEVELOPMENT_TOKEN)
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

  it('maps sessions, reacts to auth changes, and unsubscribes', async () => {
    const client = authClient()
    const session = {
      access_token: 'session-token',
      user: {
        id: 'user-1', email: 'maya@example.com', is_anonymous: false,
        user_metadata: { full_name: 'Maya Chen' },
      },
    }
    client.auth.getSession.mockResolvedValue({ data: { session }, error: null })
    authState.isSupabaseConfigured = true
    authState.supabase = client

    const { result, unmount } = renderHook(() => useAuth())
    await waitFor(() => expect(result.current.user?.displayName).toBe('Maya Chen'))
    await expect(getAccessToken()).resolves.toBe('session-token')

    const callback = client.auth.onAuthStateChange.mock.calls[0][0]
    act(() => callback('SIGNED_OUT', null))
    expect(result.current.user).toBeNull()
    unmount()
    expect(client.auth.onAuthStateChange.mock.results[0].value.data.subscription.unsubscribe)
      .toHaveBeenCalled()
  })

  it('sends facilitator links and creates anonymous member sessions', async () => {
    const client = authClient()
    authState.isSupabaseConfigured = true
    authState.supabase = client

    await sendMagicLink('maya@example.com')
    expect(client.auth.signInWithOtp).toHaveBeenCalledWith({
      email: 'maya@example.com',
      options: {
        emailRedirectTo: window.location.href,
        data: { display_name: 'maya' },
      },
    })
    await expect(signInAsMember('Maya')).resolves.toEqual({ id: 'member' })
    await signOut()
    expect(client.auth.signOut).toHaveBeenCalled()
  })

  it('surfaces provider errors and rejects calls without Supabase', async () => {
    await expect(sendMagicLink('maya@example.com')).rejects.toThrow('not configured')
    await expect(signInAsMember('Maya')).rejects.toThrow('not configured')
    await expect(signOut()).resolves.toBeUndefined()

    const client = authClient()
    const providerError = new Error('Provider unavailable')
    client.auth.signInWithOtp.mockResolvedValue({ error: providerError })
    client.auth.signInAnonymously.mockResolvedValue({ data: {}, error: providerError })
    authState.supabase = client
    await expect(sendMagicLink('maya@example.com')).rejects.toThrow(providerError)
    await expect(signInAsMember('Maya')).rejects.toThrow(providerError)
  })
})
