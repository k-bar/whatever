import { motion } from 'framer-motion'
import { useConfig, useSpring } from '../config/store'
import { X } from './Icons'
import { useLang } from '../i18n'

/**
 * The one (x). Every close button copies the proportions of the close-all (x) next to the search bar:
 * a solid white circle with the cross at 62.5% of its diameter and a 2.4 stroke. `size` defaults to the
 * editor's control size (that's the close-all); boxes and panels pass a smaller circle.
 */
export function CloseButton({ size, className = '', label, ...rest }) {
  const { values } = useConfig()
  const { t } = useLang()
  label ??= t('Close')
  const spring = useSpring()
  const d = size ?? values.controlSize
  return (
    <motion.button className={`btn icon close-btn ${className}`} style={{ width: d, height: d, minWidth: d }} aria-label={label} title={label}
      whileTap={{ rotate: 90 }} transition={spring} {...rest}>
      <X size={Math.round(d * 0.625)} stroke={2.4} />
    </motion.button>
  )
}
