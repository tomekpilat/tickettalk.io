import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const createClient = vi.hoisted(() => vi.fn())
vi.mock('@supabase/supabase-js', () => ({ createClient }))

beforeEach(() => {
  vi.resetModules()
  createClient.mockReset()
  vi.unstubAllEnvs()
})

afterEach(() => {
  vi.unstubAllEnvs()
})

describe('Supabase configuration and Realtime', () => {
  it('stays inert in development without credentials', async () => {
    vi.stubEnv('VITE_APP_ENV', 'development')
    vi.stubEnv('VITE_SUPABASE_URL', '')
    vi.stubEnv('VITE_SUPABASE_ANON_KEY', '')
    const module = await import('./supabase.js')

    expect(module.configurationError).toBeNull()
    expect(module.supabase).toBeNull()
    expect(module.isSupabaseConfigured).toBe(false)
    expect(module.subscribeToRoom('room-1', vi.fn())).toBeTypeOf('function')
  })

  it('fails closed when production credentials are missing', async () => {
    vi.stubEnv('VITE_APP_ENV', 'production')
    vi.stubEnv('VITE_SUPABASE_URL', '')
    vi.stubEnv('VITE_SUPABASE_ANON_KEY', '')
    const module = await import('./supabase.js')

    expect(module.isProduction).toBe(true)
    expect(module.configurationError).toContain('Production requires')
  })

  it('subscribes only to room-scoped safe tables and removes the channel', async () => {
    vi.stubEnv('VITE_APP_ENV', 'production')
    vi.stubEnv('VITE_SUPABASE_URL', 'https://project.supabase.co')
    vi.stubEnv('VITE_SUPABASE_ANON_KEY', 'publishable-key')
    const channel = {
      on: vi.fn(),
      subscribe: vi.fn(),
    }
    channel.on.mockReturnValue(channel)
    channel.subscribe.mockReturnValue(channel)
    const client = {
      channel: vi.fn().mockReturnValue(channel),
      removeChannel: vi.fn(),
    }
    createClient.mockReturnValue(client)
    const module = await import('./supabase.js')
    const onChange = vi.fn()

    const unsubscribe = module.subscribeToRoom('room-1', onChange)

    expect(createClient).toHaveBeenCalledWith(
      'https://project.supabase.co',
      'publishable-key',
      { auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true } },
    )
    expect(client.channel).toHaveBeenCalledWith('room:room-1')
    expect(channel.on).toHaveBeenCalledTimes(4)
    expect(channel.on.mock.calls.map((call) => call[1].table)).toEqual([
      'rooms', 'room_members', 'tickets', 'vote_statuses',
    ])
    expect(channel.on.mock.calls.every((call) => call[2] === onChange)).toBe(true)
    unsubscribe()
    expect(client.removeChannel).toHaveBeenCalledWith(channel)
  })
})
