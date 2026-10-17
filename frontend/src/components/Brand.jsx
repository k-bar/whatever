import { useLang } from '../i18n'
import { Mermaid } from './Icons'

/** The syrenka.me lockup: the mermaid shield, then the name. Clicking it goes back to the landing page. */
export function Brand({ onHome, size = 'md', className = '' }) {
  const { t } = useLang()
  return (
    <button className={`brand brand-${size} ${className}`} onClick={onHome} aria-label={t('Back to the start page')} title={t('Back to the start page')}>
      <Mermaid size={size === 'lg' ? 40 : 26} />
      <span className="brand-name">syrenka.me</span>
    </button>
  )
}
