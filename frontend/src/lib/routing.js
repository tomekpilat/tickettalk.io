const ROOM_ROUTE = /^\/rooms\/([0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})\/?$/i
const JIRA_OAUTH_CALLBACK_ROUTE = '/jira/oauth/callback'

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

export function replacePath(path) {
  window.history.replaceState({}, '', path)
}

export function jiraOAuthCallbackFromLocation(location = window.location) {
  if (location.pathname !== JIRA_OAUTH_CALLBACK_ROUTE) return null
  const params = new URLSearchParams(location.search)
  return {
    code: params.get('code') || '',
    state: params.get('state') || '',
    error: params.get('error_description') || params.get('error') || '',
  }
}
