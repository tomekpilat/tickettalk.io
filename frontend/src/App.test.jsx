import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App.jsx'

const roomId = 'b8b43e86-1bd7-4df9-94ab-4314b4bf3d41'
const user = {
  id: '00000000-0000-0000-0000-000000000001',
  email: 'owner@example.com',
  displayName: 'Owner User',
  isDevelopment: true,
}

const apiMock = vi.hoisted(() => ({
  rooms: vi.fn(),
  room: vi.fn(),
  tickets: vi.fn(),
  createRoom: vi.fn(),
  updateRoom: vi.fn(),
  importTickets: vi.fn(),
  estimate: vi.fn(),
}))

vi.mock('./lib/api.js', () => ({ api: apiMock }))
vi.mock('./lib/auth.js', () => ({
  useAuth: () => ({ user, loading: false }),
  sendMagicLink: vi.fn(),
  signOut: vi.fn(),
}))
vi.mock('./lib/supabase.js', () => ({
  subscribeToRoom: () => () => {},
}))

describe('room creation', () => {
  beforeEach(() => {
    window.history.replaceState({}, '', '/')
    apiMock.rooms.mockResolvedValue([])
    apiMock.tickets.mockResolvedValue([])
    apiMock.createRoom.mockResolvedValue({
      id: roomId,
      owner_id: user.id,
      name: 'Sprint 44',
      scale: 'extended',
      reveal_mode: 'auto',
      active_ticket_id: null,
      ticket_count: 0,
      sized_count: 0,
      total_points: 0,
    })
  })

  it('creates a configured room and moves to its canonical URL', async () => {
    render(<App />)

    expect(await screen.findByRole('heading', { name: 'Pricing rooms' })).toBeVisible()
    const name = screen.getByLabelText('Room name')
    fireEvent.change(name, { target: { value: 'Sprint 44' } })
    fireEvent.click(screen.getByRole('button', { name: /Extended/ }))
    fireEvent.click(screen.getByRole('button', { name: 'When all voted' }))
    fireEvent.click(screen.getByRole('button', { name: /Create pricing room/ }))

    expect(await screen.findByRole('heading', { name: 'Bring in the tickets.' })).toBeVisible()
    expect(apiMock.createRoom).toHaveBeenCalledWith({
      name: 'Sprint 44',
      scale: 'extended',
      reveal_mode: 'auto',
    })
    expect(window.location.pathname).toBe(`/rooms/${roomId}`)
  })

  it('shows local validation before calling the API', async () => {
    render(<App />)
    await screen.findByRole('heading', { name: 'Pricing rooms' })
    fireEvent.change(screen.getByLabelText('Room name'), { target: { value: 'x' } })
    fireEvent.click(screen.getByRole('button', { name: /Create pricing room/ }))

    expect(screen.getByText('Room name needs at least 3 characters.')).toBeVisible()
    expect(apiMock.createRoom).not.toHaveBeenCalled()
  })
})

describe('canonical room settings', () => {
  it('loads a room from its URL and saves owner settings', async () => {
    const room = {
      id: roomId,
      owner_id: user.id,
      name: 'Sprint 43',
      scale: 'fibonacci',
      reveal_mode: 'manual',
      active_ticket_id: null,
      ticket_count: 0,
      sized_count: 0,
      total_points: 0,
    }
    window.history.replaceState({}, '', `/rooms/${roomId}`)
    apiMock.room.mockResolvedValue(room)
    apiMock.tickets.mockResolvedValue([])
    apiMock.updateRoom.mockResolvedValue({ ...room, name: 'Sprint 44' })

    render(<App />)
    expect(await screen.findByRole('heading', { name: 'Bring in the tickets.' })).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Room settings' }))
    fireEvent.change(screen.getByLabelText('Room name'), { target: { value: 'Sprint 44' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save settings' }))

    await waitFor(() => expect(apiMock.updateRoom).toHaveBeenCalledWith(roomId, {
      name: 'Sprint 44',
      scale: 'fibonacci',
      reveal_mode: 'manual',
    }))
    expect(await screen.findByText('Sprint 44 / import')).toBeVisible()
  })
})
