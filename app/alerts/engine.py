from app.alerts.rules import SEVERITY
from app.db import repository as repo


class AlertEngine:
    """Opens an alert once, keeps it open while the condition holds, closes it when it clears."""

    def __init__(self):
        # (rule, subject) -> {"id": alert id, "peak": highest value so far}
        self.open = {}
        for a in repo.load_open_alerts():
            self.open[(a["rule"], a["subject"])] = {"id": a["id"], "peak": a["peak"] or 0}

    def is_open(self, rule, subject):
        """True if an alert for this rule+subject is currently open (rules use it for hysteresis)."""
        return (rule, subject) in self.open

    def sync(self, rule, states, ts):
        """Apply the latest state of a rule.

        states: {subject: (active, value, detail)}. Subjects that are open but no longer
        listed (mount gone, process exited...) are closed.
        """
        for subject, (active, value, detail) in states.items():
            key = (rule, subject)
            cur = self.open.get(key)
            if active and cur is None:
                alert_id = repo.open_alert(rule, subject, SEVERITY[rule], ts, value, detail)
                self.open[key] = {"id": alert_id, "peak": value}
            elif active and value > cur["peak"]:
                cur["peak"] = value
                repo.update_peak(cur["id"], value)
            elif not active and cur is not None:
                repo.close_alert(cur["id"], ts)
                del self.open[key]
        for key in [k for k in self.open if k[0] == rule and k[1] not in states]:
            repo.close_alert(self.open.pop(key)["id"], ts)
