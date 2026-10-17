import { createContext, useCallback, useContext, useMemo, useState } from 'react'
import { PL } from './pl'

/**
 * UI language. Polish by default; English only when the `lang=en` cookie says so.
 * Strings are written in English in the code and looked up in PL when the language is Polish:
 * t('Busy') -> 'Tu się dzieje'. `{name}` placeholders are filled from `vars`.
 */
const COOKIE = 'lang'
const Ctx = createContext(null)

const readCookie = () => (document.cookie.match(/(?:^|;\s*)lang=(pl|en)/)?.[1] === 'en' ? 'en' : 'pl')
const writeCookie = (lang) => { document.cookie = `${COOKIE}=${lang}; path=/; max-age=${60 * 60 * 24 * 365}; SameSite=Lax` }

// Module-level copy so plain helpers (date formatting, category labels, curate) can translate too.
let current = readCookie()
document.documentElement.lang = current
export const getLang = () => current
export const locale = () => (current === 'pl' ? 'pl-PL' : 'en-GB')

export function translate(text, vars) {
  let s = current === 'pl' ? (PL[text] ?? text) : text
  if (vars) for (const [k, v] of Object.entries(vars)) s = s.replaceAll(`{${k}}`, v)
  return s
}

export function LangProvider({ children }) {
  const [lang, setLangState] = useState(current)
  const setLang = useCallback((l) => {
    current = l
    document.documentElement.lang = l
    writeCookie(l)
    setLangState(l)
  }, [])
  // `lang` in the deps makes every consumer re-render (and re-translate) on change
  const t = useCallback((text, vars) => translate(text, vars), [lang]) // eslint-disable-line react-hooks/exhaustive-deps
  const api = useMemo(() => ({ lang, setLang, t }), [lang, setLang, t])
  return <Ctx.Provider value={api}>{children}</Ctx.Provider>
}

export const useLang = () => useContext(Ctx)
