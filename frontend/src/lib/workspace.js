export function roomView(room, tickets) {
  if (room.active_ticket_id) return 'session'
  if (!tickets.length) return 'import'
  return tickets.every((ticket) => ticket.final_estimate != null) ? 'summary' : 'backlog'
}

export function completionPercentage(tickets) {
  if (!tickets.length) return 0
  const priced = tickets.filter((ticket) => ticket.final_estimate != null).length
  return Math.round((priced / tickets.length) * 100)
}

export function remainingTicketIndex(tickets, currentIndex) {
  const afterCurrent = tickets.findIndex(
    (ticket, index) => index > currentIndex && ticket.final_estimate == null,
  )
  if (afterCurrent >= 0) return afterCurrent
  return tickets.findIndex(
    (ticket, index) => index !== currentIndex && ticket.final_estimate == null,
  )
}
