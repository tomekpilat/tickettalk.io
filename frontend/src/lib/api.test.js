import { beforeEach, describe, expect, it, vi } from 'vitest'

const authMock = vi.hoisted(() => ({ getAccessToken: vi.fn() }))
vi.mock('./auth.js', () => ({ getAccessToken: authMock.getAccessToken }))

import { api, ApiError } from './api.js'

function jsonResponse(payload = { ok: true }, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: vi.fn().mockResolvedValue(payload),
    blob: vi.fn().mockResolvedValue(new Blob(['export'])),
    headers: { get: vi.fn().mockReturnValue(null) },
  }
}

beforeEach(() => {
  authMock.getAccessToken.mockResolvedValue('access-token')
  global.fetch = vi.fn().mockResolvedValue(jsonResponse())
})

describe('API client', () => {
  it('maps every JSON endpoint to its HTTP contract', async () => {
    const roomId = 'room-1'
    const ticketId = 'ticket-1'
    const calls = [
      [() => api.me(), '/api/me', 'GET'],
      [() => api.rooms(), '/api/rooms', 'GET'],
      [() => api.room(roomId), `/api/rooms/${roomId}`, 'GET'],
      [() => api.createRoom({ name: 'Room' }), '/api/rooms', 'POST'],
      [() => api.joinRoom(roomId, 'Maya'), `/api/rooms/${roomId}/join`, 'POST'],
      [() => api.members(roomId), `/api/rooms/${roomId}/members`, 'GET'],
      [() => api.touchPresence(roomId), `/api/rooms/${roomId}/presence`, 'POST'],
      [() => api.updateRoom(roomId, { name: 'Next' }), `/api/rooms/${roomId}`, 'PATCH'],
      [() => api.deleteRoom(roomId), `/api/rooms/${roomId}`, 'DELETE'],
      [() => api.setActiveTicket(roomId, ticketId), `/api/rooms/${roomId}/active-ticket`, 'PATCH'],
      [() => api.submitVote(roomId, ticketId, '5'), `/api/rooms/${roomId}/tickets/${ticketId}/vote`, 'PUT'],
      [() => api.voteResults(roomId, ticketId), `/api/rooms/${roomId}/tickets/${ticketId}/votes`, 'GET'],
      [() => api.revealVotes(roomId, ticketId), `/api/rooms/${roomId}/tickets/${ticketId}/reveal`, 'POST'],
      [() => api.restartVote(roomId, ticketId), `/api/rooms/${roomId}/tickets/${ticketId}/revote`, 'POST'],
      [() => api.setFinalEstimate(roomId, ticketId, '8'), `/api/rooms/${roomId}/tickets/${ticketId}/final-estimate`, 'PUT'],
      [() => api.tickets(roomId), `/api/rooms/${roomId}/tickets`, 'GET'],
      [() => api.previewImport(roomId, 'csv', 'skip'), `/api/rooms/${roomId}/tickets/import/preview`, 'POST'],
      [() => api.importTickets(roomId, 'csv', 'replace'), `/api/rooms/${roomId}/tickets/import`, 'POST'],
      [() => api.createTicket(roomId, { summary: 'Ticket' }), `/api/rooms/${roomId}/tickets`, 'POST'],
      [() => api.updateTicket(roomId, ticketId, { summary: 'Updated' }), `/api/rooms/${roomId}/tickets/${ticketId}`, 'PATCH'],
      [() => api.deleteTicket(roomId, ticketId), `/api/rooms/${roomId}/tickets/${ticketId}`, 'DELETE'],
      [() => api.reorderTickets(roomId, [ticketId]), `/api/rooms/${roomId}/tickets/order`, 'PUT'],
    ]

    for (const [call, path, method] of calls) {
      await call()
      const [url, options] = global.fetch.mock.calls.at(-1)
      expect(url).toBe(`http://localhost:8000${path}`)
      expect(options.headers.Authorization).toBe('Bearer access-token')
      expect(options.method || 'GET').toBe(method)
    }
  })

  it('handles empty success responses and validation errors', async () => {
    global.fetch.mockResolvedValueOnce(jsonResponse(null, 204))
    await expect(api.deleteRoom('room-1')).resolves.toBeNull()

    global.fetch.mockResolvedValueOnce(jsonResponse({
      detail: [{ message: 'Bad summary' }, { msg: 'Bad scale' }],
    }, 422))
    await expect(api.createRoom({})).rejects.toEqual(
      expect.objectContaining({ message: 'Bad summary Bad scale', status: 422 }),
    )
  })

  it('falls back safely when an error body is not JSON', async () => {
    const response = jsonResponse({}, 503)
    response.json.mockRejectedValue(new Error('not json'))
    global.fetch.mockResolvedValueOnce(response)

    await expect(api.rooms()).rejects.toEqual(
      new ApiError('Request failed with 503', 503),
    )
  })

  it('downloads exports using the server filename and no JSON content header', async () => {
    const response = jsonResponse()
    response.headers.get.mockReturnValue('attachment; filename="planning.csv"')
    global.fetch.mockResolvedValueOnce(response)

    const result = await api.downloadRoomExport('room-1')

    expect(result.filename).toBe('planning.csv')
    expect(result.blob).toBeInstanceOf(Blob)
    expect(global.fetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/rooms/room-1/export',
      { headers: { Authorization: 'Bearer access-token' } },
    )
  })

  it('uses fallback export errors and filenames when headers are absent', async () => {
    authMock.getAccessToken.mockResolvedValue(null)
    const success = jsonResponse()
    global.fetch.mockResolvedValueOnce(success)
    await expect(api.downloadRoomExport('room-1')).resolves.toEqual({
      blob: expect.any(Blob), filename: 'tickettalk-export.csv',
    })

    const failure = jsonResponse({}, 500)
    failure.json.mockRejectedValue(new Error('not json'))
    global.fetch.mockResolvedValueOnce(failure)
    await expect(api.downloadRoomExport('room-1')).rejects.toEqual(
      expect.objectContaining({ message: 'Request failed with 500', status: 500 }),
    )
  })
})
