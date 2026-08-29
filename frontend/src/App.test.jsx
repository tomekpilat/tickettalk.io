import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
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
  previewImport: vi.fn(),
  importTickets: vi.fn(),
  createTicket: vi.fn(),
  updateTicket: vi.fn(),
  deleteTicket: vi.fn(),
  reorderTickets: vi.fn(),
  setActiveTicket: vi.fn(),
  submitVote: vi.fn(),
  voteResults: vi.fn(),
  revealVotes: vi.fn(),
  restartVote: vi.fn(),
  setFinalEstimate: vi.fn(),
  downloadRoomExport: vi.fn(),
  deleteRoom: vi.fn(),
}))

const authMock = vi.hoisted(() => ({
  useAuth: vi.fn(),
  setAnonymousDisplayName: vi.fn(),
}))

const realtimeMock = vi.hoisted(() => ({ callback: null }))

vi.mock('./lib/api.js', () => ({ api: apiMock }))
vi.mock('./lib/auth.js', () => ({
  useAuth: authMock.useAuth,
  setAnonymousDisplayName: authMock.setAnonymousDisplayName,
}))
vi.mock('./lib/supabase.js', () => ({
  subscribeToRoom: (_roomId, callback) => {
    realtimeMock.callback = callback
    return () => {}
  },
}))

beforeEach(() => {
  vi.clearAllMocks()
  realtimeMock.callback = null
  authMock.useAuth.mockReturnValue({ user, loading: false })
  authMock.setAnonymousDisplayName.mockResolvedValue(user)
  apiMock.members.mockResolvedValue([])
  apiMock.touchPresence.mockResolvedValue({})
  apiMock.previewImport.mockResolvedValue({
    rows: [], errors: [], source_count: 0, saved_count: 0, skipped_count: 0,
  })
  apiMock.voteResults.mockResolvedValue({
    room_id: roomId, ticket_id: 'ticket-1', state: 'voting', round: 1, votes: [],
    average: null, minimum: null, maximum: null, consensus: null, final_estimate: null,
  })
})

describe('session entry states', () => {
  it('renders loading and configuration failures without calling the API', () => {
    authMock.useAuth.mockReturnValueOnce({ user: null, loading: true })
    const { unmount } = render(<App />)
    expect(screen.getByRole('heading', { name: 'Checking your session…' })).toBeVisible()
    unmount()

    authMock.useAuth.mockReturnValueOnce({
      user: null, loading: false, error: 'Missing production configuration',
    })
    render(<App />)
    expect(screen.getByRole('heading', { name: 'The app needs attention.' })).toBeVisible()
    expect(screen.getByText('Missing production configuration')).toBeVisible()
    expect(apiMock.rooms).not.toHaveBeenCalled()
  })

  it('does not offer registration when an anonymous identity cannot be provisioned', () => {
    window.history.replaceState({}, '', '/')
    authMock.useAuth.mockReturnValue({ user: null, loading: false })
    render(<App />)

    expect(screen.getByRole('heading', {
      name: 'A private browser session could not be created.',
    })).toBeVisible()
    expect(screen.queryByLabelText('Work email')).not.toBeInTheDocument()
  })

  it('rejects malformed room paths without leaking room data', () => {
    window.history.replaceState({}, '', '/rooms/not-a-uuid')
    authMock.useAuth.mockReturnValue({ user: null, loading: false })
    render(<App />)

    expect(screen.getByRole('heading', { name: 'Room link not recognized.' })).toBeVisible()
    expect(apiMock.room).not.toHaveBeenCalled()
  })
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
    fireEvent.change(screen.getByLabelText('Your name'), {
      target: { value: '  Maya   Chen  ' },
    })
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
      display_name: 'Maya Chen',
    })
    expect(authMock.setAnonymousDisplayName).toHaveBeenCalledWith('Maya Chen')
    expect(window.location.pathname).toBe(`/rooms/${roomId}`)
  })

  it('shows local validation before calling the API', async () => {
    render(<App />)
    await screen.findByRole('heading', { name: 'Pricing rooms' })
    fireEvent.change(screen.getByLabelText('Your name'), { target: { value: 'Maya' } })
    fireEvent.change(screen.getByLabelText('Room name'), { target: { value: 'x' } })
    fireEvent.click(screen.getByRole('button', { name: /Create pricing room/ }))

    expect(screen.getByText('Room name needs at least 3 characters.')).toBeVisible()
    expect(apiMock.createRoom).not.toHaveBeenCalled()
  })

  it('requires only a display name before creating a protected room', async () => {
    render(<App />)
    await screen.findByRole('heading', { name: 'Pricing rooms' })
    fireEvent.change(screen.getByLabelText('Your name'), { target: { value: '   ' } })
    fireEvent.click(screen.getByRole('button', { name: /Create pricing room/ }))

    expect(screen.getByText('Enter your name to create a room.')).toBeVisible()
    expect(screen.queryByLabelText('Work email')).not.toBeInTheDocument()
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

  it('copies the canonical room URL with the browser origin', async () => {
    const room = {
      id: roomId,
      owner_id: user.id,
      name: 'Shared sprint',
      scale: 'fibonacci',
      reveal_mode: 'manual',
      active_ticket_id: null,
      ticket_count: 0,
      sized_count: 0,
      total_points: 0,
    }
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    })
    window.history.replaceState({}, '', `/rooms/${roomId}`)
    apiMock.room.mockResolvedValue(room)
    apiMock.tickets.mockResolvedValue([])

    render(<App />)
    expect(await screen.findByRole('heading', { name: 'Bring in the tickets.' })).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Copy room link' }))

    await waitFor(() => expect(writeText).toHaveBeenCalledWith(
      `${window.location.origin}/rooms/${roomId}`,
    ))
    expect(await screen.findByText('Room link copied')).toBeVisible()
  })
})

describe('anonymous room join', () => {
  it('creates an anonymous identity and joins with only a display name', async () => {
    window.history.replaceState({}, '', `/rooms/${roomId}`)
    authMock.useAuth.mockReturnValue({ user: null, loading: false })
    authMock.setAnonymousDisplayName.mockResolvedValue({ id: 'anonymous-user' })
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

    await waitFor(() => expect(authMock.setAnonymousDisplayName).toHaveBeenCalledWith('Maya Chen'))
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
    expect(authMock.setAnonymousDisplayName).not.toHaveBeenCalled()
    expect(apiMock.joinRoom).not.toHaveBeenCalled()
  })
})

describe('ticket backlog', () => {
  const backlogRoom = {
    id: roomId,
    owner_id: user.id,
    name: 'Backlog room',
    scale: 'fibonacci',
    reveal_mode: 'manual',
    active_ticket_id: null,
    ticket_count: 0,
    sized_count: 0,
    total_points: 0,
  }

  it('previews validated Jira rows before saving them', async () => {
    window.history.replaceState({}, '', `/rooms/${roomId}`)
    apiMock.room.mockResolvedValue(backlogRoom)
    apiMock.tickets.mockResolvedValue([])
    apiMock.previewImport.mockResolvedValue({
      rows: [
        { row_number: 2, issue_key: 'PAY-201', summary: 'Wallet alert', issue_type: 'Story', action: 'import' },
        { row_number: 3, issue_key: 'PAY-205', summary: 'Webhook retry', issue_type: 'Bug', action: 'import' },
      ],
      errors: [],
      source_count: 2,
      saved_count: 2,
      skipped_count: 0,
    })
    apiMock.importTickets.mockResolvedValue({
      tickets: [
        { id: 'ticket-1', room_id: roomId, position: 0, issue_key: 'PAY-201', summary: 'Wallet alert', issue_type: 'Story', description: '', story_points: null },
        { id: 'ticket-2', room_id: roomId, position: 1, issue_key: 'PAY-205', summary: 'Webhook retry', issue_type: 'Bug', description: '', story_points: null },
      ],
      imported_count: 2,
      replaced_count: 0,
      skipped_count: 0,
    })

    render(<App />)

    expect(await screen.findByText('Wallet alert')).toBeVisible()
    expect(apiMock.previewImport).toHaveBeenCalledWith(roomId, expect.stringContaining('PAY-201'), 'error')
    fireEvent.click(screen.getByRole('button', { name: /Save 2 to backlog/ }))

    await waitFor(() => expect(apiMock.importTickets).toHaveBeenCalledWith(
      roomId, expect.stringContaining('PAY-201'), 'error',
    ))
    expect(await screen.findByRole('heading', { name: 'Backlog' })).toBeVisible()
  })

  it('adds, edits, and reorders a manual ticket', async () => {
    const existing = { id: 'ticket-1', room_id: roomId, position: 0, issue_key: 'PAY-201', summary: 'Existing', issue_type: 'Story', description: '', story_points: null }
    const created = { id: 'ticket-2', room_id: roomId, position: 1, issue_key: null, summary: 'Manual decision', issue_type: 'Discussion', description: 'Discuss it', story_points: null }
    window.history.replaceState({}, '', `/rooms/${roomId}`)
    apiMock.room.mockResolvedValue({ ...backlogRoom, ticket_count: 1 })
    apiMock.tickets.mockResolvedValue([existing])
    apiMock.createTicket.mockResolvedValue(created)
    apiMock.updateTicket.mockResolvedValue({ ...created, summary: 'Updated decision' })
    apiMock.reorderTickets.mockResolvedValue([
      { ...created, summary: 'Updated decision', position: 0 },
      { ...existing, position: 1 },
    ])

    render(<App />)
    expect(await screen.findByRole('heading', { name: 'Backlog' })).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Add ticket' }))
    fireEvent.change(screen.getByLabelText('Summary'), { target: { value: 'Manual decision' } })
    fireEvent.change(screen.getByLabelText('Type'), { target: { value: 'Discussion' } })
    fireEvent.change(screen.getByLabelText('Description'), { target: { value: 'Discuss it' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add to backlog' }))

    await waitFor(() => expect(apiMock.createTicket).toHaveBeenCalledWith(roomId, {
      issue_key: null,
      summary: 'Manual decision',
      issue_type: 'Discussion',
      description: 'Discuss it',
    }))
    fireEvent.click(screen.getByRole('button', { name: 'Edit Manual decision' }))
    fireEvent.change(screen.getByLabelText('Summary'), { target: { value: 'Updated decision' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(apiMock.updateTicket).toHaveBeenCalled())
    fireEvent.click(screen.getByRole('button', { name: 'Move Updated decision up' }))
    await waitFor(() => expect(apiMock.reorderTickets).toHaveBeenCalledWith(
      roomId, ['ticket-2', 'ticket-1'],
    ))
  })
})

describe('active ticket synchronization', () => {
  const ticketOne = { id: 'ticket-1', room_id: roomId, position: 0, issue_key: 'PAY-201', summary: 'Wallet alert', issue_type: 'Story', description: 'Notify customers.', story_points: null }
  const ticketTwo = { id: 'ticket-2', room_id: roomId, position: 1, issue_key: 'PAY-205', summary: 'Webhook retry', issue_type: 'Bug', description: 'Retry safely.', story_points: null }
  const room = {
    id: roomId,
    owner_id: user.id,
    name: 'Live planning',
    scale: 'fibonacci',
    reveal_mode: 'manual',
    active_ticket_id: null,
    ticket_count: 2,
    sized_count: 0,
    total_points: 0,
  }

  it('persists the facilitator selection before opening the session', async () => {
    window.history.replaceState({}, '', `/rooms/${roomId}`)
    apiMock.room.mockResolvedValue(room)
    apiMock.tickets.mockResolvedValue([ticketOne, ticketTwo])
    apiMock.setActiveTicket.mockResolvedValue({ ...room, active_ticket_id: ticketTwo.id })

    render(<App />)

    expect(await screen.findByRole('heading', { name: 'Backlog' })).toBeVisible()
    fireEvent.click(screen.getByText('Webhook retry').closest('button'))

    await waitFor(() => expect(apiMock.setActiveTicket).toHaveBeenCalledWith(roomId, ticketTwo.id))
    expect(await screen.findByRole('heading', { name: 'Webhook retry' })).toBeVisible()
    expect(screen.getByText('PAY-205 · Bug')).toBeVisible()
  })

  it('moves a member through Realtime and clears their ticket-scoped vote status', async () => {
    const member = {
      id: '00000000-0000-0000-0000-000000000099',
      displayName: 'Maya Chen',
      isAnonymous: true,
    }
    const firstActiveRoom = { ...room, active_ticket_id: ticketOne.id }
    const secondActiveRoom = { ...room, active_ticket_id: ticketTwo.id }
    window.history.replaceState({}, '', `/rooms/${roomId}`)
    authMock.useAuth.mockReturnValue({ user: member, loading: false })
    apiMock.room.mockResolvedValueOnce(firstActiveRoom)
    apiMock.tickets.mockResolvedValue([ticketOne, ticketTwo])

    render(<App />)

    expect(await screen.findByRole('heading', { name: 'Wallet alert' })).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: '5' }))
    expect(await screen.findByText('Vote submitted')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Next ticket' })).toBeDisabled()

    apiMock.room.mockResolvedValue(secondActiveRoom)
    await act(async () => realtimeMock.callback())

    expect(await screen.findByRole('heading', { name: 'Webhook retry' })).toBeVisible()
    expect(screen.getByRole('button', { name: '5' })).toBeVisible()
    expect(screen.queryByText('Vote submitted')).not.toBeInTheDocument()
    expect(apiMock.setActiveTicket).not.toHaveBeenCalled()
  })

  it('submits and changes a vote without echoing the facilitator value', async () => {
    const activeRoom = { ...room, active_ticket_id: ticketOne.id }
    window.history.replaceState({}, '', `/rooms/${roomId}`)
    apiMock.room.mockResolvedValue(activeRoom)
    apiMock.tickets.mockResolvedValue([ticketOne, ticketTwo])
    apiMock.submitVote.mockResolvedValue({
      room_id: roomId,
      ticket_id: ticketOne.id,
      user_id: user.id,
      has_voted: true,
    })

    render(<App />)

    expect(await screen.findByRole('heading', { name: 'Wallet alert' })).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: '8' }))
    await waitFor(() => expect(apiMock.submitVote).toHaveBeenCalledWith(roomId, ticketOne.id, '8'))
    expect(await screen.findByText('Vote submitted')).toBeVisible()
    expect(screen.queryByRole('button', { name: '8' })).not.toBeInTheDocument()
    expect(screen.getByText(/estimate stays hidden/)).toBeVisible()

    fireEvent.click(screen.getByRole('button', { name: 'Change vote' }))
    fireEvent.click(screen.getByRole('button', { name: '13' }))
    await waitFor(() => expect(apiMock.submitVote).toHaveBeenLastCalledWith(
      roomId, ticketOne.id, '13',
    ))
    expect(await screen.findByText('Vote submitted')).toBeVisible()
    expect(screen.queryByRole('button', { name: '13' })).not.toBeInTheDocument()
  })
})

describe('vote reveal and final estimate', () => {
  const ticket = { id: 'ticket-1', room_id: roomId, position: 0, issue_key: 'PAY-201', summary: 'Wallet alert', issue_type: 'Story', description: '', story_points: null, final_estimate: null, vote_state: 'voting', vote_round: 1 }
  const nextTicket = { ...ticket, id: 'ticket-2', position: 1, issue_key: 'PAY-202', summary: 'Next ticket' }
  const room = { id: roomId, owner_id: user.id, name: 'Reveal room', scale: 'fibonacci', reveal_mode: 'manual', active_ticket_id: ticket.id, ticket_count: 2, sized_count: 0, total_points: 0 }
  const roster = [{ room_id: roomId, user_id: user.id, role: 'facilitator', display_name: user.displayName, is_online: true, has_voted: true }]
  const revealed = { room_id: roomId, ticket_id: ticket.id, state: 'revealed', round: 1, votes: [{ user_id: user.id, display_name: user.displayName, value: '5' }], average: 5, minimum: 5, maximum: 5, consensus: 'unanimous', final_estimate: null }

  it('reveals durable results and saves a final estimate before advancing', async () => {
    window.history.replaceState({}, '', `/rooms/${roomId}`)
    apiMock.room.mockResolvedValue(room)
    apiMock.tickets.mockResolvedValue([ticket, nextTicket])
    apiMock.members.mockResolvedValue(roster)
    apiMock.revealVotes.mockResolvedValue(revealed)
    apiMock.setFinalEstimate.mockResolvedValue({ ...ticket, vote_state: 'revealed', final_estimate: '5' })
    apiMock.setActiveTicket.mockResolvedValue({ ...room, active_ticket_id: nextTicket.id })

    render(<App />)

    expect(await screen.findByText('1 of 1 voted')).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Reveal votes' }))
    expect(await screen.findByText('Unanimous')).toBeVisible()
    expect(screen.getByText(user.displayName)).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: '5' }))
    fireEvent.click(screen.getByRole('button', { name: /Save & next/ }))

    await waitFor(() => expect(apiMock.setFinalEstimate).toHaveBeenCalledWith(roomId, ticket.id, '5'))
    await waitFor(() => expect(apiMock.setActiveTicket).toHaveBeenCalledWith(roomId, nextTicket.id))
  })

  it('renders automatically revealed results after the final vote response', async () => {
    window.history.replaceState({}, '', `/rooms/${roomId}`)
    apiMock.room.mockResolvedValue(room)
    apiMock.tickets
      .mockResolvedValueOnce([ticket, nextTicket])
      .mockResolvedValue([{ ...ticket, vote_state: 'revealed' }, nextTicket])
    apiMock.members.mockResolvedValue([{ ...roster[0], has_voted: false }])
    apiMock.submitVote.mockResolvedValue({ room_id: roomId, ticket_id: ticket.id, user_id: user.id, has_voted: true, revealed: true })
    apiMock.voteResults.mockResolvedValue(revealed)

    render(<App />)
    expect(await screen.findByRole('heading', { name: 'Wallet alert' })).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: '5' }))

    expect(await screen.findByText('Unanimous')).toBeVisible()
    expect(apiMock.voteResults).toHaveBeenCalledWith(roomId, ticket.id)
  })
})

describe('room export and deletion', () => {
  const ticket = { id: 'ticket-1', room_id: roomId, position: 0, issue_key: 'PAY-201', summary: 'Wallet alert', issue_type: 'Story', description: 'Quoted, context', story_points: 3, final_estimate: '5', vote_state: 'revealed', vote_round: 1 }
  const room = { id: roomId, owner_id: user.id, name: 'Release planning', scale: 'fibonacci', reveal_mode: 'manual', active_ticket_id: null, ticket_count: 1, sized_count: 1, total_points: 5 }

  it('downloads the facilitator export from the authorized server response', async () => {
    window.history.replaceState({}, '', `/rooms/${roomId}`)
    apiMock.room.mockResolvedValue({ ...room, active_ticket_id: ticket.id })
    apiMock.tickets.mockResolvedValue([ticket])
    apiMock.downloadRoomExport.mockResolvedValue({
      blob: new Blob(['csv']), filename: 'release-planning-2026-08-28.csv',
    })
    URL.createObjectURL = vi.fn(() => 'blob:export')
    URL.revokeObjectURL = vi.fn()
    const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})

    render(<App />)
    expect(await screen.findByRole('heading', { name: 'Wallet alert' })).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Summary' }))
    fireEvent.click(screen.getByRole('button', { name: /Export CSV/ }))
    await waitFor(() => expect(apiMock.downloadRoomExport).toHaveBeenCalledWith(roomId))
    anchorClick.mockRestore()
  })

  it('requires the exact room name before deleting and redirects home', async () => {
    window.history.replaceState({}, '', `/rooms/${roomId}`)
    apiMock.room.mockResolvedValue(room)
    apiMock.tickets.mockResolvedValue([ticket])
    apiMock.rooms.mockResolvedValue([])
    apiMock.deleteRoom.mockResolvedValue(null)
    const prompt = vi.spyOn(window, 'prompt')
      .mockReturnValueOnce(null)
      .mockReturnValueOnce(room.name)

    render(<App />)
    expect(await screen.findByRole('heading', { name: 'Backlog' })).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Room settings' }))
    fireEvent.click(screen.getByRole('button', { name: 'Delete room' }))
    expect(apiMock.deleteRoom).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Delete room' }))

    await waitFor(() => expect(apiMock.deleteRoom).toHaveBeenCalledWith(roomId))
    expect(prompt.mock.calls[0][0]).toContain(room.name)
    expect(window.location.pathname).toBe('/')
    prompt.mockRestore()
  })
})
