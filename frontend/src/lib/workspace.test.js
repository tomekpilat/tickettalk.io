import { describe, expect, it } from 'vitest'
import {
  completionPercentage,
  remainingTicketIndex,
  roomView,
  ticketDistribution,
} from './workspace.js'

const tickets = [
  { final_estimate: '3' },
  { final_estimate: null },
  { final_estimate: '5' },
  { final_estimate: null },
]

describe('workspace state helpers', () => {
  it('chooses the room screen from persisted room and ticket state', () => {
    expect(roomView({ active_ticket_id: 'ticket-1' }, [])).toBe('session')
    expect(roomView({ active_ticket_id: null }, [])).toBe('import')
    expect(roomView({ active_ticket_id: null }, tickets)).toBe('backlog')
    expect(roomView({ active_ticket_id: null }, tickets.map((ticket) => ({ ...ticket, final_estimate: '3' })))).toBe('summary')
  })

  it('calculates completion without dividing by zero', () => {
    expect(completionPercentage([])).toBe(0)
    expect(completionPercentage(tickets)).toBe(50)
  })

  it('prefers the next unpriced ticket and then wraps around', () => {
    expect(remainingTicketIndex(tickets, 1)).toBe(3)
    expect(remainingTicketIndex(tickets, 3)).toBe(1)
    expect(remainingTicketIndex(tickets.map((ticket) => ({ ...ticket, final_estimate: '3' })), 1)).toBe(-1)
  })

  it('groups ticket counts and numeric points by final assignee', () => {
    expect(ticketDistribution([
      { final_assignee_display_name: 'Maya', final_estimate: '5' },
      { final_assignee_display_name: 'Maya', final_estimate: '3' },
      { final_assignee_display_name: 'Alex', final_estimate: 'M' },
      { final_assignee_display_name: null, final_estimate: '2' },
    ])).toEqual([
      { assignee: 'Maya', count: 2, points: 8, share: 0.5 },
      { assignee: 'Alex', count: 1, points: 0, share: 0.25 },
      { assignee: 'Unassigned', count: 1, points: 2, share: 0.25 },
    ])
    expect(ticketDistribution([])).toEqual([])
  })
})
