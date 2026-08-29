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
    throw new ApiError(payload.detail || `Request failed with ${response.status}`, response.status)
  }
  return response.json()
}

export const api = {
  me: () => request('/api/me'),
  rooms: () => request('/api/rooms'),
  room: (roomId) => request(`/api/rooms/${roomId}`),
  createRoom: (room) => request('/api/rooms', { method: 'POST', body: JSON.stringify(room) }),
  updateRoom: (roomId, room) => request(`/api/rooms/${roomId}`, {
    method: 'PATCH', body: JSON.stringify(room),
  }),
  tickets: (roomId) => request(`/api/rooms/${roomId}/tickets`),
  importTickets: (roomId, tickets) => request(`/api/rooms/${roomId}/tickets/import`, {
    method: 'POST', body: JSON.stringify({ tickets }),
  }),
  estimate: (ticketId, storyPoints) => request(`/api/tickets/${ticketId}/estimate`, {
    method: 'PATCH', body: JSON.stringify({ story_points: storyPoints }),
  }),
}
