import { useLang } from '../i18n'
import { PIN_GROUPS } from '../data/pinGroups'
import { SEARCH_TYPES, TYPES, typeLabel } from '../data/types'
import {
  allTypesOn, groupState, setAllTypes, setFriendsOnly, setGroup, setUsersOnly, setWhen, setWhere, toggleType, useMapFilter,
} from '../data/mapFilter'
import { WhenPart, WherePart } from './LandingSearch'
import { Search } from './Icons'

// the panel's headings: the pin menu's groups, minus "New friends" (that's the Friend events toggle here)
const GROUPS = PIN_GROUPS.filter((g) => g.id !== 'friends')

const Switch = ({ on }) => <span className={`ctl-toggle ${on ? 'on' : ''}`} aria-hidden="true"><span className="ctl-knob" /></span>

/**
 * The event search (Events mode of the search bar): a tall panel of switches that decide the map.
 * Opening it blanks the map (data/mapFilter.js); every category toggle switches its dots on or off right
 * away, When and Where thin them live, and the button lists what's on the map.
 */
export function EventFilterPanel({ features, matchCount = 0, onSearch }) {
  const { t } = useLang()
  const f = useMapFilter()
  const all = allTypesOn(f)
  return (
    <div className="evf">
      <div className="evf-scroll">
        <button className={`evf-master ${all ? 'on' : ''}`} onClick={() => setAllTypes(!all)} aria-pressed={all}>
          <span className="txt"><b>{t(all ? 'All categories on' : 'Turn all categories on')}</b><small>{t('Switch every category on or off')}</small></span>
          <Switch on={all} />
        </button>

        <div className="evf-ww">
          <WhenPart value={f.when} onChange={setWhen} />
          <WherePart value={f.where} onChange={setWhere} features={features} />
        </div>

        <div className="evf-people">
          <button className={`evf-row ${f.users ? 'on' : ''}`} onClick={() => setUsersOnly(!f.users)} aria-pressed={f.users}>
            <span className="emo">🙋</span><span className="txt"><b>{t('User events')}</b><small>{t('Made by people on Syrenka')}</small></span><Switch on={f.users} />
          </button>
          <button className={`evf-row ${f.friends ? 'on' : ''}`} onClick={() => setFriendsOnly(!f.friends)} aria-pressed={f.friends}>
            <span className="emo">🤝</span><span className="txt"><b>{t('Friend events')}</b><small>{t('Made by your friends')}</small></span><Switch on={f.friends} />
          </button>
        </div>

        {GROUPS.map((g) => {
          const gs = groupState(g.id, f)
          return (
            <section key={g.id} className="evf-group">
              <button className={`evf-ghead ${gs}`} data-group={g.id} onClick={() => setGroup(g.id, gs !== 'on')} aria-pressed={gs === 'on'}>
                <span className="emo">{g.emoji}</span>{t(g.label)}<small>{t(gs === 'on' ? 'All on' : gs === 'some' ? 'Some on' : 'Off')}</small>
              </button>
              <div className="evf-chips">
                {SEARCH_TYPES.filter((id) => TYPES[id].group === g.id).map((id) => {
                  const on = f.types.includes(id)
                  return (
                    <button key={id} data-type={id} className={`evf-chip ${on ? 'on' : ''}`} style={{ '--c': TYPES[id].color }} onClick={() => toggleType(id)} aria-pressed={on}>
                      <span className="emo">{TYPES[id].emoji}</span>{typeLabel(id)}
                    </button>
                  )
                })}
              </div>
            </section>
          )
        })}
      </div>
      <button className="evf-go" onClick={onSearch}><Search size={18} />{t(matchCount === 1 ? 'Show {n} result' : 'Show {n} results', { n: matchCount })}</button>
    </div>
  )
}
