import mermaidSvg from '../../mermaid.svg'

const S = ({ children, size = 20, stroke = 1.9, ...rest }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={stroke}
    strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...rest}>{children}</svg>
)

export const Burger = (p) => <S {...p}><path d="M4 7h16M4 12h16M4 17h16" /></S>
export const Search = (p) => <S {...p}><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></S>
export const Chevron = (p) => <S {...p}><path d="m6 9 6 6 6-6" /></S>
export const ChevronL = (p) => <S {...p}><path d="m15 6-6 6 6 6" /></S>
export const ChevronR = (p) => <S {...p}><path d="m9 6 6 6-6 6" /></S>
export const X = (p) => <S {...p}><path d="M6 6l12 12M18 6 6 18" /></S>
export const Plus = (p) => <S {...p}><path d="M12 5v14M5 12h14" /></S>
export const Minus = (p) => <S {...p}><path d="M5 12h14" /></S>
export const Home = (p) => <S {...p}><path d="M3 11.5 12 4l9 7.5" /><path d="M5.5 10v10h13V10" /><path d="M10 20v-5h4v5" /></S>
export const Flame = (p) => <S {...p}><path d="M12 3c1 3 4 4.5 4 8.5a4 4 0 0 1-8 0c0-1.5.5-2.5 1-3.5.6 1 1.5 1.5 2 1.5 0-2.5-.5-4.5 1-6.5Z" /></S>
export const Moon = (p) => <S {...p}><path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5Z" /></S>
export const Sun = (p) => <S {...p}><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></S>
export const Sliders = (p) => <S {...p}><path d="M4 7h10M18 7h2M4 17h4M12 17h8" /><circle cx="16" cy="7" r="2" /><circle cx="10" cy="17" r="2" /></S>
export const Star = ({ filled, ...p }) => <S {...p} fill={filled ? 'currentColor' : 'none'}><path d="m12 3 2.8 5.9 6.4.8-4.7 4.4 1.2 6.4L12 17.4l-5.7 3.1 1.2-6.4L2.8 9.7l6.4-.8Z" /></S>
export const Clock = (p) => <S {...p}><circle cx="12" cy="12" r="8.5" /><path d="M12 7.5V12l3 2" /></S>
export const Pin = (p) => <S {...p}><path d="M12 21s-6-5.3-6-10.5a6 6 0 1 1 12 0C18 15.7 12 21 12 21Z" /><circle cx="12" cy="10.5" r="2" /></S>
export const MapIcon = (p) => <S {...p}><path d="m3 6 6-2 6 2 6-2v14l-6 2-6-2-6 2Z" /><path d="M9 4v14M15 6v14" /></S>
export const Repeat = (p) => <S {...p}><path d="M17 2l4 4-4 4" /><path d="M3 11V9a4 4 0 0 1 4-4h14" /><path d="M7 22l-4-4 4-4" /><path d="M21 13v2a4 4 0 0 1-4 4H3" /></S>
export const Users = (p) => <S {...p}><circle cx="9" cy="8" r="3.5" /><path d="M2.5 20a6.5 6.5 0 0 1 13 0" /><path d="M16 4.5a3.5 3.5 0 0 1 0 7M21.5 20a6.5 6.5 0 0 0-5-6.3" /></S>
export const Access = (p) => <S {...p}><circle cx="12" cy="4.5" r="1.5" /><path d="M10 8h4l1 5h4" /><path d="M8 12a5 5 0 1 0 8 5" /></S>
export const Phone = (p) => <S {...p}><path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2Z" /></S>
export const Sparkle = (p) => <S {...p}><path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2 2M16 16l2 2M6 18l2-2M16 8l2-2" /></S>
export const User = (p) => <S {...p}><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></S>
export const Message = (p) => <S {...p}><path d="M21 12a8 8 0 0 1-11.6 7.2L4 21l1.8-5.4A8 8 0 1 1 21 12Z" /></S>
export const Layers = (p) => <S {...p}><path d="m12 3 9 5-9 5-9-5Z" /><path d="m3 13 9 5 9-5" /></S>
export const Calendar = (p) => <S {...p}><rect x="3" y="5" width="18" height="16" rx="3" /><path d="M3 10h18M8 3v4M16 3v4" /></S>
export const Database = (p) => <S {...p}><ellipse cx="12" cy="5.5" rx="8" ry="3" /><path d="M4 5.5v13c0 1.7 3.6 3 8 3s8-1.3 8-3v-13" /><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3" /></S>
export const Check = (p) => <S {...p}><path d="m5 12 5 5L20 7" /></S>
export const Ticket = (p) => <S {...p}><path d="M3 9a2 2 0 0 0 0 6v3h18v-3a2 2 0 0 1 0-6V6H3Z" /><path d="M13 6v12" strokeDasharray="2 2" /></S>

export const Expand = (p) => <S {...p}><path d="M14 4h6v6M10 20H4v-6M20 4l-7 7M4 20l7-7" /></S>
export const Shrink = (p) => <S {...p}><path d="M20 10h-6V4M4 14h6v6M14 10l7-7M10 14l-7 7" /></S>

export const Undo =(p) => <S {...p}><path d="M9 14 4 9l5-5" /><path d="M4 9h10a6 6 0 0 1 0 12h-3" /></S>
export const Redo = (p) => <S {...p}><path d="m15 14 5-5-5-5" /><path d="M20 9H10a6 6 0 0 0 0 12h3" /></S>
export const Walk = (p) => <S {...p}><circle cx="13" cy="4" r="1.8" /><path d="M10 21l2-6 3 2 1 4" /><path d="M9 12l2-4 3 1 2 3h2" /><path d="M11 8 8 13" /></S>
export const Bike = (p) => <S {...p}><circle cx="5.5" cy="17" r="3.5" /><circle cx="18.5" cy="17" r="3.5" /><path d="M5.5 17 10 9h5l3.5 8" /><path d="M10 9l3 8" /><path d="M13 6h3" /></S>
export const Send = (p) => <S {...p}><path d="m3 11 18-8-8 18-2-8Z" /></S>
export const History = (p) => <S {...p}><path d="M3 12a9 9 0 1 0 3-6.7" /><path d="M3 4v5h5" /><path d="M12 7v5l3 2" /></S>
export const Music = (p) => <S {...p}><path d="M9 18V6l11-2v12" /><circle cx="6" cy="18" r="3" /><circle cx="17" cy="16" r="3" /></S>
export const FACT_ICON = { clock: Clock, pin: Pin, map: MapIcon, repeat: Repeat, users: Users, access: Access, phone: Phone }

/** The Warsaw mermaid (Syrenka): the city's red shield, frontend/mermaid.svg. */
export const Mermaid = ({ size = 26, className }) => (
  <img src={mermaidSvg} width={size} height={size} alt="Warsaw mermaid" className={className} draggable={false} />
)
export const Globe = (p) => <S {...p}><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18" /></S>
export const UserCheck = (p) => <S {...p}><circle cx="9" cy="8" r="3.5" /><path d="M2.5 20a6.5 6.5 0 0 1 13 0" /><path d="m16 11 2 2 4-4" /></S>
export const Lock = (p) => <S {...p}><rect x="5" y="11" width="14" height="10" rx="2.5" /><path d="M8 11V8a4 4 0 0 1 8 0v3" /></S>
export const Photo = (p) => <S {...p}><rect x="3" y="5" width="18" height="15" rx="3" /><circle cx="9" cy="10.5" r="1.8" /><path d="m21 16-5-5-9 9" /></S>
