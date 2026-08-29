import { useEffect, useState } from 'react'
import {
  configurationError,
  isProduction,
  isSupabaseConfigured,
  supabase,
} from './supabase.js'

export const DEVELOPMENT_TOKEN = import.meta.env.VITE_DEMO_AUTH_TOKEN || 'dev-facilitator'
const developmentUser = {
  id: '00000000-0000-0000-0000-000000000001',
  email: 'facilitator@local.tickettalks',
  displayName: 'Tomasz Pilat',
  isDevelopment: true,
}

function userFromSession(session) {
  const user = session?.user
  if (!user) return null
  const metadata = user.user_metadata || {}
  return {
    id: user.id,
    email: user.email,
    displayName: metadata.display_name || metadata.full_name || metadata.name || user.email?.split('@')[0] || 'Facilitator',
    isAnonymous: Boolean(user.is_anonymous),
  }
}

export function useAuth() {
  const [state, setState] = useState({ user: null, loading: true })

  useEffect(() => {
    if (configurationError) {
      setState({ user: null, loading: false, error: configurationError })
      return undefined
    }
    if (!isSupabaseConfigured) {
      setState({ user: developmentUser, loading: false, mode: 'development' })
      return undefined
    }

    let mounted = true
    supabase.auth.getSession().then(({ data, error }) => {
      if (!mounted) return
      setState({ user: userFromSession(data.session), loading: false, error: error?.message })
    })
    const { data } = supabase.auth.onAuthStateChange((_event, session) => {
      if (mounted) setState({ user: userFromSession(session), loading: false })
    })
    return () => {
      mounted = false
      data.subscription.unsubscribe()
    }
  }, [])

  return state
}

export async function getAccessToken() {
  if (!isSupabaseConfigured) return isProduction ? null : DEVELOPMENT_TOKEN
  const { data } = await supabase.auth.getSession()
  return data.session?.access_token || null
}

export async function sendMagicLink(email) {
  if (!supabase) throw new Error('Supabase Auth is not configured')
  const { error } = await supabase.auth.signInWithOtp({
    email,
    options: {
      emailRedirectTo: window.location.href,
      data: { display_name: email.split('@')[0] },
    },
  })
  if (error) throw error
}

export async function signInAsMember(displayName) {
  if (!supabase) throw new Error('Supabase Auth is not configured')
  const { data, error } = await supabase.auth.signInAnonymously({
    options: { data: { display_name: displayName } },
  })
  if (error) throw error
  return data.user
}

export async function signOut() {
  if (supabase) await supabase.auth.signOut()
}
