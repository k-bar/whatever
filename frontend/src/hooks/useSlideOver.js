import { useState } from 'react'

/**
 * The slide-over tray: the burger opens it on its menu ('menu'), items open inside it (profile, messages,
 * favourites, selects, settings). Every way in or out resets what belongs to the section left behind, so
 * nothing from one visit (someone else's profile, an event chat, favourites-only pins) sticks to the next.
 *
 * On phones the slide-over covers the screen: the event sheet steps aside (setSheet(null)) so it can't
 * sit on top of it. Opening a chat or a profile closes "+ Create event" (closeCreate); the menu's
 * "Create event" item is handed back to the app (onCreate).
 */
export function useSlideOver({ mobile, setSheet, closeCreate, onCreate }) {
  const [panel, setPanel] = useState(null)
  const [panelFull, setPanelFull] = useState(false) // desktop mode 3: the slide-over fills the screen
  const [person, setPerson] = useState(null) // { id } of someone tapped on the map: their profile in the slide-over
  const [eventChat, setEventChat] = useState(null) // the event chat open in Messages: { kind: 'event' | 'userevent', id }
  const [favOnly, setFavOnly] = useState(false) // the map shows only favourite spots while that section is open

  const sheetAside = () => { if (mobile) setSheet(null) }

  const onMenu = (id) => {
    if (id === 'create') { onCreate(); return }
    setFavOnly(id === 'favourites'); setPerson(null); sheetAside(); setPanel(id)
  }
  const closePanel = () => { setPanel(null); setPanelFull(false); setFavOnly(false); setPerson(null); setEventChat(null) }
  /** Picking an event from the tray: the tray goes away where it covers the map (phones, full screen). */
  const closeIfCovering = () => { if (mobile || panelFull) closePanel() }
  const backToMenu = () => { setFavOnly(false); setEventChat(null); setPerson(null); setPanel('menu') }
  const toggleTray = () => { if (panel) closePanel(); else { sheetAside(); setPanel('menu') } }
  const toggleFull = () => setPanelFull((f) => !f)
  const openChat = (target) => { closeCreate(); setEventChat(target); sheetAside(); setPanel('messages') }
  // a person's pulsing pin on the map ("share my area"), or a face in a chat: their profile, in the same slide-over
  // id null = mine (also brings me back from a friend's profile)
  const openPerson = (id) => { closeCreate(); setFavOnly(false); sheetAside(); setPerson({ id, at: Date.now() }); setPanel('profile') }
  const openProfile = () => openPerson(null)

  return {
    panel, panelFull, person, eventChat, favOnly, setEventChat,
    onMenu, closePanel, closeIfCovering, backToMenu, toggleTray, toggleFull, openChat, openPerson, openProfile,
  }
}
