const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

async function request(path, options) {
  const response = await fetch(`${API_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!response.ok) throw new Error(`API request failed: ${response.status}`)
  return response.json()
}

export const api = {
  rooms: () => request('/api/rooms'),
  createRoom: (room) => request('/api/rooms', { method: 'POST', body: JSON.stringify(room) }),
  tickets: (roomId) => request(`/api/rooms/${roomId}/tickets`),
  importTickets: (roomId, tickets) => request(`/api/rooms/${roomId}/tickets/import`, {
    method: 'POST', body: JSON.stringify({ tickets }),
  }),
  estimate: (ticketId, storyPoints) => request(`/api/tickets/${ticketId}/estimate`, {
    method: 'PATCH', body: JSON.stringify({ story_points: storyPoints }),
  }),
}

