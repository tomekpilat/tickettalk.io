import { createClient } from '@supabase/supabase-js'

const url = import.meta.env.VITE_SUPABASE_URL
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY
export const appEnvironment = import.meta.env.VITE_APP_ENV || 'development'
export const isProduction = appEnvironment === 'production'
export const isSupabaseConfigured = Boolean(url && anonKey)

export const configurationError = isProduction && !isSupabaseConfigured
  ? 'Production requires VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY.'
  : null

export const supabase = isSupabaseConfigured
  ? createClient(url, anonKey, {
      auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
    })
  : null

export function subscribeToRoom(roomId, onChange) {
  if (!supabase) return () => {}
  const channel = supabase
    .channel(`room:${roomId}`)
    .on('postgres_changes', {
      event: 'UPDATE', schema: 'public', table: 'rooms', filter: `id=eq.${roomId}`,
    }, onChange)
    .on('postgres_changes', {
      event: '*', schema: 'public', table: 'room_members', filter: `room_id=eq.${roomId}`,
    }, onChange)
    .on('postgres_changes', {
      event: '*', schema: 'public', table: 'tickets', filter: `room_id=eq.${roomId}`,
    }, onChange)
    .on('postgres_changes', {
      event: '*', schema: 'public', table: 'vote_statuses', filter: `room_id=eq.${roomId}`,
    }, onChange)
    .subscribe()
  return () => { supabase.removeChannel(channel) }
}
