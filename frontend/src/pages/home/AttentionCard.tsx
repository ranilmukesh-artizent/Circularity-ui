/** The attention card at the top of Home and Alerts (the demo's frAttn). */
import { Icon } from '../../components/Icon';

export const AttentionCard = ({ head, line, btn, onClick }: { head: string; line: string; btn?: string; onClick?: () => void }) => (
  <div className="frattn" role="status">
    <Icon name="alert" />
    <div>
      <b>{head}</b>
      <p>{line}</p>
      {btn && (
        <button className="btn sm" onClick={onClick}>
          {btn}
        </button>
      )}
    </div>
  </div>
);
