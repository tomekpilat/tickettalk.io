const ROOM_ROUTE = /^\/rooms\/([0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})\/?$/i

export function roomPath(roomId) {
  return `/rooms/${roomId}`
}

export function roomIdFromPath(pathname = window.location.pathname) {
  return pathname.match(ROOM_ROUTE)?.[1] || null
}

export function isRoomLikePath(pathname = window.location.pathname) {
  return pathname.startsWith('/rooms/')
}

export function pushPath(path) {
  if (window.location.pathname !== path) window.history.pushState({}, '', path)
}
