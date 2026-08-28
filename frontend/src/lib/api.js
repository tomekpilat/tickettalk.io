import { getAccessToken } from './auth.js'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.status = status
  }
}

async function request(path, options) {
  const token = await getAccessToken()
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options?.headers,
    },
  })
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}))
    const detail = Array.isArray(payload.detail)
      ? payload.detail.map((item) => item.message || item.msg || String(item)).join(' ')
      : payload.detail
    throw new ApiError(detail || `Request failed with ${response.status}`, response.status)
  }
  if (response.status === 204) return null
  return response.json()
}

export const api = {
  me: () => request('/api/me'),
  rooms: () => request('/api/rooms'),
  room: (roomId) => request(`/api/rooms/${roomId}`),
  createRoom: (room) => request('/api/rooms', { method: 'POST', body: JSON.stringify(room) }),
  joinRoom: (roomId, displayName) => request(`/api/rooms/${roomId}/join`, {
    method: 'POST', body: JSON.stringify({ display_name: displayName }),
  }),
  members: (roomId) => request(`/api/rooms/${roomId}/members`),
  touchPresence: (roomId) => request(`/api/rooms/${roomId}/presence`, { method: 'POST' }),
  updateRoom: (roomId, room) => request(`/api/rooms/${roomId}`, {
    method: 'PATCH', body: JSON.stringify(room),
  }),
  setActiveTicket: (roomId, ticketId) => request(`/api/rooms/${roomId}/active-ticket`, {
    method: 'PATCH', body: JSON.stringify({ ticket_id: ticketId }),
  }),
  tickets: (roomId) => request(`/api/rooms/${roomId}/tickets`),
  previewImport: (roomId, content, duplicateBehavior) => request(`/api/rooms/${roomId}/tickets/import/preview`, {
    method: 'POST', body: JSON.stringify({ content, duplicate_behavior: duplicateBehavior }),
  }),
  importTickets: (roomId, content, duplicateBehavior) => request(`/api/rooms/${roomId}/tickets/import`, {
    method: 'POST', body: JSON.stringify({ content, duplicate_behavior: duplicateBehavior }),
  }),
  createTicket: (roomId, ticket) => request(`/api/rooms/${roomId}/tickets`, {
    method: 'POST', body: JSON.stringify(ticket),
  }),
  updateTicket: (roomId, ticketId, ticket) => request(`/api/rooms/${roomId}/tickets/${ticketId}`, {
    method: 'PATCH', body: JSON.stringify(ticket),
  }),
  deleteTicket: (roomId, ticketId) => request(`/api/rooms/${roomId}/tickets/${ticketId}`, {
    method: 'DELETE',
  }),
  reorderTickets: (roomId, ticketIds) => request(`/api/rooms/${roomId}/tickets/order`, {
    method: 'PUT', body: JSON.stringify({ ticket_ids: ticketIds }),
  }),
  estimate: (ticketId, storyPoints) => request(`/api/tickets/${ticketId}/estimate`, {
    method: 'PATCH', body: JSON.stringify({ story_points: storyPoints }),
  }),
}
