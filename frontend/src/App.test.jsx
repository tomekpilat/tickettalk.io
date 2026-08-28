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
  members: vi.fn(),
  createRoom: vi.fn(),
  joinRoom: vi.fn(),
  touchPresence: vi.fn(),
  updateRoom: vi.fn(),
  importTickets: vi.fn(),
  estimate: vi.fn(),
}))

const authMock = vi.hoisted(() => ({
  useAuth: vi.fn(),
  signInAsMember: vi.fn(),
}))

vi.mock('./lib/api.js', () => ({ api: apiMock }))
vi.mock('./lib/auth.js', () => ({
  useAuth: authMock.useAuth,
  sendMagicLink: vi.fn(),
  signInAsMember: authMock.signInAsMember,
  signOut: vi.fn(),
}))
vi.mock('./lib/supabase.js', () => ({
  subscribeToRoom: () => () => {},
}))

beforeEach(() => {
  authMock.useAuth.mockReturnValue({ user, loading: false })
  apiMock.members.mockResolvedValue([])
  apiMock.touchPresence.mockResolvedValue({})
})

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

describe('anonymous room join', () => {
  it('creates an anonymous identity and joins with only a display name', async () => {
    window.history.replaceState({}, '', `/rooms/${roomId}`)
    authMock.useAuth.mockReturnValue({ user: null, loading: false })
    authMock.signInAsMember.mockResolvedValue({ id: 'anonymous-user' })
    apiMock.joinRoom.mockResolvedValue({
      room_id: roomId,
      user_id: 'anonymous-user',
      role: 'member',
      display_name: 'Maya Chen',
      is_online: true,
      has_voted: false,
    })

    render(<App />)
    expect(await screen.findByRole('heading', { name: 'Join the conversation.' })).toBeVisible()
    fireEvent.change(screen.getByLabelText('Your name'), { target: { value: '  Maya   Chen  ' } })
    fireEvent.click(screen.getByRole('button', { name: /Join room/ }))

    await waitFor(() => expect(authMock.signInAsMember).toHaveBeenCalledWith('Maya Chen'))
    expect(apiMock.joinRoom).toHaveBeenCalledWith(roomId, 'Maya Chen')
    expect(await screen.findByRole('heading', { name: 'You’re in.' })).toBeVisible()
  })

  it('reuses an existing anonymous session after refresh', async () => {
    const anonymousUser = {
      id: '00000000-0000-0000-0000-000000000099',
      displayName: 'Maya Chen',
      isAnonymous: true,
    }
    const room = {
      id: roomId,
      owner_id: user.id,
      name: 'Shared planning',
      scale: 'fibonacci',
      reveal_mode: 'manual',
      active_ticket_id: null,
      ticket_count: 0,
      sized_count: 0,
      total_points: 0,
    }
    window.history.replaceState({}, '', `/rooms/${roomId}`)
    authMock.useAuth.mockReturnValue({ user: anonymousUser, loading: false })
    apiMock.room.mockResolvedValue(room)
    apiMock.tickets.mockResolvedValue([])
    apiMock.members.mockResolvedValue([{
      room_id: roomId,
      user_id: anonymousUser.id,
      role: 'member',
      display_name: anonymousUser.displayName,
      is_online: true,
      has_voted: false,
    }])

    render(<App />)

    expect(await screen.findByRole('heading', { name: 'You’re in.' })).toBeVisible()
    expect(screen.getByText('Maya Chen (you)')).toBeVisible()
    expect(authMock.signInAsMember).not.toHaveBeenCalled()
    expect(apiMock.joinRoom).not.toHaveBeenCalled()
  })
})
