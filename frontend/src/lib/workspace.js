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

export function ticketDistribution(tickets) {
  const grouped = new Map()
  for (const ticket of tickets) {
    const assignee = ticket.final_assignee_display_name || 'Unassigned'
    const current = grouped.get(assignee) || { assignee, count: 0, points: 0 }
    current.count += 1
    current.points += Number(ticket.final_estimate) || 0
    grouped.set(assignee, current)
  }
  return [...grouped.values()]
    .sort((left, right) => (
      left.assignee === 'Unassigned' ? 1
        : right.assignee === 'Unassigned' ? -1
          : right.count - left.count || left.assignee.localeCompare(right.assignee)
    ))
    .map((item) => ({
      ...item,
      share: tickets.length ? item.count / tickets.length : 0,
    }))
}
